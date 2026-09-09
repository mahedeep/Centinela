/** Evidencias ordenadas por peso descendente. Solo Analista y Supervisor. */

import type { Evidence } from '../lib/types'
import { EVIDENCE_TYPE_LABEL, humanizeName } from '../lib/format'

const TYPE_STYLE: Record<string, string> = {
  rule: 'bg-petrol-50 text-petrol-800 border-petrol-200',
  similarity: 'bg-violet-50 text-violet-800 border-violet-200',
  vision: 'bg-sky-50 text-sky-800 border-sky-200',
  metadata: 'bg-slate-100 text-slate-700 border-slate-200',
  consistency: 'bg-orange-50 text-orange-800 border-orange-200',
}

export function EvidenceTable({ evidence }: { evidence: Evidence[] }) {
  if (evidence.length === 0) {
    return (
      <p className="rounded-lg bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
        Ninguna señal se activó para este caso.
      </p>
    )
  }

  const ordered = [...evidence].sort((a, b) => b.weight - a.weight)

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse">
        <caption className="sr-only">Evidencias ordenadas por peso descendente</caption>
        <thead>
          <tr>
            <th scope="col" className="table-header w-32">Tipo</th>
            <th scope="col" className="table-header">Señal</th>
            <th scope="col" className="table-header w-24 text-right">Peso</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((item, index) => (
            <tr key={`${item.name}-${index}`} className="align-top">
              <td className="table-cell">
                <span
                  className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${
                    TYPE_STYLE[item.type] ?? TYPE_STYLE.metadata
                  }`}
                >
                  {EVIDENCE_TYPE_LABEL[item.type] ?? item.type}
                </span>
              </td>
              <td className="table-cell">
                <div className="font-medium text-slate-900">{humanizeName(item.name)}</div>
                <div className="mt-0.5 text-slate-600">{item.detail}</div>
              </td>
              <td className="table-cell text-right font-mono tabular-nums">
                {item.weight.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
