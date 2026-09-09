/** Formateadores para español de Chile. */

const CLP = new Intl.NumberFormat('es-CL', {
  style: 'currency',
  currency: 'CLP',
  maximumFractionDigits: 0,
})

const DATE_TIME = new Intl.DateTimeFormat('es-CL', {
  dateStyle: 'short',
  timeStyle: 'short',
})

export const formatCLP = (amount: number): string => CLP.format(amount)

export const formatPercent = (value: number, digits = 1): string =>
  `${(value * 100).toFixed(digits)} %`

export const formatDateTime = (iso: string): string => {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '—' : DATE_TIME.format(date)
}

/** Costos que suelen ser muy pequeños: se muestran con dígitos significativos. */
export const formatUsd = (amount: number): string => {
  if (amount === 0) return 'USD 0'
  if (amount < 0.0001) return `USD ${amount.toExponential(2)}`
  if (amount < 1) return `USD ${amount.toFixed(6)}`
  return `USD ${amount.toFixed(2)}`
}

/** Antigüedad de un caso, para el indicador de SLA. */
export const formatAge = (seconds: number): string => {
  if (seconds < 60) return `${Math.round(seconds)} s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  if (seconds < 86_400) return `${Math.round(seconds / 3600)} h`
  return `${Math.round(seconds / 86_400)} d`
}

/** `new_beneficiary_amount_above_average` → `New beneficiary amount above average` */
export const humanizeName = (name: string | null | undefined): string => {
  const spaced = String(name ?? '').replace(/_/g, ' ').trim()
  if (!spaced) return '—'
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export const VERDICT_LABEL: Record<string, string> = {
  aprobar: 'Aprobada',
  validacion_adicional: 'Validación adicional',
  bloquear: 'Bloqueada',
  autentico: 'Auténtico',
  sospechoso: 'Sospechoso',
  falso: 'Falso',
}

export const PROCESS_LABEL: Record<string, string> = {
  transaction: 'Transacción',
  document: 'Documento',
}

export const CHECK_LABEL: Record<string, string> = {
  rut_modulo_11: 'RUT · módulo 11',
  date_consistency: 'Consistencia de fechas',
  arithmetic_consistency: 'Consistencia aritmética',
  expected_fields_match: 'Cruce con datos declarados',
  format_by_type: 'Formato por tipo de documento',
  metadata_coherence: 'Metadatos del archivo',
  signature_match: 'Comparación de firma',
}

export const EVIDENCE_TYPE_LABEL: Record<string, string> = {
  rule: 'Regla',
  similarity: 'Similitud',
  vision: 'Visión',
  metadata: 'Metadatos',
  consistency: 'Consistencia',
}

export const FEEDBACK_LABEL: Record<string, string> = {
  fraude_confirmado: 'Fraude confirmado',
  legitimo: 'Legítimo',
  documento_falso: 'Documento falso',
  documento_autentico: 'Documento auténtico',
}
