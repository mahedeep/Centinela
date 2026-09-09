/**
 * Cliente · simular una transacción.
 *
 * PROHIBIDO mostrar aquí score, reglas, evidencias, similitudes, nombres de
 * modelos o costos. El único texto que el cliente ve es `explanation_customer`.
 */

import { useState } from 'react'
import { ApiError, evaluateTransaction } from '../lib/api'
import { formatCLP } from '../lib/format'
import type { Decision, TransactionInput } from '../lib/types'
import { Spinner } from '../components/states'

type Escenario = 'legitima' | 'dudosa' | 'fraudulenta'

interface FormState {
  amount: number
  type: TransactionInput['type']
  channel: TransactionInput['channel']
  isNewBeneficiary: boolean
  isNewDevice: boolean
  ipCountry: string
  vpn: boolean
  distanceKm: number
  txLastHour: number
  failedLogins: number
  sessionSeconds: number
  avgMonthlyAmount: number
}

const BASE: FormState = {
  amount: 85_000,
  type: 'pago',
  channel: 'app_movil',
  isNewBeneficiary: false,
  isNewDevice: false,
  ipCountry: 'CL',
  vpn: false,
  distanceKm: 2.1,
  txLastHour: 0,
  failedLogins: 0,
  sessionSeconds: 180,
  avgMonthlyAmount: 900_000,
}

// Los tres escenarios vienen de la hoja `escenarios_demo` del set de prueba.
const ESCENARIOS: Record<Escenario, { label: string; hint: string; state: FormState }> = {
  legitima: {
    label: 'Legítima',
    hint: 'Monto bajo, beneficiario y dispositivo conocidos.',
    state: BASE,
  },
  dudosa: {
    label: 'Dudosa',
    hint: 'Beneficiario nuevo con monto 1,4× el promedio.',
    state: {
      ...BASE,
      amount: 1_250_000,
      type: 'transferencia',
      isNewBeneficiary: true,
      distanceKm: 3.2,
      txLastHour: 1,
      failedLogins: 1,
      sessionSeconds: 95,
    },
  },
  fraudulenta: {
    label: 'Fraudulenta',
    hint: 'Dispositivo y beneficiario nuevos, IP extranjera con VPN, sesión de 22 s.',
    state: {
      ...BASE,
      amount: 3_900_000,
      type: 'transferencia',
      channel: 'web',
      isNewBeneficiary: true,
      isNewDevice: true,
      ipCountry: 'BR',
      vpn: true,
      distanceKm: 640,
      txLastHour: 3,
      failedLogins: 5,
      sessionSeconds: 22,
    },
  },
}

function toPayload(form: FormState): TransactionInput {
  return {
    transaction_id: `TX-WEB-${Date.now().toString(36).toUpperCase()}`,
    timestamp: new Date().toISOString(),
    amount: form.amount,
    currency: 'CLP',
    channel: form.channel,
    type: form.type,
    origin_account: {
      id: 'ACC-1001',
      age_days: 1450,
      avg_monthly_amount: form.avgMonthlyAmount,
      country: 'CL',
    },
    destination_account: {
      id: `ACC-77${Math.floor(Math.random() * 90 + 10)}`,
      bank: 'OtroBanco',
      is_new_beneficiary: form.isNewBeneficiary,
      country: 'CL',
    },
    device: {
      id: 'DEV-55',
      is_new_device: form.isNewDevice,
      os: 'Android',
      ip_country: form.ipCountry,
      vpn: form.vpn,
    },
    geo: { lat: -33.45, lon: -70.66, distance_from_home_km: form.distanceKm },
    behavior: {
      tx_last_hour: form.txLastHour,
      tx_last_24h: form.txLastHour * 2 + 1,
      failed_logins_24h: form.failedLogins,
      session_seconds: form.sessionSeconds,
    },
    customer_profile: { segment: 'persona_natural', risk_tier: 'medio' },
  }
}

