/**
 * Semáforo de veredicto. Nunca color solo: siempre ícono + texto, para daltonismo
 * y para lectores de pantalla.
 */

import type { Verdict } from '../lib/types'
import { VERDICT_LABEL } from '../lib/format'

type Tone = 'ok' | 'warn' | 'bad'

const TONE_BY_VERDICT: Record<Verdict, Tone> = {
  aprobar: 'ok',
  autentico: 'ok',
  validacion_adicional: 'warn',
  sospechoso: 'warn',
  bloquear: 'bad',
  falso: 'bad',
}

const STYLES: Record<Tone, string> = {
  ok: 'bg-green-50 text-green-800 border-green-200',
  warn: 'bg-amber-50 text-amber-900 border-amber-200',
  bad: 'bg-red-50 text-red-800 border-red-200',
}

const ICON: Record<Tone, string> = { ok: '✓', warn: '!', bad: '✕' }

interface Props {
  verdict: Verdict
  size?: 'sm' | 'md' | 'lg'
  shadow?: boolean
}

export function VerdictBadge({ verdict, size = 'md', shadow = false }: Props) {
  const tone = TONE_BY_VERDICT[verdict] ?? 'warn'
  const sizeClass =
    size === 'lg' ? 'text-base px-4 py-2' : size === 'sm' ? 'text-xs px-2 py-1' : 'text-sm px-3 py-1.5'

  return (
    <span className="inline-flex items-center gap-2">
      <span
        className={`inline-flex items-center gap-2 rounded-full border font-medium ${STYLES[tone]} ${sizeClass}`}
      >
        <span aria-hidden="true" className="font-bold">
          {ICON[tone]}
        </span>
        {VERDICT_LABEL[verdict] ?? verdict}
      </span>
      {shadow && (
        <span
          className="rounded-full border border-slate-300 bg-slate-100 px-2 py-1 text-xs text-slate-600"
          title="Modo sombra: el sistema registró la decisión pero no bloqueó la operación"
        >
          modo sombra
        </span>
      )}
    </span>
  )
}
