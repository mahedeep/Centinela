/**
 * Cliente HTTP de la API de agentes.
 *
 * Prohibido llamar a OpenAI desde el front: toda la inteligencia pasa por aquí.
 * Con `demoMode` activo, ninguna función toca la red.
 */

import * as demo from './demo'
import type {
  CaseDetail,
  CaseSummary,
  Decision,
  DocumentDecision,
  DocumentType,
  EvidenceRegions,
  FeedbackLabel,
  Health,
  Metrics,
  Process,
  PublicSettings,
  TransactionInput,
  Verdict,
} from './types'

const STORAGE_BASE_URL = 'centinela.apiBaseUrl'
const STORAGE_DEMO = 'centinela.demoMode'

export function getApiBaseUrl(): string {
  const stored = localStorage.getItem(STORAGE_BASE_URL)
  if (stored) return stored.replace(/\/$/, '')
  const fromEnv = import.meta.env.VITE_API_BASE_URL as string | undefined
  return (fromEnv || 'http://localhost:8000').replace(/\/$/, '')
}

export function setApiBaseUrl(url: string): void {
  localStorage.setItem(STORAGE_BASE_URL, url.replace(/\/$/, ''))
}

export function isDemoMode(): boolean {
  const stored = localStorage.getItem(STORAGE_DEMO)
  if (stored !== null) return stored === 'true'
  return (import.meta.env.VITE_DEMO_MODE as string | undefined) === 'true'
}

export function setDemoMode(value: boolean): void {
  localStorage.setItem(STORAGE_DEMO, String(value))
  window.dispatchEvent(new CustomEvent('centinela:demo-mode', { detail: value }))
}

/** Error de la API con mensaje en español, listo para mostrar. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

const FRIENDLY_BY_STATUS: Record<number, string> = {
  400: 'La solicitud tiene un formato incorrecto.',
  404: 'No encontramos lo que buscabas.',
  413: 'El archivo es demasiado grande.',
  415: 'Ese formato de archivo no es compatible. Usa JPG, PNG o PDF.',
  422: 'Faltan datos o alguno tiene un valor inválido.',
  500: 'La API tuvo un problema interno. Intenta nuevamente.',
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getApiBaseUrl()}${path}`
  let response: Response
  try {
    response = await fetch(url, {
      ...init,
      headers: { Accept: 'application/json', ...(init?.headers || {}) },
    })
  } catch {
    throw new ApiError(
      'No pudimos conectar con la API de agentes. Revisa la URL en Ajustes o activa el modo demo.',
      0,
    )
  }

  if (!response.ok) {
    let detail: string | undefined
    try {
      detail = ((await response.json()) as { detail?: string }).detail
    } catch {
      detail = undefined
    }
    throw new ApiError(
      detail || FRIENDLY_BY_STATUS[response.status] || `La API respondió ${response.status}.`,
      response.status,
      detail,
    )
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

// --- salud y configuración ---------------------------------------------------

export async function getHealth(): Promise<Health> {
  if (isDemoMode()) return demo.DEMO_HEALTH
  return request<Health>('/api/v1/health')
}

export async function getSettings(): Promise<PublicSettings> {
  if (isDemoMode()) return demo.DEMO_SETTINGS
  return request<PublicSettings>('/api/v1/settings')
}

// --- transacciones -----------------------------------------------------------

export async function evaluateTransaction(input: TransactionInput): Promise<Decision> {
  if (isDemoMode()) {
    await new Promise((resolve) => setTimeout(resolve, 900))
    return demo.demoEvaluateTransaction(input)
  }
  return request<Decision>('/api/v1/transactions/evaluate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
}

// --- documentos --------------------------------------------------------------

export interface ValidateDocumentOptions {
  documentType?: DocumentType | ''
  referenceId?: string
  expectedFields?: Record<string, string>
}

export async function validateDocument(
  file: File,
  options: ValidateDocumentOptions = {},
): Promise<DocumentDecision> {
  if (isDemoMode()) {
    await new Promise((resolve) => setTimeout(resolve, 1600))
    return demo.demoValidateDocument(file.name)
  }
  const form = new FormData()
  form.append('file', file)
  if (options.documentType) form.append('document_type', options.documentType)
  if (options.referenceId) form.append('reference_id', options.referenceId)
  if (options.expectedFields && Object.keys(options.expectedFields).length > 0) {
    form.append('expected_fields', JSON.stringify(options.expectedFields))
  }
  return request<DocumentDecision>('/api/v1/documents/validate', { method: 'POST', body: form })
}

export async function getDocumentEvidence(traceId: string): Promise<EvidenceRegions> {
  if (isDemoMode()) {
    const detail = demo.demoCaseDetail(traceId)
    const decision = detail?.decision as DocumentDecision | undefined
    return {
      trace_id: traceId,
      pages_analyzed: decision?.pages_analyzed ?? 1,
      image_quality: decision?.image_quality ?? 1,
      findings: decision?.findings ?? [],
      artifacts_available: false,
    }
  }
  return request<EvidenceRegions>(`/api/v1/documents/${encodeURIComponent(traceId)}/evidence`)
}

/** URL directa de la página procesada. `null` en modo demo (no hay imagen real). */
export function documentPageUrl(traceId: string, page = 1): string | null {
  if (isDemoMode()) return null
  return `${getApiBaseUrl()}/api/v1/documents/${encodeURIComponent(traceId)}/page/${page}`
}

