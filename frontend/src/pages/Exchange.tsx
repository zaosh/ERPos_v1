import { useState, useRef } from 'react'
import { api, apiErrorMessage } from '../utils/api'
import { money } from '../utils/currency'
import { useTheme } from '../styles/theme'
import { Spinner } from '../components/ui'
import { BillHistoryTimeline, type BillHistoryEvent } from '../components/BillHistoryTimeline'

// ─── Types ────────────────────────────────────────────────────────────────────

interface CustomerLookup {
  customer_uid: string
  first_name: string
  last_initial: string
  phone_masked: string
  total_purchases: number
}

interface EligibleItem {
  item_id: number
  barcode: string
  label: string | null
  category: string
  color: string | null
  size: string | null
  condition: string | null
  price: string
  exchange_fee_paid: string
  image_url: string | null
  image_thumb_url: string | null
}

interface EligibleBill {
  sale_ref: string
  receipt_number: string
  created_at: string
  total_amount: string
  days_old: number
  window_expires_in_days: number
  eligible_items: EligibleItem[]
}

interface ExchangeResult {
  exchange_ref: string
  status: string
  original_item_id: number
  new_item_id: number | null
}

// ─── Step indicator ───────────────────────────────────────────────────────────

function Steps({ current }: { current: number }) {
  const t = useTheme()
  const steps = ['Customer', 'Bill', 'Item', 'New Item', 'Done']
  return (
    <div style={{ display: 'flex', gap: 0, marginBottom: 24 }}>
      {steps.map((label, i) => {
        const step = i + 1
        const active = step === current
        const done = step < current
        return (
          <div key={label} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1 }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%',
                background: done ? t.success : active ? t.accent : t.surface2,
                color: done || active ? t.bg : t.textMuted,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontWeight: 700, fontSize: 13,
                border: `2px solid ${done ? t.success : active ? t.accent : t.border}`,
              }}>
                {done ? '✓' : step}
              </div>
              <div style={{ fontSize: 10, color: active ? t.text : t.textMuted, marginTop: 4, textAlign: 'center', fontWeight: active ? 700 : 400 }}>
                {label}
              </div>
            </div>
            {i < steps.length - 1 && (
              <div style={{ height: 2, background: done ? t.success : t.border, width: 20, flexShrink: 0, marginBottom: 14 }} />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Shared primitives ────────────────────────────────────────────────────────

function Card({ children, title }: { children: React.ReactNode; title?: string }) {
  const t = useTheme()
  return (
    <div style={{ background: t.surface, border: `1px solid ${t.border}`, borderRadius: 12, boxShadow: t.shadow, padding: 20 }}>
      {title && <div style={{ fontWeight: 700, fontSize: 15, color: t.text, marginBottom: 14 }}>{title}</div>}
      {children}
    </div>
  )
}

function Btn({ children, onClick, disabled, variant = 'primary' }: {
  children: React.ReactNode; onClick?: () => void; disabled?: boolean; variant?: 'primary' | 'secondary'
}) {
  const t = useTheme()
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding: '10px 20px', borderRadius: 8, fontWeight: 700, fontSize: 14,
      border: 'none', cursor: disabled ? 'not-allowed' : 'pointer',
      fontFamily: 'inherit', background: disabled ? t.surface2 : variant === 'primary' ? t.accent : t.surface3,
      color: disabled ? t.textMuted : variant === 'primary' ? t.bg : t.text,
      opacity: disabled ? 0.6 : 1,
    }}>
      {children}
    </button>
  )
}

const INPUT = (t: ReturnType<typeof useTheme>): React.CSSProperties => ({
  width: '100%', boxSizing: 'border-box',
  background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 8,
  padding: '10px 12px', color: t.text, fontSize: 14, outline: 'none', fontFamily: 'inherit',
})

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function Exchange() {
  const t = useTheme()
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [phone, setPhone] = useState('')
  const [customer, setCustomer] = useState<CustomerLookup | null>(null)

  const [bills, setBills] = useState<EligibleBill[]>([])
  const [selectedBill, setSelectedBill] = useState<EligibleBill | null>(null)
  const [selectedItem, setSelectedItem] = useState<EligibleItem | null>(null)

  const [imageConfirmed, setImageConfirmed] = useState(false)
  const [returnedCondition, setReturnedCondition] = useState('good')
  const [exchangeReason, setExchangeReason] = useState('')

  const [newBarcode, setNewBarcode] = useState('')
  const [newItemPreview, setNewItemPreview] = useState<any>(null)
  const [exchangeResult, setExchangeResult] = useState<ExchangeResult | null>(null)
  const [billHistory, setBillHistory] = useState<BillHistoryEvent[]>([])

  const newBarcodeRef = useRef<HTMLInputElement>(null)
  const clear = () => setError(null)

  // Step 1: phone lookup → /customers/lookup (staff accessible)
  const lookupCustomer = async () => {
    if (!phone.trim()) return
    setLoading(true); clear()
    try {
      const { data } = await api.get('/customers/lookup', { params: { phone: phone.trim() } })
      setCustomer(data)
      // Fetch eligible bills for this customer
      const { data: bills } = await api.get(`/customers/${data.customer_uid}/eligible-bills`)
      setBills(bills)
      setStep(2)
    } catch (e) {
      setError(apiErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  // Step 2 → 3: select bill and item
  const selectItem = (bill: EligibleBill, item: EligibleItem) => {
    setSelectedBill(bill)
    setSelectedItem(item)
    setImageConfirmed(false)
    setStep(3)
  }

  // Step 3 → 4: initiate exchange
  const initiateExchange = async () => {
    if (!selectedBill || !selectedItem || !customer) return
    if (!imageConfirmed) { setError('Confirm the physical item matches the stored photo before continuing.'); return }
    if (exchangeReason.trim().length < 3) { setError('Enter an exchange reason (at least 3 characters).'); return }
    setLoading(true); clear()
    try {
      const { data } = await api.post('/exchanges/initiate', {
        sale_ref: selectedBill.sale_ref,
        item_id: selectedItem.item_id,
        customer_uid: customer.customer_uid,
        exchange_reason: exchangeReason.trim(),
        returned_condition: returnedCondition,
        image_confirmed: imageConfirmed,
      })
      setExchangeResult(data)
      setStep(4)
      setTimeout(() => newBarcodeRef.current?.focus(), 100)
    } catch (e) {
      setError(apiErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  // Step 4: look up replacement item
  const lookupNewItem = async () => {
    if (!newBarcode.trim()) return
    setLoading(true); clear()
    try {
      const { data } = await api.get('/items/', { params: { barcode: newBarcode.trim(), limit: 1 } })
      if (!data.items?.length) { setError('Item not found'); setLoading(false); return }
      const item = data.items[0]
      if (item.status !== 'in_stock') { setError(`${item.barcode} is not in stock (${item.status})`); setLoading(false); return }
      setNewItemPreview(item)
    } catch (e) {
      setError(apiErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  // Step 4 → 5: complete exchange
  const completeExchange = async () => {
    if (!exchangeResult || !newItemPreview) return
    setLoading(true); clear()
    try {
      const { data } = await api.post(`/exchanges/${exchangeResult.exchange_ref}/complete`, {
        new_item_barcode: newItemPreview.barcode,
      })
      setExchangeResult(data)
      const { data: history } = await api.get(`/sales/${selectedBill!.sale_ref}/history`)
      setBillHistory(history)
      setStep(5)
    } catch (e) {
      setError(apiErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setStep(1); setPhone(''); setCustomer(null); setBills([])
    setSelectedBill(null); setSelectedItem(null); setImageConfirmed(false)
    setReturnedCondition('good'); setExchangeReason(''); setNewBarcode('')
    setNewItemPreview(null); setExchangeResult(null); setBillHistory([]); clear()
  }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '20px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <h2 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: t.text }}>Exchange</h2>
        {step > 1 && (
          <button onClick={reset} style={{ background: 'transparent', border: `1px solid ${t.border}`, color: t.textMuted, padding: '6px 14px', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>
            Start over
          </button>
        )}
      </div>

      <Steps current={step} />

      {error && (
        <div style={{ background: t.dangerDim, border: `1px solid ${t.danger}`, borderRadius: 8, padding: '10px 14px', color: t.danger, fontSize: 13, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          {error}
          <button onClick={clear} style={{ background: 'none', border: 'none', color: t.danger, cursor: 'pointer', fontSize: 18 }}>×</button>
        </div>
      )}

      {/* ── Step 1: Phone ── */}
      {step === 1 && (
        <Card title="Customer phone lookup">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={phone}
                onChange={e => setPhone(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && lookupCustomer()}
                placeholder="+91 98765 43210"
                type="tel"
                style={{ ...INPUT(t), flex: 1, fontFamily: t.mono }}
                autoFocus
              />
              <Btn onClick={lookupCustomer} disabled={!phone.trim() || loading}>
                {loading ? <Spinner size={14} /> : 'Look up'}
              </Btn>
            </div>
            <div style={{ fontSize: 12, color: t.textMuted }}>
              Enter the customer's phone number to see their purchase history.
            </div>
          </div>
        </Card>
      )}

      {/* ── Step 2: Bill + item selection ── */}
      {step === 2 && customer && (
        <Card title="Select the item to exchange">
          {/* Customer summary */}
          <div style={{ marginBottom: 14, padding: '10px 14px', background: t.surface2, borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: t.text }}>
                {customer.first_name} {customer.last_initial}.
              </div>
              <div style={{ fontSize: 12, color: t.textMuted }}>{customer.phone_masked} · {customer.total_purchases} purchases</div>
            </div>
          </div>

          {bills.length === 0 ? (
            <div style={{ color: t.textMuted, fontSize: 13, padding: '20px', textAlign: 'center', background: t.surface2, borderRadius: 8 }}>
              No exchange-eligible items found within the exchange window.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {bills.map(bill => (
                <div key={bill.sale_ref} style={{ border: `1px solid ${t.border}`, borderRadius: 10, overflow: 'hidden' }}>
                  {/* Bill header */}
                  <div style={{ padding: '10px 14px', background: t.surface2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <span style={{ fontFamily: t.mono, fontSize: 12, color: t.accent, fontWeight: 700 }}>{bill.receipt_number}</span>
                      <span style={{ fontSize: 11, color: t.textMuted, marginLeft: 10 }}>
                        {new Date(bill.created_at).toLocaleDateString('en-IN')} · {money(parseFloat(bill.total_amount))}
                      </span>
                    </div>
                    <span style={{
                      fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
                      background: bill.window_expires_in_days <= 5 ? t.warningDim : t.accentDim,
                      color: bill.window_expires_in_days <= 5 ? t.warning : t.accent,
                      border: `1px solid ${bill.window_expires_in_days <= 5 ? t.warning : t.accent}`,
                    }}>
                      {bill.window_expires_in_days} days left
                    </span>
                  </div>

                  {/* Eligible items */}
                  {bill.eligible_items.map(item => (
                    <button
                      key={item.item_id}
                      onClick={() => selectItem(bill, item)}
                      style={{
                        width: '100%', textAlign: 'left', background: 'transparent', border: 'none',
                        borderTop: `1px solid ${t.border}`, padding: '12px 14px', cursor: 'pointer',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        fontFamily: 'inherit',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = t.surface2)}
                      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                    >
                      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                        {item.image_thumb_url ? (
                          <img src={item.image_thumb_url} alt="" style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 6, border: `1px solid ${t.border}`, flexShrink: 0 }} />
                        ) : (
                          <div style={{ width: 40, height: 40, borderRadius: 6, border: `1px solid ${t.border}`, background: t.surface2, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, flexShrink: 0 }}>👕</div>
                        )}
                        <div>
                          <div style={{ fontWeight: 700, fontSize: 13, color: t.text }}>{(item.label || item.category).toUpperCase()}</div>
                          <div style={{ fontSize: 11, color: t.textMuted }}>{[item.color, item.size, item.condition].filter(Boolean).join(' · ')}</div>
                          <div style={{ fontSize: 10, color: t.textMuted, fontFamily: t.mono }}>{item.barcode}</div>
                        </div>
                      </div>
                      <div style={{ textAlign: 'right', flexShrink: 0 }}>
                        <div style={{ fontWeight: 700, fontSize: 14, color: t.text }}>{money(parseFloat(item.price))}</div>
                        {parseFloat(item.exchange_fee_paid) > 0 && (
                          <div style={{ fontSize: 10, color: t.warning }}>Fee paid: {money(parseFloat(item.exchange_fee_paid))}</div>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* ── Step 3: Confirm item identity ── */}
      {step === 3 && selectedItem && selectedBill && (
        <Card title="Confirm the item is the same">
          <div style={{ display: 'flex', gap: 16, marginBottom: 18, flexWrap: 'wrap' }}>
            {/* Image */}
            <div style={{ flexShrink: 0 }}>
              {selectedItem.image_url ? (
                <img src={selectedItem.image_url} alt="Original item" style={{ width: 140, height: 140, objectFit: 'cover', borderRadius: 10, border: `2px solid ${t.border}` }} />
              ) : (
                <div style={{ width: 140, height: 140, borderRadius: 10, border: `2px dashed ${t.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: t.textMuted, fontSize: 40, background: t.surface2 }}>👕</div>
              )}
              <div style={{ fontSize: 10, color: t.textMuted, textAlign: 'center', marginTop: 4 }}>Original intake photo</div>
            </div>

            <div style={{ flex: 1, minWidth: 180 }}>
              <div style={{ fontWeight: 700, fontSize: 15, color: t.text, marginBottom: 4 }}>
                {(selectedItem.label || selectedItem.category).toUpperCase()}
              </div>
              <div style={{ fontSize: 13, color: t.textMuted, marginBottom: 4 }}>
                {[selectedItem.color, selectedItem.size, selectedItem.condition].filter(Boolean).join(' · ')}
              </div>
              <div style={{ fontSize: 11, color: t.textMuted, fontFamily: t.mono, marginBottom: 14 }}>{selectedItem.barcode}</div>

              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', padding: '10px 12px', background: imageConfirmed ? t.successDim : t.surface2, border: `1px solid ${imageConfirmed ? t.success : t.border}`, borderRadius: 8 }}>
                <input type="checkbox" checked={imageConfirmed} onChange={e => setImageConfirmed(e.target.checked)} style={{ width: 16, height: 16 }} />
                <span style={{ fontSize: 13, fontWeight: 700, color: imageConfirmed ? t.success : t.text }}>
                  Physical item matches stored photo
                </span>
              </label>

              {!imageConfirmed && (
                <div style={{ fontSize: 11, color: t.warning, marginTop: 8 }}>
                  Compare the item in hand against the photo above before proceeding.
                </div>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <label style={{ fontSize: 11, fontWeight: 700, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }}>
                Condition of returned item
              </label>
              <select value={returnedCondition} onChange={e => setReturnedCondition(e.target.value)} style={{ ...INPUT(t), cursor: 'pointer' }}>
                {['excellent', 'good', 'fair', 'worn', 'damaged'].map(c => (
                  <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 700, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }}>
                Reason for exchange
              </label>
              <textarea
                value={exchangeReason}
                onChange={e => setExchangeReason(e.target.value)}
                placeholder="Wrong size, colour not as expected, etc."
                rows={2}
                style={{ ...INPUT(t), resize: 'vertical', minHeight: 60 }}
              />
            </div>
            <Btn onClick={initiateExchange} disabled={!imageConfirmed || exchangeReason.trim().length < 3 || loading}>
              {loading ? <><Spinner size={14} /> Processing…</> : 'Continue to new item →'}
            </Btn>
          </div>
        </Card>
      )}

      {/* ── Step 4: Scan replacement ── */}
      {step === 4 && exchangeResult && (
        <Card title="Scan or enter the replacement item">
          <div style={{ padding: '8px 12px', background: t.accentDim, borderRadius: 8, marginBottom: 16, fontFamily: t.mono, fontSize: 12, color: t.accent }}>
            {exchangeResult.exchange_ref} · pending
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
            <input
              ref={newBarcodeRef}
              value={newBarcode}
              onChange={e => setNewBarcode(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && lookupNewItem()}
              placeholder="Scan or type barcode…"
              style={{ ...INPUT(t), flex: 1, fontFamily: t.mono }}
            />
            <Btn onClick={lookupNewItem} disabled={!newBarcode.trim() || loading}>
              {loading ? <Spinner size={14} /> : 'Verify'}
            </Btn>
          </div>

          {newItemPreview && (
            <div style={{ border: `1px solid ${t.success}`, borderRadius: 8, padding: 12, marginBottom: 14, background: t.successDim }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: t.success, marginBottom: 4 }}>✓ In stock — confirmed</div>
              <div style={{ fontSize: 13, color: t.text }}>
                {(newItemPreview.label || newItemPreview.category).toUpperCase()} · {[newItemPreview.color, newItemPreview.size, newItemPreview.condition].filter(Boolean).join(' · ')}
              </div>
              <div style={{ fontSize: 11, color: t.textMuted, fontFamily: t.mono }}>{newItemPreview.barcode} · {money(parseFloat(newItemPreview.price))}</div>
            </div>
          )}

          <Btn onClick={completeExchange} disabled={!newItemPreview || loading}>
            {loading ? <><Spinner size={14} /> Completing…</> : 'Complete exchange'}
          </Btn>
        </Card>
      )}

      {/* ── Step 5: Done ── */}
      {step === 5 && exchangeResult && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Card>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{ width: 48, height: 48, borderRadius: '50%', background: t.successDim, border: `2px solid ${t.success}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke={t.success} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: t.text }}>Exchange complete</div>
                <div style={{ fontFamily: t.mono, fontSize: 13, color: t.accent }}>{exchangeResult.exchange_ref}</div>
              </div>
            </div>
          </Card>

          {billHistory.length > 0 && (
            <Card title="Bill history">
              <BillHistoryTimeline events={billHistory} />
            </Card>
          )}

          <Btn onClick={reset} variant="secondary">Process another exchange</Btn>
        </div>
      )}
    </div>
  )
}
