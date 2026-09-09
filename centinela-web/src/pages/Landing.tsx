/** Portada y acceso por rol. */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { useApiStatus } from '../hooks/useApiStatus'
import { setDemoMode } from '../lib/api'
import type { Role } from '../lib/types'

const ROLES: Array<{ role: Role; title: string; description: string; to: string }> = [
  {
    role: 'cliente',
    title: 'Cliente',
    description:
      'Simula una transferencia o sube un documento. La protección es invisible: solo verás si la operación siguió su curso.',
    to: '/cliente/transaccion',
  },
  {
    role: 'analista',
    title: 'Analista de fraude',
    description:
      'Revisa por excepción, con las evidencias ordenadas por peso y los hallazgos dibujados sobre el documento.',
    to: '/analista',
  },
  {
    role: 'supervisor',
    title: 'Supervisor',
    description:
      'Sigue volumen, tasa de bloqueo, latencia, costo por evento y el piloto en modo sombra.',
    to: '/supervisor',
  },
]

export function Landing() {
  const { session, supabaseEnabled, signInLocal, signInWithPassword, signOut } = useAuth()
  const { health, reachable, demoMode } = useApiStatus()
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const enter = (role: Role, to: string) => {
    signInLocal(role, name || ROLES.find((r) => r.role === role)!.title)
    navigate(to)
  }

  const submitSupabase = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await signInWithPassword(email, password)
      navigate('/')
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'No pudimos iniciar sesión.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-8">
      <section className="card px-6 py-10 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
          Protección antifraude que no se nota
        </h1>
        <p className="mx-auto mt-3 max-w-2xl text-slate-600">
          Centinela evalúa transacciones y documentos combinando reglas de negocio, memoria de
          casos confirmados y modelos multimodales en una sola decisión explicable. Cada bloqueo
          pasa por una persona.
        </p>

        <div className="mx-auto mt-6 flex max-w-2xl flex-wrap justify-center gap-2 text-sm">
          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-600">
            Decisión en menos de 2 segundos
          </span>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-600">
            Validación documental en menos de 1 minuto
          </span>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-600">
            Cero pasos adicionales para el cliente
          </span>
        </div>

        <p className="mt-5 text-sm text-slate-500">
          {demoMode ? (
            <>
              Modo demo activo: los resultados vienen de respuestas precargadas.{' '}
              <button type="button" className="underline" onClick={() => setDemoMode(false)}>
                Usar la API real
              </button>
            </>
          ) : reachable && health ? (
            <>
              API conectada · versión {health.version}
              {health.mock_mode && ' · la API está en modo mock (sin llamadas a OpenAI)'}
              {health.shadow_mode && ' · modo sombra activo'}
            </>
          ) : (
            <>
              Sin conexión con la API.{' '}
              <button type="button" className="underline" onClick={() => setDemoMode(true)}>
                Activar modo demo
              </button>
            </>
          )}
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-900">Entrar como</h2>

        {session && (
          <p className="mb-4 rounded-lg border border-petrol-200 bg-petrol-50 px-4 py-3 text-sm text-petrol-900">
            Sesión iniciada como <strong>{session.displayName}</strong>. Elige otro rol para
            cambiar, o{' '}
            <button type="button" className="underline" onClick={signOut}>
              cierra la sesión
            </button>
            .
          </p>
        )}

        {!supabaseEnabled && (
          <div className="mb-4">
            <label className="field-label" htmlFor="nombre">
              Tu nombre (opcional, se usa para firmar las revisiones)
            </label>
            <input
              id="nombre"
              className="field-input max-w-sm"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Ana Pérez"
              autoComplete="name"
            />
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-3">
          {ROLES.map((item) => (
            <div key={item.role} className="card flex flex-col p-5">
              <h3 className="text-base font-semibold text-slate-900">{item.title}</h3>
              <p className="mt-1 flex-1 text-sm text-slate-600">{item.description}</p>
              <button
                type="button"
                className="btn-primary mt-4 w-full"
                onClick={() => enter(item.role, item.to)}
              >
                Entrar como {item.title}
              </button>
            </div>
          ))}
        </div>

        {supabaseEnabled && (
          <form onSubmit={submitSupabase} className="card mt-6 max-w-md space-y-3 p-5">
            <h3 className="text-base font-semibold text-slate-900">Acceso con cuenta</h3>
            <p className="text-sm text-slate-600">
              Tu rol se toma de la tabla <code className="text-xs">profiles</code> de Supabase.
            </p>
            <div>
              <label className="field-label" htmlFor="email">Correo</label>
              <input
                id="email"
                type="email"
                className="field-input"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </div>
            <div>
              <label className="field-label" htmlFor="password">Contraseña</label>
              <input
                id="password"
                type="password"
                className="field-input"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
                {error}
              </p>
            )}
            <button type="submit" className="btn-primary w-full" disabled={busy}>
              {busy ? 'Entrando…' : 'Entrar'}
            </button>
          </form>
        )}
      </section>
    </div>
  )
}
