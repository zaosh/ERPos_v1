import { ITEM_CATEGORIES, ITEM_CONDITIONS, ITEM_TYPES, type ItemCategory, type ItemCondition, type ItemType } from '../utils/constants'

export interface ItemFormData {
  temp_image_id: string
  category: ItemCategory
  color: string
  secondary_color: string
  type: ItemType
  label: string
  size: string
  condition: ItemCondition
  price: string
  notes: string
}

interface CVResult {
  color: string | null
  type: string | null
  confidence: number
  needs_review: boolean
}

interface Props {
  cvResult: CVResult
  form: ItemFormData
  onChange: (field: keyof ItemFormData, value: string) => void
  onSubmit: () => void
  onReset: () => void
  submitting: boolean
}

const SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', 'One Size']

export default function CVResultCard({ cvResult, form, onChange, onSubmit, onReset, submitting }: Props) {
  const confidence = Math.round(cvResult.confidence * 100)
  const confidenceColor = confidence >= 70 ? 'text-green-600' : confidence >= 40 ? 'text-yellow-600' : 'text-red-600'

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-gray-800">CV Suggestions</h2>
        <div className="flex items-center gap-2 text-sm">
          <span className={`font-medium ${confidenceColor}`}>{confidence}% confidence</span>
          {cvResult.needs_review && (
            <span className="bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full text-xs font-medium">
              Review needed
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Category *</label>
          <select
            value={form.category}
            onChange={(e) => onChange('category', e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
          >
            {ITEM_CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Type *</label>
          <select
            value={form.type}
            onChange={(e) => onChange('type', e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
          >
            {ITEM_TYPES.map((t) => (
              <option key={t} value={t}>{t.replace('_', ' ')}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Color</label>
          <input
            type="text"
            value={form.color}
            onChange={(e) => onChange('color', e.target.value)}
            placeholder="e.g. black"
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Secondary Color</label>
          <input
            type="text"
            value={form.secondary_color}
            onChange={(e) => onChange('secondary_color', e.target.value)}
            placeholder="optional"
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Label / Brand</label>
          <input
            type="text"
            value={form.label}
            onChange={(e) => onChange('label', e.target.value)}
            placeholder="e.g. AC/DC, Nike, plain"
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Size</label>
          <select
            value={form.size}
            onChange={(e) => onChange('size', e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
          >
            <option value="">— select —</option>
            {SIZES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Condition *</label>
          <select
            value={form.condition}
            onChange={(e) => onChange('condition', e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
          >
            {ITEM_CONDITIONS.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Price ($) *</label>
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={form.price}
            onChange={(e) => onChange('price', e.target.value)}
            placeholder="5.00"
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
          />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
        <input
          type="text"
          value={form.notes}
          onChange={(e) => onChange('notes', e.target.value)}
          placeholder="optional"
          className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
        />
      </div>

      <div className="flex gap-2 pt-1">
        <button
          onClick={onReset}
          className="flex-1 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50 transition-colors text-sm"
        >
          Retake
        </button>
        <button
          onClick={onSubmit}
          disabled={submitting || !form.price}
          className="flex-2 flex-grow-[2] py-2 bg-green-600 text-white rounded-lg font-semibold hover:bg-green-700 disabled:opacity-50 transition-colors"
        >
          {submitting ? 'Saving…' : '✓ Confirm & Print'}
        </button>
      </div>
    </div>
  )
}
