/** Línea de tiempo del caso: decisión, derivación y etiquetas del analista. */

import type { CaseDetail } from '../lib/types'
import { FEEDBACK_LABEL, formatDateTime } from '../lib/format'

export function CaseTimeline({ detail }: { detail: CaseDetail }) {
  const { decision, feedback } = detail

  const events: Array<{ title: string; detail: string; when: string; tone: string }> = [
    {
      title: 'Decisión del agente',
      detail: `Veredicto ${decision.verdict} · score ${decision.score.toFixed(3)} · ${decision.latency_ms} ms`,
      when: formatDateTime(decision.created_at),
      tone: 'bg-petrol-600',
    },
  ]

  if (decision.requires_human_review) {
    events.push({
      title: 'Derivado a revisión humana',
      detail: 'El caso entró a la bandeja del analista.',
      when: formatDateTime(decision.created_at),
      tone: 'bg-amber-500',
    })
  }

  if (decision.shadow) {
    events.push({
      title: 'Modo sombra',
      detail: 'La decisión se registró pero no afectó la operación del cliente.',
      when: formatDateTime(decision.created_at),
      tone: 'bg-slate-400',
    })
  }

  feedback.forEach((item) => {
    events.push({
      title: `Etiqueta del analista · ${FEEDBACK_LABEL[item.label] ?? item.label}`,
      detail: `${item.analyst}${item.comment ? ` — ${item.comment}` : ''}`,
      when: '',
      tone: 'bg-green-600',
    })
  })

  return (
    <ol className="space-y-4">
      {events.map((event, index) => (
        <li key={index} className="flex gap-3">
          <div className="flex flex-col items-center">
            <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${event.tone}`} aria-hidden="true" />
            {index < events.length - 1 && <span className="mt-1 w-px flex-1 bg-slate-200" aria-hidden="true" />}
          </div>
          <div className="pb-1">
            <p className="text-sm font-medium text-slate-900">{event.title}</p>
            <p className="text-sm text-slate-600">{event.detail}</p>
            {event.when && <p className="mt-0.5 text-xs text-slate-400">{event.when}</p>}
          </div>
        </li>
      ))}
    </ol>
  )
}
