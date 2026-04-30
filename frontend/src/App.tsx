import type { ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { useLogout } from './hooks/useAuth'
import Login from './pages/Login'
import Intake from './pages/Intake'
import Checkout from './pages/Checkout'
import Analytics from './pages/Analytics'
import Inventory from './pages/Inventory'

function NavBar() {
  const user = useAuthStore((s) => s.user)
  const logout = useLogout()

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 rounded text-sm font-medium transition-colors ${
      isActive ? 'bg-brand-600 text-white' : 'text-gray-700 hover:bg-gray-100'
    }`

  return (
    <nav className="bg-white border-b border-gray-200 px-4 py-2 flex items-center gap-2">
      <span className="font-bold text-brand-600 mr-4 text-lg">ThriftOS</span>
      <NavLink to="/intake" className={linkClass}>Intake</NavLink>
      <NavLink to="/checkout" className={linkClass}>Checkout</NavLink>
      <NavLink to="/inventory" className={linkClass}>Inventory</NavLink>
      {user?.role !== 'staff' && (
        <NavLink to="/analytics" className={linkClass}>Analytics</NavLink>
      )}
      <div className="ml-auto flex items-center gap-3 text-sm text-gray-500">
        <span>{user?.username} ({user?.role})</span>
        <button
          onClick={logout}
          className="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 text-gray-700"
        >
          Logout
        </button>
      </div>
    </nav>
  )
}

function ProtectedLayout({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return (
    <div className="min-h-screen flex flex-col">
      <NavBar />
      <main className="flex-1 p-4">{children}</main>
    </div>
  )
}

function AdminOnly({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user)
  if (user?.role === 'staff') return <Navigate to="/intake" replace />
  return <>{children}</>
}

export default function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={isAuthenticated ? <Navigate to="/intake" replace /> : <Login />}
        />
        <Route path="/intake" element={<ProtectedLayout><Intake /></ProtectedLayout>} />
        <Route path="/checkout" element={<ProtectedLayout><Checkout /></ProtectedLayout>} />
        <Route path="/inventory" element={<ProtectedLayout><Inventory /></ProtectedLayout>} />
        <Route
          path="/analytics"
          element={
            <ProtectedLayout>
              <AdminOnly><Analytics /></AdminOnly>
            </ProtectedLayout>
          }
        />
        <Route path="/" element={<Navigate to="/intake" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
