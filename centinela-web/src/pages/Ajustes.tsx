/** Supervisor · ajustes de conexión y parámetros del sistema (solo lectura). */

import { useEffect, useState } from 'react'
import {
  getApiBaseUrl,
  getSettings,
  isDemoMode,
  setApiBaseUrl,
  setDemoMode,
} from '../lib/api'
import { useApiStatus } from '../hooks/useApiStatus'
import type { PublicSettings } from '../lib/types'
import { Spinner } from '../components/states'

const REPO_URL = 'https://github.com/{{USUARIO}}/centinela-agents'

export function Ajustes() {
  const { health, reachable, checking, refresh } = useApiStatus()
  const [baseUrl, setBaseUrl] = useState(getApiBaseUrl())
  const [demo, setDemo] = useState(isDemoMode())
  const [settings, setSettings] = useState<PublicSettings | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    getSettings().then(setSettings).catch(() => setSettings(null))
  }, [demo, reachable])

  const save = (event: React.FormEvent) => {
    event.preventDefault()
    setApiBaseUrl(baseUrl)
    setSaved(true)
    refresh()
    window.setTimeout(() => setSaved(false), 2500)
  }

  const toggleDemo = (value: boolean) => {
    setDemo(value)
    setDemoMode(value)
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Ajustes</h1>
        <p className="mt-1 text-sm text-slate-600">
          Conexión con la API de agentes y parámetros vigentes del sistema.
        </p>
      </header>

      <section className="card p-5">
        <h2 className="mb-3 text-base font-semibold text-slate-900">Conexión</h2>
        <form onSubmit={save} className="space-y-3">
          <div>
            <label className="field-label" htmlFor="base-url">URL base de la API</label>
            <input
              id="base-url"
              type="url"
              className="field-input"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="http://localhost:8000"
            />
            <p className="mt-1 text-xs text-slate-500">
              Se guarda en este navegador. El valor por defecto viene de{' '}
              <code>VITE_API_BASE_URL</code>.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" className="btn-primary">Guardar</button>
            {saved && <span className="text-sm text-green-700">Guardado.</span>}
            {checking && <Spinner label="Comprobando…" />}
          </div>
        </form>

        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
          {demo ? (
            <p className="text-slate-700">
              <strong>Modo demo activo.</strong> La app usa respuestas precargadas y no llama a
              la API.
            </p>
          ) : reachable && health ? (
            <p className="text-slate-700">
              <strong>API conectada</strong> · versión {health.version} ·{' '}
              {health.mock_mode ? 'la API está en modo mock' : 'la API llama a OpenAI'}
              {health.shadow_mode && ' · modo sombra activo'}
              {health.models?.ocr_engine && ` · OCR: ${health.models.ocr_engine}`}
            </p>
          ) : (
            <p className="text-amber-900">
              <strong>Sin conexión con la API.</strong> Revisa la URL o activa el modo demo.
            </p>
          )}
        </div>

        <label className="mt-4 flex min-h-[44px] items-center gap-3 text-sm">
          <input
            type="checkbox"
            className="h-5 w-5 rounded border-slate-300 text-petrol-700"
            checked={demo}
            onChange={(event) => toggleDemo(event.target.checked)}
          />
          <span className="text-slate-700">
            Modo demo · usa respuestas precargadas, sin API ni tokens
          </span>
        </label>
      </section>

      {settings && (
        <section className="card p-5">
          <h2 className="mb-1 text-base font-semibold text-slate-900">
            Parámetros del sistema
          </h2>
          <p className="mb-4 text-sm text-slate-600">
            Solo lectura. Se cambian con variables de entorno en la API de agentes.
          </p>

          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-slate-900">Umbrales</h3>
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <dt className="text-slate-500">Revisión adicional</dt>
                  <dd className="font-mono tabular-nums">{settings.thresholds.review}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Bloqueo</dt>
                  <dd className="font-mono tabular-nums">{settings.thresholds.block}</dd>
                </div>
              </dl>

              <h3 className="mb-2 mt-4 text-sm font-semibold text-slate-900">
                Pesos · transacciones
              </h3>
              <dl className="space-y-1 text-sm">
                {Object.entries(settings.weights.transactions).map(([key, value]) => (
                  <div key={key} className="flex justify-between">
                    <dt className="text-slate-500">{key}</dt>
                    <dd className="font-mono tabular-nums">{value}</dd>
                  </div>
                ))}
              </dl>

              <h3 className="mb-2 mt-4 text-sm font-semibold text-slate-900">
                Pesos · documentos
              </h3>
              <dl className="space-y-1 text-sm">
                {Object.entries(settings.weights.documents).map(([key, value]) => (
                  <div key={key} className="flex justify-between">
                    <dt className="text-slate-500">{key}</dt>
                    <dd className="font-mono tabular-nums">{value}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <div>
              <h3 className="mb-2 text-sm font-semibold text-slate-900">Documentos</h3>
              <dl className="space-y-1 text-sm">
                {Object.entries(settings.documents).map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-3">
                    <dt className="text-slate-500">{key}</dt>
                    <dd className="font-mono text-xs tabular-nums">{String(value)}</dd>
                  </div>
                ))}
              </dl>

              <h3 className="mb-2 mt-4 text-sm font-semibold text-slate-900">
                Precios (USD por 1M de tokens)
              </h3>
              <dl className="space-y-1 text-sm">
                {Object.entries(settings.pricing_usd_per_1m_tokens)
                  .filter(([key]) => key !== 'nota')
                  .map(([key, value]) => (
                    <div key={key} className="flex justify-between">
                      <dt className="text-slate-500">{key}</dt>
                      <dd className="font-mono tabular-nums">{String(value)}</dd>
                    </div>
                  ))}
              </dl>
              {settings.pricing_usd_per_1m_tokens.nota && (
                <p className="mt-2 text-xs text-slate-500">
                  {String(settings.pricing_usd_per_1m_tokens.nota)}
                </p>
              )}
            </div>
          </div>
        </section>
      )}

      <section className="card p-5">
        <h2 className="mb-2 text-base font-semibold text-slate-900">Repositorio de agentes</h2>
        <p className="text-sm text-slate-600">
          Toda la inteligencia vive en la API. El front nunca llama a OpenAI.
        </p>
        <a
          href={REPO_URL}
          target="_blank"
          rel="noreferrer"
          className="btn-secondary mt-3 inline-flex"
        >
          Abrir el repositorio
        </a>
      </section>
    </div>
  )
}
