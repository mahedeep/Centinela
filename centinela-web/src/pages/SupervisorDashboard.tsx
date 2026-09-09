/** Supervisor · KPIs, costo y piloto en modo sombra. */

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ApiError, getMetrics } from '../lib/api'
import {
  PROCESS_LABEL,
  VERDICT_LABEL,
  formatPercent,
  formatUsd,
  humanizeName,
} from '../lib/format'
import type { Metrics } from '../lib/types'
import { KpiTile } from '../components/KpiTile'
import { EmptyState, ErrorBlock, LoadingBlock } from '../components/states'

const VERDICT_COLOR: Record<string, string> = {
  aprobar: '#15803d',
  autentico: '#15803d',
  validacion_adicional: '#b45309',
  sospechoso: '#b45309',
  bloquear: '#b91c1c',
  falso: '#b91c1c',
}

export function SupervisorDashboard() {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setMetrics(
        await getMetrics(
          dateFrom ? new Date(dateFrom).toISOString() : undefined,
          dateTo ? new Date(`${dateTo}T23:59:59`).toISOString() : undefined,
        ),
      )
    } catch (exception) {
      setError(
        exception instanceof ApiError ? exception.message : 'No pudimos cargar las métricas.',
      )
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo])

  useEffect(() => {
    void load()
  }, [load])

  /** La serie viene como (fecha, veredicto, conteo); Recharts necesita una fila por fecha. */
  const timeseries = useMemo(() => {
    if (!metrics) return { rows: [], verdicts: [] as string[] }
    const byDate = new Map<string, Record<string, number | string>>()
    const verdicts = new Set<string>()
    metrics.timeseries.forEach((point) => {
      verdicts.add(point.verdict)
      const row = byDate.get(point.date) ?? { date: point.date }
      row[point.verdict] = ((row[point.verdict] as number) ?? 0) + point.count
      byDate.set(point.date, row)
    })
    const rows = [...byDate.values()].sort((a, b) =>
      String(a.date).localeCompare(String(b.date)),
    )
    // Recharts no dibuja una serie si la clave falta en algunas filas.
    rows.forEach((row) => verdicts.forEach((v) => { if (!(v in row)) row[v] = 0 }))
    return { rows, verdicts: [...verdicts] }
  }, [metrics])

  if (loading) return <LoadingBlock label="Cargando métricas…" />
  if (error) return <ErrorBlock message={error} onRetry={() => void load()} />
  if (!metrics || metrics.total_volume === 0) {
    return (
      <EmptyState
        title="Todavía no hay eventos"
        description="Evalúa transacciones o documentos para que el dashboard tenga qué mostrar. También puedes activar el modo demo en Ajustes."
      />
    )
  }

  const humanReviewRate =
    metrics.by_process.reduce((sum, p) => sum + p.human_review_rate * p.volume, 0) /
    Math.max(metrics.total_volume, 1)
  const blockRate =
    metrics.by_process.reduce((sum, p) => sum + p.block_rate * p.volume, 0) /
    Math.max(metrics.total_volume, 1)
  const worstP95 = Math.max(0, ...metrics.by_process.map((p) => p.latency_p95_ms))

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-600">
            Volumen, riesgo, latencia y costo de las decisiones del sistema.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="field-label" htmlFor="desde">Desde</label>
            <input
              id="desde"
              type="date"
              className="field-input"
              value={dateFrom}
              onChange={(event) => setDateFrom(event.target.value)}
            />
          </div>
          <div>
            <label className="field-label" htmlFor="hasta">Hasta</label>
            <input
              id="hasta"
              type="date"
              className="field-input"
              value={dateTo}
              onChange={(event) => setDateTo(event.target.value)}
            />
          </div>
          <button type="button" className="btn-secondary" onClick={() => void load()}>
            Aplicar
          </button>
        </div>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile label="Eventos evaluados" value={metrics.total_volume.toLocaleString('es-CL')} />
        <KpiTile
          label="Tasa de bloqueo"
          value={formatPercent(blockRate)}
          tone={blockRate > 0.1 ? 'warn' : 'ok'}
          hint="Bloqueos y documentos falsos sobre el total"
        />
        <KpiTile
          label="Revisión humana"
          value={formatPercent(humanReviewRate)}
          hint="Casos derivados a un analista"
        />
        <KpiTile
          label="Latencia p95"
          value={`${worstP95.toFixed(0)} ms`}
          tone={worstP95 > 2000 ? 'warn' : 'ok'}
          hint="La peor entre ambos procesos"
        />
        <KpiTile label="Costo acumulado" value={formatUsd(metrics.total_cost_usd)} />
        <KpiTile
          label="Costo por evento"
          value={formatUsd(metrics.cost_per_event_usd)}
          hint="Costo total dividido por eventos"
        />
        <KpiTile
          label="Feedback recibido"
          value={metrics.feedback_count.toLocaleString('es-CL')}
          hint="Casos etiquetados por analistas"
        />
        <KpiTile
          label="Precisión estimada"
          value={metrics.estimated_accuracy === null ? '—' : formatPercent(metrics.estimated_accuracy)}
          hint="Sobre los casos con feedback"
          tone={
            metrics.estimated_accuracy === null
              ? 'neutral'
              : metrics.estimated_accuracy >= 0.8
                ? 'ok'
                : 'warn'
          }
        />
      </section>

      <section className="card p-5">
        <h2 className="mb-1 text-base font-semibold text-slate-900">Piloto en modo sombra</h2>
        <p className="mb-4 text-sm text-slate-600">
          Cuántos casos <em>se habrían</em> bloqueado sin haber afectado a ningún cliente.
        </p>
        {metrics.shadow_approved === 0 ? (
          <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-500">
            No hay casos en modo sombra en este período. Actívalo con{' '}
            <code className="text-xs">SHADOW_MODE=true</code> en la API para pilotar sin bloquear.
          </p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-3">
            <KpiTile
              label="Aprobados por modo sombra"
              value={metrics.shadow_approved.toLocaleString('es-CL')}
            />
            <KpiTile
              label="Se habrían bloqueado"
              value={metrics.shadow_would_block.toLocaleString('es-CL')}
              tone="warn"
            />
            <KpiTile
              label="Impacto potencial"
              value={formatPercent(metrics.shadow_would_block / Math.max(metrics.shadow_approved, 1))}
              hint="Fracción del tráfico que el sistema habría frenado"
            />
          </div>
        )}
      </section>

      <section className="card p-5">
        <h2 className="mb-4 text-base font-semibold text-slate-900">Decisiones por día</h2>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={timeseries.rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="#64748b" />
              <YAxis allowDecimals={false} tick={{ fontSize: 12 }} stroke="#64748b" />
              <Tooltip />
              <Legend formatter={(value) => VERDICT_LABEL[String(value)] ?? String(value)} />
              {timeseries.verdicts.map((verdict) => (
                <Line
                  key={verdict}
                  type="monotone"
                  dataKey={verdict}
                  stroke={VERDICT_COLOR[verdict] ?? '#1d5b70'}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="card p-5">
          <h2 className="mb-4 text-base font-semibold text-slate-900">
            Evidencias más frecuentes
          </h2>
          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={metrics.top_evidence.map((item) => ({
                  ...item,
                  label: humanizeName(item.name),
                }))}
                layout="vertical"
                margin={{ top: 4, right: 16, bottom: 4, left: 8 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} stroke="#64748b" />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={160}
                  tick={{ fontSize: 11 }}
                  stroke="#64748b"
                />
                <Tooltip />
                <Bar dataKey="count" name="Casos" fill="#1d5b70" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="card p-5">
          <h2 className="mb-4 text-base font-semibold text-slate-900">Costo por modelo</h2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] border-collapse">
              <thead>
                <tr>
                  <th scope="col" className="table-header">Modelo</th>
                  <th scope="col" className="table-header text-right">Eventos</th>
                  <th scope="col" className="table-header text-right">Tokens</th>
                  <th scope="col" className="table-header text-right">Costo</th>
                </tr>
              </thead>
              <tbody>
                {metrics.by_model.map((row) => (
                  <tr key={row.model}>
                    <td className="table-cell font-mono text-xs">{row.model}</td>
                    <td className="table-cell text-right tabular-nums">
                      {row.events.toLocaleString('es-CL')}
                    </td>
                    <td className="table-cell text-right tabular-nums">
                      {(row.tokens_in + row.tokens_out).toLocaleString('es-CL')}
                    </td>
                    <td className="table-cell text-right tabular-nums">{formatUsd(row.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="mb-2 mt-5 text-sm font-semibold text-slate-900">Por proceso</h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] border-collapse">
              <thead>
                <tr>
                  <th scope="col" className="table-header">Proceso</th>
                  <th scope="col" className="table-header text-right">Volumen</th>
                  <th scope="col" className="table-header text-right">p50 / p95</th>
                  <th scope="col" className="table-header text-right">Costo/evento</th>
                </tr>
              </thead>
              <tbody>
                {metrics.by_process.map((row) => (
                  <tr key={row.process}>
                    <td className="table-cell">{PROCESS_LABEL[row.process]}</td>
                    <td className="table-cell text-right tabular-nums">
                      {row.volume.toLocaleString('es-CL')}
                    </td>
                    <td className="table-cell text-right tabular-nums">
                      {row.latency_p50_ms.toFixed(0)} / {row.latency_p95_ms.toFixed(0)} ms
                    </td>
                    <td className="table-cell text-right tabular-nums">
                      {formatUsd(row.cost_per_event_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  )
}
