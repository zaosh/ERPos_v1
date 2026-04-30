import { useState, useCallback } from 'react'
import { useMutation } from '@tanstack/react-query'
import BarcodeScanner from '../components/BarcodeScanner'
import Cart, { type CartItem } from '../components/Cart'
import { api, apiErrorMessage } from '../utils/api'
import type { PaymentType } from '../utils/constants'

interface ItemLookup {
  id: number
  barcode: string
  category: string
  color: string | null
  label: string | null
  size: string | null
  condition: string
  price: string
  status: string
  image_thumb_url: string | null
}

interface SaleResult {
  id: number
  sale_ref: string
  total_amount: string
  items: Array<{ id: number; item_id: number; price: string }>
}

export default function Checkout() {
  const [scanning, setScanning] = useState(true)
  const [cart, setCart] = useState<CartItem[]>([])
  const [discount, setDiscount] = useState('')
  const [paymentType, setPaymentType] = useState<PaymentType>('cash')
  const [error, setError] = useState<string | null>(null)
  const [lastSale, setLastSale] = useState<SaleResult | null>(null)
  const [manualBarcode, setManualBarcode] = useState('')

  const lookupMutation = useMutation({
    mutationFn: async (barcode: string) => {
      const { data } = await api.get<{ items: ItemLookup[]; total: number }>('/items/', {
        params: { barcode, limit: 1 },
      })
      if (!data.items.length) throw new Error('Item not found: ' + barcode)
      return data.items[0]
    },
    onSuccess: (item) => {
      if (item.status !== 'in_stock') {
        setError(`${item.barcode} is not in stock (status: ${item.status})`)
        return
      }
      if (cart.some((c) => c.barcode === item.barcode)) {
        setError(`${item.barcode} already in cart`)
        return
      }
      setCart((prev) => [
        ...prev,
        {
          barcode: item.barcode,
          category: item.category,
          color: item.color,
          label: item.label,
          size: item.size,
          condition: item.condition,
          price: parseFloat(item.price),
        },
      ])
      setError(null)
      setScanning(true)
    },
    onError: (err) => setError(apiErrorMessage(err)),
  })

  const checkoutMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<SaleResult>('/sales/', {
        items: cart.map((c) => ({ barcode: c.barcode })),
        payment_type: paymentType,
        discount: parseFloat(discount) || 0,
      })
      return data
    },
    onSuccess: (data) => {
      setLastSale(data)
      setCart([])
      setDiscount('')
      setScanning(true)
      setError(null)
    },
    onError: (err) => setError(apiErrorMessage(err)),
  })

  const handleScan = useCallback(
    (barcode: string) => {
      setScanning(false)
      lookupMutation.mutate(barcode)
    },
    [lookupMutation]
  )

  const handleManualAdd = (e: React.FormEvent) => {
    e.preventDefault()
    if (manualBarcode.trim()) {
      handleScan(manualBarcode.trim())
      setManualBarcode('')
    }
  }

  const handleNewSale = () => {
    setLastSale(null)
    setScanning(true)
    setError(null)
  }

  if (lastSale) {
    return (
      <div className="max-w-md mx-auto text-center space-y-4 mt-10">
        <div className="text-5xl">🎉</div>
        <h2 className="text-xl font-bold text-green-800">Sale Complete!</h2>
        <div className="bg-green-50 border border-green-200 rounded-xl p-5 space-y-2 text-sm">
          <p><span className="font-medium">Sale Ref:</span> {lastSale.sale_ref}</p>
          <p><span className="font-medium">Total:</span> ${parseFloat(lastSale.total_amount).toFixed(2)}</p>
          <p><span className="font-medium">Items:</span> {lastSale.items.length}</p>
        </div>
        <button
          onClick={handleNewSale}
          className="w-full py-3 bg-brand-600 text-white rounded-lg font-semibold hover:bg-brand-700 transition-colors"
        >
          New Sale
        </button>
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-xl font-bold text-gray-800 mb-4">Checkout</h1>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" style={{ minHeight: '70vh' }}>
        <div className="space-y-3">
          <BarcodeScanner onScan={handleScan} active={scanning && !lookupMutation.isPending} />

          {lookupMutation.isPending && (
            <p className="text-center text-sm text-gray-500 animate-pulse">Looking up item…</p>
          )}

          <form onSubmit={handleManualAdd} className="flex gap-2">
            <input
              type="text"
              value={manualBarcode}
              onChange={(e) => setManualBarcode(e.target.value)}
              placeholder="Enter barcode manually"
              className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
            />
            <button
              type="submit"
              className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm font-medium hover:bg-gray-800 transition-colors"
            >
              Add
            </button>
          </form>

          <button
            onClick={() => setScanning((v) => !v)}
            className="w-full py-2 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50"
          >
            {scanning ? 'Pause Scanner' : 'Resume Scanner'}
          </button>
        </div>

        <Cart
          items={cart}
          discount={discount}
          paymentType={paymentType}
          onRemove={(barcode) => setCart((prev) => prev.filter((i) => i.barcode !== barcode))}
          onDiscountChange={setDiscount}
          onPaymentTypeChange={setPaymentType}
          onCheckout={() => checkoutMutation.mutate()}
          submitting={checkoutMutation.isPending}
        />
      </div>
    </div>
  )
}
