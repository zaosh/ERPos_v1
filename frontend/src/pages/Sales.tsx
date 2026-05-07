import { useState, useRef } from 'react'
import { api, apiErrorMessage } from '../utils/api'
import { money } from '../utils/currency'
import { useTheme } from '../styles/theme'
import { useAuthStore } from '../store/authStore'
import { Spinner, ErrorAlert } from '../components/ui'

// ─── Types ────────────────────────────────────────────────────────────────────

type ReceiptLineItem = {
  item_id: number
  barcode: string
  label: string | null
  category: string
  color: string | null
  size: string | null
  condition: string | null
  price: string
  returned: boolean
}

type Receipt = {
  sale_id: number
  store_name: string
  receipt_footer: string
  sale_ref: string
  receipt_number: string
  created_at: string
  cashier_first_name: string
  customer_display: string | null
  line_items: ReceiptLineItem[]
  subtotal: string
  discount_amount: string
  tax_rate: string
  tax_amount: string
  total_amount: string
  payment_type: string
  return_window_days: number
}


// ─── Receipt helpers ──────────────────────────────────────────────────────────

function RDivider({ dark }: { dark?: boolean }) {
  return <div style={{ borderTop: `1px dashed ${dark ? '#c8bfb0' : '#ccc'}`, margin: '8px 0' }} />
}

function RRow({ label, value, valueColor, small }: { label: string; value: string; valueColor?: string; small?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: small ? 10 : 12, color: small ? '#b8ad9f' : '#444' }}>
      <span>{label}</span>
      <span style={{ fontWeight: small ? 400 : 600, color: valueColor, fontFamily: "'IBM Plex Mono', monospace" }}>{value}</span>
    </div>
  )
}

// ─── ReadOnlyBill ─────────────────────────────────────────────────────────────

