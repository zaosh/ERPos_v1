import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Cart, { type CartItem } from '../src/components/Cart'

const sampleItems: CartItem[] = [
  { barcode: 'THR-20260429-00001', category: 'tshirt', color: 'black', label: 'AC/DC', size: 'L', condition: 'good', price: 8.00 },
  { barcode: 'THR-20260429-00002', category: 'pants', color: 'blue', label: null, size: '32', condition: 'excellent', price: 12.00 },
]

function renderCart(items: CartItem[] = sampleItems, overrides: Partial<React.ComponentProps<typeof Cart>> = {}) {
  const qc = new QueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <Cart
        items={items}
        discount=""
        paymentType="cash"
        onRemove={vi.fn()}
        onDiscountChange={vi.fn()}
        onPaymentTypeChange={vi.fn()}
        onCheckout={vi.fn()}
        submitting={false}
        {...overrides}
      />
    </QueryClientProvider>
  )
}

describe('Cart', () => {
  it('shows cart item count in heading', () => {
    renderCart()
    expect(screen.getByText('Cart (2)')).toBeInTheDocument()
  })

  it('calculates correct subtotal', () => {
    renderCart()
    expect(screen.getByText('$20.00')).toBeInTheDocument()
  })

  it('shows empty state message when no items', () => {
    renderCart([])
    expect(screen.getByText(/Scan items to add/)).toBeInTheDocument()
  })

  it('disables checkout button when cart is empty', () => {
    renderCart([])
    const btn = screen.getByRole('button', { name: /Complete Sale/i })
    expect(btn).toBeDisabled()
  })

  it('enables checkout when cart has items', () => {
    renderCart()
    const btn = screen.getByRole('button', { name: /Complete Sale/i })
    expect(btn).not.toBeDisabled()
  })

  it('calls onRemove when remove button clicked', () => {
    const onRemove = vi.fn()
    renderCart(sampleItems, { onRemove })
    const removeBtns = screen.getAllByTitle('Remove')
    fireEvent.click(removeBtns[0])
    expect(onRemove).toHaveBeenCalledWith('THR-20260429-00001')
  })

  it('shows discount line when discount is set', () => {
    renderCart(sampleItems, { discount: '3.00' })
    expect(screen.getByText('-$3.00')).toBeInTheDocument()
    expect(screen.getByText('$17.00')).toBeInTheDocument()
  })

  it('shows processing state', () => {
    renderCart(sampleItems, { submitting: true })
    expect(screen.getByText(/Processing/)).toBeInTheDocument()
  })

  it('calls onCheckout when button clicked', () => {
    const onCheckout = vi.fn()
    renderCart(sampleItems, { onCheckout })
    fireEvent.click(screen.getByRole('button', { name: /Complete Sale/i }))
    expect(onCheckout).toHaveBeenCalledOnce()
  })
})
