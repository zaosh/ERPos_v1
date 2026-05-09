import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useMutation } from '@tanstack/react-query'
import { AsYouType, isValidPhoneNumber, parsePhoneNumber } from 'libphonenumber-js'
import { api, apiErrorMessage } from '../utils/api'
import { money } from '../utils/currency'
import { useTheme } from '../styles/theme'
import { Spinner } from '../components/ui'
import type { PaymentType } from '../utils/constants'

// ─── Types ────────────────────────────────────────────────────────────────────

interface ItemLookup {
  id: number; barcode: string; category: string; color: string | null
  label: string | null; size: string | null; condition: string
  price: string; status: string
}

interface CartItem {
  barcode: string; category: string; color: string | null
  label: string | null; size: string | null; condition: string
  price: number; basePrice: number; override?: boolean
  exchangeEligible: boolean; exchangeFee: number
}

interface CustomerInfo {
  firstName: string; lastName: string; phone: string
  customer_uid?: string; total_purchases?: number; isReturning?: boolean
}

interface SaleResult {
  id: number; sale_ref: string; receipt_number: string
  subtotal: string; discount_amount: string; tax_rate: string; tax_amount: string
  total_amount: string; customer_id: number | null
  items: Array<{ id: number; item_id: number; price: string }>
}


// ─── Styles ───────────────────────────────────────────────────────────────────

const lblStyle: React.CSSProperties = {
  fontSize: 11, fontWeight: 600, color: '#888',
  textTransform: 'uppercase', letterSpacing: '0.06em',
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ScanIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 7V5a2 2 0 0 1 2-2h2" />
      <path d="M17 3h2a2 2 0 0 1 2 2v2" />
      <path d="M21 17v2a2 2 0 0 1-2 2h-2" />
      <path d="M7 21H5a2 2 0 0 1-2-2v-2" />
      <line x1="7" y1="8" x2="7" y2="16" />
      <line x1="11" y1="8" x2="11" y2="16" />
      <line x1="15" y1="8" x2="15" y2="16" />
      <line x1="19" y1="8" x2="19" y2="16" />
    </svg>
  )
}

function KeyHint({ k, label }: { k: string; label: string }) {
  const t = useTheme()
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: t.textMuted }}>
      <kbd style={{
        fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
        background: t.surface2, border: `1px solid ${t.border}`, color: t.text,
        fontFamily: t.mono,
      }}>{k}</kbd>
      <span>{label}</span>
    </div>
  )
}

// ─── Receipt helpers ───────────────────────────────────────────────────────────

function ReceiptDivider({ dark }: { dark?: boolean }) {
  return <div style={{ borderTop: `1px dashed ${dark ? '#c8bfb0' : '#ccc'}`, margin: '8px 0' }} />
}

function ReceiptRow({ label, value, valueColor, small, dark }: {
  label: string; value: string; valueColor?: string; small?: boolean; dark?: boolean
}) {
  const muted = dark ? '#7a6f63' : '#aaa'
  const normal = dark ? '#444' : '#444'
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: small ? 10 : 12, color: small ? muted : normal }}>
      <span>{label}</span>
      <span style={{ fontWeight: small ? 400 : 600, color: valueColor, fontFamily: "'IBM Plex Mono', monospace" }}>{value}</span>
    </div>
  )
}

// ─── Price cell (click to override) ──────────────────────────────────────────

function PriceCell({ price, basePrice, override, onChange }: {
  price: number; basePrice: number; override?: boolean; onChange: (p: number) => void
}) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(price.toFixed(2))
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { setVal(price.toFixed(2)) }, [price])
  useEffect(() => { if (editing) inputRef.current?.select() }, [editing])

  const commit = () => {
    const n = parseFloat(val)
    if (!isNaN(n) && n >= 0 && n !== price) onChange(n)
    else setVal(price.toFixed(2))
    setEditing(false)
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="number" min="0" step="0.01" value={val}
        onChange={e => setVal(e.target.value)}
        onBlur={commit}
        onKeyDown={e => {
          if (e.key === 'Enter') commit()
          else if (e.key === 'Escape') { setVal(price.toFixed(2)); setEditing(false) }
        }}
        style={{
          width: 80, fontSize: 13, fontWeight: 700,
          fontFamily: "'IBM Plex Mono', monospace", textAlign: 'right',
          background: '#fffbe6', color: '#1a1614',
          border: '1px solid #c2410c', borderRadius: 4,
          padding: '2px 4px', outline: 'none',
        }}
      />
    )
  }

  return (
    <button
      onClick={() => setEditing(true)}
      title="Click to override price"
      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 2px', textAlign: 'right', fontFamily: "'IBM Plex Mono', monospace" }}
    >
      <div style={{ fontWeight: 700, fontSize: 13, color: override ? '#c2410c' : '#1a1614' }}>{money(price)}</div>
      {override && <div style={{ fontSize: 9, color: '#a89e90', textDecoration: 'line-through' }}>{money(basePrice)}</div>}
    </button>
  )
}

// ─── Live Bill ────────────────────────────────────────────────────────────────

