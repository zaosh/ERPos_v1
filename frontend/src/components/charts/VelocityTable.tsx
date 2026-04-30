interface VelocityRow {
  category: string
  condition: string
  avg_days_to_sell: number
  sample_size: number
}

interface Props {
  rows: VelocityRow[]
}

export default function VelocityTable({ rows }: Props) {
  if (!rows?.length) {
    return <p className="text-gray-400 text-sm text-center py-6">Not enough sales data yet.</p>
  }

  const sorted = [...rows].sort((a, b) => a.avg_days_to_sell - b.avg_days_to_sell)

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100">
            {['Category', 'Condition', 'Avg Days to Sell', 'Sample'].map((h) => (
              <th key={h} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {sorted.map((row, i) => (
            <tr key={i} className="hover:bg-gray-50 transition-colors">
              <td className="px-3 py-2 capitalize font-medium">{row.category}</td>
              <td className="px-3 py-2 capitalize">{row.condition}</td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <div
                    className="h-2 rounded-full bg-brand-500"
                    style={{ width: `${Math.min(100, row.avg_days_to_sell * 2)}px` }}
                  />
                  <span>{row.avg_days_to_sell.toFixed(1)}d</span>
                </div>
              </td>
              <td className="px-3 py-2 text-gray-400">{row.sample_size}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
