import { useState } from 'react'
import { useSummary, useTrends, useDeadStock, useVelocity } from '../hooks/useAnalytics'
import SalesTrendChart from '../components/charts/SalesTrendChart'
import CategoryBreakdownChart from '../components/charts/CategoryBreakdownChart'
import DeadStockTable from '../components/charts/DeadStockTable'
import VelocityTable from '../components/charts/VelocityTable'
import type { AnalyticsPeriod } from '../utils/constants'
import { ANALYTICS_PERIODS, DEAD_STOCK_DAYS_DEFAULT } from '../utils/constants'

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-1">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-gray-800">{value}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>
  )
}

function Panel({ title, children, className = '' }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white border border-gray-200 rounded-xl p-4 space-y-3 ${className}`}>
      <h3 className="font-semibold text-gray-700">{title}</h3>
      {children}
    </div>
  )
}

export default function Analytics() {
  const [period, setPeriod] = useState<AnalyticsPeriod>('30d')
  const [trendGroup, setTrendGroup] = useState('label')
  const [deadDays, setDeadDays] = useState(DEAD_STOCK_DAYS_DEFAULT)

  const summary = useSummary(period)
  const trends = useTrends(period, trendGroup)
  const deadStock = useDeadStock(deadDays)
  const velocity = useVelocity()

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-800">Analytics Dashboard</h1>
        <div className="flex gap-1">
          {ANALYTICS_PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${
                period === p ? 'bg-brand-600 text-white' : 'border border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Summary cards */}
      {summary.data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Total Items" value={summary.data.total_items.toLocaleString()} />
          <StatCard label="In Stock" value={summary.data.in_stock.toLocaleString()} />
          <StatCard label="Sold" value={summary.data.sold.toLocaleString()} sub={period} />
          <StatCard
            label="Revenue"
            value={`$${parseFloat(summary.data.revenue).toFixed(2)}`}
            sub={`avg $${parseFloat(summary.data.avg_price).toFixed(2)}/item`}
          />
        </div>
      )}
      {summary.isLoading && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[0,1,2,3].map((i) => (
            <div key={i} className="bg-gray-100 animate-pulse rounded-xl h-20" />
          ))}
        </div>
      )}

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Sales Trend">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs text-gray-500">Group by:</span>
            {['label', 'color', 'category'].map((g) => (
              <button
                key={g}
                onClick={() => setTrendGroup(g)}
                className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                  trendGroup === g ? 'bg-brand-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {g}
              </button>
            ))}
          </div>
          {trends.isLoading && <div className="h-48 bg-gray-50 animate-pulse rounded-lg" />}
          {trends.data && <SalesTrendChart data={trends.data.data} period={period} />}
        </Panel>

        <Panel title="Label Sell-Through %">
          {summary.isLoading && <div className="h-48 bg-gray-50 animate-pulse rounded-lg" />}
          {summary.data && <CategoryBreakdownChart data={summary.data.top_labels} />}
        </Panel>
      </div>

      {/* Dead stock & velocity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Dead Stock">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs text-gray-500">Unsold for</span>
            <select
              value={deadDays}
              onChange={(e) => setDeadDays(Number(e.target.value))}
              className="border border-gray-300 rounded px-2 py-0.5 text-xs"
            >
              {[14, 21, 30, 45, 60].map((d) => (
                <option key={d} value={d}>{d} days</option>
              ))}
            </select>
          </div>
          {deadStock.isLoading && <div className="h-40 bg-gray-50 animate-pulse rounded-lg" />}
          {deadStock.data && <DeadStockTable items={deadStock.data} />}
        </Panel>

        <Panel title="Sales Velocity">
          {velocity.isLoading && <div className="h-40 bg-gray-50 animate-pulse rounded-lg" />}
          {velocity.data && <VelocityTable rows={velocity.data} />}
        </Panel>
      </div>
    </div>
  )
}
