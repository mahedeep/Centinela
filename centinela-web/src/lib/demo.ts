/**
 * Modo demo: respuestas precargadas, sin API externa.
 *
 * Reproducen la forma exacta del contrato y los tres escenarios del kit, para
 * poder presentar sin tokens y sin backend. Los `trace_id` son fijos, de modo
 * que la bandeja y el detalle son navegables.
 */

import type {
  CaseDetail,
  CaseSummary,
  Decision,
  DocumentDecision,
  Health,
  Metrics,
  PublicSettings,
  TransactionInput,
} from './types'

const NOW = () => new Date().toISOString()

export const DEMO_HEALTH: Health = {
  status: 'ok',
  mock_mode: true,
  shadow_mode: false,
  version: '0.1.0 (demo)',
  openai_configured: false,
  models: { chat: 'demo', vision: 'demo', embedding: 'demo', ocr_engine: 'mock' },
}

const APROBAR: Decision = {
  trace_id: 'tx-demo-aprobar-0001',
  process: 'transaction',
  verdict: 'aprobar',
  score: 0.0,
  confidence: 0.55,
  reasons: ['Sin señales de riesgo relevantes en esta operación'],
  evidence: [],
  requires_human_review: false,
  shadow: false,
  explanation_customer: 'Tu operación se realizó correctamente.',
  explanation_analyst:
    'Veredicto aprobar · score 0.00 (reglas 0.00 · similitud sin datos comparables · modelo 0.00).\nEvidencias por peso:\n  · Sin señales activas.',
  model: 'demo',
  tokens_in: 512,
  tokens_out: 96,
  cost_usd: 0.0001088,
  latency_ms: 780,
  created_at: NOW(),
}

const VALIDACION: Decision = {
  trace_id: 'tx-demo-validacion-0002',
  process: 'transaction',
  verdict: 'validacion_adicional',
  score: 0.3841,
  confidence: 0.68,
  reasons: [
    'Beneficiario nuevo recibiendo 1,39× el promedio mensual del cliente',
    'Primera transferencia hacia esta cuenta de destino',
  ],
  evidence: [
    {
      type: 'rule',
      name: 'new_beneficiary_amount_above_average',
      value: true,
      weight: 0.45,
      detail: 'Beneficiario nuevo recibiendo 1.3889× el promedio mensual del cliente',
    },
    {
      type: 'rule',
      name: 'new_beneficiary',
      value: true,
      weight: 0.1,
      detail: 'Primera transferencia hacia esta cuenta de destino',
    },
  ],
  requires_human_review: false,
  shadow: false,
  explanation_customer:
    'Para confirmar que eres tú, vamos a pedirte un código de verificación antes de completar la operación.',
  explanation_analyst:
    'Veredicto validacion_adicional · score 0.38 (reglas 0.37 · similitud sin datos comparables · modelo 0.37).\nEvidencias por peso:\n  · [rule] new_beneficiary_amount_above_average (0.45) — Beneficiario nuevo recibiendo 1.3889× el promedio mensual\n  · [rule] new_beneficiary (0.10) — Primera transferencia hacia esta cuenta de destino',
  model: 'demo',
  tokens_in: 640,
  tokens_out: 128,
  cost_usd: 0.0001408,
  latency_ms: 910,
  created_at: NOW(),
}