export function ClienteTransaccion() {
  const [form, setForm] = useState<FormState>(BASE)
  const [decision, setDecision] = useState<Decision | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Autenticación reforzada simulada, cuando el veredicto lo pide.
  const [code, setCode] = useState('')
  const [stepUpDone, setStepUpDone] = useState(false)
  const [contactOpen, setContactOpen] = useState(false)
  const [contactSent, setContactSent] = useState(false)

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }))

  const applyScenario = (escenario: Escenario) => {
    setForm(ESCENARIOS[escenario].state)
    setDecision(null)
    setError(null)
    setStepUpDone(false)
    setCode('')
    setContactOpen(false)
    setContactSent(false)
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    setDecision(null)
    setStepUpDone(false)
    setCode('')
    setContactOpen(false)
    setContactSent(false)
    try {
      setDecision(await evaluateTransaction(toPayload(form)))
    } catch (exception) {
      setError(
        exception instanceof ApiError
          ? exception.message
          : 'No pudimos procesar tu operación. Intenta nuevamente en unos minutos.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Transferir o pagar</h1>
        <p className="mt-1 text-sm text-slate-600">
          Completa la operación como lo harías en la app del banco.
        </p>
      </header>

      <section className="card p-4">
        <p className="mb-2 text-sm font-medium text-slate-700">Escenarios de ejemplo</p>
        <div className="grid gap-2 sm:grid-cols-3">
          {(Object.keys(ESCENARIOS) as Escenario[]).map((key) => (
            <button
              key={key}
              type="button"
              className="btn-secondary flex-col items-start !justify-center py-2 text-left"
              onClick={() => applyScenario(key)}
            >
              <span className="font-medium">{ESCENARIOS[key].label}</span>
              <span className="text-xs font-normal text-slate-500">{ESCENARIOS[key].hint}</span>
            </button>
          ))}
        </div>
      </section>

      <form onSubmit={submit} className="card space-y-4 p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="field-label" htmlFor="monto">Monto</label>
            <input
              id="monto"
              type="number"
              min={1}
              step="any"
              className="field-input"
              value={form.amount}
              onChange={(event) => set('amount', Number(event.target.value))}
              required
            />
            <p className="mt-1 text-xs text-slate-500">{formatCLP(form.amount)}</p>
          </div>

          <div>
            <label className="field-label" htmlFor="tipo">Tipo de operación</label>
            <select
              id="tipo"
              className="field-input"
              value={form.type}
              onChange={(event) => set('type', event.target.value as FormState['type'])}
            >
              <option value="transferencia">Transferencia</option>
              <option value="pago">Pago</option>
              <option value="compra">Compra</option>
              <option value="retiro">Retiro</option>
            </select>
          </div>

          <div>
            <label className="field-label" htmlFor="canal">Canal</label>
            <select
              id="canal"
              className="field-input"
              value={form.channel}
              onChange={(event) => set('channel', event.target.value as FormState['channel'])}
            >
              <option value="app_movil">App móvil</option>
              <option value="web">Sitio web</option>
              <option value="cajero">Cajero</option>
              <option value="sucursal">Sucursal</option>
            </select>
          </div>

          <div>
            <label className="field-label" htmlFor="promedio">Promedio mensual de la cuenta</label>
            <input
              id="promedio"
              type="number"
              min={1}
              step="any"
              className="field-input"
              value={form.avgMonthlyAmount}
              onChange={(event) => set('avgMonthlyAmount', Number(event.target.value))}
            />
          </div>

          <div>
            <label className="field-label" htmlFor="pais">País desde el que te conectas</label>
            <select
              id="pais"
              className="field-input"
              value={form.ipCountry}
              onChange={(event) => set('ipCountry', event.target.value)}
            >
              <option value="CL">Chile</option>
              <option value="AR">Argentina</option>
              <option value="BR">Brasil</option>
              <option value="PE">Perú</option>
            </select>
          </div>

          <div>
            <label className="field-label" htmlFor="distancia">Distancia del domicilio (km)</label>
            <input
              id="distancia"
              type="number"
              min={0}
              step={0.1}
              className="field-input"
              value={form.distanceKm}
              onChange={(event) => set('distanceKm', Number(event.target.value))}
            />
          </div>

          <div>
            <label className="field-label" htmlFor="ultima-hora">Operaciones en la última hora</label>
            <input
              id="ultima-hora"
              type="number"
              min={0}
              className="field-input"
              value={form.txLastHour}
              onChange={(event) => set('txLastHour', Number(event.target.value))}
            />
          </div>

          <div>
            <label className="field-label" htmlFor="fallidos">Intentos de acceso fallidos (24 h)</label>
            <input
              id="fallidos"
              type="number"
              min={0}
              className="field-input"
              value={form.failedLogins}
              onChange={(event) => set('failedLogins', Number(event.target.value))}
            />
          </div>

          <div>
            <label className="field-label" htmlFor="sesion">Duración de la sesión (segundos)</label>
            <input
              id="sesion"
              type="number"
              min={0}
              className="field-input"
              value={form.sessionSeconds}
              onChange={(event) => set('sessionSeconds', Number(event.target.value))}
            />
          </div>
        </div>

        <fieldset className="space-y-2">
          <legend className="field-label">Contexto de la operación</legend>
          {(
            [
              ['isNewBeneficiary', 'Es la primera vez que transfiero a este destinatario'],
              ['isNewDevice', 'Estoy usando un dispositivo nuevo'],
              ['vpn', 'Estoy conectado a través de una VPN'],
            ] as Array<[keyof FormState, string]>
          ).map(([key, label]) => (
            <label key={String(key)} className="flex min-h-[44px] items-center gap-3 text-sm">
              <input
                type="checkbox"
                className="h-5 w-5 rounded border-slate-300 text-petrol-700"
                checked={Boolean(form[key])}
                onChange={(event) => set(key, event.target.checked as never)}
              />
              <span className="text-slate-700">{label}</span>
            </label>
          ))}
        </fieldset>

        <button type="submit" className="btn-primary w-full" disabled={loading}>
          {loading ? <Spinner label="Procesando tu operación…" /> : 'Confirmar operación'}
        </button>
      </form>

      {error && (
        <div className="card border-red-200 bg-red-50 p-5" role="alert">
          <p className="text-sm font-medium text-red-900">{error}</p>
        </div>
      )}

      {decision && (
        <section className="card p-6" aria-live="polite">
          {decision.verdict === 'aprobar' && (
            <div className="text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-green-100 text-2xl text-green-700" aria-hidden="true">
                ✓
              </div>
              <h2 className="mt-3 text-xl font-semibold text-slate-900">Operación realizada</h2>
              <p className="mt-2 text-slate-600">{decision.explanation_customer}</p>
              <p className="mt-4 text-sm text-slate-500">
                {formatCLP(form.amount)} · comprobante enviado a tu correo
              </p>
            </div>
          )}

          {decision.verdict === 'validacion_adicional' && (
            <div>
              {!stepUpDone ? (
                <div className="text-center">
                  <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-amber-100 text-2xl text-amber-700" aria-hidden="true">
                    !
                  </div>
                  <h2 className="mt-3 text-xl font-semibold text-slate-900">
                    Confirmemos que eres tú
                  </h2>
                  <p className="mt-2 text-slate-600">{decision.explanation_customer}</p>

                  <form
                    className="mx-auto mt-5 max-w-xs space-y-3"
                    onSubmit={(event) => {
                      event.preventDefault()
                      setStepUpDone(true)
                    }}
                  >
                    <label className="field-label" htmlFor="codigo">
                      Código de 6 dígitos que enviamos a tu teléfono
                    </label>
                    <input
                      id="codigo"
                      inputMode="numeric"
                      pattern="\d{6}"
                      maxLength={6}
                      className="field-input text-center font-mono text-lg tracking-[0.4em]"
                      value={code}
                      onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))}
                      placeholder="123456"
                      required
                    />
                    <button type="submit" className="btn-primary w-full" disabled={code.length !== 6}>
                      Verificar y continuar
                    </button>
                    <p className="text-xs text-slate-500">
                      Demo: cualquier combinación de 6 dígitos sirve.
                    </p>
                  </form>
                </div>
              ) : (
                <div className="text-center">
                  <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-green-100 text-2xl text-green-700" aria-hidden="true">
                    ✓
                  </div>
                  <h2 className="mt-3 text-xl font-semibold text-slate-900">Operación realizada</h2>
                  <p className="mt-2 text-slate-600">
                    Confirmamos tu identidad y completamos la operación por {formatCLP(form.amount)}.
                  </p>
                </div>
              )}
            </div>
          )}

          {decision.verdict === 'bloquear' && (
            <div className="text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-100 text-2xl text-red-700" aria-hidden="true">
                ✕
              </div>
              <h2 className="mt-3 text-xl font-semibold text-slate-900">
                Dejamos tu operación en pausa
              </h2>
              <p className="mt-2 text-slate-600">{decision.explanation_customer}</p>

              {!contactOpen && !contactSent && (
                <button type="button" className="btn-primary mt-5" onClick={() => setContactOpen(true)}>
                  Hablar con un ejecutivo
                </button>
              )}

              {contactOpen && !contactSent && (
                <form
                  className="mx-auto mt-5 max-w-sm space-y-3 text-left"
                  onSubmit={(event) => {
                    event.preventDefault()
                    setContactSent(true)
                    setContactOpen(false)
                  }}
                >
                  <div>
                    <label className="field-label" htmlFor="telefono">Teléfono de contacto</label>
                    <input id="telefono" type="tel" className="field-input" placeholder="+56 9 1234 5678" required />
                  </div>
                  <div>
                    <label className="field-label" htmlFor="horario">¿Cuándo te llamamos?</label>
                    <select id="horario" className="field-input">
                      <option>Lo antes posible</option>
                      <option>Esta tarde</option>
                      <option>Mañana por la mañana</option>
                    </select>
                  </div>
                  <button type="submit" className="btn-primary w-full">Solicitar llamada</button>
                </form>
              )}

              {contactSent && (
                <p className="mt-5 rounded-lg bg-green-50 px-4 py-3 text-sm text-green-900">
                  Listo. Un ejecutivo te contactará para revisar la operación contigo.
                </p>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  )
}
