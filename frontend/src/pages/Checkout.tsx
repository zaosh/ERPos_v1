import { useState, useCallback, useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { BrowserMultiFormatReader } from '@zxing/library'
import { api, apiErrorMessage } from '../utils/api'
import { useTheme } from '../styles/theme'
import { Badge, Btn, Card, ErrorAlert, SectionHeader, Select, Spinner, Empty } from '../components/ui'
import type { PaymentType } from '../utils/constants'

interface ItemLookup {
  id: number; barcode: string; category: string; color: string | null
  label: string | null; size: string | null; condition: string
  price: string; status: string; image_thumb_url: string | null
}

interface CartItem {
  barcode: string; category: string; color: string | null
  label: string | null; size: string | null; condition: string; price: number
}

interface SaleResult {
  id: number; sale_ref: string; total_amount: string
  items: Array<{ id: number; item_id: number; price: string }>
}

const PAYMENT_OPTS: Array<{ value: PaymentType; label: string }> = [
  { value: 'cash', label: 'Cash' },
  { value: 'card', label: 'Card' },
  { value: 'other', label: 'Other' },
]

// Scanner panel
function ScannerPanel({ onScan, looking }: { onScan: (b: string) => void; looking: boolean }) {
  const t = useTheme()
  const [manual, setManual] = useState('')
  const [scanAnim, setScanAnim] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const readerRef = useRef<BrowserMultiFormatReader | null>(null)

  const doScan = useCallback((code: string) => {
    if (!code.trim()) return
    setScanAnim(true)
    setTimeout(() => setScanAnim(false), 600)
    onScan(code.trim())
  }, [onScan])

  useEffect(() => {
    const reader = new BrowserMultiFormatReader()
    readerRef.current = reader
    reader.decodeFromVideoDevice(undefined, videoRef.current!, (result, err) => {
      if (result) {
        onScan(result.getText())
        reader.reset()
      }
      if (err && !(err.message?.includes('No MultiFormat'))) { /* suppress */ }
    }).catch(() => {})
    return () => { reader.reset() }
  }, [onScan])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{
        position: 'relative', width: '100%', aspectRatio: '16/7',
        background: '#000', borderRadius: 14,
        border: `2px solid ${t.border}`,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        overflow: 'hidden',
      }}>
        {/* Live camera */}
        <video ref={videoRef} muted style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />

        {/* Scan success flash */}
        {scanAnim && (
          <div style={{ position: 'absolute', inset: 0, background: `${t.accent}22`, animation: 'fadeIn 0.3s ease', zIndex: 2, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width={40} height={40} viewBox="0 0 24 24" fill="none" stroke={t.accent} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
        )}

        {/* Scan line */}
        {!looking && (
          <div style={{ position: 'absolute', left: '10%', right: '10%', height: 2, background: `linear-gradient(90deg, transparent, ${t.accent}, transparent)`, animation: 'scanline 1.5s linear infinite', opacity: 0.7, zIndex: 1 }} />
        )}

        {/* Center guide */}
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1, pointerEvents: 'none' }}>
          <div style={{ width: 200, height: 60, border: `2px solid ${t.accent}`, borderRadius: 8, opacity: 0.5 }} />
        </div>

        {looking && (
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 3, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
            <Spinner size={28} />
            <span style={{ color: t.accent, fontSize: 12 }}>Looking up item…</span>
          </div>
        )}
      </div>

      {/* Manual entry */}
      <form onSubmit={e => { e.preventDefault(); doScan(manual); setManual('') }} style={{ display: 'flex', gap: 8 }}>
        <input
          value={manual}
          onChange={e => setManual(e.target.value)}
          placeholder="Enter barcode manually…"
          style={{ flex: 1, background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 8, padding: '9px 12px', color: t.text, fontSize: 14, outline: 'none', fontFamily: t.mono }}
        />
        <Btn type="submit" variant="secondary" disabled={!manual.trim()}>Add</Btn>
      </form>
    </div>
  )
}

