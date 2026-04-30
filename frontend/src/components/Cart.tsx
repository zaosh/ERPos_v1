import type { PaymentType } from '../utils/constants'
import { PAYMENT_TYPES } from '../utils/constants'

export interface CartItem {
  barcode: string
  category: string
  color: string | null
  label: string | null
  size: string | null
  condition: string
  price: number
}

interface Props {
  items: CartItem[]
  discount: string
  paymentType: PaymentType
  onRemove: (barcode: string) => void
  onDiscountChange: (val: string) => void
  onPaymentTypeChange: (val: PaymentType) => void
  onCheckout: () => void
  submitting: boolean
}

export default function Cart({
  items,
  discount,
  paymentType,
  onRemove,
  onDiscountChange,
  onPaymentTypeChange,
  onCheckout,
  submitting,
}: Props) {
  const subtotal = items.reduce((sum, i) => sum + i.price, 0)
  const discountAmt = parseFloat(discount) || 0
  const total = Math.max(0, subtotal - discountAmt)

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm flex flex-col h-full">
      <div className="p-4 border-b border-gray-100">
        <h2 className="font-semibold text-gray-800">Cart ({items.length})</h2>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {items.length === 0 && (
          <p className="text-gray-400 text-sm text-center py-8">Scan items to add them</p>
        )}
        {items.map((item) => (
          <div key={item.barcode} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-800 truncate">
                {item.label ?? item.category} · {item.color ?? '—'} · {item.size ?? '?'}
              </p>
              <p className="text-xs text-gray-500">{item.barcode} · {item.condition}</p>
            </div>
            <div className="flex items-center gap-2 ml-2">
              <span className="text-sm font-semibold text-gray-700">${item.price.toFixed(2)}</span>
              <button
                onClick={() => onRemove(item.barcode)}
                className="text-red-400 hover:text-red-600 text-xs"
                title="Remove"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="p-4 border-t border-gray-100 space-y-3">
        <div className="flex gap-2">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">Discount ($)</label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={discount}
              onChange={(e) => onDiscountChange(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">Payment</label>
            <select
              value={paymentType}
              onChange={(e) => onPaymentTypeChange(e.target.value as PaymentType)}
              className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
            >
              {PAYMENT_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="text-sm space-y-1">
          <div className="flex justify-between text-gray-500">
            <span>Subtotal</span>
            <span>${subtotal.toFixed(2)}</span>
          </div>
          {discountAmt > 0 && (
            <div className="flex justify-between text-red-500">
              <span>Discount</span>
              <span>-${discountAmt.toFixed(2)}</span>
            </div>
          )}
          <div className="flex justify-between font-bold text-gray-800 text-base border-t border-gray-200 pt-1">
            <span>Total</span>
            <span>${total.toFixed(2)}</span>
          </div>
        </div>

        <button
          onClick={onCheckout}
          disabled={submitting || items.length === 0}
          className="w-full py-3 bg-green-600 text-white rounded-lg font-bold text-lg hover:bg-green-700 disabled:opacity-40 transition-colors"
        >
          {submitting ? 'Processing…' : `Complete Sale · $${total.toFixed(2)}`}
        </button>
      </div>
    </div>
  )
}
