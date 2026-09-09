/** Marco de la aplicación: navegación por rol y aviso de estado de la API. */

import { NavLink, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from '../hooks/useAuth'
import { useApiStatus } from '../hooks/useApiStatus'
import { setDemoMode } from '../lib/api'
import type { Role } from '../lib/types'

const NAV_BY_ROLE: Record<Role, Array<{ to: string; label: string }>> = {
  cliente: [
    { to: '/cliente/transaccion', label: 'Simular transacción' },
    { to: '/cliente/documento', label: 'Subir documento' },
  ],
  analista: [{ to: '/analista', label: 'Bandeja de revisión' }],
  supervisor: [
    { to: '/supervisor', label: 'Dashboard' },
    { to: '/analista', label: 'Bandeja' },
    { to: '/ajustes', label: 'Ajustes' },
  ],
}

const ROLE_LABEL: Record<Role, string> = {
  cliente: 'Cliente',
  analista: 'Analista de fraude',
  supervisor: 'Supervisor',
}

export function Layout({ children }: { children: ReactNode }) {
  const { session, signOut } = useAuth()
  const { reachable, checking, demoMode } = useApiStatus()
  const navigate = useNavigate()

  const links = session ? NAV_BY_ROLE[session.role] : []

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-4 focus:py-2 focus:text-petrol-800 focus:shadow"
      >
        Saltar al contenido
      </a>

      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2">
            <span
              className="flex h-9 w-9 items-center justify-center rounded-lg bg-petrol-700 text-sm font-bold text-white"
              aria-hidden="true"
            >
              CE
            </span>
            <span className="text-lg font-semibold text-slate-900">Centinela</span>
          </NavLink>

          {links.length > 0 && (
            <nav aria-label="Navegación principal" className="flex flex-wrap gap-1">
              {links.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  className={({ isActive }) =>
                    `flex min-h-[44px] items-center rounded-lg px-3 text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-petrol-50 text-petrol-800'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`
                  }
                >
                  {link.label}
                </NavLink>
              ))}
            </nav>
          )}

          <div className="ml-auto flex items-center gap-3">
            {demoMode && (
              <span className="rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-900">
                Modo demo
              </span>
            )}
            {session && (
              <>
                <span className="hidden text-sm text-slate-600 sm:inline">
                  {session.displayName} · {ROLE_LABEL[session.role]}
                </span>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => {
                    signOut()
                    navigate('/')
                  }}
                >
                  Salir
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      {!reachable && !checking && !demoMode && (
        <div className="border-b border-amber-200 bg-amber-50" role="alert">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3">
            <p className="text-sm text-amber-900">
              No podemos conectar con la API de agentes. Revisa la URL en Ajustes o activa el
              modo demo para seguir navegando con datos de ejemplo.
            </p>
            <button
              type="button"
              className="btn-secondary ml-auto"
              onClick={() => setDemoMode(true)}
            >
              Activar modo demo
            </button>
          </div>
        </div>
      )}

      <main id="contenido" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        {children}
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-4 text-xs text-slate-500">
          Centinela · plataforma antifraude multimodal. Proyecto académico de
          <em> Advanced Prompt Engineering 4 Generative AI</em>, Universidad Adolfo Ibáñez.
          Todos los datos son sintéticos.
        </div>
      </footer>
    </div>
  )
}
