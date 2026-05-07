import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { money } from '../../utils/currency'

interface TrendPoint {
  date: string
  count: number
  revenue: number
}

interface TrendGroup {
  group_key: string
  points: TrendPoint[]
}

interface Props {
  data: TrendGroup[]
  period: string
}

const COLORS = ['#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']

export default function SalesTrendChart({ data, period }: Props) {
  if (!data?.length) {
    return <div className="flex items-center justify-center h-48 text-gray-400 text-sm">No trend data</div>
  }

  const allDates = [...new Set(data.flatMap((g) => g.points.map((p) => p.date)))].sort()
  const chartData = allDates.map((date) => {
    const row: Record<string, string | number> = { date }
    data.forEach((g) => {
      const pt = g.points.find((p) => p.date === date)
      row[g.group_key] = pt ? pt.revenue : 0
    })
    return row
  })

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => money(v)} />
        <Tooltip formatter={(v: number) => [money(v), 'Revenue']} />
        <Legend />
        {data.map((g, i) => (
          <Line
            key={g.group_key}
            type="monotone"
            dataKey={g.group_key}
            stroke={COLORS[i % COLORS.length]}
            dot={false}
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