const BLOQUEAR: Decision = {
  trace_id: 'tx-demo-bloquear-0003',
  process: 'transaction',
  verdict: 'bloquear',
  score: 0.9216,
  confidence: 0.9,
  reasons: [
    'Dispositivo nuevo y beneficiario nuevo en la misma sesión: combinación típica de toma de cuenta',
    'Monto 4.3333× el promedio mensual de la cuenta',
    'La conexión proviene de un país distinto al de la cuenta',
    '5 intentos de acceso fallidos en 24 horas',
  ],
  evidence: [
    {
      type: 'rule',
      name: 'new_beneficiary_amount_above_average',
      value: true,
      weight: 0.45,
      detail: 'Beneficiario nuevo recibiendo 4.3333× el promedio mensual del cliente',
    },
    {
      type: 'rule',
      name: 'new_device_and_new_beneficiary',
      value: true,
      weight: 0.3,
      detail: 'Dispositivo nuevo y beneficiario nuevo en la misma sesión: combinación típica de toma de cuenta',
    },
    {
      type: 'rule',
      name: 'amount_over_3x_average',
      value: true,
      weight: 0.25,
      detail: 'Monto 4.3333× el promedio mensual de la cuenta',
    },
    {
      type: 'rule',
      name: 'ip_country_mismatch',
      value: true,
      weight: 0.22,
      detail: 'La conexión proviene de un país distinto al de la cuenta',
    },
    {
      type: 'rule',
      name: 'failed_logins_3_or_more',
      value: true,
      weight: 0.18,
      detail: '5 intentos de acceso fallidos en 24 horas',
    },
    {
      type: 'rule',
      name: 'vpn_with_high_amount',
      value: true,
      weight: 0.16,
      detail: 'VPN activa en una operación de monto alto',
    },
    {
      type: 'similarity',
      name: 'similar_confirmed_fraud',
      value: ['a1b2c3d4', 'e5f60718'],
      weight: 0.24,
      detail: 'Patrón similar a 2 fraude(s) confirmado(s) (similitud máxima 0.81)',
    },
  ],
  requires_human_review: true,
  shadow: false,
  explanation_customer:
    'Por seguridad dejamos esta operación en pausa mientras la revisamos. Un ejecutivo puede confirmarla contigo cuando quieras.',
  explanation_analyst:
    'Veredicto bloquear · score 0.92 (reglas 0.87 · similitud 0.81 · modelo 0.95).\nEvidencias por peso:\n  · [rule] new_beneficiary_amount_above_average (0.45)\n  · [rule] new_device_and_new_beneficiary (0.30)\n  · [similarity] similar_confirmed_fraud (0.24)',
  model: 'demo',
  tokens_in: 812,
  tokens_out: 186,
  cost_usd: 0.0001928,
  latency_ms: 1240,
  created_at: NOW(),
}

const DOC_AUTENTICO: DocumentDecision = {
  trace_id: 'doc-demo-autentico-0001',
  process: 'document',
  verdict: 'autentico',
  score: 0.0269,
  confidence: 0.83,
  reasons: ['Campos extraídos consistentes y sin señales de alteración visibles'],
  evidence: [],
  requires_human_review: false,
  shadow: false,
  explanation_customer: 'Tu documento fue validado correctamente. No necesitas hacer nada más.',
  explanation_analyst:
    'Veredicto autentico · score 0.03 (forense 0.05 · checks 0.00 · modelo 0.03).\nVerificaciones:\n  · PASS rut_modulo_11 — RUT 12.345.678-5 válido por módulo 11.\n  · PASS date_consistency — Las fechas extraídas son coherentes.',
  model: 'demo',
  tokens_in: 1840,
  tokens_out: 210,
  cost_usd: 0.000310,
  latency_ms: 4300,
  created_at: NOW(),
  document_type_detected: 'cedula',
  fields: {
    nombre: { value: 'MARÍA FICTICIA PÉREZ DE PRUEBA', confidence: 0.95, source: 'vision' },
    rut: { value: '12.345.678-5', confidence: 0.94, source: 'vision' },
    fecha_emision: { value: '05/01/2022', confidence: 0.92, source: 'vision' },
    fecha_vencimiento: { value: '05/01/2032', confidence: 0.9, source: 'vision' },
  },
  checks: [
    { name: 'rut_modulo_11', status: 'pass', detail: 'RUT 12.345.678-5 válido por módulo 11.', critical: true },
    { name: 'date_consistency', status: 'pass', detail: 'Las fechas extraídas son coherentes entre sí y con la fecha actual.', critical: true },
    { name: 'arithmetic_consistency', status: 'pending', detail: 'No aplica a este tipo de documento.', critical: true },
    { name: 'expected_fields_match', status: 'pending', detail: 'No se entregaron campos esperados para cruzar.', critical: true },
    { name: 'format_by_type', status: 'pass', detail: '1 campo(s) con el formato esperado para «cedula».', critical: false },
    { name: 'metadata_coherence', status: 'pass', detail: 'Los metadatos del archivo no muestran señales de edición.', critical: false },
    { name: 'signature_match', status: 'pending', detail: 'No se entregó una firma de referencia para comparar.', critical: true },
  ],
  findings: [],
  pages_analyzed: 1,
  image_quality: 0.96,
}

