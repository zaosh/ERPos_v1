import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../utils/api'
import { ITEM_CATEGORIES, ITEM_STATUSES, type ItemCategory, type ItemStatus } from '../utils/constants'

interface ItemRow {
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
  created_at: string
}

interface ItemList {
  items: ItemRow[]
  total: number
  limit: number
  offset: number
}

const PAGE_SIZE = 30

export default function Inventory() {
  const [category, setCategory] = useState<ItemCategory | ''>('')
  const [status, setStatus] = useState<ItemStatus | ''>('in_stock')
  const [label, setLabel] = useState('')
  const [page, setPage] = useState(0)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['inventory', category, status, label, page],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }
      if (category) params.category = category
      if (status) params.status = status
      if (label) params.label = label
      const { data } = await api.get<ItemList>('/items/', { params })
      return data
    },
    staleTime: 15_000,
  })

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      <h1 className="text-xl font-bold text-gray-800">Inventory</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 bg-white border border-gray-200 rounded-xl p-3">
        <select
          value={category}
          onChange={(e) => { setCategory(e.target.value as ItemCategory | ''); setPage(0) }}
          className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
        >
          <option value="">All categories</option>
          {ITEM_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>

        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value as ItemStatus | ''); setPage(0) }}
          className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
        >
          <option value="">All statuses</option>
          {ITEM_STATUSES.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
        </select>

        <input
          type="text"
          placeholder="Search label…"
          value={label}
          onChange={(e) => { setLabel(e.target.value); setPage(0) }}
          className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none w-44"
        />

        {data && (
          <span className="ml-auto self-center text-sm text-gray-500">
            {data.total.toLocaleString()} items
          </span>
        )}
      </div>

      {/* Table */}
      {isLoading && <p className="text-center text-gray-400 py-10">Loading…</p>}
      {isError && <p className="text-center text-red-600 py-10">Failed to load inventory.</p>}

      {data && (
        <>
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  {['Barcode', 'Category', 'Color', 'Label', 'Size', 'Cond.', 'Price', 'Status', 'Added'].map((h) => (
                    <th key={h} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {data.items.map((item) => (
                  <tr key={item.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-3 py-2 font-mono text-xs text-gray-600">{item.barcode}</td>
                    <td className="px-3 py-2 capitalize">{item.category}</td>
                    <td className="px-3 py-2">{item.color ?? '—'}</td>
                    <td className="px-3 py-2 max-w-[120px] truncate">{item.label ?? '—'}</td>
                    <td className="px-3 py-2">{item.size ?? '—'}</td>
                    <td className="px-3 py-2">{item.condition}</td>
                    <td className="px-3 py-2 font-medium">${parseFloat(item.price).toFixed(2)}</td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        item.status === 'in_stock' ? 'bg-green-100 text-green-700' :
                        item.status === 'sold' ? 'bg-gray-100 text-gray-600' :
                        'bg-yellow-100 text-yellow-700'
                      }`}>
                        {item.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-gray-400 text-xs">
                      {new Date(item.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {data.items.length === 0 && (
              <p className="text-center text-gray-400 py-10">No items found.</p>
            )}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1 border border-gray-300 rounded text-sm disabled:opacity-40 hover:bg-gray-50"
              >
                ← Prev
              </button>
              <span className="text-sm text-gray-600">Page {page + 1} of {totalPages}</span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-3 py-1 border border-gray-300 rounded text-sm disabled:opacity-40 hover:bg-gray-50"
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
