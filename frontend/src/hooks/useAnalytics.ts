import { useQuery } from '@tanstack/react-query'
import { api } from '../utils/api'
import type { AnalyticsPeriod } from '../utils/constants'

export function useSummary(period: AnalyticsPeriod) {
  return useQuery({
    queryKey: ['analytics', 'summary', period],
    queryFn: async () => {
      const { data } = await api.get('/analytics/summary', { params: { period } })
      return data
    },
    staleTime: 30_000,
  })
}

export function useTrends(period: AnalyticsPeriod, groupBy: string) {
  return useQuery({
    queryKey: ['analytics', 'trends', period, groupBy],
    queryFn: async () => {
      const { data } = await api.get('/analytics/trends', { params: { period, group_by: groupBy } })
      return data
    },
    staleTime: 60_000,
  })
}

export function useDeadStock(days: number) {
  return useQuery({
    queryKey: ['analytics', 'dead_stock', days],
    queryFn: async () => {
      const { data } = await api.get('/analytics/dead_stock', { params: { days } })
      return data
    },
    staleTime: 60_000,
  })
}

export function useVelocity() {
  return useQuery({
    queryKey: ['analytics', 'velocity'],
    queryFn: async () => {
      const { data } = await api.get('/analytics/velocity')
      return data
    },
    staleTime: 120_000,
  })
}

export function useCVPerformance() {
  return useQuery({
    queryKey: ['analytics', 'cv-performance'],
    queryFn: async () => {
      const { data } = await api.get('/analytics/cv-performance')
      return data
    },
    staleTime: 120_000,
  })
}
