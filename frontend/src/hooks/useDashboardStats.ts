import { useState, useEffect, useCallback } from 'react'
import { fetchDashboardStats, type DashboardStats } from '../services/api'

export function useDashboardStats() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await fetchDashboardStats()
      setStats(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard stats')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()

    // Listen for custom event triggered when review items / ledger / docs are updated
    const handleUpdate = () => {
      refresh()
    }

    window.addEventListener('review-queue-updated', handleUpdate)
    window.addEventListener('focus', handleUpdate)

    // Polling interval every 4 seconds to keep badge and stats live
    const interval = setInterval(refresh, 4000)

    return () => {
      window.removeEventListener('review-queue-updated', handleUpdate)
      window.removeEventListener('focus', handleUpdate)
      clearInterval(interval)
    }
  }, [refresh])

  return { stats, loading, error, refresh }
}

