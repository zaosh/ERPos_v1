import { useState } from 'react'
import { useSummary, useTrends, useDeadStock, useCVPerformance } from '../hooks/useAnalytics'
import { useTheme } from '../styles/theme'
import { Badge, Card, Panel, SectionHeader, Spinner, StatCard, Empty } from '../components/ui'
import type { AnalyticsPeriod } from '../utils/constants'
import { ANALYTICS_PERIODS, DEAD_STOCK_DAYS_DEFAULT } from '../utils/constants'
import { money } from '../utils/currency'

const PERIODS = ANALYTICS_PERIODS

// Mini sparkline bar chart
function Sparkline({ data, color }: { data: Array<{ revenue: number }>; color: string }) {
  const max = Math.max(...data.map(d => d.revenue), 1)
  const W = 200, H = 48
  const barW = (W / data.length) - 2
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ overflow: 'visible' }}>
      {data.map((d, i) => {
        const h = Math.max(3, (d.revenue / max) * (H - 4))
        const x = i * (W / data.length) + 1
        return <rect key={i} x={x} y={H - h} width={barW} height={h} rx={2} fill={color} opacity={i === data.length - 1 ? 1 : 0.4} />
      })}
    </svg>
  )
}

// Today hero strip
function TodayStrip({ summary, trend }: { summary: any; trend: any[] | null }) {
  const t = useTheme()
  const today = trend ? trend[trend.length - 1] : null

  return (
    <div style={{ background: `linear-gradient(135deg, ${t.accentDim}, ${t.surface})`, border: `1px solid ${t.accent}44`, borderRadius: 14, padding: '20px 24px', display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
      <div style={{ flex: 1, minWidth: 160 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>Today's Revenue</div>
        <div style={{ fontSize: 36, fontWeight: 800, color: t.accent, letterSpacing: '-0.03em', lineHeight: 1 }}>
          {summary?.today_revenue != null ? money(summary.today_revenue) : today ? money(today.revenue) : '—'}
        </div>
        <div style={{ fontSize: 13, color: t.textMuted, marginTop: 4 }}>
          {today ? `${today.items ?? today.count ?? ''} items sold` : ''}
        </div>
      </div>
      {trend && (
        <div style={{ flex: 1, minWidth: 120 }}>
          <div style={{ fontSize: 11, color: t.textMuted, marginBottom: 6 }}>7-day trend</div>
          <Sparkline data={trend} color={t.accent} />
        </div>
      )}
      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
        {[
          ['In Stock', summary?.in_stock, t.success],
          ['Total Sold', summary?.sold, t.text],
          ['Avg Price', summary?.avg_price ? money(summary.avg_price) : '—', t.text],
        ].map(([label, val, color]) => (
          <div key={label as string} style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: color as string, letterSpacing: '-0.02em' }}>{val ?? '—'}</div>
            <div style={{ fontSize: 11, color: t.textMuted, marginTop: 2 }}>{label as string}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// Sales trend bar chart
function SalesTrendChart({ data }: { data: Array<{ date: string; revenue: number }> }) {
  const t = useTheme()
  const max = Math.max(...data.map(d => d.revenue), 1)
  const W = 400, H = 160, padLeft = 40, padBottom = 24
  const innerW = W - padLeft - 10
  const innerH = H - padBottom - 8
  const barW = Math.max(8, (innerW / data.length) - 4)

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ minWidth: 260 }}>
        {[0, 0.25, 0.5, 0.75, 1].map(pct => {
          const y = padBottom + (1 - pct) * innerH
          return (
            <g key={pct}>
              <line x1={padLeft} y1={y} x2={W - 10} y2={y} stroke={t.border} strokeDasharray="3 3" strokeWidth={0.5} />
              <text x={padLeft - 4} y={y + 4} textAnchor="end" fill={t.textMuted} fontSize={8} fontFamily="inherit">{Math.round(max * pct)}</text>
            </g>
          )
        })}
        {data.map((d, i) => {
          const h = Math.max(3, (d.revenue / max) * innerH)
          const x = padLeft + i * (innerW / data.length) + (innerW / data.length - barW) / 2
          const y = padBottom + innerH - h
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW} height={h} rx={3} fill={t.accent} opacity={i === data.length - 1 ? 0.95 : 0.4} />
              <text x={x + barW / 2} y={H - 6} textAnchor="middle" fill={t.textMuted} fontSize={8} fontFamily="inherit">{d.date}</text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

// Category heatmap
function CategoryHeatmap({ data }: { data: Array<{ label: string; sell_through_pct: number; count: number }> }) {
  const t = useTheme()
  if (!data?.length) return <Empty message="No category data" />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {data.map(row => {
        const pct = row.sell_through_pct / 100
        const barColor = pct >= 0.75 ? t.success : pct >= 0.5 ? t.warning : t.danger
        return (
          <div key={row.label} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 72, fontSize: 12, fontWeight: 600, color: t.text, flexShrink: 0, textTransform: 'capitalize' }}>{row.label}</div>
            <div style={{ flex: 1, height: 22, background: t.surface2, borderRadius: 6, overflow: 'hidden', position: 'relative' }}>
              <div style={{ width: `${row.sell_through_pct}%`, height: '100%', background: barColor, opacity: 0.7, borderRadius: 6, transition: 'width 0.6s cubic-bezier(0.34,1.56,0.64,1)' }} />
              <div style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', fontSize: 11, fontWeight: 600, color: t.text }}>{Math.round(row.sell_through_pct)}%</div>
            </div>
            <div style={{ width: 40, fontSize: 11, color: t.textMuted, textAlign: 'right', flexShrink: 0 }}>{row.count}</div>
          </div>
        )
      })}
      <div style={{ display: 'flex', gap: 12, marginTop: 4, justifyContent: 'flex-end' }}>
        {[['≥75%', t.success], ['≥50%', t.warning], ['<50%', t.danger]].map(([label, color]) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: t.textMuted }}>
            <div style={{ width: 8, height: 8, borderRadius: 2, background: color }} />
            {label}
          </div>
        ))}
      </div>
    </div>
  )
}

// Dead stock list
function DeadStockList({ items, days }: { items: any[]; days: number }) {
  const t = useTheme()
  if (!items?.length) return <Empty message={`No items unsold for ${days}+ days`} />
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {items.map((item: any, i: number) => (
        <div key={item.barcode || item.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: i < items.length - 1 ? `1px solid ${t.border}` : 'none' }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: t.dangerDim, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontSize: 16 }}>⚠</span>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: t.text }}>{item.label || item.category} · {item.color} · {item.size || '?'}</div>
            <div style={{ fontSize: 11, color: t.textMuted, fontFamily: t.mono }}>{item.barcode} · {money(item.price)}</div>
          </div>
          <div style={{ flexShrink: 0 }}>
            <Badge color="danger">{item.days_in_stock}d unsold</Badge>
          </div>
        </div>
      ))}
    </div>
  )
}

