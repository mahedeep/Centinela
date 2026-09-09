/**
 * Sesión y rol.
 *
 * Supabase es opcional: si `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` están
 * configuradas, se autentica contra Supabase (email + contraseña) y el rol se
 * lee de la tabla `profiles`. Si no lo están —el caso de la demo del curso— se
 * usa acceso por rol guardado en el navegador.
 *
 * El esquema de Supabase con sus políticas RLS está en `supabase/schema.sql`.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Role } from '../lib/types'

const STORAGE_KEY = 'centinela.session'

export interface Session {
  role: Role
  displayName: string
  email?: string
  source: 'local' | 'supabase'
}

interface AuthValue {
  session: Session | null
  supabaseEnabled: boolean
  signInLocal: (role: Role, displayName: string) => void
  signInWithPassword: (email: string, password: string) => Promise<void>
  signOut: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string | undefined
const SUPABASE_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined
const supabaseEnabled = Boolean(SUPABASE_URL && SUPABASE_KEY)

function readStoredSession(): Session | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(readStoredSession)

  useEffect(() => {
    if (session) localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
    else localStorage.removeItem(STORAGE_KEY)
  }, [session])

  const signInLocal = useCallback((role: Role, displayName: string) => {
    setSession({ role, displayName: displayName.trim() || role, source: 'local' })
  }, [])

  const signInWithPassword = useCallback(async (email: string, password: string) => {
    if (!supabaseEnabled) {
      throw new Error(
        'Supabase no está configurado. Usa el acceso por rol o define VITE_SUPABASE_URL y VITE_SUPABASE_ANON_KEY.',
      )
    }

    // Llamada directa a la API REST de Supabase: evita sumar el SDK completo
    // solo para un login de demo.
    const authResponse = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', apikey: SUPABASE_KEY as string },
      body: JSON.stringify({ email, password }),
    })
    if (!authResponse.ok) {
      throw new Error('Correo o contraseña incorrectos.')
    }
    const auth = (await authResponse.json()) as {
      access_token: string
      user: { id: string; email: string }
    }

    const profileResponse = await fetch(
      `${SUPABASE_URL}/rest/v1/profiles?id=eq.${auth.user.id}&select=role,display_name`,
      {
        headers: {
          apikey: SUPABASE_KEY as string,
          Authorization: `Bearer ${auth.access_token}`,
        },
      },
    )
    const profiles = profileResponse.ok
      ? ((await profileResponse.json()) as Array<{ role: Role; display_name: string }>)
      : []
    const profile = profiles[0]

    setSession({
      role: profile?.role ?? 'cliente',
      displayName: profile?.display_name || auth.user.email,
      email: auth.user.email,
      source: 'supabase',
    })
  }, [])

  const signOut = useCallback(() => setSession(null), [])

  const value = useMemo<AuthValue>(
    () => ({ session, supabaseEnabled, signInLocal, signInWithPassword, signOut }),
    [session, signInLocal, signInWithPassword, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return context
}