// --- casos -------------------------------------------------------------------

export interface CaseFilters {
  process?: Process | ''
  verdict?: Verdict | ''
  requiresHumanReview?: boolean
  dateFrom?: string
  dateTo?: string
  orderBy?: 'score' | 'created_at'
  limit?: number
}

export async function listCases(filters: CaseFilters = {}): Promise<CaseSummary[]> {
  if (isDemoMode()) {
    let cases = [...demo.DEMO_CASES]
    if (filters.process) cases = cases.filter((c) => c.process === filters.process)
    if (filters.verdict) cases = cases.filter((c) => c.verdict === filters.verdict)
    if (filters.requiresHumanReview !== undefined) {
      cases = cases.filter((c) => c.requires_human_review === filters.requiresHumanReview)
    }
    return filters.orderBy === 'created_at'
      ? cases.sort((a, b) => b.created_at.localeCompare(a.created_at))
      : cases.sort((a, b) => b.score - a.score)
  }

  const params = new URLSearchParams()
  if (filters.process) params.set('process', filters.process)
  if (filters.verdict) params.set('verdict', filters.verdict)
  if (filters.requiresHumanReview !== undefined) {
    params.set('requires_human_review', String(filters.requiresHumanReview))
  }
  if (filters.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters.dateTo) params.set('date_to', filters.dateTo)
  params.set('order_by', filters.orderBy || 'score')
  params.set('limit', String(filters.limit ?? 100))
  return request<CaseSummary[]>(`/api/v1/cases?${params.toString()}`)
}

export async function getCase(traceId: string): Promise<CaseDetail> {
  if (isDemoMode()) {
    const detail = demo.demoCaseDetail(traceId)
    if (!detail) throw new ApiError('Ese caso no existe en el modo demo.', 404)
    return detail
  }
  return request<CaseDetail>(`/api/v1/cases/${encodeURIComponent(traceId)}`)
}

export interface FeedbackPayload {
  trace_id: string
  label: FeedbackLabel
  analyst: string
  comment: string
}

export async function sendFeedback(
  payload: FeedbackPayload,
): Promise<{ trace_id: string; label: FeedbackLabel; indexed: boolean; message: string }> {
  if (isDemoMode()) {
    await new Promise((resolve) => setTimeout(resolve, 500))
    return {
      trace_id: payload.trace_id,
      label: payload.label,
      indexed: true,
      message: 'Feedback registrado (modo demo: no se envió a la API).',
    }
  }
  return request('/api/v1/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// --- métricas ----------------------------------------------------------------

export async function getMetrics(dateFrom?: string, dateTo?: string): Promise<Metrics> {
  if (isDemoMode()) return demo.DEMO_METRICS
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  const query = params.toString()
  return request<Metrics>(`/api/v1/metrics${query ? `?${query}` : ''}`)
}