// Flatten trend data from real API format [{group_key, points:[{date,revenue}]}] to [{date, revenue}]
function flattenTrend(data: any): Array<{ date: string; revenue: number; items?: number; count?: number }> | null {
  if (!data) return null
  if (Array.isArray(data)) {
    // Real API: array of {group_key, points:[{date,revenue,count}]}
    if (data[0]?.points) {
      const allDates = [...new Set(data.flatMap((g: any) => g.points.map((p: any) => p.date)))].sort() as string[]
      return allDates.map(date => {
        const revenue = data.reduce((sum: number, g: any) => {
          const pt = g.points.find((p: any) => p.date === date)
          return sum + (pt?.revenue ?? 0)
        }, 0)
        const count = data.reduce((sum: number, g: any) => {
          const pt = g.points.find((p: any) => p.date === date)
          return sum + (pt?.count ?? 0)
        }, 0)
        return { date, revenue, count }
      })
    }
    // Already flat array [{date, revenue, items}]
    return data
  }
  // data.data field
  if (data.data) return flattenTrend(data.data)
  return null
}

// CV accuracy bar
function AccuracyBar({ label, accuracy, fixes }: { label: string; accuracy: number; fixes: number }) {
  const t = useTheme()
  const pct = Math.round(accuracy * 100)
  const barColor = pct >= 75 ? t.success : pct >= 50 ? t.warning : t.danger
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ width: 56, fontSize: 12, fontWeight: 600, color: t.text, flexShrink: 0 }}>{label}</div>
      <div style={{ flex: 1, height: 20, background: t.surface2, borderRadius: 6, overflow: 'hidden', position: 'relative' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: barColor, opacity: 0.75, borderRadius: 6, transition: 'width 0.6s cubic-bezier(0.34,1.56,0.64,1)' }} />
        <div style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', fontSize: 11, fontWeight: 600, color: t.text }}>{pct}%</div>
      </div>
      {fixes > 0 && <div style={{ flexShrink: 0, fontSize: 11, color: t.textMuted, width: 60, textAlign: 'right' }}>{fixes} fixes</div>}
    </div>
  )
}

