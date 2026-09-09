/**
 * Tipos derivados del contrato `openapi.json` de la API de agentes.
 *
 * Si el backend cambia el contrato, este archivo es lo primero que hay que
 * actualizar. Nada del front debe inventar campos que el contrato no tenga.
 */

export type Process = 'transaction' | 'document'

export type TransactionVerdict = 'aprobar' | 'validacion_adicional' | 'bloquear'
export type DocumentVerdict = 'autentico' | 'sospechoso' | 'falso'
export type Verdict = TransactionVerdict | DocumentVerdict

export type EvidenceType = 'rule' | 'similarity' | 'vision' | 'metadata' | 'consistency'
export type CheckStatus = 'pass' | 'fail' | 'warn' | 'pending'

export type FeedbackLabel =
  | 'fraude_confirmado'
  | 'legitimo'
  | 'documento_falso'
  | 'documento_autentico'

export interface Evidence {
  type: EvidenceType
  name: string
  value: unknown
  weight: number
  detail: string
}

export interface Region {
  page: number
  x: number
  y: number
  width: number
  height: number
}

export interface Finding {
  name: string
  detail: string
  confidence: number
  region: Region | null
}

export interface Check {
  name: string
  status: CheckStatus
  detail: string
  critical: boolean
}

export interface FieldValue {
  value: string
  confidence: number
  source: 'vision' | 'ocr' | 'metadata' | 'expected'
}

export interface Decision {
  trace_id: string
  process: Process
  verdict: Verdict
  score: number
  confidence: number
  reasons: string[]
  evidence: Evidence[]
  requires_human_review: boolean
  shadow: boolean
  /** Único texto que el rol Cliente puede ver. */
  explanation_customer: string
  explanation_analyst: string
  model: string
  tokens_in: number
  tokens_out: number
  cost_usd: number
  latency_ms: number
  created_at: string
}

export interface DocumentDecision extends Decision {
  document_type_detected: DocumentType
  fields: Record<string, FieldValue>
  checks: Check[]
  findings: Finding[]
  pages_analyzed: number
  image_quality: number
}

export type DocumentType =
  | 'cedula'
  | 'comprobante_domicilio'
  | 'contrato'
  | 'poder'
  | 'liquidacion'
  | 'firma'
  | 'otro'

export interface CaseSummary {
  trace_id: string
  process: Process
  verdict: Verdict
  score: number
  confidence: number
  requires_human_review: boolean
  shadow: boolean
  created_at: string
  cost_usd: number
  latency_ms: number
  feedback_label: FeedbackLabel | null
  age_seconds: number
}

export interface CaseDetail {
  decision: Decision | DocumentDecision
  inputs: Record<string, unknown>
  prompts: Record<string, unknown>
  prompt_version: string
  weights: Record<string, number | null>
  neighbors: Array<{ id: string; label: string; similarity: number; meta: Record<string, unknown> }>
  extra: Record<string, unknown>
  feedback: Array<{ trace_id: string; label: FeedbackLabel; analyst: string; comment: string }>
}

export interface EvidenceRegions {
  trace_id: string
  pages_analyzed: number
  image_quality: number
  findings: Finding[]
  artifacts_available: boolean
}

export interface Health {
  status: 'ok' | 'degraded'
  mock_mode: boolean
  shadow_mode: boolean
  version: string
  openai_configured: boolean
  models: Record<string, string>
}

export interface ProcessMetrics {
  process: Process
  volume: number
  block_rate: number
  human_review_rate: number
  latency_p50_ms: number
  latency_p95_ms: number
  cost_usd: number
  cost_per_event_usd: number
  verdicts: Array<{ verdict: string; count: number }>
}

export interface Metrics {
  generated_at: string
  total_volume: number
  total_cost_usd: number
  cost_per_event_usd: number
  feedback_count: number
  estimated_accuracy: number | null
  shadow_would_block: number
  shadow_approved: number
  by_process: ProcessMetrics[]
  by_model: Array<{
    model: string
    events: number
    tokens_in: number
    tokens_out: number
    cost_usd: number
  }>
  top_evidence: Array<{ name: string; count: number }>
  timeseries: Array<{ date: string; verdict: string; count: number }>
}

export interface PublicSettings {
  mock_mode: boolean
  shadow_mode: boolean
  thresholds: { review: number; block: number }
  weights: {
    transactions: { rules: number; similarity: number; model: number }
    documents: { vision: number; checks: number; model: number }
  }
  documents: {
    max_upload_mb: number
    max_pdf_pages: number
    min_image_quality: number
    ocr_engine: string
    trace_retention_days: number
  }
  pricing_usd_per_1m_tokens: Record<string, number | string>
  team: string
}

/** Entrada de `POST /transactions/evaluate`. */
export interface TransactionInput {
  transaction_id: string
  timestamp: string
  amount: number
  currency: string
  channel: 'app_movil' | 'web' | 'cajero' | 'sucursal' | 'call_center' | 'api'
  type: 'transferencia' | 'pago' | 'retiro' | 'compra'
  origin_account: {
    id: string
    age_days: number
    avg_monthly_amount: number
    country: string
  }
  destination_account: {
    id: string
    bank: string
    is_new_beneficiary: boolean
    country: string
  }
  device: {
    id: string
    is_new_device: boolean
    os: string
    ip_country: string
    vpn: boolean
  }
  geo: { lat?: number; lon?: number; distance_from_home_km: number }
  behavior: {
    tx_last_hour: number
    tx_last_24h: number
    failed_logins_24h: number
    session_seconds: number
  }
  customer_profile: {
    segment: 'persona_natural' | 'empresa'
    risk_tier: 'bajo' | 'medio' | 'alto'
  }
}

export type Role = 'cliente' | 'analista' | 'supervisor'
