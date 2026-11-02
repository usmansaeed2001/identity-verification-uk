import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, ApiError } from './client'
import type { DriverApplication, Me, StaffDetail, StaffList } from './types'

export const keys = {
  me: ['me'] as const,
  application: ['application'] as const,
  staffList: (params: Record<string, string>) => ['staff', 'list', params] as const,
  staffDetail: (id: string) => ['staff', 'detail', id] as const,
}

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: async () => {
      try {
        return await api<Me>('/api/auth/me')
      } catch (error) {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return null
        throw error
      }
    },
    staleTime: 60_000,
  })
}

export function useApplication() {
  return useQuery({
    queryKey: keys.application,
    queryFn: () => api<DriverApplication>('/api/driver/application'),
    // Live checks take 15-40 seconds: poll while one is running.
    refetchInterval: (query) => {
      const data = query.state.data
      return data && (data.right_to_work.state === 'running' || data.licence.state === 'running') ? 3000 : false
    },
  })
}

/** A driver action that returns the updated application. */
export function useDriverAction<V>(request: (vars: V) => Promise<DriverApplication>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: (data) => queryClient.setQueryData(keys.application, data),
  })
}

export function useStaffList(params: Record<string, string>) {
  const search = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
  return useQuery({
    queryKey: keys.staffList(params),
    queryFn: () => api<StaffList>(`/api/staff/applications${search ? `?${search}` : ''}`),
    refetchInterval: 15_000,
  })
}

export function useStaffDetail(id: string) {
  return useQuery({
    queryKey: keys.staffDetail(id),
    queryFn: () => api<StaffDetail>(`/api/staff/applications/${id}`),
  })
}

export function useStaffAction<V>(id: string, request: (vars: V) => Promise<StaffDetail>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: (data) => {
      queryClient.setQueryData(keys.staffDetail(id), data)
      queryClient.invalidateQueries({ queryKey: ['staff', 'list'] })
    },
  })
}
