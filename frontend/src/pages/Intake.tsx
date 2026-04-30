import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import Camera from '../components/Camera'
import CVResultCard, { type ItemFormData } from '../components/CVResultCard'
import { api, apiErrorMessage } from '../utils/api'

type Stage = 'camera' | 'confirm' | 'success'

interface CaptureResult {
  cv_result: {
    color: string | null
    type: string | null
    confidence: number
    needs_review: boolean
  }
  temp_image_id: string
}

interface CreateResult {
  id: number
  barcode: string
  label_printed: boolean
  category: string
  color: string | null
  size: string | null
  price: string
}

const DEFAULT_FORM: Omit<ItemFormData, 'temp_image_id'> = {
  category: 'tshirt',
  color: '',
  secondary_color: '',
  type: 'unknown',
  label: '',
  size: '',
  condition: 'good',
  price: '',
  notes: '',
}

export default function Intake() {
  const [stage, setStage] = useState<Stage>('camera')
  const [captureResult, setCaptureResult] = useState<CaptureResult | null>(null)
  const [form, setForm] = useState<ItemFormData>({ ...DEFAULT_FORM, temp_image_id: '' })
  const [lastItem, setLastItem] = useState<CreateResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const captureMutation = useMutation({
    mutationFn: async (blob: Blob) => {
      const fd = new FormData()
      fd.append('image', blob, 'capture.jpg')
      const { data } = await api.post<CaptureResult>('/items/capture', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return data
    },
    onSuccess: (data) => {
      setCaptureResult(data)
      setForm({
        temp_image_id: data.temp_image_id,
        category: 'tshirt',
        color: data.cv_result.color ?? '',
        secondary_color: '',
        type: (data.cv_result.type as ItemFormData['type']) ?? 'unknown',
        label: '',
        size: '',
        condition: 'good',
        price: '',
        notes: '',
      })
      setStage('confirm')
      setError(null)
    },
    onError: (err) => setError(apiErrorMessage(err)),
  })

  const createMutation = useMutation({
    mutationFn: async (formData: ItemFormData) => {
      const { data } = await api.post<CreateResult>('/items/', {
        temp_image_id: formData.temp_image_id,
        category: formData.category,
        color: formData.color || null,
        secondary_color: formData.secondary_color || null,
        type: formData.type,
        label: formData.label || null,
        size: formData.size || null,
        condition: formData.condition,
        price: parseFloat(formData.price),
        notes: formData.notes || null,
      })
      return data
    },
    onSuccess: (data) => {
      setLastItem(data)
      setStage('success')
      setError(null)
    },
    onError: (err) => setError(apiErrorMessage(err)),
  })

  const handleCapture = (blob: Blob) => {
    setError(null)
    captureMutation.mutate(blob)
  }

  const handleFieldChange = (field: keyof ItemFormData, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  const handleReset = () => {
    setStage('camera')
    setCaptureResult(null)
    setError(null)
  }

  const handleNext = () => {
    setStage('camera')
    setCaptureResult(null)
    setLastItem(null)
    setForm({ ...DEFAULT_FORM, temp_image_id: '' })
    setError(null)
  }

  return (
    <div className="max-w-xl mx-auto space-y-4">
      <h1 className="text-xl font-bold text-gray-800">Item Intake</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {stage === 'camera' && (
        <div className="space-y-3">
          <Camera onCapture={handleCapture} disabled={captureMutation.isPending} />
          {captureMutation.isPending && (
            <p className="text-center text-sm text-gray-500 animate-pulse">
              Analyzing image…
            </p>
          )}
        </div>
      )}

      {stage === 'confirm' && captureResult && (
        <CVResultCard
          cvResult={captureResult.cv_result}
          form={form}
          onChange={handleFieldChange}
          onSubmit={() => createMutation.mutate(form)}
          onReset={handleReset}
          submitting={createMutation.isPending}
        />
      )}

      {stage === 'success' && lastItem && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center space-y-3">
          <div className="text-4xl">✅</div>
          <h2 className="text-lg font-bold text-green-800">Item Saved!</h2>
          <div className="text-sm text-green-700 space-y-1">
            <p><span className="font-medium">Barcode:</span> {lastItem.barcode}</p>
            <p><span className="font-medium">Price:</span> ${lastItem.price}</p>
            <p>
              <span className="font-medium">Label:</span>{' '}
              {lastItem.label_printed ? '🖨️ Printed' : '⏳ Queued for printing'}
            </p>
          </div>
          <button
            onClick={handleNext}
            className="mt-2 w-full py-3 bg-brand-600 text-white rounded-lg font-semibold hover:bg-brand-700 transition-colors"
          >
            Next Item →
          </button>
        </div>
      )}
    </div>
  )
}