const DOC_FALSO: DocumentDecision = {
  trace_id: 'doc-demo-falso-0002',
  process: 'document',
  verdict: 'falso',
  score: 0.8602,
  confidence: 0.88,
  reasons: [
    'Verificación en falla: arithmetic_consistency',
    'Hallazgo forense: digit_retouch',
  ],
  evidence: [
    {
      type: 'consistency',
      name: 'arithmetic_consistency',
      value: 'fail',
      weight: 0.35,
      detail:
        'La suma no cuadra: bruto 1.850.000 − descuentos 370.000 = 1.480.000, pero el documento declara 1.780.000.',
    },
    {
      type: 'vision',
      name: 'digit_retouch',
      value: { page: 1, x: 0.58, y: 0.6, width: 0.28, height: 0.08 },
      weight: 0.74,
      detail: 'Los dígitos del monto líquido presentan compresión distinta al resto de la tabla.',
    },
  ],
  requires_human_review: true,
  shadow: false,
  explanation_customer:
    'No pudimos validar este documento en línea. Un ejecutivo te contactará para revisarlo contigo.',
  explanation_analyst:
    'Veredicto falso · score 0.86 (forense 0.74 · checks 1.00 · modelo 0.86).\nVerificaciones:\n  · FAIL [CRÍTICO] arithmetic_consistency — La suma no cuadra.\nHallazgos forenses:\n  · digit_retouch (confianza 0.74) · región p1 (0.58, 0.60)',
  model: 'demo',
  tokens_in: 1920,
  tokens_out: 240,
  cost_usd: 0.000336,
  latency_ms: 4800,
  created_at: NOW(),
  document_type_detected: 'liquidacion',
  fields: {
    nombre: { value: 'MARÍA FICTICIA PÉREZ DE PRUEBA', confidence: 0.94, source: 'vision' },
    rut: { value: '12.345.678-5', confidence: 0.93, source: 'vision' },
    monto_bruto: { value: '$ 1.850.000', confidence: 0.91, source: 'vision' },
    monto_descuentos: { value: '$ 370.000', confidence: 0.9, source: 'vision' },
    monto_liquido: { value: '$ 1.780.000', confidence: 0.89, source: 'vision' },
  },
  checks: [
    { name: 'rut_modulo_11', status: 'pass', detail: 'RUT 12.345.678-5 válido por módulo 11.', critical: true },
    { name: 'date_consistency', status: 'pass', detail: 'Las fechas extraídas son coherentes.', critical: true },
    {
      name: 'arithmetic_consistency',
      status: 'fail',
      detail:
        'La suma no cuadra: bruto 1.850.000 − descuentos 370.000 = 1.480.000, pero el documento declara 1.780.000.',
      critical: true,
    },
    { name: 'expected_fields_match', status: 'pending', detail: 'No se entregaron campos esperados.', critical: true },
    { name: 'format_by_type', status: 'pass', detail: 'Formato esperado para «liquidacion».', critical: false },
    { name: 'metadata_coherence', status: 'pass', detail: 'Sin señales de edición en los metadatos.', critical: false },
    { name: 'signature_match', status: 'pending', detail: 'Sin firma de referencia.', critical: true },
  ],
  findings: [
    {
      name: 'digit_retouch',
      detail: 'Los dígitos del monto líquido presentan compresión distinta al resto de la tabla.',
      confidence: 0.74,
      region: { page: 1, x: 0.58, y: 0.6, width: 0.28, height: 0.08 },
    },
  ],
  pages_analyzed: 1,
  image_quality: 0.96,
}

