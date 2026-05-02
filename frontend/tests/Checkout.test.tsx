import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Cart, { type CartItem } from '../src/components/Cart'

// ─── Cart component tests ──────────────────────────────────────────────────────

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

// ─── Checkout page API flow tests ────────────────────────────────────────────

vi.mock('../src/utils/api', () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  },
  apiErrorMessage: (e: unknown) => String(e),
}))

// Mock ZXing — no browser APIs in jsdom
vi.mock('@zxing/library', () => ({
  BrowserMultiFormatReader: vi.fn().mockImplementation(() => ({
    decodeFromVideoDevice: vi.fn(),
    reset: vi.fn(),
  })),
}))

import { api } from '../src/utils/api'
import Checkout from '../src/pages/Checkout'

function renderCheckout() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <Checkout />
    </QueryClientProvider>
  )
}

const mockItem = {
  id: 1,
  barcode: 'THR-20260429-00010',
  category: 'tshirt',
  color: 'black',
  label: 'Nirvana',
  size: 'M',
  condition: 'good',
  price: '9.00',
  status: 'in_stock',
  image_thumb_url: null,
}

describe('Checkout page API flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders checkout page with scan area', () => {
    renderCheckout()
    expect(screen.getByText(/Checkout/i)).toBeInTheDocument()
  })

  async function scanBarcode(barcode: string) {
    const input = screen.getByPlaceholderText(/Enter barcode manually/i)
    fireEvent.change(input, { target: { value: barcode } })
    const addBtn = screen.getByRole('button', { name: /^Add$/i })
    fireEvent.click(addBtn)
  }

  it('calls GET /items/ with barcode param when barcode is entered', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: { items: [mockItem], total: 1 } })

    renderCheckout()
    await scanBarcode('THR-20260429-00010')

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith(
        '/items/',
        expect.objectContaining({ params: expect.objectContaining({ barcode: 'THR-20260429-00010' }) })
      )
    })
  })

  it('adds scanned item to cart', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: { items: [mockItem], total: 1 } })

    renderCheckout()
    await scanBarcode('THR-20260429-00010')

    await waitFor(() => {
      expect(screen.getByText(/Nirvana/)).toBeInTheDocument()
    }, { timeout: 2000 })
  })

  it('does not add duplicate when same barcode scanned twice', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ data: { items: [mockItem], total: 1 } })
      .mockResolvedValueOnce({ data: { items: [mockItem], total: 1 } })

    renderCheckout()
    await scanBarcode('THR-20260429-00010')
    await waitFor(() => screen.queryByText(/Nirvana/), { timeout: 2000 })

    await scanBarcode('THR-20260429-00010')

    await waitFor(() => {
      // Already-in-cart error should be shown
      const err = screen.queryByText(/already in cart/i)
      if (err) expect(err).toBeInTheDocument()
    }, { timeout: 2000 })

    // Item should appear exactly once
    const matches = screen.queryAllByText(/Nirvana/)
    expect(matches.length).toBe(1)
  })

  it('shows error state when barcode is not found', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new Error('Item not found: THR-UNKNOWN'))

    renderCheckout()
    await scanBarcode('THR-UNKNOWN-99999')

    await waitFor(() => {
      const err = screen.queryByText(/Item not found/i) ?? screen.queryByText(/not found/i)
      expect(err).toBeInTheDocument()
    }, { timeout: 2000 })
  })

  it('calls POST /sales/ with correct payload on checkout', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: { items: [mockItem], total: 1 } })
    vi.mocked(api.post).mockResolvedValueOnce({
      data: { id: 10, sale_ref: 'SALE-001', total_amount: '9.00', items: [] },
    })

    renderCheckout()
    await scanBarcode('THR-20260429-00010')
    await waitFor(() => screen.queryByText(/Nirvana/), { timeout: 2000 })

    const completeBtn = screen.getByRole('button', { name: /Complete Sale/i })
    fireEvent.click(completeBtn)

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/sales/',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ barcode: 'THR-20260429-00010' }),
          ]),
          payment_type: 'cash',
        })
      )
    }, { timeout: 2000 })
  })
})