// CV Performance panel
function CVPerformancePanel() {
  const t = useTheme()
  const { data, isLoading, isError } = useCVPerformance()

  if (isLoading) return <Panel title="CV Performance"><Spinner size={24} /></Panel>
  if (isError || !data) return <Panel title="CV Performance"><Empty message="No CV data yet" /></Panel>
  if (data.total_items_analyzed === 0) return (
    <Panel title="CV Performance" action={<span style={{ fontSize: 11, color: t.textMuted }}>starts collecting from next scan</span>}>
      <Empty message="No items with CV tracking yet" />
    </Panel>
  )

  const colorFixes = data.top_mistakes.filter((m: any) => m.field === 'color').reduce((s: number, m: any) => s + m.count, 0)
  const typeFixes = data.top_mistakes.filter((m: any) => m.field === 'type').reduce((s: number, m: any) => s + m.count, 0)

  return (
    <Panel
      title="CV Performance"
      action={<span style={{ fontSize: 11, color: t.textMuted }}>{data.total_items_analyzed} items analyzed</span>}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Accuracy bars */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <AccuracyBar label="Color" accuracy={data.color_accuracy} fixes={colorFixes} />
          <AccuracyBar label="Type" accuracy={data.type_accuracy} fixes={typeFixes} />
          <AccuracyBar label="Label" accuracy={data.label_accuracy} fixes={0} />
        </div>

        {/* Overall stat */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {[
            ['Overall', `${Math.round(data.overall_accuracy * 100)}%`, t.accent],
            ['Needs review', `${data.items_needing_review_pct.toFixed(1)}%`, t.warning],
          ].map(([label, val, color]) => (
            <div key={label as string} style={{ background: t.surface2, borderRadius: 8, padding: '8px 14px', textAlign: 'center', flex: 1 }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: color as string }}>{val as string}</div>
              <div style={{ fontSize: 11, color: t.textMuted, marginTop: 2 }}>{label as string}</div>
            </div>
          ))}
          {data.confidence_calibration.map((b: any) => (
            <div key={b.range} style={{ background: t.surface2, borderRadius: 8, padding: '8px 14px', textAlign: 'center', flex: 1 }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: b.accuracy >= 0.75 ? t.success : b.accuracy >= 0.5 ? t.warning : t.danger }}>{b.total > 0 ? `${Math.round(b.accuracy * 100)}%` : '—'}</div>
              <div style={{ fontSize: 10, color: t.textMuted, marginTop: 2 }}>{b.range}</div>
              <div style={{ fontSize: 10, color: t.textMuted }}>{b.total} items</div>
            </div>
          ))}
        </div>

        {/* Top mistakes table */}
        {data.top_mistakes.length > 0 && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Top Mistakes</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {data.top_mistakes.slice(0, 6).map((m: any, i: number) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderBottom: i < Math.min(data.top_mistakes.length, 6) - 1 ? `1px solid ${t.border}` : 'none' }}>
                  <Badge>{m.field}</Badge>
                  <span style={{ fontSize: 12, color: t.danger }}>{m.cv_suggested}</span>
                  <span style={{ fontSize: 11, color: t.textMuted }}>→</span>
                  <span style={{ fontSize: 12, color: t.success }}>{m.human_confirmed}</span>
                  <span style={{ marginLeft: 'auto', fontSize: 11, color: t.textMuted }}>{m.count}×</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Panel>
  )
}