const DOC_SOSPECHOSO: DocumentDecision = {
  ...DOC_AUTENTICO,
  trace_id: 'doc-demo-sospechoso-0003',
  verdict: 'sospechoso',
  score: 0.1194,
  reasons: [
    'Verificación en advertencia: metadata_coherence',
    'metadatos con señales de edición: solicitar el documento original',
  ],
  requires_human_review: true,
  document_type_detected: 'comprobante_domicilio',
  explanation_customer:
    'Necesitamos revisar este documento con más detalle. Si puedes, súbelo nuevamente desde el original.',
  explanation_analyst:
    'Veredicto sospechoso · score 0.12 (forense 0.05 · checks 0.20 · modelo 0.12).\nCompuertas aplicadas: metadatos con señales de edición.',
  checks: DOC_AUTENTICO.checks.map((c) =>
    c.name === 'metadata_coherence'
      ? {
          ...c,
          status: 'warn' as const,
          detail: 'Metadatos con señales de edición: los metadatos declaran software de edición de imagen (Adobe Photoshop 26.0).',
        }
      : c,
  ),
  evidence: [
    {
      type: 'metadata',
      name: 'metadata_coherence',
      value: 'warn',
      weight: 0.15,
      detail: 'Metadatos con señales de edición: software de edición de imagen (Adobe Photoshop 26.0).',
    },
  ],
}

/** Elige el escenario de demo según el perfil de riesgo de la entrada. */
export function demoEvaluateTransaction(input: TransactionInput): Decision {
  const ratio = input.amount / Math.max(input.origin_account.avg_monthly_amount, 1)
  const risky =
    input.device.is_new_device &&
    input.destination_account.is_new_beneficiary &&
    (input.device.vpn || input.device.ip_country !== input.origin_account.country)

  const base = risky || ratio > 3 ? BLOQUEAR : input.destination_account.is_new_beneficiary && ratio > 1.2 ? VALIDACION : APROBAR
  return { ...base, trace_id: `${base.trace_id}-${Date.now().toString(36)}`, created_at: NOW() }
}

/** Elige el documento de demo según el nombre del archivo. */
export function demoValidateDocument(filename: string): DocumentDecision {
  const name = filename.toLowerCase()
  const base = name.includes('montos') || name.includes('falso') || name.includes('alterad')
    ? DOC_FALSO
    : name.includes('metadat') || name.includes('sospech')
      ? DOC_SOSPECHOSO
      : DOC_AUTENTICO
  return { ...base, trace_id: `${base.trace_id}-${Date.now().toString(36)}`, created_at: NOW() }
}

export const DEMO_DECISIONS: Array<Decision | DocumentDecision> = [
  BLOQUEAR,
  DOC_FALSO,
  VALIDACION,
  DOC_SOSPECHOSO,
  APROBAR,
  DOC_AUTENTICO,
]

export const DEMO_CASES: CaseSummary[] = DEMO_DECISIONS.map((d, index) => ({
  trace_id: d.trace_id,
  process: d.process,
  verdict: d.verdict,
  score: d.score,
  confidence: d.confidence,
  requires_human_review: d.requires_human_review,
  shadow: d.shadow,
  created_at: new Date(Date.now() - index * 1000 * 60 * 17).toISOString(),
  cost_usd: d.cost_usd,
  latency_ms: d.latency_ms,
  feedback_label: null,
  age_seconds: index * 1020 + 240,
}))

export function demoCaseDetail(traceId: string): CaseDetail | null {
  const decision = DEMO_DECISIONS.find((d) => d.trace_id === traceId)
  if (!decision) return null
  const isTransaction = decision.process === 'transaction'
  return {
    decision,
    inputs: isTransaction
      ? { transaction_id: 'TX-000777', amount: 3900000, currency: 'CLP', channel: 'web' }
      : { filename: 'liquidacion_montos_editados.png', size_bytes: 148223 },
    prompts: {
      system: '(modo demo · los prompts reales viven en la traza de la API)',
      version: isTransaction ? 'tx-2026.09.09-v1' : 'doc-2026.09.09-v1',
    },
    prompt_version: isTransaction ? 'tx-2026.09.09-v1' : 'doc-2026.09.09-v1',
    weights: isTransaction
      ? { rules: 0.45, similarity: 0.25, model: 0.3, score_rules: 0.8712, score_similarity: 0.81, score_model: 0.9512 }
      : { vision: 0.4, checks: 0.35, model: 0.25, score_vision: 0.74, score_checks: 1.0, score_model: 0.86 },
    neighbors: isTransaction
      ? [
          { id: 'a1b2c3d4e5f60718', label: 'fraude', similarity: 0.81, meta: { patron: 'account_takeover' } },
          { id: 'b2c3d4e5f6071829', label: 'fraude', similarity: 0.62, meta: { patron: 'cuenta_mula' } },
        ]
      : [],
    extra: {},
    feedback: [],
  }
}

