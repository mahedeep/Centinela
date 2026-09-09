/** Analista · detalle de un caso, con evidencias, traza y decisión humana. */

import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ApiError,
  documentPageUrl,
  getCase,
  getDocumentEvidence,
  getSettings,
  sendFeedback,
} from '../lib/api'
import {
  FEEDBACK_LABEL,
  PROCESS_LABEL,
  formatDateTime,
  formatUsd,
  humanizeName,
} from '../lib/format'
import type {
  CaseDetail,
  DocumentDecision,
  EvidenceRegions,
  FeedbackLabel,
  PublicSettings,
} from '../lib/types'
import { useAuth } from '../hooks/useAuth'
import { VerdictBadge } from '../components/VerdictBadge'
import { ScoreMeter } from '../components/ScoreMeter'
import { EvidenceTable } from '../components/EvidenceTable'
import { ChecksTable } from '../components/ChecksTable'
import { DocumentViewer } from '../components/DocumentViewer'
import { CaseTimeline } from '../components/CaseTimeline'
import { ErrorBlock, LoadingBlock, Spinner } from '../components/states'

const ACTIONS: Record<'transaction' | 'document', Array<{ label: string; value: FeedbackLabel }>> = {
  transaction: [
    { label: 'Confirmar fraude', value: 'fraude_confirmado' },
    { label: 'Marcar legítimo', value: 'legitimo' },
  ],
  document: [
    { label: 'Documento falso', value: 'documento_falso' },
    { label: 'Documento auténtico', value: 'documento_autentico' },
  ],
}

