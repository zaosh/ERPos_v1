import type { ReactNode } from 'react'
import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from './store/authStore'
import { useLogout } from './hooks/useAuth'
import { ThemeContext, THEMES } from './styles/theme'
import { api } from './utils/api'
import Login from './pages/Login'
import Intake from './pages/Intake'
import Checkout from './pages/Checkout'
import Analytics from './pages/Analytics'
import Inventory from './pages/Inventory'
import Sales from './pages/Sales'

const ROUTES = [
  { id: 'intake',    label: 'Intake',     path: '/intake',    icon: 'M12 5v14M5 12h14', adminOnly: false },
  { id: 'checkout',  label: 'Checkout',   path: '/checkout',  icon: 'M3 3h18M3 9h18M3 15h18', adminOnly: false },
  { id: 'inventory', label: 'Inventory',  path: '/inventory', icon: 'M20 7H4a2 2 0 00-2 2v10a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2zm-1-4H5a2 2 0 00-2 2v2h18V5a2 2 0 00-2-2z', adminOnly: false },
  { id: 'sales',     label: 'Sales',      path: '/sales',     icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z', adminOnly: false },
  { id: 'analytics', label: 'Analytics',  path: '/analytics', icon: 'M3 3v18h18M8 17l4-8 4 4 4-6', adminOnly: true },
]

function Icon({ d, size = 16, color, strokeWidth = 2 }: { d: string; size?: number; color?: string; strokeWidth?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color || 'currentColor'} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  )
}

interface QueueSummary {
  pending_count: number
  failed_count: number
  pending_by_type: Record<string, number>
}
interface FailedJob {
  id: number
  job_type: string
  item_id: number | null
  attempts: number
  error_message: string | null
  created_at: string
}

