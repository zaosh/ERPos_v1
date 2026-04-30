interface DeadStockItem {
  id: number
  barcode: string
  category: string
  color: string | null
  label: string | null
  size: string | null
  condition: string
  price: number
  days_in_stock: number
  image_thumb_url: string | null
}

interface Props {
  items: DeadStockItem[]
}

export default function DeadStockTable({ items }: Props) {
  if (!items?.length) {
    return <p className="text-green-600 text-sm text-center py-6">No dead stock — everything is moving!</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100">
            {['Barcode', 'Category', 'Color', 'Label', 'Size', 'Cond.', 'Price', 'Days'].map((h) => (
              <th key={h} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {items.map((item) => (
            <tr key={item.id} className="hover:bg-orange-50 transition-colors">
              <td className="px-3 py-2 font-mono text-xs">{item.barcode}</td>
              <td className="px-3 py-2 capitalize">{item.category}</td>
              <td className="px-3 py-2">{item.color ?? '—'}</td>
              <td className="px-3 py-2 max-w-[100px] truncate">{item.label ?? '—'}</td>
              <td className="px-3 py-2">{item.size ?? '—'}</td>
              <td className="px-3 py-2">{item.condition}</td>
              <td className="px-3 py-2 font-medium">${Number(item.price).toFixed(2)}</td>
              <td className="px-3 py-2">
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                  item.days_in_stock > 42 ? 'bg-red-100 text-red-700' : 'bg-orange-100 text-orange-700'
                }`}>
                  {item.days_in_stock}d
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
