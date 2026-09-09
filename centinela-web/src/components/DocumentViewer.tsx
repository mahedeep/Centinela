/**
 * Visor de documento con los hallazgos forenses dibujados como recuadros.
 *
 * Las regiones vienen normalizadas (0–1), así que se posicionan en porcentaje y
 * siguen siendo correctas a cualquier tamaño de render.
 */

import { useState } from 'react'
import type { Finding } from '../lib/types'
import { humanizeName } from '../lib/format'

interface Props {
  imageUrl: string | null
  findings: Finding[]
  page?: number
  artifactsAvailable?: boolean
  retentionDays?: number
}

export function DocumentViewer({
  imageUrl,
  findings,
  page = 1,
  artifactsAvailable = true,
  retentionDays = 7,
}: Props) {
  const [selected, setSelected] = useState<number | null>(null)
  const [failed, setFailed] = useState(false)

  const visible = findings.filter((f) => f.region && f.region.page === page)
  const canRender = Boolean(imageUrl) && artifactsAvailable && !failed

  return (
    <div className="space-y-3">
      {canRender ? (
        <div className="relative overflow-hidden rounded-lg border border-slate-200 bg-slate-100">
          <img
            src={imageUrl as string}
            alt={`Página ${page} del documento en revisión`}
            className="block w-full"
            onError={() => setFailed(true)}
          />
          {visible.map((finding, index) => {
            const region = finding.region!
            const active = selected === index
            return (
              <button
                key={`${finding.name}-${index}`}
                type="button"
                onClick={() => setSelected(active ? null : index)}
                aria-pressed={active}
                title={finding.detail}
                className={`absolute rounded border-2 transition-colors ${
                  active
                    ? 'border-red-600 bg-red-500/25'
                    : 'border-red-500 bg-red-500/10 hover:bg-red-500/20'
                }`}
                style={{
                  left: `${region.x * 100}%`,
                  top: `${region.y * 100}%`,
                  width: `${region.width * 100}%`,
                  height: `${region.height * 100}%`,
                }}
              >
                <span className="absolute -top-6 left-0 whitespace-nowrap rounded bg-red-600 px-1.5 py-0.5 text-[11px] font-medium text-white">
                  {humanizeName(finding.name)} · {finding.confidence.toFixed(2)}
                </span>
              </button>
            )
          })}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center">
          <p className="text-sm font-medium text-slate-700">
            {artifactsAvailable
              ? 'La imagen del documento no está disponible.'
              : 'La imagen ya fue eliminada.'}
          </p>
          <p className="mt-1 text-sm text-slate-500">
            {artifactsAvailable
              ? 'Los hallazgos se muestran igual en la lista de abajo.'
              : `La retención de ${retentionDays} días venció y las imágenes procesadas se borraron. Los hallazgos quedan registrados.`}
          </p>
        </div>
      )}

      {visible.length > 0 ? (
        <ul className="space-y-2">
          {visible.map((finding, index) => (
            <li
              key={`detalle-${finding.name}-${index}`}
              className={`rounded-lg border px-3 py-2 text-sm ${
                selected === index ? 'border-red-300 bg-red-50' : 'border-slate-200 bg-white'
              }`}
            >
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-medium text-slate-900">{humanizeName(finding.name)}</span>
                <span className="font-mono text-xs tabular-nums text-slate-500">
                  confianza {finding.confidence.toFixed(2)}
                </span>
              </div>
              <p className="mt-1 text-slate-600">{finding.detail}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-500">
          El análisis forense no encontró señales de alteración en esta página.
        </p>
      )}
    </div>
  )
}