export const DEMO_METRICS: Metrics = {
  generated_at: NOW(),
  total_volume: 312,
  total_cost_usd: 0.041233,
  cost_per_event_usd: 0.00013215,
  feedback_count: 14,
  estimated_accuracy: 0.857,
  shadow_would_block: 11,
  shadow_approved: 46,
  by_process: [
    {
      process: 'transaction',
      volume: 300,
      block_rate: 0.06,
      human_review_rate: 0.06,
      latency_p50_ms: 840,
      latency_p95_ms: 1460,
      cost_usd: 0.0378,
      cost_per_event_usd: 0.000126,
      verdicts: [
        { verdict: 'aprobar', count: 273 },
        { verdict: 'bloquear', count: 18 },
        { verdict: 'validacion_adicional', count: 9 },
      ],
    },
    {
      process: 'document',
      volume: 12,
      block_rate: 0.333,
      human_review_rate: 0.5,
      latency_p50_ms: 4300,
      latency_p95_ms: 5900,
      cost_usd: 0.003433,
      cost_per_event_usd: 0.000286,
      verdicts: [
        { verdict: 'autentico', count: 6 },
        { verdict: 'falso', count: 4 },
        { verdict: 'sospechoso', count: 2 },
      ],
    },
  ],
  by_model: [
    { model: 'demo-chat', events: 300, tokens_in: 200453, tokens_out: 26628, cost_usd: 0.0378 },
    { model: 'demo-vision', events: 12, tokens_in: 22400, tokens_out: 2640, cost_usd: 0.003433 },
  ],
  top_evidence: [
    { name: 'new_beneficiary', count: 41 },
    { name: 'new_beneficiary_amount_above_average', count: 27 },
    { name: 'amount_over_3x_average', count: 19 },
    { name: 'ip_country_mismatch', count: 14 },
    { name: 'failed_logins_3_or_more', count: 11 },
    { name: 'similar_confirmed_fraud', count: 9 },
    { name: 'session_under_20_seconds', count: 7 },
  ],
  timeseries: (() => {
    const out: Metrics['timeseries'] = []
    for (let day = 6; day >= 0; day -= 1) {
      const date = new Date(Date.now() - day * 86_400_000).toISOString().slice(0, 10)
      out.push({ date, verdict: 'aprobar', count: 32 + ((day * 7) % 11) })
      out.push({ date, verdict: 'validacion_adicional', count: 1 + (day % 3) })
      out.push({ date, verdict: 'bloquear', count: 1 + ((day * 3) % 4) })
    }
    return out
  })(),
}

export const DEMO_SETTINGS: PublicSettings = {
  mock_mode: true,
  shadow_mode: false,
  thresholds: { review: 0.35, block: 0.7 },
  weights: {
    transactions: { rules: 0.45, similarity: 0.25, model: 0.3 },
    documents: { vision: 0.4, checks: 0.35, model: 0.25 },
  },
  documents: {
    max_upload_mb: 10,
    max_pdf_pages: 5,
    min_image_quality: 0.4,
    ocr_engine: 'vision',
    trace_retention_days: 7,
  },
  pricing_usd_per_1m_tokens: {
    chat_input: 0.1,
    chat_output: 0.6,
    embedding_input: 0.02,
    nota: 'Verificar contra la lista de precios vigente de OpenAI.',
  },
  team: 'Grupo Centinela (demo)',
}
