import { useState } from 'react'
import { useLogin } from '../hooks/useAuth'
import { apiErrorMessage } from '../utils/api'
import { useTheme } from '../styles/theme'
import { Input, Btn, ErrorAlert } from '../components/ui'

export default function Login() {
  const t = useTheme()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin1234')
  const login = useLogin()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    login.mutate({ username, password })
  }

  return (
    <div style={{ minHeight: '100vh', background: t.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 32 }}>
      {/* Logo mark */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
        <div style={{ fontSize: 28, fontWeight: 800, color: t.text, letterSpacing: '-0.02em' }}>qstar</div>
        <div style={{ fontSize: 9, color: t.textMuted, textAlign: 'center', letterSpacing: '0.38em', textTransform: 'uppercase' }}>
          inventory ops
        </div>
      </div>

      <div style={{ width: '100%', maxWidth: 360, background: t.surface, border: `1px solid ${t.border}`, borderRadius: 16, padding: 28, boxShadow: t.shadowLg }}>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Input label="Username" value={username} onChange={setUsername} placeholder="admin" />
          <Input label="Password" value={password} onChange={setPassword} placeholder="password" type="password" />

          {login.isError && <ErrorAlert message={apiErrorMessage(login.error)} />}

          <Btn variant="primary" full size="lg" disabled={login.isPending} type="submit">
            {login.isPending ? 'Signing in…' : 'Sign In'}
          </Btn>
        </form>
      </div>
    </div>
  )
}
