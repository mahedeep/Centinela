/** Verificaciones deterministas con su estado. Solo Analista y Supervisor. */

import type { Check, CheckStatus } from '../lib/types'
import { CHECK_LABEL } from '../lib/format'

const STATUS: Record<CheckStatus, { label: string; icon: string; className: string }> = {
  pass: { label: 'Aprobado', icon: '✓', className: 'bg-green-50 text-green-800 border-green-200' },
  fail: { label: 'Falla', icon: '✕', className: 'bg-red-50 text-red-800 border-red-200' },
  warn: { label: 'Advertencia', icon: '!', className: 'bg-amber-50 text-amber-900 border-amber-200' },
  pending: {
    label: 'Pendiente',
    icon: '–',
    className: 'bg-slate-100 text-slate-600 border-slate-200',
  },
}

export function ChecksTable({ checks }: { checks: Check[] }) {
  if (checks.length === 0) {
    return <p className="text-sm text-slate-500">Este caso no tiene verificaciones asociadas.</p>
  }

  // Primero lo que exige atención: falla, advertencia, pendiente, aprobado.
  const order: Record<CheckStatus, number> = { fail: 0, warn: 1, pending: 2, pass: 3 }
  const ordered = [...checks].sort((a, b) => order[a.status] - order[b.status])

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] border-collapse">
        <caption className="sr-only">Verificaciones deterministas del documento</caption>
        <thead>
          <tr>
            <th scope="col" className="table-header w-36">Estado</th>
            <th scope="col" className="table-header">Verificación</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((check) => {
            const style = STATUS[check.status]
            return (
              <tr key={check.name} className="align-top">
                <td className="table-cell">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs font-medium ${style.className}`}
                  >
                    <span aria-hidden="true" className="font-bold">{style.icon}</span>
                    {style.label}
                  </span>
                </td>
                <td className="table-cell">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-slate-900">
                      {CHECK_LABEL[check.name] ?? check.name}
                    </span>
                    {check.critical && (
                      <span
                        className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white"
                        title="Si esta verificación falla, el veredicto mínimo es sospechoso"
                      >
                        crítica
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-slate-600">{check.detail}</p>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
