import { useTheme } from '../styles/theme'

export interface BillHistoryEvent {
  id: number
  sale_id: number
  event_type:
    | 'purchase'
    | 'exchange_initiated'
    | 'exchange_completed'
    | 'return_initiated'
    | 'return_completed'
    | 'item_added'
  item_id: number | null
  exchange_id: number | null
  return_id: number | null
  description: string
  created_by: number
  created_at: string
}

const EVENT_META: Record<
  BillHistoryEvent['event_type'],
  { label: string; color: string; icon: string }
> = {
  purchase:            { label: 'Purchase',           color: '#00e5a0', icon: '🛍' },
  exchange_initiated:  { label: 'Exchange Initiated', color: '#f59e0b', icon: '↕' },
  exchange_completed:  { label: 'Exchange Completed', color: '#f59e0b', icon: '✓↕' },
  return_initiated:    { label: 'Return Initiated',   color: '#60a5fa', icon: '↩' },
  return_completed:    { label: 'Return Completed',   color: '#60a5fa', icon: '✓↩' },
  item_added:          { label: 'Item Added',          color: '#9ca3af', icon: '+' },
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export function BillHistoryTimeline({ events }: { events: BillHistoryEvent[] }) {
  const t = useTheme()

  if (!events || events.length === 0) {
    return (
      <div style={{ color: t.textMuted, fontSize: 13, padding: '12px 0', textAlign: 'center' }}>
        No history recorded for this sale.
      </div>
    )
  }

  return (
    <div style={{ position: 'relative', padding: '4px 0' }}>
      {/* Vertical line */}
      <div style={{
        position: 'absolute', left: 16, top: 8, bottom: 8,
        width: 2, background: t.border,
      }} />

      {events.map((event, idx) => {
        const meta = EVENT_META[event.event_type] ?? { label: event.event_type, color: t.textMuted, icon: '•' }
        return (
          <div key={event.id} style={{
            display: 'flex', gap: 16, paddingBottom: idx < events.length - 1 ? 20 : 0,
            position: 'relative',
          }}>
            {/* Dot */}
            <div style={{
              width: 34, flexShrink: 0, display: 'flex', justifyContent: 'center',
              paddingTop: 2,
            }}>
              <div style={{
                width: 24, height: 24, borderRadius: '50%',
                background: t.bg,
                border: `2px solid ${meta.color}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, color: meta.color, fontWeight: 700,
                position: 'relative', zIndex: 1,
              }}>
                {meta.icon}
              </div>
            </div>

            {/* Content */}
            <div style={{ flex: 1, minWidth: 0, paddingTop: 2 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span style={{
                  fontSize: 12, fontWeight: 700, color: meta.color,
                  textTransform: 'uppercase', letterSpacing: '0.04em',
                }}>
                  {meta.label}
                </span>
                <span style={{ fontSize: 11, color: t.textMuted, fontFamily: 'monospace' }}>
                  {formatDate(event.created_at)}
                </span>
              </div>
              <div style={{ fontSize: 13, color: t.text, marginTop: 2, lineHeight: 1.5 }}>
                {event.description}
              </div>
              {(event.exchange_id || event.return_id) && (
                <div style={{ fontSize: 11, color: t.textMuted, marginTop: 2, fontFamily: 'monospace' }}>
                  {event.exchange_id && `Exchange #${event.exchange_id}`}
                  {event.return_id && `Return #${event.return_id}`}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
