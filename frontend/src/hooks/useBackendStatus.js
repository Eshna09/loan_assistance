/**
 * useBackendStatus.js
 * Polls GET /api/kb/info to determine if the backend is reachable.
 * Returns { status: 'online'|'offline'|'checking', kbInfo }
 */

import { useState, useEffect, useCallback } from 'react'
import { getKbInfo } from '../services/api'

const POLL_INTERVAL_MS = 30_000

export function useBackendStatus() {
  const [status, setStatus] = useState('checking') // 'checking' | 'online' | 'offline'
  const [kbInfo, setKbInfo] = useState(null)

  const check = useCallback(async () => {
    try {
      const data = await getKbInfo()
      setKbInfo(data)
      setStatus('online')
    } catch {
      setStatus('offline')
    }
  }, [])

  useEffect(() => {
    check()
    const timer = setInterval(check, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [check])

  // Lets an upload/delete push the backend's fresh KB straight into state
  // instead of waiting for the next poll.
  const applyKbInfo = useCallback((data) => {
    if (!data) return
    setKbInfo(data)
    setStatus('online')
  }, [])

  return { status, kbInfo, refresh: check, applyKbInfo }
}