export function AnalistaCaso() {
  const { traceId = '' } = useParams()
  const { session } = useAuth()

  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [evidence, setEvidence] = useState<EvidenceRegions | null>(null)
  const [settings, setSettings] = useState<PublicSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [comment, setComment] = useState('')
  const [sending, setSending] = useState<FeedbackLabel | null>(null)
  const [sent, setSent] = useState<string | null>(null)
  const [sendError, setSendError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const caseDetail = await getCase(traceId)
      setDetail(caseDetail)
      if (caseDetail.decision.process === 'document') {
        try {
          setEvidence(await getDocumentEvidence(traceId))
        } catch {
          setEvidence(null)
        }
      }
      try {
        setSettings(await getSettings())
      } catch {
        setSettings(null)
      }
    } catch (exception) {
      setError(exception instanceof ApiError ? exception.message : 'No pudimos cargar el caso.')
    } finally {
      setLoading(false)
    }
  }, [traceId])

  useEffect(() => {
    void load()
  }, [load])

  const submitFeedback = async (label: FeedbackLabel) => {
    setSending(label)
    setSendError(null)
    try {
      const ack = await sendFeedback({
        trace_id: traceId,
        label,
        analyst: session?.displayName || 'analista',
        comment,
      })
      setSent(ack.message)
      setComment('')
      await load()
    } catch (exception) {
      setSendError(
        exception instanceof ApiError ? exception.message : 'No pudimos registrar tu decisión.',
      )
    } finally {
      setSending(null)
    }
  }

  if (loading) return <LoadingBlock label="Cargando el caso…" />
  if (error || !detail) {
    return (
      <ErrorBlock
        message={error || 'Caso no encontrado.'}
        onRetry={() => void load()}
        action={
          <Link to="/analista" className="btn-secondary">
            Volver a la bandeja
          </Link>
        }
      />
    )
  }

  const { decision } = detail
  const isDocument = decision.process === 'document'
  const document = isDocument ? (decision as DocumentDecision) : null
  const thresholds = settings?.thresholds ?? { review: 0.35, block: 0.7 }

  return (
    <div className="space-y-5">
      <nav className="text-sm">
        <Link to="/analista" className="text-petrol-700 underline underline-offset-2">
          ← Volver a la bandeja
        </Link>
      </nav>

      <header className="card p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">
              {PROCESS_LABEL[decision.process]}
            </p>
            <h1 className="mt-0.5 font-mono text-lg font-semibold text-slate-900">
              {decision.trace_id}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              {formatDateTime(decision.created_at)} · {decision.latency_ms} ms
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <VerdictBadge verdict={decision.verdict} size="lg" shadow={decision.shadow} />
            {decision.requires_human_review && (
              <span className="rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-900">
                Requiere revisión humana
              </span>
            )}
          </div>
        </div>

        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <ScoreMeter
            score={decision.score}
            reviewThreshold={thresholds.review}
            blockThreshold={thresholds.block}
          />
          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4 lg:grid-cols-2">
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">Confianza</p>
              <p className="font-mono tabular-nums">{decision.confidence.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">Costo</p>
              <p className="font-mono tabular-nums">{formatUsd(decision.cost_usd)}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">Tokens</p>
              <p className="font-mono tabular-nums">
                {decision.tokens_in.toLocaleString('es-CL')} / {decision.tokens_out.toLocaleString('es-CL')}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">Modelo</p>
              <p className="truncate" title={decision.model}>{decision.model || '—'}</p>
            </div>
          </div>
        </div>
      </header>

      {decision.reasons.length > 0 && (
        <section className="card p-5">
          <h2 className="mb-3 text-base font-semibold text-slate-900">Motivos</h2>
          <ul className="space-y-1.5">
            {decision.reasons.map((reason, index) => (
              <li key={index} className="flex gap-2 text-sm text-slate-700">
                <span className="text-slate-400" aria-hidden="true">•</span>
                {reason}
              </li>
            ))}
          </ul>
        </section>
      )}

      {document && (
        <section className="card p-5">
          <h2 className="mb-3 text-base font-semibold text-slate-900">
            Documento · {humanizeName(document.document_type_detected)}
          </h2>
          <div className="grid gap-5 lg:grid-cols-2">
            <DocumentViewer
              imageUrl={documentPageUrl(decision.trace_id, 1)}
              findings={evidence?.findings ?? document.findings ?? []}
              artifactsAvailable={evidence?.artifacts_available ?? false}
              retentionDays={settings?.documents.trace_retention_days ?? 7}
            />
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500">Calidad de imagen</p>
                  <p className="font-mono tabular-nums">
                    {typeof document.image_quality === 'number'
                      ? document.image_quality.toFixed(2)
                      : '—'}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500">Páginas</p>
                  <p className="font-mono tabular-nums">{document.pages_analyzed ?? '—'}</p>
                </div>
              </div>

              <div>
                <h3 className="mb-2 text-sm font-semibold text-slate-900">Campos extraídos</h3>
                {Object.keys(document.fields ?? {}).length === 0 ? (
                  <p className="text-sm text-slate-500">No se extrajo ningún campo legible.</p>
                ) : (
                  <dl className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                    {Object.entries(document.fields ?? {}).map(([name, field]) => (
                      <div key={name} className="flex items-baseline justify-between gap-3 px-3 py-2">
                        <dt className="text-xs uppercase tracking-wide text-slate-500">
                          {humanizeName(name)}
                        </dt>
                        <dd className="text-right text-sm text-slate-900">
                          {field.value || '—'}
                          <span className="ml-2 font-mono text-xs text-slate-400">
                            {typeof field.confidence === 'number'
                              ? field.confidence.toFixed(2)
                              : '—'}
                          </span>
                        </dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>
            </div>
          </div>

          <h3 className="mb-2 mt-5 text-sm font-semibold text-slate-900">Verificaciones</h3>
          <ChecksTable checks={document.checks ?? []} />
        </section>
      )}

      <section className="card p-5">
        <h2 className="mb-3 text-base font-semibold text-slate-900">Evidencias</h2>
        <EvidenceTable evidence={decision.evidence ?? []} />
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="card p-5">
          <h2 className="mb-3 text-base font-semibold text-slate-900">Lectura del analista</h2>
          <pre className="whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-3 text-xs leading-relaxed text-slate-700">
            {decision.explanation_analyst || 'Sin detalle técnico.'}
          </pre>

          <h3 className="mb-2 mt-4 text-sm font-semibold text-slate-900">Traza</h3>
          <dl className="space-y-1.5 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-slate-500">Versión del prompt</dt>
              <dd className="font-mono text-xs">{detail.prompt_version || '—'}</dd>
            </div>
            {Object.entries(detail.weights).map(([key, value]) => (
              <div key={key} className="flex justify-between gap-3">
                <dt className="text-slate-500">{humanizeName(key)}</dt>
                <dd className="font-mono text-xs tabular-nums">
                  {value === null ? 'sin datos' : Number(value).toFixed(4)}
                </dd>
              </div>
            ))}
          </dl>

          {detail.neighbors.length > 0 && (
            <>
              <h3 className="mb-2 mt-4 text-sm font-semibold text-slate-900">
                Casos comparables recuperados
              </h3>
              <ul className="space-y-1 text-sm text-slate-700">
                {detail.neighbors.map((neighbor) => (
                  <li key={neighbor.id} className="flex justify-between gap-3">
                    <span className="font-mono text-xs">{neighbor.id}</span>
                    <span>
                      {neighbor.label} ·{' '}
                      <span className="font-mono tabular-nums">
                        {neighbor.similarity.toFixed(2)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        <div className="space-y-5">
          <section className="card p-5">
            <h2 className="mb-3 text-base font-semibold text-slate-900">Línea de tiempo</h2>
            <CaseTimeline detail={detail} />
          </section>

          <section className="card p-5">
            <h2 className="mb-1 text-base font-semibold text-slate-900">Tu decisión</h2>
            <p className="mb-3 text-sm text-slate-600">
              Tu etiqueta se guarda con el caso y alimenta la memoria de similitud.
            </p>

            {detail.feedback.length > 0 && (
              <div className="mb-3 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-900">
                Ya etiquetado como{' '}
                <strong>{FEEDBACK_LABEL[detail.feedback[0].label]}</strong> por{' '}
                {detail.feedback[0].analyst}.
              </div>
            )}

            <label className="field-label" htmlFor="comentario">Comentario</label>
            <textarea
              id="comentario"
              className="field-input min-h-[88px] py-2"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="Qué encontraste al revisar el caso."
            />

            <div className="mt-3 flex flex-wrap gap-2">
              {ACTIONS[decision.process].map((action) => (
                <button
                  key={action.value}
                  type="button"
                  className="btn-primary"
                  disabled={sending !== null}
                  onClick={() => void submitFeedback(action.value)}
                >
                  {sending === action.value ? <Spinner label="Enviando…" /> : action.label}
                </button>
              ))}
            </div>

            {sent && (
              <p className="mt-3 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-900" role="status">
                {sent}
              </p>
            )}
            {sendError && (
              <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
                {sendError}
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
