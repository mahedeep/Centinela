/** Analista · bandeja de revisión, filtrable y ordenada por score. */

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, listCases } from '../lib/api'
import type { CaseFilters } from '../lib/api'
import { FEEDBACK_LABEL, PROCESS_LABEL, formatAge, formatDateTime } from '../lib/format'
import type { CaseSummary, Process, Verdict } from '../lib/types'
import { VerdictBadge } from '../components/VerdictBadge'
import { EmptyState, ErrorBlock, LoadingBlock } from '../components/states'

const VERDICTS: Array<{ value: Verdict | ''; label: string }> = [
  { value: '', label: 'Todos los veredictos' },
  { value: 'bloquear', label: 'Bloqueada' },
  { value: 'validacion_adicional', label: 'Validación adicional' },
  { value: 'aprobar', label: 'Aprobada' },
  { value: 'falso', label: 'Documento falso' },
  { value: 'sospechoso', label: 'Documento sospechoso' },
  { value: 'autentico', label: 'Documento auténtico' },
]

/** SLA: sobre 4 horas sin revisar, el caso se marca. */
const SLA_WARN_SECONDS = 2 * 3600
const SLA_BAD_SECONDS = 4 * 3600

function SlaBadge({ seconds }: { seconds: number }) {
  const tone =
    seconds >= SLA_BAD_SECONDS
      ? 'bg-red-50 text-red-800 border-red-200'
      : seconds >= SLA_WARN_SECONDS
        ? 'bg-amber-50 text-amber-900 border-amber-200'
        : 'bg-slate-50 text-slate-600 border-slate-200'
  return (
    <span className={`rounded border px-2 py-0.5 text-xs font-medium ${tone}`}>
      {formatAge(seconds)}
    </span>
  )
}

export function AnalistaBandeja() {
  const [cases, setCases] = useState<CaseSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [process, setProcess] = useState<Process | ''>('')
  const [verdict, setVerdict] = useState<Verdict | ''>('')
  const [onlyReview, setOnlyReview] = useState(true)
  const [dateFrom, setDateFrom] = useState('')
  const [orderBy, setOrderBy] = useState<'score' | 'created_at'>('score')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    const filters: CaseFilters = {
      process: process || undefined,
      verdict: verdict || undefined,
      requiresHumanReview: onlyReview ? true : undefined,
      dateFrom: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      orderBy,
      limit: 200,
    }
    try {
      setCases(await listCases(filters))
    } catch (exception) {
      setError(
        exception instanceof ApiError ? exception.message : 'No pudimos cargar la bandeja.',
      )
    } finally {
      setLoading(false)
    }
  }, [process, verdict, onlyReview, dateFrom, orderBy])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Bandeja de revisión</h1>
          <p className="mt-1 text-sm text-slate-600">
            Casos ordenados por score. El indicador de SLA muestra cuánto llevan esperando.
          </p>
        </div>
        <button type="button" className="btn-secondary" onClick={() => void load()}>
          Actualizar
        </button>
      </header>

      <section className="card p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <label className="field-label" htmlFor="f-proceso">Proceso</label>
            <select
              id="f-proceso"
              className="field-input"
              value={process}
              onChange={(event) => setProcess(event.target.value as Process | '')}
            >
              <option value="">Todos</option>
              <option value="transaction">Transacciones</option>
              <option value="document">Documentos</option>
            </select>
          </div>

          <div>
            <label className="field-label" htmlFor="f-veredicto">Veredicto</label>
            <select
              id="f-veredicto"
              className="field-input"
              value={verdict}
              onChange={(event) => setVerdict(event.target.value as Verdict | '')}
            >
              {VERDICTS.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="field-label" htmlFor="f-desde">Desde</label>
            <input
              id="f-desde"
              type="date"
              className="field-input"
              value={dateFrom}
              onChange={(event) => setDateFrom(event.target.value)}
            />
          </div>

          <div>
            <label className="field-label" htmlFor="f-orden">Ordenar por</label>
            <select
              id="f-orden"
              className="field-input"
              value={orderBy}
              onChange={(event) => setOrderBy(event.target.value as 'score' | 'created_at')}
            >
              <option value="score">Score (mayor primero)</option>
              <option value="created_at">Más recientes</option>
            </select>
          </div>

          <label className="flex min-h-[44px] items-center gap-2 self-end text-sm">
            <input
              type="checkbox"
              className="h-5 w-5 rounded border-slate-300 text-petrol-700"
              checked={onlyReview}
              onChange={(event) => setOnlyReview(event.target.checked)}
            />
            <span className="text-slate-700">Solo revisión humana</span>
          </label>
        </div>
      </section>

      {loading ? (
        <LoadingBlock label="Cargando casos…" />
      ) : error ? (
        <ErrorBlock message={error} onRetry={() => void load()} />
      ) : cases.length === 0 ? (
        <EmptyState
          title="No hay casos con esos filtros"
          description="Prueba quitando el filtro de revisión humana o ampliando el rango de fechas. Si acabas de levantar la API, evalúa una transacción desde la vista de Cliente para generar casos."
        />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[860px] border-collapse">
            <caption className="sr-only">Casos pendientes de revisión</caption>
            <thead>
              <tr>
                <th scope="col" className="table-header">Caso</th>
                <th scope="col" className="table-header w-32">Proceso</th>
                <th scope="col" className="table-header w-48">Veredicto</th>
                <th scope="col" className="table-header w-24 text-right">Score</th>
                <th scope="col" className="table-header w-28">SLA</th>
                <th scope="col" className="table-header w-40">Creado</th>
                <th scope="col" className="table-header w-40">Etiqueta</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((item) => (
                <tr key={item.trace_id} className="hover:bg-slate-50">
                  <td className="table-cell">
                    <Link
                      to={`/casos/${encodeURIComponent(item.trace_id)}`}
                      className="font-mono text-xs text-petrol-700 underline underline-offset-2"
                    >
                      {item.trace_id}
                    </Link>
                  </td>
                  <td className="table-cell">{PROCESS_LABEL[item.process]}</td>
                  <td className="table-cell">
                    <VerdictBadge verdict={item.verdict} size="sm" shadow={item.shadow} />
                  </td>
                  <td className="table-cell text-right font-mono tabular-nums">
                    {item.score.toFixed(3)}
                  </td>
                  <td className="table-cell"><SlaBadge seconds={item.age_seconds} /></td>
                  <td className="table-cell whitespace-nowrap">{formatDateTime(item.created_at)}</td>
                  <td className="table-cell">
                    {item.feedback_label ? (
                      <span className="rounded border border-green-200 bg-green-50 px-2 py-0.5 text-xs text-green-800">
                        {FEEDBACK_LABEL[item.feedback_label]}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">Sin revisar</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
