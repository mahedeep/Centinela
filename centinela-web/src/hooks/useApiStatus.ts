/**
 * Estado de la API. Si `health` falla, la app muestra un aviso persistente y
 * ofrece activar el modo demo.
 */

import { useCallback, useEffect, useState } from 'react'
import { getHealth, isDemoMode } from '../lib/api'
import type { Health } from '../lib/types'

interface ApiStatus {
  health: Health | null
  reachable: boolean
  checking: boolean
  demoMode: boolean
  refresh: () => void
}

export function useApiStatus(): ApiStatus {
  const [health, setHealth] = useState<Health | null>(null)
  const [reachable, setReachable] = useState(true)
  const [checking, setChecking] = useState(true)
  const [demoMode, setDemoModeState] = useState(isDemoMode)

  const check = useCallback(async () => {
    setChecking(true)
    try {
      setHealth(await getHealth())
      setReachable(true)
    } catch {
      setHealth(null)
      setReachable(false)
    } finally {
      setChecking(false)
    }
  }, [])

  useEffect(() => {
    void check()
    const onDemoChange = () => {
      setDemoModeState(isDemoMode())
      void check()
    }
    window.addEventListener('centinela:demo-mode', onDemoChange)
    return () => window.removeEventListener('centinela:demo-mode', onDemoChange)
  }, [check])

  return { health, reachable, checking, demoMode, refresh: () => void check() }
}