function ReadOnlyBill({ receipt }: { receipt: Receipt }) {
  const paper = '#f5f1ea'
  const ink = '#1a1614'
  const dim = '#7a6f63'
  const dimmer = '#b8ad9f'
  const border = '#d8cfc1'
  const punchBg = '#0a0a0a'
  const created = new Date(receipt.created_at)

  return (
    <div style={{
      background: paper, color: ink,
      fontFamily: "'IBM Plex Mono', 'Courier New', monospace",
      borderRadius: 14,
      boxShadow: '0 6px 32px rgba(0,0,0,0.45), 0 1px 3px rgba(0,0,0,0.25)',
      backgroundImage: 'linear-gradient(180deg, #f7f3ec 0%, #f3eee5 100%)',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      {/* Perforated top */}
      <div style={{
        height: 8, background: paper, flexShrink: 0,
        backgroundImage: `radial-gradient(circle at 6px 0, ${punchBg} 4px, ${paper} 4px)`,
        backgroundSize: '12px 8px', backgroundPosition: 'top',
      }} />

      <div style={{ padding: '4px 24px 0', flexShrink: 0 }}>
        <div style={{ textAlign: 'center', marginBottom: 10 }}>
          <div style={{ fontSize: 24, fontWeight: 900, letterSpacing: '0.18em', color: ink }}>
            {receipt.store_name}
          </div>
          <div style={{ fontSize: 10, color: dim, marginTop: 4 }}>
            {created.toLocaleDateString('en-IN', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' })}
            {' · '}
            {created.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
          <div style={{ fontSize: 9, color: dimmer, marginTop: 3, letterSpacing: '0.04em' }}>
            {receipt.sale_ref} · {receipt.receipt_number}
          </div>
        </div>
        <RDivider />

        {receipt.customer_display && (
          <>
            <div style={{ padding: '4px 0', fontSize: 12, fontWeight: 700 }}>{receipt.customer_display}</div>
            <RDivider />
          </>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: dimmer, letterSpacing: '0.08em', padding: '2px 0', textTransform: 'uppercase' }}>
          <span>Item</span><span>Price</span>
        </div>
      </div>

      <div style={{ overflowY: 'auto', padding: '0 24px', maxHeight: 340 }}>
        {receipt.line_items.map((item, i) => (
          <div key={item.item_id} style={{
            display: 'flex', alignItems: 'flex-start', gap: 8, padding: '8px 0',
            borderBottom: i < receipt.line_items.length - 1 ? `1px dotted ${border}` : 'none',
            opacity: item.returned ? 0.5 : 1,
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textDecoration: item.returned ? 'line-through' : 'none' }}>
                {(item.label || item.category).toUpperCase()}
              </div>
              <div style={{ fontSize: 10, color: dim }}>
                {[item.color, item.size, item.condition].filter(Boolean).join(' · ')}
                {item.returned && <span style={{ marginLeft: 6, fontSize: 9, fontWeight: 700, color: '#c2410c', letterSpacing: '0.06em' }}>RETURNED</span>}
              </div>
              <div style={{ fontSize: 9, color: dimmer }}>{item.barcode}</div>
            </div>
            <div style={{ fontWeight: 700, fontSize: 13, flexShrink: 0, color: ink, textDecoration: item.returned ? 'line-through' : 'none' }}>
              {money(parseFloat(item.price))}
            </div>
          </div>
        ))}
      </div>

      <div style={{ padding: '0 24px 20px', flexShrink: 0 }}>
        <RDivider />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <RRow label={`Subtotal (${receipt.line_items.length} item${receipt.line_items.length !== 1 ? 's' : ''})`} value={money(parseFloat(receipt.subtotal))} />
          {parseFloat(receipt.discount_amount) > 0 && (
            <RRow label="Discount" value={`−${money(parseFloat(receipt.discount_amount))}`} valueColor="#c00" />
          )}
          {parseFloat(receipt.tax_amount) > 0 && (
            <RRow label={`GST (${(parseFloat(receipt.tax_rate) * 100).toFixed(0)}%)`} value={money(parseFloat(receipt.tax_amount))} />
          )}
        </div>
        <div style={{ borderTop: `2px solid ${ink}`, marginTop: 10, paddingTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: '0.08em' }}>TOTAL</span>
          <span style={{ fontSize: 28, fontWeight: 900, fontFamily: "'IBM Plex Mono', monospace" }}>
            {money(parseFloat(receipt.total_amount))}
          </span>
        </div>
        <RDivider />
        <RRow label="Payment" value={receipt.payment_type.toUpperCase()} />
        <RRow small label="Served by" value={receipt.cashier_first_name} />
        {receipt.receipt_footer && (
          <div style={{ textAlign: 'center', fontSize: 10, color: dim, fontStyle: 'italic', marginTop: 10 }}>
            {receipt.receipt_footer}
          </div>
        )}
      </div>

      {/* Perforated bottom */}
      <div style={{
        height: 8, background: paper, flexShrink: 0,
        backgroundImage: `radial-gradient(circle at 6px 8px, ${punchBg} 4px, ${paper} 4px)`,
        backgroundSize: '12px 8px', backgroundPosition: 'bottom',
      }} />
    </div>
  )
}

// ─── Days banner ──────────────────────────────────────────────────────────────

function DaysBanner({ receipt }: { receipt: Receipt }) {
  const t = useTheme()
  const ageDays = Math.floor((Date.now() - new Date(receipt.created_at).getTime()) / 86_400_000)
  const daysLeft = receipt.return_window_days - ageDays
  const expired = daysLeft < 0

  let bg: string, border: string, color: string, text: string
  if (expired) {
    bg = t.dangerDim; border = t.danger; color = t.danger
    text = `Return window closed · ${ageDays} day${ageDays !== 1 ? 's' : ''} ago`
  } else if (daysLeft <= 3) {
    bg = t.warningDim; border = t.warning; color = t.warning
    text = `${ageDays} day${ageDays !== 1 ? 's' : ''} ago · ${daysLeft} day${daysLeft !== 1 ? 's' : ''} left to return`
  } else {
    bg = t.successDim; border = t.success; color = t.success
    text = `${ageDays} day${ageDays !== 1 ? 's' : ''} ago · ${daysLeft} day${daysLeft !== 1 ? 's' : ''} left to return`
  }

  return (
    <div style={{
      background: bg, border: `1px solid ${border}`, borderRadius: 10,
      padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    }}>
      <span style={{ fontSize: 13, fontWeight: 700, color }}>{text}</span>
      <span style={{ fontSize: 11, color, opacity: 0.7, fontFamily: "'IBM Plex Mono', monospace" }}>
        {receipt.return_window_days}d window
      </span>
    </div>
  )
}

// ─── Return Panel ─────────────────────────────────────────────────────────────

function ReturnPanel({ receipt, onSuccess }: { receipt: Receipt; onSuccess: (ref: string, count: number) => void }) {
  const t = useTheme()
  const user = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'admin'

  const ageDays = Math.floor((Date.now() - new Date(receipt.created_at).getTime()) / 86_400_000)
  const expired = ageDays > receipt.return_window_days

  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [reason, setReason] = useState('')
  const [refundMethod, setRefundMethod] = useState<'cash' | 'card' | 'store_credit'>('cash')
  const [resellable, setResellable] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [submitErr, setSubmitErr] = useState<string | null>(null)

  const toggleItem = (item_id: number) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(item_id) ? next.delete(item_id) : next.add(item_id)
      return next
    })
  }

  const refundTotal = receipt.line_items
    .filter(li => selected.has(li.item_id))
    .reduce((s, li) => s + parseFloat(li.price), 0)

  const submit = async () => {
    setSubmitting(true); setSubmitErr(null)
    try {
      const { data } = await api.post('/returns/', {
        sale_ref: receipt.sale_ref,
        item_ids: Array.from(selected),
        return_reason: reason.trim(),
        refund_method: refundMethod,
        resellable,
      })
      onSuccess(data.return_ref, selected.size)
    } catch (e: any) {
      setSubmitErr(apiErrorMessage(e))
    } finally { setSubmitting(false) }
  }

  const fieldSt: React.CSSProperties = {
    background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 8,
    padding: '8px 11px', color: t.text, fontSize: 14, outline: 'none',
    width: '100%', boxSizing: 'border-box', fontFamily: t.font, resize: 'vertical' as const,
  }
  const lblSt: React.CSSProperties = { fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }

  // Non-admin or expired: show info card
  if (!isAdmin) {
    return (
      <div style={{ background: t.surface, border: `1px solid ${t.border}`, borderRadius: 12, padding: '20px 18px', color: t.textMuted, fontSize: 13 }}>
        Returns can only be processed by an admin.
      </div>
    )
  }
  if (expired) {
    return (
      <div style={{ background: t.surface, border: `1px solid ${t.border}`, borderRadius: 12, padding: '20px 18px', color: t.textMuted, fontSize: 13 }}>
        The {receipt.return_window_days}-day return window has passed for this sale.
      </div>
    )
  }

  return (
    <div style={{ background: t.surface, border: `1px solid ${t.border}`, borderRadius: 12, boxShadow: t.shadow, overflow: 'hidden' }}>
      <div style={{ padding: '13px 16px', borderBottom: `1px solid ${t.border}` }}>
        <span style={{ fontWeight: 700, fontSize: 14, color: t.text }}>Process Return</span>
      </div>

      <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* Item checklist */}
        <div>
          <div style={{ ...lblSt, marginBottom: 8 }}>Select items to return</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {receipt.line_items.map(li => {
              const sel = selected.has(li.item_id)
              const alreadyReturned = li.returned
              return (
                <div
                  key={li.item_id}
                  onClick={() => !alreadyReturned && toggleItem(li.item_id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
                    borderRadius: 8, cursor: alreadyReturned ? 'not-allowed' : 'pointer',
                    background: alreadyReturned ? t.surface3 : sel ? t.accentDim : t.surface2,
                    border: `1px solid ${alreadyReturned ? t.border : sel ? t.accent : t.border}`,
                    opacity: alreadyReturned ? 0.5 : 1,
                    transition: 'all 0.12s',
                  }}
                >
                  <div style={{
                    width: 16, height: 16, borderRadius: 4, flexShrink: 0,
                    background: sel ? t.accent : 'transparent',
                    border: `2px solid ${alreadyReturned ? t.border : sel ? t.accent : t.border}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    {sel && <svg width={10} height={10} viewBox="0 0 12 12" fill="none" stroke={t.bg} strokeWidth={2.5} strokeLinecap="round"><polyline points="2 6 5 9 10 3" /></svg>}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: t.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textDecoration: alreadyReturned ? 'line-through' : 'none' }}>
                      {(li.label || li.category).toUpperCase()}
                    </div>
                    <div style={{ fontSize: 10, color: t.textMuted, fontFamily: t.mono }}>
                      {li.barcode}
                      {alreadyReturned && <span style={{ marginLeft: 8, color: '#c2410c', fontWeight: 700 }}>RETURNED</span>}
                    </div>
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: t.text, fontFamily: t.mono, flexShrink: 0, textDecoration: alreadyReturned ? 'line-through' : 'none' }}>
                    {money(parseFloat(li.price))}
                  </div>
                </div>
              )
            })}
          </div>
          {selected.size > 0 && (
            <div style={{ marginTop: 8, fontSize: 12, color: t.textMuted, textAlign: 'right' }}>
              Refund total: <span style={{ color: t.accent, fontWeight: 700, fontFamily: t.mono }}>{money(refundTotal)}</span>
            </div>
          )}
        </div>

        {/* Reason */}
        <div>
          <div style={{ ...lblSt, marginBottom: 6 }}>Reason</div>
          <textarea
            value={reason}
            onChange={e => setReason(e.target.value)}
            placeholder="Customer return reason…"
            rows={2}
            style={fieldSt}
          />
        </div>

        {/* Refund method */}
        <div>
          <div style={{ ...lblSt, marginBottom: 6 }}>Refund method</div>
          <div style={{ display: 'flex', gap: 6 }}>
            {([['cash', 'Cash'], ['card', 'Card'], ['store_credit', 'Store Credit']] as const).map(([val, lbl]) => (
              <button
                key={val}
                onClick={() => setRefundMethod(val)}
                style={{
                  flex: 1, padding: '9px 8px', borderRadius: 8, fontSize: 13, fontWeight: 600,
                  cursor: 'pointer', fontFamily: 'inherit',
                  background: refundMethod === val ? t.accent : t.surface2,
                  color: refundMethod === val ? t.bg : t.text,
                  border: `1px solid ${refundMethod === val ? t.accent : t.border}`,
                  transition: 'all 0.12s',
                }}
              >{lbl}</button>
            ))}
          </div>
        </div>

        {/* Resellable toggle */}
        <div
          onClick={() => setResellable(r => !r)}
          style={{
            display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer',
            padding: '10px 12px', borderRadius: 8,
            background: resellable ? t.accentDim : t.dangerDim,
            border: `1px solid ${resellable ? t.accent : t.danger}`,
            transition: 'all 0.12s',
          }}
        >
          <div style={{
            width: 18, height: 18, borderRadius: 4, flexShrink: 0, marginTop: 1,
            background: resellable ? t.accent : 'transparent',
            border: `2px solid ${resellable ? t.accent : t.danger}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {resellable && <svg width={11} height={11} viewBox="0 0 12 12" fill="none" stroke={t.bg} strokeWidth={2.5} strokeLinecap="round"><polyline points="2 6 5 9 10 3" /></svg>}
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: resellable ? t.accent : t.danger }}>
              {resellable ? 'Return to inventory' : 'Archive item'}
            </div>
            <div style={{ fontSize: 11, color: t.textMuted, marginTop: 2 }}>
              {resellable
                ? 'Item goes back in stock with its original barcode'
                : 'Item will be archived and not resellable'}
            </div>
          </div>
        </div>

        {submitErr && <ErrorAlert message={submitErr} onDismiss={() => setSubmitErr(null)} />}

        <button
          onClick={submit}
          disabled={selected.size === 0 || !reason.trim() || submitting}
          style={{
            width: '100%', padding: '13px',
            background: selected.size === 0 || !reason.trim() || submitting ? t.surface2 : t.accent,
            color: selected.size === 0 || !reason.trim() || submitting ? t.textMuted : t.bg,
            border: 'none', borderRadius: 8, fontWeight: 700, fontSize: 14,
            cursor: selected.size === 0 || !reason.trim() || submitting ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            fontFamily: 'inherit', transition: 'all 0.12s',
          }}
        >
          {submitting
            ? <><Spinner size={14} /> Processing…</>
            : selected.size === 0
              ? 'Select items to return'
              : `Return ${selected.size} item${selected.size !== 1 ? 's' : ''} · ${money(refundTotal)}`}
        </button>
      </div>
    </div>
  )
}

// ─── Return Success ───────────────────────────────────────────────────────────

function ReturnSuccess({ returnRef, itemCount, onDone }: { returnRef: string; itemCount: number; onDone: () => void }) {
  const t = useTheme()
  return (
    <div style={{
      background: t.surface, border: `1px solid ${t.border}`, borderRadius: 12,
      padding: '28px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16,
    }}>
      <div style={{ width: 52, height: 52, borderRadius: '50%', background: t.successDim, border: `2px solid ${t.success}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width={24} height={24} viewBox="0 0 24 24" fill="none" stroke={t.success} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 17, fontWeight: 700, color: t.text }}>Return Processed</div>
        <div style={{ fontFamily: t.mono, fontSize: 14, color: t.accent, marginTop: 4, letterSpacing: '0.06em' }}>{returnRef}</div>
        <div style={{ fontSize: 13, color: t.textMuted, marginTop: 8 }}>
          {itemCount} item{itemCount !== 1 ? 's' : ''} returned to inventory with original barcode
        </div>
      </div>
      <button
        onClick={onDone}
        style={{
          background: t.accent, color: t.bg, border: 'none', borderRadius: 8,
          padding: '11px 28px', fontWeight: 700, fontSize: 14, cursor: 'pointer', fontFamily: 'inherit',
        }}
      >Done</button>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Sales() {
  const t = useTheme()
  const [query, setQuery] = useState('')
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [returnRef, setReturnRef] = useState<string | null>(null)
  const [returnCount, setReturnCount] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const search = async () => {
    const q = query.trim()
    if (!q) return
    setLoading(true); setErr(null); setReceipt(null); setReturnRef(null)
    try {
      const path = q.toUpperCase().startsWith('RCP-')
        ? `/sales/by-receipt/${encodeURIComponent(q)}`
        : `/sales/${encodeURIComponent(q)}/receipt`
      const { data } = await api.get<Receipt>(path)
      setReceipt(data)
    } catch (e: any) {
      setErr(apiErrorMessage(e) || 'Sale not found')
    } finally { setLoading(false) }
  }

  const reset = () => {
    setReceipt(null); setQuery(''); setErr(null); setReturnRef(null)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  return (
    <div style={{ maxWidth: 1280, margin: '0 auto', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <h2 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: t.text, letterSpacing: '-0.01em' }}>Sales</h2>

      {/* Search bar */}
      <div style={{
        background: t.surface, border: `1px solid ${t.border}`, borderRadius: 12,
        display: 'flex', alignItems: 'center', overflow: 'hidden',
        boxShadow: t.shadow,
      }}>
        <div style={{ padding: '0 16px', color: t.textMuted }}>
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </div>
        <input
          ref={inputRef}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && search()}
          placeholder="Search by order ID (SALE-20260507-001) or receipt number (RCP-…)"
          autoFocus
          style={{
            flex: 1, background: 'transparent', border: 'none',
            padding: '16px 0', color: t.text, fontSize: 15,
            outline: 'none', fontFamily: t.mono, letterSpacing: '0.02em',
          }}
        />
        {receipt && (
          <button
            onClick={reset}
            style={{ background: 'none', border: 'none', color: t.textMuted, cursor: 'pointer', padding: '0 12px', fontSize: 20 }}
            title="Clear"
          >×</button>
        )}
        <div style={{ padding: '0 12px' }}>
          <button
            onClick={search}
            disabled={!query.trim() || loading}
            style={{
              background: query.trim() && !loading ? t.accent : t.surface2,
              color: query.trim() && !loading ? t.bg : t.textMuted,
              border: 'none', borderRadius: 8, padding: '10px 20px',
              fontWeight: 700, fontSize: 14, cursor: query.trim() && !loading ? 'pointer' : 'not-allowed',
              fontFamily: 'inherit', transition: 'all 0.12s',
            }}
          >
            {loading ? <Spinner size={14} /> : 'Find'}
          </button>
        </div>
      </div>

      {err && <ErrorAlert message={err} onDismiss={() => setErr(null)} />}

      {/* Empty state */}
      {!receipt && !loading && !err && (
        <div style={{ textAlign: 'center', color: t.textDim, padding: '60px 0', fontSize: 13 }}>
          <div style={{ fontSize: 36, marginBottom: 12, opacity: 0.3 }}>🧾</div>
          Search by sale ref or receipt number to view billing details and process returns
        </div>
      )}

      {/* Results */}
      {receipt && (
        <div style={{ display: 'grid', gridTemplateColumns: '420px 1fr', gap: 24, alignItems: 'start' }}>
          {/* Left: thermal receipt */}
          <ReadOnlyBill receipt={receipt} />

          {/* Right: days banner + return panel / success */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <DaysBanner receipt={receipt} />

            {returnRef
              ? <ReturnSuccess returnRef={returnRef} itemCount={returnCount} onDone={reset} />
              : <ReturnPanel
                  receipt={receipt}
                  onSuccess={(ref, count) => { setReturnRef(ref); setReturnCount(count) }}
                />
            }
          </div>
        </div>
      )}
    </div>
  )
}