function LiveBill({ cart, customer, discount, discountMode, paymentType, storeName, onRemove, onPriceOverride }: {
  cart: CartItem[]; customer: CustomerInfo; discount: string
  discountMode: 'amount' | 'percent'; paymentType: PaymentType; storeName: string
  onRemove: (b: string) => void; onPriceOverride: (b: string, p: number) => void
}) {
  const subtotal = cart.reduce((s, i) => s + i.price, 0)
  const exchangeFeeTotal = cart.reduce((s, i) => s + (i.exchangeEligible ? i.exchangeFee : 0), 0)
  const discountVal = parseFloat(discount) || 0
  const discountAmt = discountMode === 'percent'
    ? Math.min(subtotal * (discountVal / 100), subtotal)
    : Math.min(discountVal, subtotal)
  const total = subtotal - discountAmt + exchangeFeeTotal
  const now = new Date()
  const hasCustomer = customer.firstName || customer.lastName || customer.phone
  const itemCount = cart.length

  const paper = '#f5f1ea'
  const ink = '#1a1614'
  const dim = '#7a6f63'
  const dimmer = '#b8ad9f'
  const border = '#d8cfc1'
  const punchBg = '#0a0a0a'

  return (
    <div style={{
      background: paper, color: ink,
      fontFamily: "'IBM Plex Mono', 'Courier New', Courier, monospace",
      borderRadius: 14,
      boxShadow: '0 6px 32px rgba(0,0,0,0.45), 0 1px 3px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.4)',
      backgroundImage: 'linear-gradient(180deg, #f7f3ec 0%, #f3eee5 100%)',
      height: '100%', display: 'flex', flexDirection: 'column',
      overflow: 'hidden', position: 'relative',
    }}>
      {/* Perforated tear edge top */}
      <div style={{
        height: 8, background: paper, flexShrink: 0,
        backgroundImage: `radial-gradient(circle at 6px 0, ${punchBg} 4px, ${paper} 4px)`,
        backgroundSize: '12px 8px', backgroundPosition: 'top',
      }} />

      <div style={{ padding: '4px 24px 0', flexShrink: 0 }}>
        <div style={{ textAlign: 'center', marginBottom: 12 }}>
          <div style={{ fontSize: 24, fontWeight: 900, letterSpacing: '0.18em', color: ink }}>
            {storeName}
          </div>
          <div style={{ fontSize: 10, color: dim, marginTop: 4, letterSpacing: '0.04em' }}>
            {now.toLocaleDateString('en-IN', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' })}
            {' · '}
            {now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
        </div>
        <ReceiptDivider dark />

        {hasCustomer && (
          <>
            <div style={{ padding: '4px 0', fontSize: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 700 }}>
                  {[customer.firstName, customer.lastName].filter(Boolean).join(' ') || 'Walk-in'}
                </div>
                {customer.phone && <div style={{ color: dim, fontSize: 11 }}>{customer.phone}</div>}
              </div>
              {customer.isReturning && (
                <div style={{ background: '#16a34a', color: '#fff', fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 4, letterSpacing: '0.06em' }}>
                  RETURNING · {customer.total_purchases}
                </div>
              )}
            </div>
            <ReceiptDivider dark />
          </>
        )}

        {cart.length > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: dimmer, letterSpacing: '0.08em', padding: '2px 0', textTransform: 'uppercase' }}>
            <span>Item</span>
            <span>Price</span>
          </div>
        )}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0 24px', minHeight: 80 }}>
        {cart.length === 0 ? (
          <div style={{ textAlign: 'center', color: dimmer, fontSize: 12, padding: '60px 20px', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            <div style={{ fontSize: 36, marginBottom: 12, opacity: 0.35 }}>⌥</div>
            scan items to begin
          </div>
        ) : cart.map((item, i) => (
          <div key={item.barcode} style={{
            display: 'flex', flexDirection: 'column', padding: '8px 0',
            borderBottom: i < cart.length - 1 ? `1px dotted ${border}` : 'none',
          }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {(item.label || item.category).toUpperCase()}
                </div>
                <div style={{ fontSize: 10, color: dim }}>
                  {[item.color, item.size, item.condition].filter(Boolean).join(' · ')}
                </div>
                <div style={{ fontSize: 9, color: dimmer }}>{item.barcode}</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 4, flexShrink: 0 }}>
                <PriceCell
                  price={item.price} basePrice={item.basePrice} override={item.override}
                  onChange={p => onPriceOverride(item.barcode, p)}
                />
                <button
                  onClick={() => onRemove(item.barcode)}
                  style={{ background: 'none', border: 'none', color: dimmer, cursor: 'pointer', fontSize: 18, lineHeight: 1, padding: '0 2px', transition: 'color 0.15s' }}
                  title="Remove"
                >×</button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {cart.length > 0 && (
        <div style={{ padding: '0 24px 20px', flexShrink: 0 }}>
          <ReceiptDivider dark />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <ReceiptRow dark label={`Subtotal (${itemCount} item${itemCount !== 1 ? 's' : ''})`} value={money(subtotal)} />
            {discountAmt > 0 && (
              <ReceiptRow dark
                label={discountMode === 'percent' ? `Discount (${discountVal}%)` : 'Discount'}
                value={`−${money(discountAmt)}`}
                valueColor="#c00"
              />
            )}
            {exchangeFeeTotal > 0 && (
              <ReceiptRow dark
                label={`Exchange fee (${cart.filter(i => i.exchangeEligible).length} item${cart.filter(i => i.exchangeEligible).length !== 1 ? 's' : ''})`}
                value={money(exchangeFeeTotal)}
                valueColor="#f59e0b"
              />
            )}
            <ReceiptRow dark label="Tax" value="calculated at checkout" small />
          </div>
          <div style={{ borderTop: `2px solid ${ink}`, marginTop: 10, paddingTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: '0.08em', color: ink }}>TOTAL</span>
            <span style={{ fontSize: 28, fontWeight: 900, letterSpacing: '-0.02em', color: ink, fontFamily: "'IBM Plex Mono', monospace" }}>
              {money(total)}
              <span style={{ fontSize: 11, color: dim, fontWeight: 400, letterSpacing: 0 }}> + tax</span>
            </span>
          </div>
          <ReceiptDivider dark />
          <ReceiptRow dark label="Payment" value={paymentType.toUpperCase()} />
          {customer.phone && (
            <div style={{ textAlign: 'center', fontSize: 10, color: dim, fontStyle: 'italic', marginTop: 12, letterSpacing: '0.04em' }}>
              ✉ SMS receipt → {customer.phone}
            </div>
          )}
        </div>
      )}

      {/* Perforated tear edge bottom */}
      <div style={{
        height: 8, background: paper, flexShrink: 0,
        backgroundImage: `radial-gradient(circle at 6px 8px, ${punchBg} 4px, ${paper} 4px)`,
        backgroundSize: '12px 8px', backgroundPosition: 'bottom',
      }} />
    </div>
  )
}

// ─── Cart strip ───────────────────────────────────────────────────────────────

function CartStrip({ count, subtotal, onVoid }: { count: number; subtotal: number; onVoid: () => void }) {
  const t = useTheme()
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '10px 14px', background: t.surface,
      border: `1px solid ${t.border}`, borderRadius: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 6,
          background: count > 0 ? t.accentDim : t.surface3,
          color: count > 0 ? t.accentText : t.textMuted,
          fontWeight: 700, fontSize: 13, fontFamily: t.mono,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>{count}</div>
        <div>
          <div style={{ fontSize: 11, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>Cart</div>
          <div style={{ fontSize: 14, color: t.text, fontWeight: 700, fontFamily: t.mono }}>{money(subtotal)}</div>
        </div>
      </div>
      <button
        onClick={onVoid}
        disabled={count === 0}
        style={{
          background: 'transparent',
          border: `1px solid ${count === 0 ? t.border : t.danger}`,
          color: count === 0 ? t.textDim : t.danger,
          padding: '6px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600,
          cursor: count === 0 ? 'not-allowed' : 'pointer',
          opacity: count === 0 ? 0.5 : 1, fontFamily: 'inherit',
        }}
      >Void cart</button>
    </div>
  )
}

// ─── Customer drawer ──────────────────────────────────────────────────────────

type PhoneState = 'idle' | 'valid' | 'invalid' | 'landline'

function CustomerDrawer({ open, onToggle, customer, setCustomer, lookingUp, onPhoneChange, onFieldBlur }: {
  open: boolean; onToggle: () => void
  customer: CustomerInfo; setCustomer: React.Dispatch<React.SetStateAction<CustomerInfo>>
  lookingUp: boolean; onPhoneChange: (p: string) => void; onFieldBlur: () => void
}) {
  const t = useTheme()
  const [phoneState, setPhoneState] = useState<PhoneState>('idle')
  const formatter = useRef(new AsYouType('IN'))

  const summary = (customer.firstName || customer.phone)
    ? `${[customer.firstName, customer.lastName].filter(Boolean).join(' ')}${customer.phone ? ` · ${customer.phone}` : ''}`
    : 'Walk-in customer'

  const phoneBorderColor = {
    idle:     t.border,
    valid:    t.success,
    invalid:  '#ef4444',
    landline: t.warning,
  }[phoneState]

  const fieldSt: React.CSSProperties = {
    background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 8,
    padding: '8px 11px', color: t.text, fontSize: 14, outline: 'none', width: '100%',
    boxSizing: 'border-box', fontFamily: t.font,
  }

  const handlePhoneInput = (raw: string) => {
    // Format live using AsYouType
    formatter.current.reset()
    const formatted = formatter.current.input(raw)
    setPhoneState('idle')
    onPhoneChange(formatted)
  }

  const handlePhoneBlur = () => {
    const val = customer.phone.trim()
    if (!val) { setPhoneState('idle'); onFieldBlur(); return }

    if (!isValidPhoneNumber(val, 'IN')) {
      setPhoneState('invalid')
      onFieldBlur()
      return
    }

    try {
      const parsed = parsePhoneNumber(val, 'IN')
      const type = parsed.getType()
      if (type === 'FIXED_LINE') {
        setPhoneState('landline')
      } else {
        setPhoneState('valid')
      }
    } catch {
      setPhoneState('valid')
    }
    onFieldBlur()
  }

  return (
    <div style={{ background: t.surface, border: `1px solid ${t.border}`, borderRadius: 12, boxShadow: t.shadow, overflow: 'hidden' }}>
      <button
        onClick={onToggle}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', background: 'transparent', border: 'none', cursor: 'pointer',
          color: t.text, fontFamily: 'inherit',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontWeight: 700, fontSize: 14 }}>Customer</span>
          {customer.isReturning && (
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 99,
              background: t.successDim, color: t.success, letterSpacing: '0.06em',
            }}>
              ✓ {customer.total_purchases} VISITS
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {lookingUp && <Spinner size={13} />}
          <span style={{ fontSize: 12, color: t.textMuted, fontFamily: t.mono }}>{summary}</span>
          <span style={{ fontSize: 11, color: t.textMuted, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s', display: 'inline-block' }}>▾</span>
        </div>
      </button>

      {open && (
        <div style={{ padding: '12px 16px 14px', display: 'flex', flexDirection: 'column', gap: 9, borderTop: `1px solid ${t.border}` }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <label style={lblStyle}>Phone (lookup)</label>
              {phoneState === 'valid' && (
                <span style={{ fontSize: 11, color: t.success, fontWeight: 700 }}>✓ Valid</span>
              )}
            </div>
            <input
              value={customer.phone}
              onChange={e => handlePhoneInput(e.target.value)}
              onBlur={handlePhoneBlur}
              placeholder="+91 98765 43210" type="tel"
              style={{ ...fieldSt, fontFamily: t.mono, borderColor: phoneBorderColor, transition: 'border-color 0.15s' }}
            />
            {phoneState === 'invalid' && (
              <div style={{ fontSize: 11, color: '#ef4444', marginTop: 2 }}>
                Enter a valid Indian mobile number
              </div>
            )}
            {phoneState === 'landline' && (
              <div style={{ fontSize: 11, color: t.warning, marginTop: 2 }}>
                This looks like a landline — confirm it is correct
              </div>
            )}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <label style={lblStyle}>First name</label>
              <input value={customer.firstName}
                onChange={e => setCustomer(c => ({ ...c, firstName: e.target.value }))}
                onBlur={onFieldBlur}
                placeholder="Priya" style={fieldSt} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <label style={lblStyle}>Last name</label>
              <input value={customer.lastName}
                onChange={e => setCustomer(c => ({ ...c, lastName: e.target.value }))}
                onBlur={onFieldBlur}
                placeholder="Sharma" style={fieldSt} />
            </div>
          </div>
          <div style={{ fontSize: 11, color: t.textMuted }}>
            Optional — SMS receipt sent to phone on file.
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Quick cash ───────────────────────────────────────────────────────────────

function QuickCash({ total, amounts }: { total: number; amounts: number[] }) {
  const t = useTheme()
  const [tendered, setTendered] = useState<number | null>(null)
  const change = tendered !== null ? tendered - total : 0

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={lblStyle}>Cash tendered</span>
        {tendered !== null && (
          <button onClick={() => setTendered(null)} style={{ background: 'none', border: 'none', color: t.textMuted, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>Clear</button>
        )}
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
        {amounts.map(amt => (
          <button
            key={amt}
            onClick={() => setTendered(amt)}
            style={{
              flex: 1, minWidth: 60,
              background: tendered === amt ? t.accent : t.surface2,
              color: tendered === amt ? t.bg : t.text,
              border: `1px solid ${tendered === amt ? t.accent : t.border}`,
              borderRadius: 6, padding: '8px 10px', fontSize: 14, fontWeight: 700,
              cursor: 'pointer', fontFamily: t.mono, transition: 'all 0.12s',
            }}
          >₹{amt}</button>
        ))}
      </div>
      {tendered !== null && change >= 0 && (
        <div style={{
          marginTop: 8, padding: '8px 12px',
          background: change > 0 ? t.warningDim : t.successDim,
          border: `1px solid ${change > 0 ? t.warning : t.success}`,
          borderRadius: 6, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
        }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: change > 0 ? t.warning : t.success, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Change due
          </span>
          <span style={{ fontSize: 18, fontWeight: 800, color: change > 0 ? t.warning : t.success, fontFamily: t.mono }}>
            {money(change)}
          </span>
        </div>
      )}
    </div>
  )
}

// ─── Sale complete ────────────────────────────────────────────────────────────

function SaleComplete({ sale, customer, onNew, onSameCustomer }: {
  sale: SaleResult; customer: CustomerInfo; onNew: () => void; onSameCustomer: () => void
}) {
  const t = useTheme()
  const [receipt, setReceipt] = useState<any>(null)
  const displayName = [customer.firstName, customer.lastName].filter(Boolean).join(' ')

  useEffect(() => {
    api.get(`/sales/${sale.sale_ref}/receipt`).then(r => setReceipt(r.data)).catch(() => {})
  }, [sale.sale_ref])

  return (
    <div style={{ maxWidth: 560, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{
          width: 48, height: 48, borderRadius: '50%',
          background: t.successDim, border: `2px solid ${t.success}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke={t.success} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: t.text }}>Sale Complete</div>
          <div style={{ fontFamily: t.mono, fontSize: 16, color: t.accent, letterSpacing: '0.06em' }}>{sale.receipt_number}</div>
        </div>
        <div style={{ fontSize: 26, fontWeight: 900, color: t.text, fontFamily: t.mono }}>
          {money(parseFloat(sale.total_amount))}
        </div>
      </div>

      <div id="receipt-print" style={{
        background: '#f5f1ea', color: '#1a1614', borderRadius: 14,
        backgroundImage: 'linear-gradient(180deg, #f7f3ec 0%, #f3eee5 100%)',
        boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
        fontFamily: "'IBM Plex Mono', Courier, monospace",
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        {/* Perforated tear edge top */}
        <div style={{
          height: 8, background: '#f5f1ea', flexShrink: 0,
          backgroundImage: 'radial-gradient(circle at 6px 0, #0a0a0a 4px, #f5f1ea 4px)',
          backgroundSize: '12px 8px', backgroundPosition: 'top',
        }} />

        {receipt ? (
          <div style={{ padding: '16px 24px 20px' }}>
            <div style={{ textAlign: 'center', marginBottom: 12 }}>
              <div style={{ fontSize: 20, fontWeight: 900, letterSpacing: '0.15em' }}>{receipt.store_name}</div>
              <div style={{ fontSize: 11, color: '#7a6f63', marginTop: 3 }}>{new Date(receipt.created_at).toLocaleString('en-IN')}</div>
              <div style={{ fontSize: 11, color: '#b8ad9f' }}>Receipt: {sale.receipt_number}</div>
            </div>
            <ReceiptDivider />
            {(displayName || customer.phone) && (
              <>
                <div style={{ padding: '4px 0', fontSize: 13 }}>
                  {displayName && <div style={{ fontWeight: 700 }}>{displayName}</div>}
                  {customer.phone && <div style={{ color: '#7a6f63', fontSize: 12 }}>{customer.phone}</div>}
                </div>
                <ReceiptDivider />
              </>
            )}
            {receipt.line_items.map((li: any, i: number) => (
              <div key={li.barcode} style={{
                display: 'flex', justifyContent: 'space-between', padding: '6px 0',
                borderBottom: i < receipt.line_items.length - 1 ? '1px dotted #d8cfc1' : 'none',
              }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 13 }}>{(li.label || li.category).toUpperCase()}</div>
                  <div style={{ fontSize: 11, color: '#7a6f63' }}>{[li.color, li.size].filter(Boolean).join(' · ')}</div>
                  <div style={{ fontSize: 10, color: '#b8ad9f' }}>{li.barcode}</div>
                </div>
                <div style={{ fontWeight: 700, fontSize: 14, alignSelf: 'center' }}>{money(parseFloat(li.price))}</div>
              </div>
            ))}
            <ReceiptDivider />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <ReceiptRow label={`Subtotal (${receipt.line_items.length} items)`} value={money(parseFloat(receipt.subtotal))} />
              {parseFloat(receipt.discount_amount) > 0 && (
                <ReceiptRow label="Discount" value={`−${money(parseFloat(receipt.discount_amount))}`} valueColor="#c00" />
              )}
              {parseFloat(receipt.tax_amount) > 0 && (
                <ReceiptRow label={`GST (${(parseFloat(receipt.tax_rate) * 100).toFixed(0)}%)`} value={money(parseFloat(receipt.tax_amount))} />
              )}
            </div>
            <div style={{ borderTop: '2px solid #1a1614', marginTop: 10, paddingTop: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: 16, fontWeight: 800 }}>TOTAL</span>
              <span style={{ fontSize: 24, fontWeight: 900 }}>{money(parseFloat(receipt.total_amount))}</span>
            </div>
            <ReceiptDivider />
            <ReceiptRow label="Payment" value={receipt.payment_type.toUpperCase()} />
            <div style={{ textAlign: 'center', fontSize: 11, color: '#7a6f63', marginTop: 10 }}>{receipt.receipt_footer}</div>
            <div style={{ textAlign: 'center', fontSize: 10, color: '#b8ad9f', marginTop: 3 }}>
              Returns within {receipt.return_window_days} days with receipt
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><Spinner size={24} /></div>
        )}

        {/* Perforated tear edge bottom */}
        <div style={{
          height: 8, background: '#f5f1ea', flexShrink: 0,
          backgroundImage: 'radial-gradient(circle at 6px 8px, #0a0a0a 4px, #f5f1ea 4px)',
          backgroundSize: '12px 8px', backgroundPosition: 'bottom',
        }} />
      </div>

      <div style={{ display: 'flex', gap: 10 }}>
        <button
          onClick={() => window.print()}
          style={{
            flex: 1, background: 'transparent', color: '#e8e8e2',
            border: '1px solid #2a2a2a', borderRadius: 8, padding: '12px',
            fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
          }}
        >Print</button>
        {(customer.firstName || customer.phone) && (
          <button onClick={onSameCustomer} style={{
            flex: 1, background: '#1e1e1e', color: '#e8e8e2',
            border: '1px solid #2a2a2a', borderRadius: 8, padding: '12px',
            fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
          }}>
            Another for {customer.firstName || 'Customer'}
          </button>
        )}
        <button onClick={onNew} style={{
          flex: 1, background: '#00e5a0', color: '#0a0a0a',
          border: 'none', borderRadius: 8, padding: '12px',
          fontSize: 14, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
        }}>
          New Sale
        </button>
      </div>

      <style>{`@media print{body>*{display:none!important}#receipt-print{display:block!important;box-shadow:none!important;border:none!important}}`}</style>
    </div>
  )
}

// ─── Main checkout ────────────────────────────────────────────────────────────

export default function Checkout() {
  const t = useTheme()
  const [cart, setCart] = useState<CartItem[]>([])
  const [discount, setDiscount] = useState('')
  const [discountMode, setDiscountMode] = useState<'amount' | 'percent'>('amount')
  const [paymentType, setPaymentType] = useState<PaymentType>('cash')
  const [error, setError] = useState<string | null>(null)
  const [lastSale, setLastSale] = useState<SaleResult | null>(null)
  const [storeName] = useState('qstar')
  const [customer, setCustomer] = useState<CustomerInfo>({ firstName: '', lastName: '', phone: '' })
  const [lookingUp, setLookingUp] = useState(false)
  const [customerOpen, setCustomerOpen] = useState(true)
  const [barcodeInput, setBarcodeInput] = useState('')
  const [scanFocused, setScanFocused] = useState(false)
  const [recentlyAdded, setRecentlyAdded] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [exchangeFeeAmount, setExchangeFeeAmount] = useState(0)

  useEffect(() => {
    api.get('/settings/public').then(r => {
      const fee = parseFloat(r.data?.exchange_fee_amount || '0')
      if (!isNaN(fee)) setExchangeFeeAmount(fee)
    }).catch(() => {})
  }, [])

  const barcodeRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const refocusTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const refocusScanner = useCallback(() => {
    if (refocusTimer.current) clearTimeout(refocusTimer.current)
    refocusTimer.current = setTimeout(() => {
      const active = document.activeElement as HTMLElement
      if (active && active.tagName === 'INPUT' && active !== barcodeRef.current) return
      barcodeRef.current?.focus()
    }, 60)
  }, [])

  useEffect(() => { barcodeRef.current?.focus() }, [])
  useEffect(() => { refocusScanner() }, [cart.length, lastSale, refocusScanner])

  const handlePhoneChange = (phone: string) => {
    setCustomer(c => ({ ...c, phone, customer_uid: undefined, isReturning: false }))
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (phone.replace(/\D/g, '').length < 7) return
    debounceRef.current = setTimeout(async () => {
      try {
        setLookingUp(true)
        const { data } = await api.get('/customers/lookup', { params: { phone } })
        setCustomer(c => ({
          ...c,
          firstName: c.firstName || data.first_name,
          lastName: c.lastName || `${data.last_initial}.`,
          customer_uid: data.customer_uid,
          total_purchases: data.total_purchases,
          isReturning: true,
        }))
        setCustomerOpen(true)
      } catch { /* new customer */ }
      finally { setLookingUp(false) }
    }, 400)
  }

  const lookupMutation = useMutation({
    mutationFn: async (barcode: string) => {
      const { data } = await api.get<{ items: ItemLookup[]; total: number }>('/items/', {
        params: { barcode, limit: 1 },
      })
      if (!data.items.length) throw new Error('Item not found: ' + barcode)
      return data.items[0]
    },
    onSuccess: (item) => {
      if (item.status !== 'in_stock') { setError(`${item.barcode} is not in stock (${item.status})`); return }
      if (cart.some(c => c.barcode === item.barcode)) { setError(`${item.barcode} already in cart`); return }
      const price = parseFloat(item.price)
      setCart(prev => [...prev, {
        barcode: item.barcode, category: item.category, color: item.color,
        label: item.label, size: item.size, condition: item.condition,
        price, basePrice: price,
        exchangeEligible: false, exchangeFee: exchangeFeeAmount,
      }])
      setError(null)
      setBarcodeInput('')
      setRecentlyAdded(item.barcode)
      setTimeout(() => setRecentlyAdded(r => r === item.barcode ? null : r), 1200)
    },
    onError: (err) => { setError(apiErrorMessage(err)); setBarcodeInput('') },
  })

  const handleBarcodeSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const val = barcodeInput.trim()
    if (!val) return
    setError(null)
    lookupMutation.mutate(val)
  }

  const removeItem = (barcode: string) => setCart(p => p.filter(i => i.barcode !== barcode))

  const overridePrice = (barcode: string, newPrice: number) =>
    setCart(p => p.map(i => i.barcode === barcode ? { ...i, price: newPrice, override: newPrice !== i.basePrice } : i))

  const toggleExchange = (barcode: string) =>
    setCart(p => p.map(i => i.barcode === barcode ? { ...i, exchangeEligible: !i.exchangeEligible } : i))

  const voidCart = useCallback(() => {
    if (cart.length === 0) return
    if (window.confirm(`Void all ${cart.length} item${cart.length !== 1 ? 's' : ''}?`)) {
      setCart([]); setDiscount(''); setError(null)
    }
  }, [cart.length])

  const subtotal = cart.reduce((s, i) => s + i.price, 0)
  const exchangeFeeTotalCart = cart.reduce((s, i) => s + (i.exchangeEligible ? i.exchangeFee : 0), 0)
  const discountVal = parseFloat(discount) || 0
  const discountAmt = discountMode === 'percent'
    ? Math.min(subtotal * (discountVal / 100), subtotal)
    : Math.min(discountVal, subtotal)
  const estimatedTotal = subtotal - discountAmt + exchangeFeeTotalCart

  const quickAmounts = useMemo(() => {
    return [...new Set([
      Math.ceil(estimatedTotal / 100) * 100,
      Math.ceil(estimatedTotal / 500) * 500,
      Math.ceil(estimatedTotal / 1000) * 1000,
      Math.ceil(estimatedTotal / 2000) * 2000,
    ])].filter(v => v >= estimatedTotal && v > 0).slice(0, 4)
  }, [estimatedTotal])

  const checkoutMutation = useMutation({
    mutationFn: async () => {
      setSubmitting(true)
      let customer_uid = customer.customer_uid

      if (!customer_uid && customer.firstName.trim() && customer.lastName.trim() && customer.phone.trim()) {
        try {
          const { data } = await api.post('/customers/', {
            first_name: customer.firstName.trim(),
            last_name: customer.lastName.trim(),
            phone: customer.phone.trim(),
          })
          customer_uid = data.customer_uid
        } catch (err: any) {
          const detail = err?.response?.data?.detail
          if (detail?.customer_uid) customer_uid = detail.customer_uid
        }
      }

      const { data } = await api.post<SaleResult>('/sales/', {
        items: cart.map(c => ({ barcode: c.barcode, exchange_eligible: c.exchangeEligible })),
        payment_type: paymentType,
        discount: discountAmt,
        customer_uid: customer_uid ?? undefined,
      })
      return data
    },
    onSuccess: (data) => {
      setLastSale(data)
      setCart([]); setDiscount(''); setError(null)
      setSubmitting(false)
    },
    onError: (err) => {
      setError(apiErrorMessage(err))
      setSubmitting(false)
    },
  })

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      const inField = target?.tagName === 'INPUT' || target?.tagName === 'SELECT' || target?.tagName === 'TEXTAREA'
      if (e.key === 'F12' && cart.length > 0 && !submitting) { e.preventDefault(); checkoutMutation.mutate(); return }
      if (e.key === 'F2') { e.preventDefault(); setCustomerOpen(o => !o); return }
      if (e.key === 'F3') {
        e.preventDefault()
        const el = document.getElementById('discount-input') as HTMLInputElement | null
        el?.focus(); el?.select(); return
      }
      if (e.key === 'Escape' && !inField && cart.length > 0) { e.preventDefault(); voidCart(); return }
      if (e.key === 'Backspace' && !inField && cart.length > 0) {
        e.preventDefault(); removeItem(cart[cart.length - 1].barcode); return
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cart, submitting, voidCart, checkoutMutation])

  if (lastSale) {
    return (
      <SaleComplete
        sale={lastSale} customer={customer}
        onSameCustomer={() => setLastSale(null)}
        onNew={() => {
          setLastSale(null)
          setCustomer({ firstName: '', lastName: '', phone: '' })
          setCustomerOpen(true)
        }}
      />
    )
  }

  return (
    <div style={{ maxWidth: 1280, margin: '0 auto', padding: '20px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <h2 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: t.text, letterSpacing: '-0.01em' }}>Checkout</h2>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          <KeyHint k="F2" label="Customer" />
          <KeyHint k="F3" label="Discount" />
          <KeyHint k="Backspace" label="Remove last" />
          <KeyHint k="F12" label="Complete" />
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          background: t.dangerDim, border: `1px solid ${t.danger}`,
          borderRadius: 8, padding: '10px 14px', color: t.danger,
          fontSize: 13, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          {error}
          <button onClick={() => setError(null)} style={{ background: 'none', border: 'none', color: t.danger, cursor: 'pointer', fontSize: 18 }}>×</button>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '420px 1fr', gap: 24, alignItems: 'start' }}>

        {/* Left: receipt */}
        <div style={{ position: 'sticky', top: 16, height: 'calc(100vh - 130px)' }}>
          <LiveBill
            cart={cart} customer={customer}
            discount={discount} discountMode={discountMode}
            paymentType={paymentType} storeName={storeName}
            onRemove={removeItem}
            onPriceOverride={overridePrice}
          />
        </div>

        {/* Right: controls */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* Barcode scanner */}
          <div style={{
            background: t.surface,
            border: `2px solid ${scanFocused ? t.accent : t.border}`,
            borderRadius: 12,
            boxShadow: scanFocused ? `0 0 0 4px ${t.accentDim}` : t.shadow,
            transition: 'border-color 0.15s, box-shadow 0.15s',
            overflow: 'hidden',
          }}>
            <form onSubmit={handleBarcodeSubmit} style={{ display: 'flex', alignItems: 'center' }}>
              <div style={{ padding: '0 16px', display: 'flex', alignItems: 'center', color: scanFocused ? t.accent : t.textMuted, transition: 'color 0.15s' }}>
                <ScanIcon />
              </div>
              <input
                ref={barcodeRef}
                value={barcodeInput}
                onChange={e => setBarcodeInput(e.target.value)}
                onFocus={() => setScanFocused(true)}
                onBlur={() => setScanFocused(false)}
                placeholder="Scan or type barcode…"
                autoComplete="off"
                style={{
                  flex: 1, background: 'transparent', border: 'none',
                  padding: '18px 0', color: t.text, fontSize: 16,
                  outline: 'none', fontFamily: t.mono, letterSpacing: '0.04em',
                }}
              />
              <div style={{ padding: '0 14px' }}>
                <button
                  type="submit"
                  disabled={!barcodeInput.trim() || lookupMutation.isPending}
                  style={{
                    background: t.accent, color: t.bg, border: 'none',
                    borderRadius: 8, padding: '10px 18px', fontWeight: 700, fontSize: 14,
                    cursor: barcodeInput.trim() && !lookupMutation.isPending ? 'pointer' : 'not-allowed',
                    opacity: barcodeInput.trim() && !lookupMutation.isPending ? 1 : 0.45,
                    fontFamily: 'inherit',
                  }}
                >{lookupMutation.isPending ? '…' : 'Add'}</button>
              </div>
            </form>
            {recentlyAdded && (
              <div style={{
                padding: '6px 16px', borderTop: `1px solid ${t.border}`,
                background: t.successDim, color: t.success,
                fontSize: 12, fontWeight: 600, fontFamily: t.mono,
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <span>✓</span> Added {recentlyAdded}
              </div>
            )}
          </div>

          <CartStrip count={cart.length} subtotal={subtotal} onVoid={voidCart} />

          {/* Per-item exchange toggle — shown whenever cart has items */}
          {cart.length > 0 && (
            <div style={{ background: t.surface, border: `1px solid ${t.border}`, borderRadius: 10, padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Exchange eligible
                {exchangeFeeAmount > 0
                  ? ` — +₹${exchangeFeeAmount.toFixed(0)} per item`
                  : ' — free'}
              </div>
              {cart.map(item => (
                <label key={item.barcode} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={item.exchangeEligible}
                    onChange={() => toggleExchange(item.barcode)}
                    style={{ width: 14, height: 14, cursor: 'pointer' }}
                  />
                  <span style={{ fontSize: 12, color: item.exchangeEligible ? t.warning : t.textMuted, flex: 1 }}>
                    {(item.label || item.category).toUpperCase()} · {item.barcode}
                  </span>
                  {item.exchangeEligible && exchangeFeeAmount > 0 && (
                    <span style={{ fontSize: 10, color: t.warning, fontWeight: 700 }}>+₹{item.exchangeFee.toFixed(0)}</span>
                  )}
                </label>
              ))}
            </div>
          )}

          <CustomerDrawer
            open={customerOpen}
            onToggle={() => setCustomerOpen(o => !o)}
            customer={customer}
            setCustomer={setCustomer}
            lookingUp={lookingUp}
            onPhoneChange={handlePhoneChange}
            onFieldBlur={refocusScanner}
          />

          {/* Payment */}
          <div style={{ background: t.surface, border: `1px solid ${t.border}`, borderRadius: 12, boxShadow: t.shadow, overflow: 'hidden' }}>
            <div style={{ padding: '12px 16px', borderBottom: `1px solid ${t.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 700, fontSize: 14, color: t.text }}>Payment</span>
              <span style={{ fontSize: 28, fontWeight: 800, color: t.text, fontFamily: t.mono, letterSpacing: '-0.02em' }}>
                {money(estimatedTotal)}
              </span>
            </div>

            <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Method */}
              <div>
                <div style={lblStyle}>Method</div>
                <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                  {([{ value: 'cash', label: 'Cash' }, { value: 'card', label: 'Card' }, { value: 'other', label: 'Other' }] as Array<{ value: PaymentType; label: string }>).map(opt => (
                    <button
                      key={opt.value}
                      onClick={() => setPaymentType(opt.value)}
                      style={{
                        flex: 1, padding: '12px 14px', borderRadius: 8, fontWeight: 600,
                        fontSize: 14, cursor: 'pointer',
                        background: paymentType === opt.value ? t.accent : t.surface2,
                        color: paymentType === opt.value ? t.bg : t.text,
                        border: `1px solid ${paymentType === opt.value ? t.accent : t.border}`,
                        transition: 'all 0.12s', fontFamily: 'inherit',
                      }}
                    >{opt.label}</button>
                  ))}
                </div>
              </div>

              {/* Discount */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={lblStyle}>Discount</span>
                  <div style={{ display: 'inline-flex', background: t.surface2, borderRadius: 6, padding: 2, border: `1px solid ${t.border}` }}>
                    {(['amount', 'percent'] as const).map(m => (
                      <button
                        key={m}
                        onClick={() => setDiscountMode(m)}
                        style={{
                          padding: '3px 12px', fontSize: 11, fontWeight: 700,
                          borderRadius: 4, border: 'none', cursor: 'pointer', fontFamily: 'inherit',
                          background: discountMode === m ? t.surface : 'transparent',
                          color: discountMode === m ? t.text : t.textMuted,
                        }}
                      >{m === 'amount' ? '₹' : '%'}</button>
                    ))}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <input
                    id="discount-input"
                    type="number" min="0" step="0.01"
                    value={discount}
                    onChange={e => setDiscount(e.target.value)}
                    onBlur={refocusScanner}
                    placeholder="0"
                    style={{
                      flex: 1, background: t.surface2, border: `1px solid ${t.border}`,
                      borderRadius: 8, padding: '8px 11px', color: t.text, fontSize: 16,
                      outline: 'none', fontFamily: t.mono, boxSizing: 'border-box',
                    }}
                  />
                  {discountMode === 'percent' && ['10', '15', '20'].map(p => (
                    <button
                      key={p}
                      onClick={() => setDiscount(p)}
                      style={{
                        padding: '0 12px', fontSize: 12, fontWeight: 600,
                        borderRadius: 6, border: `1px solid ${t.border}`,
                        background: t.surface2, color: t.textMuted, cursor: 'pointer', fontFamily: 'inherit',
                      }}
                    >{p}%</button>
                  ))}
                </div>
              </div>

              {/* Quick cash */}
              {paymentType === 'cash' && cart.length > 0 && quickAmounts.length > 0 && (
                <QuickCash total={estimatedTotal} amounts={quickAmounts} />
              )}

              {/* Complete button */}
              <button
                onClick={() => checkoutMutation.mutate()}
                disabled={cart.length === 0 || submitting}
                style={{
                  width: '100%', padding: '14px',
                  background: cart.length === 0 || submitting ? t.surface2 : t.accent,
                  color: cart.length === 0 || submitting ? t.textMuted : t.bg,
                  border: 'none', borderRadius: 8,
                  fontWeight: 700, fontSize: 15,
                  cursor: cart.length === 0 || submitting ? 'not-allowed' : 'pointer',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 10,
                  transition: 'all 0.12s', fontFamily: 'inherit',
                }}
              >
                {submitting
                  ? <><Spinner size={14} /> Processing…</>
                  : cart.length === 0
                    ? 'Scan items to start'
                    : <>Complete Sale · {money(estimatedTotal)}
                        <kbd style={{ fontSize: 10, padding: '2px 6px', borderRadius: 3, background: 'rgba(0,0,0,0.2)', fontWeight: 700, fontFamily: t.mono }}>F12</kbd>
                      </>
                }
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
