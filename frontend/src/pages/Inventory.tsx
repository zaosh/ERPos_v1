import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../utils/api'
import { useTheme } from '../styles/theme'
import { Badge, Btn, Card, Empty, SectionHeader, Select, Spinner, StatusBadge } from '../components/ui'
import { ITEM_CATEGORIES, ITEM_STATUSES, type ItemCategory, type ItemStatus } from '../utils/constants'
import { money } from '../utils/currency'

interface ItemRow {
  id: number; barcode: string; category: string; color: string | null
  label: string | null; size: string | null; condition: string
  price: string; status: string; image_thumb_url: string | null; created_at: string
  has_been_returned?: boolean
}

interface ItemList { items: ItemRow[]; total: number; limit: number; offset: number }

const PAGE_SIZE = 12

const STATUS_NEXT: Record<string, ItemStatus[]> = {
  in_stock: ['sold', 'reserved', 'archived'],
  sold: ['in_stock', 'archived'],
  reserved: ['in_stock', 'sold', 'archived'],
  archived: ['in_stock'],
}

const COLOR_MAP: Record<string, string> = {
  black: '#222', white: '#eee', grey: '#999', navy: '#1a3a6b', blue: '#3b7dd8',
  red: '#e53e3e', green: '#38a169', brown: '#7b5230', cream: '#f5ead6',
  pink: '#ed64a6', purple: '#805ad5', yellow: '#ecc94b', orange: '#ed8936', khaki: '#b5a882',
}

function ColorDot({ color }: { color: string | null }) {
  if (!color) return null
  return <div style={{ width: 10, height: 10, borderRadius: '50%', background: COLOR_MAP[color] ?? '#888', flexShrink: 0 }} />
}

