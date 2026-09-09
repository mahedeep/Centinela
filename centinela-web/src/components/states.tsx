/** Estados vacíos, de carga y de error, con mensajes accionables en español. */

export function Spinner({ label = 'Cargando…' }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-600" role="status">
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-petrol-600"
        aria-hidden="true"
      />
      {label}
    </span>
  )
}

export function LoadingBlock({ label = 'Cargando…' }: { label?: string }) {
  return (
    <div className="card flex items-center justify-center px-6 py-12">
      <Spinner label={label} />
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: React.ReactNode
}) {
  return (
    <div className="card px-6 py-12 text-center">
      <p className="text-base font-medium text-slate-900">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">{description}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

export function ErrorBlock({
  message,
  onRetry,
  action,
}: {
  message: string
  onRetry?: () => void
  action?: React.ReactNode
}) {
  return (
    <div className="card border-red-200 bg-red-50 px-6 py-8 text-center" role="alert">
      <p className="text-sm font-medium text-red-900">{message}</p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        {onRetry && (
          <button type="button" className="btn-secondary" onClick={onRetry}>
            Reintentar
          </button>
        )}
        {action}
      </div>
    </div>
  )
}