function QueueIndicator() {
  const t = THEMES.dark
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()

  const { data: summary } = useQuery<QueueSummary>({
    queryKey: ['queue-summary'],
    queryFn: async () => { const { data } = await api.get('/jobs/summary'); return data },
    refetchInterval: open ? 5000 : 30000,
  })
  const { data: failed } = useQuery<FailedJob[]>({
    queryKey: ['queue-failed'],
    queryFn: async () => { const { data } = await api.get('/jobs/failed?limit=20'); return data },
    enabled: open,
    refetchInterval: open ? 5000 : false,
  })
  const { data: recent } = useQuery<Array<{ id: number; job_type: string; item_id: number | null; completed_at: string }>>({
    queryKey: ['queue-recent'],
    queryFn: async () => { const { data } = await api.get('/jobs/recent'); return data },
    enabled: open,
    refetchInterval: open ? 5000 : false,
  })

  const pending = summary?.pending_count ?? 0
  const failedCount = summary?.failed_count ?? 0
  if (pending === 0 && failedCount === 0) return null

  const badgeColor = failedCount > 0 ? '#ef4444' : '#f59e0b'
  const count = failedCount > 0 ? failedCount : pending

  const handleRetry = async (jobId: number) => {
    try {
      await api.post(`/jobs/${jobId}/retry`)
      qc.invalidateQueries({ queryKey: ['queue-summary'] })
      qc.invalidateQueries({ queryKey: ['queue-failed'] })
    } catch {}
  }

  return (
    <div style={{ position: 'relative', marginLeft: 'auto' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: open ? t.surface2 : 'transparent',
          border: `1px solid ${open ? t.border : 'transparent'}`,
          borderRadius: 8, padding: '4px 10px', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'inherit',
          transition: 'all 0.15s',
        }}
      >
        <div style={{
          background: badgeColor, color: '#fff', borderRadius: 10,
          minWidth: 18, height: 18, display: 'flex', alignItems: 'center',
          justifyContent: 'center', fontSize: 10, fontWeight: 700, padding: '0 5px',
        }}>{count}</div>
        <span style={{ fontSize: 11, color: t.textMuted }}>
          {failedCount > 0 ? 'failed' : 'queued'}
        </span>
      </button>

      {/* Inline panel — NOT position:fixed */}
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 6px)', right: 0,
          background: t.surface, border: `1px solid ${t.border}`,
          borderRadius: 12, boxShadow: t.shadowLg, width: 360, zIndex: 90,
          overflow: 'hidden',
        }}>
          <div style={{ padding: '12px 16px', borderBottom: `1px solid ${t.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: t.text }}>Job Queue</span>
            <button onClick={() => setOpen(false)}
              style={{ background: 'none', border: 'none', color: t.textMuted, cursor: 'pointer', fontSize: 16 }}>×</button>
          </div>

          <div style={{ padding: '12px 16px', maxHeight: 400, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* Pending by type */}
            {pending > 0 && (
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>Pending ({pending})</div>
                {Object.entries(summary?.pending_by_type ?? {}).map(([type, cnt]) => (
                  <div key={type} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: t.text, padding: '3px 0' }}>
                    <span style={{ fontFamily: t.mono, color: t.textMuted }}>{type}</span>
                    <span style={{ fontWeight: 600, color: '#f59e0b' }}>{cnt}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Failed jobs */}
            {failed && failed.length > 0 && (
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#ef4444', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>Failed ({failed.length})</div>
                {failed.map(j => (
                  <div key={j.id} style={{ background: t.dangerDim, borderRadius: 8, padding: '8px 10px', marginBottom: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 11, fontFamily: t.mono, color: t.text }}>{j.job_type}</span>
                      {j.item_id && <span style={{ fontSize: 10, color: t.textMuted }}>item #{j.item_id}</span>}
                    </div>
                    {j.error_message && (
                      <span style={{ fontSize: 10, color: t.danger, wordBreak: 'break-word' }}>{j.error_message.slice(0, 80)}</span>
                    )}
                    <button onClick={() => handleRetry(j.id)}
                      style={{ alignSelf: 'flex-start', background: t.accentDim, border: 'none', borderRadius: 5, padding: '3px 10px', fontSize: 10, color: t.accent, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600 }}>
                      Retry
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Recent completed */}
            {recent && recent.length > 0 && (
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>Recent</div>
                {recent.map(j => (
                  <div key={j.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: t.textMuted, padding: '3px 0', borderBottom: `1px solid ${t.border}` }}>
                    <span style={{ fontFamily: t.mono }}>{j.job_type}</span>
                    <span style={{ color: t.success }}>✓ {j.completed_at ? new Date(j.completed_at).toLocaleTimeString() : ''}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function NavBar() {
  const user = useAuthStore(s => s.user)
  const logout = useLogout()
  const navigate = useNavigate()
  const location = useLocation()
  const t = THEMES.dark

  const visibleRoutes = user?.role === 'staff' ? ROUTES.filter(r => !r.adminOnly) : ROUTES

  return (
    <nav style={{
      background: t.navBg,
      borderBottom: `1px solid ${t.border}`,
      padding: '0 20px',
      display: 'flex', alignItems: 'center', gap: 0,
      height: 52, position: 'sticky', top: 0, zIndex: 100,
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', marginRight: 28, flexShrink: 0 }}>
        <span style={{ fontWeight: 800, fontSize: 15, color: '#fff', letterSpacing: '-0.01em', fontFamily: 'inherit' }}>qstar</span>
      </div>

      {/* Nav links */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 2, flex: 1 }}>
        {visibleRoutes.map(route => {
          const active = location.pathname.startsWith(route.path)
          return (
            <button
              key={route.id}
              onClick={() => navigate(route.path)}
              style={{
                display: 'flex', alignItems: 'center', gap: 7,
                padding: '6px 14px', borderRadius: 7,
                fontSize: 13, fontWeight: 600,
                cursor: 'pointer', border: 'none',
                background: active ? t.accentDim : 'transparent',
                color: active ? t.accent : 'rgba(255,255,255,0.5)',
                transition: 'all 0.15s', fontFamily: 'inherit',
                letterSpacing: '0.01em', position: 'relative',
              }}
              onMouseEnter={e => {
                if (!active) {
                  const el = e.currentTarget
                  el.style.background = 'rgba(255,255,255,0.06)'
                  el.style.color = 'rgba(255,255,255,0.85)'
                }
              }}
              onMouseLeave={e => {
                if (!active) {
                  const el = e.currentTarget
                  el.style.background = 'transparent'
                  el.style.color = 'rgba(255,255,255,0.5)'
                }
              }}
            >
              <Icon d={route.icon} size={14} />
              {route.label}
              {active && (
                <div style={{ position: 'absolute', bottom: -1, left: '20%', right: '20%', height: 2, background: t.accent, borderRadius: 99 }} />
              )}
            </button>
          )
        })}
      </div>

      {/* Queue indicator — admin only */}
      {user?.role !== 'staff' && <QueueIndicator />}

      {/* User + logout */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginLeft: user?.role === 'staff' ? 'auto' : 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 28, height: 28, borderRadius: '50%', background: t.surface3, border: `1px solid ${t.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: t.textMuted, textTransform: 'uppercase' }}>{user?.username?.[0] ?? 'U'}</span>
          </div>
          <div style={{ lineHeight: 1.2 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'rgba(255,255,255,0.8)' }}>{user?.username}</div>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{user?.role}</div>
          </div>
        </div>
        <button
          onClick={logout}
          style={{
            background: 'transparent', border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 6, padding: '5px 10px', fontSize: 12,
            color: 'rgba(255,255,255,0.4)', cursor: 'pointer',
            fontFamily: 'inherit', transition: 'all 0.15s',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.borderColor = 'rgba(255,255,255,0.3)'
            e.currentTarget.style.color = 'rgba(255,255,255,0.7)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.borderColor = 'rgba(255,255,255,0.12)'
            e.currentTarget.style.color = 'rgba(255,255,255,0.4)'
          }}
        >
          Logout
        </button>
      </div>
    </nav>
  )
}

function ProtectedLayout({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore(s => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  const t = THEMES.dark
  return (
    <div style={{ minHeight: '100vh', background: t.bg, display: 'flex', flexDirection: 'column' }}>
      <NavBar />
      <main style={{ flex: 1, background: t.bg }}>{children}</main>
    </div>
  )
}

function AdminOnly({ children }: { children: ReactNode }) {
  const user = useAuthStore(s => s.user)
  if (user?.role === 'staff') return <Navigate to="/intake" replace />
  return <>{children}</>
}

export default function App() {
  const [themeKey] = useState('dark')
  const t = THEMES[themeKey] ?? THEMES.dark
  const isAuthenticated = useAuthStore(s => s.isAuthenticated)

  return (
    <ThemeContext.Provider value={t}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={isAuthenticated ? <Navigate to="/intake" replace /> : <Login />} />
          <Route path="/intake" element={<ProtectedLayout><Intake /></ProtectedLayout>} />
          <Route path="/checkout" element={<ProtectedLayout><Checkout /></ProtectedLayout>} />
          <Route path="/inventory" element={<ProtectedLayout><Inventory /></ProtectedLayout>} />
          <Route path="/sales" element={<ProtectedLayout><Sales /></ProtectedLayout>} />
          <Route path="/analytics" element={<ProtectedLayout><AdminOnly><Analytics /></AdminOnly></ProtectedLayout>} />
          <Route path="/" element={<Navigate to="/intake" replace />} />
        </Routes>
      </BrowserRouter>
    </ThemeContext.Provider>
  )
}
