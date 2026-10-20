import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { canonicalGameId, catalogViews } from '../lib/runs'
import { gameName } from '../lib/format'
import { api } from './client'
import type { BenchmarkList, Catalog, Framework, Harness, Pin } from './types'

/** The run catalog, polled while the page is visible (API serves it stale-while-revalidate). */
export function useCatalog(interval = 5000) {
  const query = useQuery({
    queryKey: ['catalog'],
    queryFn: ({ signal }) => api.get<Catalog>('/catalog', signal),
    refetchInterval: interval,
    staleTime: 2000,
  })
  const views = useMemo(() => catalogViews(query.data), [query.data])
  return { ...query, views }
}

export function useHarnesses() {
  return useQuery({
    queryKey: ['harnesses'],
    queryFn: ({ signal }) => api.get<Harness[]>('/harnesses', signal),
    staleTime: 60_000,
  })
}

export function useFrameworks() {
  return useQuery({
    queryKey: ['frameworks'],
    queryFn: async ({ signal }) => (await api.get<{ frameworks: Framework[] }>('/frameworks', signal)).frameworks,
    staleTime: 300_000,
  })
}

export function useBenchmarks() {
  return useQuery({
    queryKey: ['benchmarks'],
    queryFn: ({ signal }) => api.get<BenchmarkList>('/benchmarks', signal),
    staleTime: 30_000,
  })
}

/** Display title for a game id (benchmark title when known, else a readable id). */
export function useGameTitle(): (id: string) => string {
  const benchmarks = useBenchmarks()
  return useMemo(() => {
    const titles = new Map((benchmarks.data?.games ?? []).map((g) => [g.game_id, g.title]))
    return (id: string) => titles.get(canonicalGameId(id)) ?? gameName(id)
  }, [benchmarks.data])
}

/** Pins of one run, or of every run when `run` is omitted. */
export function usePins(run?: string) {
  return useQuery({
    queryKey: ['pins', run ?? null],
    queryFn: async ({ signal }) => (await api.get<{ pins: Pin[] }>(`/pins${run ? `?run=${encodeURIComponent(run)}` : ''}`, signal)).pins,
    staleTime: 10_000,
  })
}

export function usePinActions() {
  const client = useQueryClient()
  const refresh = () => client.invalidateQueries({ queryKey: ['pins'] })
  return {
    add: useMutation({ mutationFn: (pin: Partial<Pin> & { run: string; text: string }) => api.post<Pin>('/pins', pin), onSuccess: refresh }),
    note: useMutation({ mutationFn: ({ id, note }: { id: string; note: string }) => api.patch<Pin>(`/pins/${id}`, { note }), onSuccess: refresh }),
    remove: useMutation({ mutationFn: (id: string) => api.del<null>(`/pins/${id}`), onSuccess: refresh }),
  }
}