// Cart panel
function CartPanel({ items, discount, setDiscount, paymentType, setPaymentType, onCheckout, submitting, onRemove }: {
  items: CartItem[]; discount: string; setDiscount: (v: string) => void
  paymentType: PaymentType; setPaymentType: (v: PaymentType) => void
  onCheckout: () => void; submitting: boolean; onRemove: (b: string) => void
}) {
  const t = useTheme()
  const subtotal = items.reduce((s, i) => s + i.price, 0)
  const discountAmt = parseFloat(discount) || 0
  const total = Math.max(0, subtotal - discountAmt)
  const quickAmounts = [...new Set([Math.ceil(total), Math.ceil(total / 5) * 5, Math.ceil(total / 10) * 10])].filter(v => v >= total).slice(0, 3)

  return (
    <Card style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '16px 18px', borderBottom: `1px solid ${t.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontWeight: 700, fontSize: 15, color: t.text }}>Cart</span>
        <Badge color={items.length > 0 ? 'accent' : 'default'}>{items.length} item{items.length !== 1 ? 's' : ''}</Badge>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0 18px', minHeight: 120 }}>
        {items.length === 0 ? (
          <Empty message="Scan items to add them to the cart" />
        ) : (
          items.map(i => (
            <div key={i.barcode} className="fade-in" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0', borderBottom: `1px solid ${t.border}` }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: t.surface3, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span style={{ fontSize: 9, color: t.textDim, textTransform: 'uppercase' }}>{i.category?.slice(0, 3)}</span>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: t.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {i.label || i.category}{i.color ? ` · ${i.color}` : ''}{i.size ? ` · ${i.size}` : ''}
                </div>
                <div style={{ fontSize: 11, color: t.textMuted, fontFamily: t.mono }}>{i.barcode}</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 700, fontSize: 15, color: t.text }}>${i.price.toFixed(2)}</span>
                <button onClick={() => onRemove(i.barcode)} style={{ background: 'none', border: 'none', color: t.textDim, cursor: 'pointer', fontSize: 18, lineHeight: 1, padding: 2 }}>×</button>
              </div>
            </div>
          ))
        )}
      </div>

      <div style={{ padding: '14px 18px', borderTop: `1px solid ${t.border}`, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Discount ($)</label>
            <input type="number" min="0" step="0.01" value={discount} onChange={e => setDiscount(e.target.value)}
              style={{ background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 8, padding: '7px 10px', color: t.text, fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
          </div>
          <Select label="Payment" value={paymentType} onChange={setPaymentType} options={PAYMENT_OPTS} />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: t.textMuted }}>
            <span>Subtotal</span><span>${subtotal.toFixed(2)}</span>
          </div>
          {discountAmt > 0 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: t.danger }}>
              <span>Discount</span><span>−${discountAmt.toFixed(2)}</span>
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 20, fontWeight: 800, borderTop: `1px solid ${t.border}`, paddingTop: 8, marginTop: 4 }}>
            <span style={{ color: t.text }}>Total</span>
            <span style={{ color: t.accent }}>${total.toFixed(2)}</span>
          </div>
        </div>

        {paymentType === 'cash' && items.length > 0 && quickAmounts.length > 0 && (
          <div style={{ display: 'flex', gap: 6 }}>
            <span style={{ fontSize: 11, color: t.textDim, alignSelf: 'center' }}>Quick:</span>
            {quickAmounts.map(amt => (
              <button key={amt} style={{ background: t.surface3, border: `1px solid ${t.border}`, borderRadius: 6, padding: '3px 10px', fontSize: 12, color: t.textMuted, cursor: 'pointer', fontFamily: 'inherit' }}>
                ${amt}
              </button>
            ))}
          </div>
        )}

        <Btn variant="primary" onClick={onCheckout} disabled={submitting || items.length === 0} full size="lg">
          {submitting ? 'Processing…' : `Complete Sale · $${total.toFixed(2)}`}
        </Btn>
      </div>
    </Card>
  )
}

// Sale success screen
function SaleSuccess({ sale, onNew }: { sale: SaleResult; onNew: () => void }) {
  const t = useTheme()
  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24, padding: '60px 20px', maxWidth: 400, margin: '0 auto' }}>
      <div style={{ width: 72, height: 72, borderRadius: '50%', background: t.successDim, border: `2px solid ${t.success}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width={32} height={32} viewBox="0 0 24 24" fill="none" stroke={t.success} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: t.text }}>Sale Complete</div>
        <div style={{ color: t.textMuted, fontSize: 14, marginTop: 4 }}>Receipt ready to print</div>
      </div>
      <div style={{ width: '100%', background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 12, padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {[
          ['Sale Ref', sale.sale_ref, t.accent, true],
          ['Total', `$${parseFloat(sale.total_amount).toFixed(2)}`, t.text, false],
          ['Items', String(sale.items.length), t.text, false],
        ].map(([label, val, color, mono]) => (
          <div key={label as string} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
            <span style={{ color: t.textMuted }}>{label as string}</span>
            <span style={{ color: color as string, fontWeight: 600, fontFamily: mono ? t.mono : 'inherit' }}>{val as string}</span>
          </div>
        ))}
      </div>
      <Btn variant="primary" onClick={onNew} full size="lg">New Sale</Btn>
    </div>
  )
}

export default function Checkout() {
  const t = useTheme()
  const [cart, setCart] = useState<CartItem[]>([])
  const [discount, setDiscount] = useState('')
  const [paymentType, setPaymentType] = useState<PaymentType>('cash')
  const [error, setError] = useState<string | null>(null)
  const [lastSale, setLastSale] = useState<SaleResult | null>(null)

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
      setCart(prev => [...prev, {
        barcode: item.barcode, category: item.category, color: item.color,
        label: item.label, size: item.size, condition: item.condition,
        price: parseFloat(item.price),
      }])
      setError(null)
    },
    onError: (err) => setError(apiErrorMessage(err)),
  })

  const checkoutMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<SaleResult>('/sales/', {
        items: cart.map(c => ({ barcode: c.barcode })),
        payment_type: paymentType,
        discount: parseFloat(discount) || 0,
      })
      return data
    },
    onSuccess: (data) => { setLastSale(data); setCart([]); setDiscount(''); setError(null) },
    onError: (err) => setError(apiErrorMessage(err)),
  })

  const handleScan = useCallback((barcode: string) => {
    setError(null)
    lookupMutation.mutate(barcode)
  }, [lookupMutation])

  if (lastSale) return <SaleSuccess sale={lastSale} onNew={() => setLastSale(null)} />

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionHeader>Checkout</SectionHeader>
      <ErrorAlert message={error} onDismiss={() => setError(null)} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, minHeight: '68vh' }}>
        <ScannerPanel onScan={handleScan} looking={lookupMutation.isPending} />
        <CartPanel
          items={cart} discount={discount} setDiscount={setDiscount}
          paymentType={paymentType} setPaymentType={setPaymentType}
          onCheckout={() => checkoutMutation.mutate()}
          submitting={checkoutMutation.isPending}
          onRemove={b => setCart(p => p.filter(i => i.barcode !== b))}
        />
      </div>
    </div>
  )
}
