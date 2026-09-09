/** Tarjeta de KPI del dashboard del Supervisor. */

interface Props {
  label: string
  value: string
  hint?: string
  tone?: 'neutral' | 'ok' | 'warn' | 'bad'
}

const TONE: Record<NonNullable<Props['tone']>, string> = {
  neutral: 'text-slate-900',
  ok: 'text-green-700',
  warn: 'text-amber-700',
  bad: 'text-red-700',
}

export function KpiTile({ label, value, hint, tone = 'neutral' }: Props) {
  return (
    <div className="card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${TONE[tone]}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  )
}