function StatusMenu({ current, onSet }: { current: string; onSet: (s: ItemStatus) => void }) {
  const t = useTheme()
  const [open, setOpen] = useState(false)
  const options = STATUS_NEXT[current] ?? []

  return (
    <div style={{ position: 'relative' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
        <StatusBadge status={current} />
        {options.length > 0 && (
          <button onClick={() => setOpen(o => !o)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: t.textDim, fontSize: 10, lineHeight: 1, padding: '0 2px' }}>▾</button>
        )}
      </span>
      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, zIndex: 20, background: t.surface, border: `1px solid ${t.border}`, borderRadius: 8, boxShadow: t.shadowLg, minWidth: 110, overflow: 'hidden', marginTop: 4 }}>
          {options.map(s => (
            <button key={s} onClick={() => { onSet(s); setOpen(false) }}
              style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', fontSize: 12, color: t.text, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
              onMouseEnter={e => { e.currentTarget.style.background = t.surface2 }}
              onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
            >
              {s.replace('_', ' ')}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function InventoryCard({ item, onStatusChange }: { item: ItemRow; onStatusChange: (barcode: string, s: ItemStatus) => void }) {
  const t = useTheme()
  return (
    <Card style={{ overflow: 'hidden', padding: 0 }}>
      <div style={{ width: '100%', aspectRatio: '3/2', background: t.surface2, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
        {item.image_thumb_url ? (
          <img src={item.image_thumb_url} alt={item.label ?? item.category} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            <span style={{ fontSize: 11, color: t.textDim, fontFamily: t.mono }}>no image</span>
            <span style={{ fontSize: 11, color: t.textDim }}>{item.category}</span>
          </div>
        )}
        <div style={{ position: 'absolute', top: 8, right: 8 }}>
          <StatusBadge status={item.status} />
        </div>
        <div style={{ position: 'absolute', top: 8, left: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {item.condition === 'excellent' && <Badge color="accent">★ excl</Badge>}
          {item.has_been_returned && <Badge color="warning">↩ returned</Badge>}
        </div>
      </div>
      <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <ColorDot color={item.color} />
            <span style={{ fontSize: 13, fontWeight: 600, color: t.text }}>{item.label || item.category}</span>
          </div>
          <span style={{ fontSize: 15, fontWeight: 700, color: t.accent }}>{money(item.price)}</span>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {item.size && <Badge>{item.size}</Badge>}
          {item.color && <Badge>{item.color}</Badge>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 2 }}>
          <span style={{ fontSize: 10, color: t.textMuted, fontFamily: t.mono }}>{item.barcode}</span>
          <StatusMenu current={item.status} onSet={s => onStatusChange(item.barcode, s)} />
        </div>
      </div>
    </Card>
  )
}

function InventoryRow({ item, onStatusChange }: { item: ItemRow; onStatusChange: (barcode: string, s: ItemStatus) => void }) {
  const t = useTheme()
  const [hover, setHover] = useState(false)
  return (
    <tr onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ background: hover ? t.surface2 : 'transparent', transition: 'background 0.1s' }}>
      <td style={{ padding: '10px 12px', fontFamily: t.mono, fontSize: 11, color: t.accent }}>{item.barcode}</td>
      <td style={{ padding: '10px 12px', fontSize: 13, textTransform: 'capitalize', color: t.text }}>{item.category}</td>
      <td style={{ padding: '10px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <ColorDot color={item.color} />
          <span style={{ fontSize: 13, color: t.text }}>{item.color || '—'}</span>
        </div>
      </td>
      <td style={{ padding: '10px 12px', fontSize: 13, color: t.text, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.label || '—'}</td>
      <td style={{ padding: '10px 12px', fontSize: 13, color: t.textMuted }}>{item.size || '—'}</td>
      <td style={{ padding: '10px 12px', fontSize: 13, color: t.textMuted }}>{item.condition}</td>
      <td style={{ padding: '10px 12px', fontSize: 14, fontWeight: 700, color: t.accent }}>{money(item.price)}</td>
      <td style={{ padding: '10px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <StatusMenu current={item.status} onSet={s => onStatusChange(item.barcode, s)} />
          {item.has_been_returned && <Badge color="warning">↩</Badge>}
        </div>
      </td>
      <td style={{ padding: '10px 12px', fontSize: 11, color: t.textMuted }}>{new Date(item.created_at).toLocaleDateString()}</td>
    </tr>
  )
}

const CAT_OPTIONS = [{ value: '' as ItemCategory | '', label: 'All categories' }, ...ITEM_CATEGORIES.map(c => ({ value: c, label: c }))]
const STATUS_OPTIONS = [{ value: '' as ItemStatus | '', label: 'All statuses' }, ...ITEM_STATUSES.map(s => ({ value: s, label: s.replace('_', ' ') }))]

export default function Inventory() {
  const t = useTheme()
  const qc = useQueryClient()
  const [view, setView] = useState<'grid' | 'table'>('grid')
  const [category, setCategory] = useState<ItemCategory | ''>('')
  const [status, setStatus] = useState<ItemStatus | ''>('in_stock')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)

  const { data, isLoading } = useQuery({
    queryKey: ['inventory', category, status, search, page],
    queryFn: async () => {
      const params: Record<string, string | number> = { limit: PAGE_SIZE, offset: page * PAGE_SIZE }
      if (category) params.category = category
      if (status) params.status = status
      if (search) params.search = search
      const { data } = await api.get<ItemList>('/items/', { params })
      return data
    },
    staleTime: 15_000,
  })

  const statusMutation = useMutation({
    mutationFn: async ({ barcode, newStatus }: { barcode: string; newStatus: ItemStatus }) => {
      await api.patch(`/items/${barcode}`, { status: newStatus })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory'] }),
  })

  const handleStatusChange = (barcode: string, newStatus: ItemStatus) => {
    statusMutation.mutate({ barcode, newStatus })
  }

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <SectionHeader>Inventory</SectionHeader>
        <div style={{ display: 'flex', background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 8, overflow: 'hidden' }}>
          {([['grid', '⊞ Grid'], ['table', '☰ Table']] as const).map(([v, label]) => (
            <button key={v} onClick={() => setView(v)} style={{
              padding: '6px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer', border: 'none',
              background: view === v ? t.accent : 'transparent',
              color: view === v ? t.bg : t.textMuted,
              transition: 'all 0.15s', fontFamily: 'inherit',
            }}>{label}</button>
          ))}
        </div>
      </div>

      {/* Filter bar */}
      <Card style={{ padding: '12px 16px' }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          {/* Search */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 8, padding: '0 12px', flex: '1 1 180px', minWidth: 180 }}>
            <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke={t.textMuted} strokeWidth={2} strokeLinecap="round">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
            <input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(0) }}
              placeholder="Barcode, label, category…"
              style={{ background: 'none', border: 'none', outline: 'none', color: t.text, fontSize: 13, padding: '9px 0', flex: 1, fontFamily: 'inherit' }}
            />
          </div>

          <Select value={category} onChange={v => { setCategory(v); setPage(0) }} options={CAT_OPTIONS as any} style={{ flexShrink: 0, minWidth: 140 }} />
          <Select value={status} onChange={v => { setStatus(v); setPage(0) }} options={STATUS_OPTIONS as any} style={{ flexShrink: 0, minWidth: 130 }} />

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            {isLoading ? <Spinner size={16} /> : <span style={{ fontSize: 13, color: t.textMuted }}>{data?.total ?? 0} item{data?.total !== 1 ? 's' : ''}</span>}
          </div>
        </div>
      </Card>

      {/* Content */}
      {isLoading && <div style={{ display: 'flex', justifyContent: 'center', padding: '40px 0' }}><Spinner size={32} /></div>}
      {!isLoading && (!data?.items.length) && <Empty message="No items match these filters" />}

      {!isLoading && data && data.items.length > 0 && view === 'grid' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 14 }}>
          {data.items.map(item => <InventoryCard key={item.id} item={item} onStatusChange={handleStatusChange} />)}
        </div>
      )}

      {!isLoading && data && data.items.length > 0 && view === 'table' && (
        <Card style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${t.border}` }}>
                  {['Barcode', 'Category', 'Color', 'Label', 'Size', 'Cond.', 'Price', 'Status', 'Added'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map(item => <InventoryRow key={item.id} item={item} onStatusChange={handleStatusChange} />)}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10 }}>
          <Btn variant="ghost" size="sm" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>← Prev</Btn>
          <div style={{ display: 'flex', gap: 4 }}>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
              const p = Math.min(Math.max(page - 2, 0) + i, totalPages - 1)
              return (
                <button key={p} onClick={() => setPage(p)} style={{
                  width: 30, height: 30, borderRadius: 6,
                  border: `1px solid ${p === page ? t.accent : t.border}`,
                  background: p === page ? t.accentDim : 'transparent',
                  color: p === page ? t.accent : t.textMuted,
                  cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                }}>
                  {p + 1}
                </button>
              )
            })}
          </div>
          <Btn variant="ghost" size="sm" onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}>Next →</Btn>
        </div>
      )}
    </div>
  )
}
