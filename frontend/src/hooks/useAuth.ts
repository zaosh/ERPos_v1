import { useMutation } from '@tanstack/react-query'
import { api } from '../utils/api'
import { useAuthStore } from '../store/authStore'

interface LoginCredentials {
  username: string
  password: string
}

interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: { id: number; username: string; role: 'staff' | 'admin' | 'superadmin' }
}

export function useLogin() {
  const setAuth = useAuthStore((s) => s.setAuth)

  return useMutation({
    mutationFn: async (creds: LoginCredentials) => {
      const { data } = await api.post<LoginResponse>('/auth/login', creds)
      return data
    },
    onSuccess: (data) => {
      setAuth(data.access_token, data.user)
    },
  })
}

export function useLogout() {
  const logout = useAuthStore((s) => s.logout)
  return () => {
    logout()
    window.location.href = '/login'
  }
}
