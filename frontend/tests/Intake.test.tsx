import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import CVResultCard from '../src/components/CVResultCard'
import type { ItemFormData } from '../src/components/CVResultCard'

const mockCvResult = {
  color: 'black',
  type: 'band',
  confidence: 0.82,
  needs_review: false,
}

const lowConfCvResult = {
  color: 'white',
  type: 'unknown',
  confidence: 0.31,
  needs_review: true,
}

const defaultForm: ItemFormData = {
  temp_image_id: 'abc-123',
  category: 'tshirt',
  color: 'black',
  secondary_color: '',
  type: 'band',
  label: '',
  size: '',
  condition: 'good',
  price: '',
  notes: '',
}

interface RenderCardProps {
  cvResult?: typeof mockCvResult
  form?: ItemFormData
  submitting?: boolean
  onSubmit?: () => void
  onReset?: () => void
  onChange?: (f: keyof ItemFormData, v: string) => void
}

function renderCard(overrides?: RenderCardProps) {
  const qc = new QueryClient()
  const props = {
    cvResult: mockCvResult,
    form: defaultForm,
    onChange: vi.fn(),
    onSubmit: vi.fn(),
    onReset: vi.fn(),
    submitting: false,
    ...overrides,
  }
  return render(
    <QueryClientProvider client={qc}>
      <CVResultCard {...props} />
    </QueryClientProvider>
  )
}

describe('CVResultCard', () => {
  it('displays confidence percentage', () => {
    renderCard()
    expect(screen.getByText(/82%/)).toBeInTheDocument()
  })

  it('does not show needs_review badge when confidence is high', () => {
    renderCard()
    expect(screen.queryByText(/Review needed/)).not.toBeInTheDocument()
  })

  it('shows needs_review badge when flagged', () => {
    renderCard({ cvResult: lowConfCvResult })
    expect(screen.getByText(/Review needed/)).toBeInTheDocument()
  })

  it('disables confirm button when price is empty', () => {
    renderCard({ form: { ...defaultForm, price: '' } })
    const btn = screen.getByText(/Confirm & Print/i)
    expect(btn).toBeDisabled()
  })

  it('enables confirm button when price is set', () => {
    renderCard({ form: { ...defaultForm, price: '5.00' } })
    const btn = screen.getByText(/Confirm & Print/i)
    expect(btn).not.toBeDisabled()
  })

  it('shows submitting state', () => {
    renderCard({ form: { ...defaultForm, price: '5.00' }, submitting: true })
    expect(screen.getByText(/Saving/)).toBeInTheDocument()
  })

  it('calls onReset when Retake is clicked', () => {
    const onReset = vi.fn()
    renderCard({ onReset })
    fireEvent.click(screen.getByText('Retake'))
    expect(onReset).toHaveBeenCalledOnce()
  })

  it('calls onSubmit when Confirm button is clicked', async () => {
    const onSubmit = vi.fn()
    renderCard({ form: { ...defaultForm, price: '8.00' }, onSubmit })
    fireEvent.click(screen.getByText(/Confirm & Print/i))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce())
  })
})
