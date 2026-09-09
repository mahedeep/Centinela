/**
 * Cliente · subir un documento.
 *
 * PROHIBIDO mostrar checks, hallazgos forenses, score o calidad de imagen. El
 * cliente solo recibe una instrucción de qué hacer.
 */

import { useEffect, useRef, useState } from 'react'
import { ApiError, validateDocument } from '../lib/api'
import type { DocumentDecision, DocumentType } from '../lib/types'

const TIPOS: Array<{ value: DocumentType | ''; label: string }> = [
  { value: '', label: 'Que el sistema lo detecte' },
  { value: 'cedula', label: 'Cédula de identidad' },
  { value: 'comprobante_domicilio', label: 'Comprobante de domicilio' },
  { value: 'contrato', label: 'Contrato' },
  { value: 'poder', label: 'Poder' },
  { value: 'liquidacion', label: 'Liquidación de sueldo' },
  { value: 'firma', label: 'Firma' },
  { value: 'otro', label: 'Otro' },
]

const MAX_MB = 10
const ACCEPTED = ['image/jpeg', 'image/png', 'application/pdf']

const ETAPAS = ['Leyendo', 'Verificando', 'Resultado'] as const

export function ClienteDocumento() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [documentType, setDocumentType] = useState<DocumentType | ''>('')
  const [decision, setDecision] = useState<DocumentDecision | null>(null)
  const [stage, setStage] = useState(-1)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!file || file.type === 'application/pdf') {
      setPreview(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const accept = (candidate: File | undefined) => {
    setError(null)
    setDecision(null)
    if (!candidate) return
    if (!ACCEPTED.includes(candidate.type)) {
      setError('Ese formato no sirve. Sube una foto JPG o PNG, o un archivo PDF.')
      return
    }
    if (candidate.size > MAX_MB * 1024 * 1024) {
      setError(`El archivo pesa más de ${MAX_MB} MB. Intenta con una foto de menor resolución.`)
      return
    }
    setFile(candidate)
  }

  const submit = async () => {
    if (!file) return
    setError(null)
    setDecision(null)
    setStage(0)

    // Las etapas son informativas: la llamada es una sola.
    const timers = [
      window.setTimeout(() => setStage(1), 900),
      window.setTimeout(() => setStage(2), 2200),
    ]
    try {
      const result = await validateDocument(file, { documentType })
      setDecision(result)
      setStage(2)
    } catch (exception) {
      setError(
        exception instanceof ApiError
          ? exception.message
          : 'No pudimos revisar el documento. Intenta nuevamente.',
      )
      setStage(-1)
    } finally {
      timers.forEach(window.clearTimeout)
    }
  }

  const reset = () => {
    setFile(null)
    setPreview(null)
    setDecision(null)
    setStage(-1)
    setError(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const working = stage >= 0 && !decision && !error

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Subir un documento</h1>
        <p className="mt-1 text-sm text-slate-600">
          JPG, PNG o PDF de hasta {MAX_MB} MB. Tómale la foto con buena luz y sin reflejos.
        </p>
      </header>

      {!decision && (
        <>
          <div
            onDragOver={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              accept(event.dataTransfer.files[0])
            }}
            className={`card border-2 border-dashed p-8 text-center transition-colors ${
              dragging ? 'border-petrol-500 bg-petrol-50' : 'border-slate-300'
            }`}
          >
            <p className="text-sm text-slate-600">Arrastra el archivo aquí, o</p>
            <button
              type="button"
              className="btn-secondary mt-3"
              onClick={() => inputRef.current?.click()}
            >
              Elegir archivo
            </button>
            <input
              ref={inputRef}
              type="file"
              accept=".jpg,.jpeg,.png,.pdf"
              className="sr-only"
              onChange={(event) => accept(event.target.files?.[0])}
            />
            {file && (
              <p className="mt-4 text-sm font-medium text-slate-800">
                {file.name} · {(file.size / 1024).toFixed(0)} KB
              </p>
            )}
          </div>

          {preview && (
            <div className="card overflow-hidden">
              <img src={preview} alt="Vista previa del documento" className="block w-full" />
            </div>
          )}

          <div className="card p-5">
            <label className="field-label" htmlFor="tipo-doc">¿Qué documento es?</label>
            <select
              id="tipo-doc"
              className="field-input"
              value={documentType}
              onChange={(event) => setDocumentType(event.target.value as DocumentType | '')}
            >
              {TIPOS.map((tipo) => (
                <option key={tipo.value} value={tipo.value}>
                  {tipo.label}
                </option>
              ))}
            </select>
          </div>

          <button
            type="button"
            className="btn-primary w-full"
            onClick={submit}
            disabled={!file || working}
          >
            {working ? 'Revisando…' : 'Enviar documento'}
          </button>
        </>
      )}

      {working && (
        <div className="card p-5" aria-live="polite">
          <ol className="space-y-3">
            {ETAPAS.map((etapa, index) => (
              <li key={etapa} className="flex items-center gap-3">
                <span
                  className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                    index < stage
                      ? 'bg-green-100 text-green-700'
                      : index === stage
                        ? 'bg-petrol-100 text-petrol-800'
                        : 'bg-slate-100 text-slate-400'
                  }`}
                  aria-hidden="true"
                >
                  {index < stage ? '✓' : index + 1}
                </span>
                <span
                  className={`text-sm ${index <= stage ? 'text-slate-900' : 'text-slate-400'}`}
                >
                  {etapa}
                </span>
                {index === stage && (
                  <span
                    className="ml-auto h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-petrol-600"
                    aria-hidden="true"
                  />
                )}
              </li>
            ))}
          </ol>
        </div>
      )}

      {error && (
        <div className="card border-red-200 bg-red-50 p-5" role="alert">
          <p className="text-sm font-medium text-red-900">{error}</p>
          <button type="button" className="btn-secondary mt-3" onClick={reset}>
            Empezar de nuevo
          </button>
        </div>
      )}

      {decision && (
        <section className="card p-6 text-center" aria-live="polite">
          {decision.verdict === 'autentico' && (
            <>
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-green-100 text-2xl text-green-700" aria-hidden="true">
                ✓
              </div>
              <h2 className="mt-3 text-xl font-semibold text-slate-900">Documento validado</h2>
            </>
          )}

          {decision.verdict === 'sospechoso' && (
            <>
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-amber-100 text-2xl text-amber-700" aria-hidden="true">
                !
              </div>
              <h2 className="mt-3 text-xl font-semibold text-slate-900">
                Necesitamos revisarlo mejor
              </h2>
            </>
          )}

          {decision.verdict === 'falso' && (
            <>
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-slate-200 text-2xl text-slate-700" aria-hidden="true">
                ⌛
              </div>
              <h2 className="mt-3 text-xl font-semibold text-slate-900">
                Lo revisaremos con un ejecutivo
              </h2>
            </>
          )}

          <p className="mx-auto mt-2 max-w-md text-slate-600">{decision.explanation_customer}</p>

          <div className="mt-6 flex flex-wrap justify-center gap-2">
            {decision.verdict === 'sospechoso' && (
              <button type="button" className="btn-primary" onClick={reset}>
                Subir otra foto
              </button>
            )}
            <button type="button" className="btn-secondary" onClick={reset}>
              Subir otro documento
            </button>
          </div>
        </section>
      )}
    </div>
  )
}
