import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface TopLabel {
  label: string
  count: number
  sell_through_pct: number
}

interface Props {
  data: TopLabel[]
}

export default function CategoryBreakdownChart({ data }: Props) {
  if (!data?.length) {
    return <div className="flex items-center justify-center h-48 text-gray-400 text-sm">No data</div>
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 40 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="label" tick={{ fontSize: 11 }} angle={-35} textAnchor="end" />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
        <Tooltip formatter={(v: number) => [`${v.toFixed(1)}%`, 'Sell-through']} />
        <Bar dataKey="sell_through_pct" radius={[4, 4, 0, 0]}>
          {data.map((entry, i) => (
            <Cell
              key={i}
              fill={entry.sell_through_pct >= 60 ? '#10b981' : entry.sell_through_pct >= 30 ? '#f59e0b' : '#ef4444'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
