/**
 * Medidor de score con los umbrales marcados.
 *
 * Solo para Analista y Supervisor: el rol Cliente jamás ve el score.
 */

interface Props {
  score: number
  reviewThreshold?: number
  blockThreshold?: number
  label?: string
}

export function ScoreMeter({
  score,
  reviewThreshold = 0.35,
  blockThreshold = 0.7,
  label = 'Score de riesgo',
}: Props) {
  const percent = Math.max(0, Math.min(1, score)) * 100
  const tone =
    score >= blockThreshold ? 'bg-red-600' : score >= reviewThreshold ? 'bg-amber-500' : 'bg-green-600'

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        <span className="font-mono text-lg font-semibold tabular-nums text-slate-900">
          {score.toFixed(3)}
        </span>
      </div>

      <div
        className="relative h-3 w-full overflow-hidden rounded-full bg-slate-200"
        role="meter"
        aria-valuenow={Number(score.toFixed(3))}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-label={label}
      >
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${percent}%` }} />
        <div
          className="absolute top-0 h-full w-px bg-slate-500"
          style={{ left: `${reviewThreshold * 100}%` }}
          aria-hidden="true"
        />
        <div
          className="absolute top-0 h-full w-px bg-slate-700"
          style={{ left: `${blockThreshold * 100}%` }}
          aria-hidden="true"
        />
      </div>

      <div className="mt-1 flex justify-between text-xs text-slate-500">
        <span>0</span>
        <span>revisión {reviewThreshold}</span>
        <span>bloqueo {blockThreshold}</span>
        <span>1</span>
      </div>
    </div>
  )
}