export default function Analytics() {
  const t = useTheme()
  const [period, setPeriod] = useState<AnalyticsPeriod>('30d')
  const [deadDays, setDeadDays] = useState(DEAD_STOCK_DAYS_DEFAULT)

  const summary = useSummary(period)
  const trends = useTrends(period, 'label')
  const deadStock = useDeadStock(deadDays)

  const flatTrend = flattenTrend(trends.data)
  const topLabels: Array<{ label: string; sell_through_pct: number; count: number }> = summary.data?.top_labels ?? []

  const loading = summary.isLoading || trends.isLoading

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
        <SectionHeader>Analytics</SectionHeader>
        <div style={{ display: 'flex', background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 8, overflow: 'hidden' }}>
          {PERIODS.map(p => (
            <button key={p} onClick={() => setPeriod(p)} style={{
              padding: '6px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer', border: 'none',
              background: period === p ? t.accent : 'transparent',
              color: period === p ? t.bg : t.textMuted,
              transition: 'all 0.15s', fontFamily: 'inherit',
            }}>{p}</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spinner size={36} /></div>
      ) : (
        <>
          {/* Today strip */}
          <TodayStrip summary={summary.data} trend={flatTrend} />

          {/* Stat cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
            <StatCard label="Total Items" value={(summary.data?.total_items ?? 0).toLocaleString()} />
            <StatCard label="In Stock" value={(summary.data?.in_stock ?? 0).toLocaleString()} color={t.success} />
            <StatCard label={`Sold (${period})`} value={(summary.data?.sold ?? 0).toLocaleString()} />
            <StatCard label={`Revenue (${period})`} value={money(summary.data?.revenue ?? 0)} color={t.accent} sub={`avg ${money(summary.data?.avg_price ?? 0)}/item`} />
          </div>

          {/* Charts */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <Panel title="Sales Trend" action={<span style={{ fontSize: 11, color: t.textMuted }}>{period}</span>}>
              {flatTrend ? <SalesTrendChart data={flatTrend} /> : <Empty message="No trend data" />}
            </Panel>

            <Panel title="Label Sell-Through" action={<span style={{ fontSize: 11, color: t.textMuted }}>sold %</span>}>
              <CategoryHeatmap data={topLabels} />
            </Panel>
          </div>

          {/* Dead stock */}
          <Panel
            title="Dead Stock Alerts"
            action={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 11, color: t.textMuted }}>Unsold for</span>
                <select value={deadDays} onChange={e => setDeadDays(Number(e.target.value))}
                  style={{ background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 6, padding: '3px 8px', fontSize: 12, color: t.text, outline: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>
                  {[14, 21, 30, 45, 60].map(d => <option key={d} value={d}>{d} days</option>)}
                </select>
                {deadStock.data?.length > 0 && <Badge color="danger">{deadStock.data.length} items</Badge>}
              </div>
            }
          >
            {deadStock.isLoading ? <Spinner size={24} /> : <DeadStockList items={deadStock.data ?? []} days={deadDays} />}
          </Panel>

          {/* CV Performance */}
          <CVPerformancePanel />
        </>
      )}
    </div>
  )
}
