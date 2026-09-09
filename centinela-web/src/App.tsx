import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { useAuth } from './hooks/useAuth'
import type { Role } from './lib/types'
import { Landing } from './pages/Landing'
import { ClienteTransaccion } from './pages/ClienteTransaccion'
import { ClienteDocumento } from './pages/ClienteDocumento'
import { AnalistaBandeja } from './pages/AnalistaBandeja'
import { AnalistaCaso } from './pages/AnalistaCaso'
import { SupervisorDashboard } from './pages/SupervisorDashboard'
import { Ajustes } from './pages/Ajustes'

/** Ruta protegida: exige sesión y, opcionalmente, uno de varios roles. */
function Protected({ roles, children }: { roles: Role[]; children: JSX.Element }) {
  const { session } = useAuth()
  if (!session) return <Navigate to="/" replace />
  if (!roles.includes(session.role)) return <Navigate to="/" replace />
  return children
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Landing />} />

        <Route
          path="/cliente/transaccion"
          element={
            <Protected roles={['cliente']}>
              <ClienteTransaccion />
            </Protected>
          }
        />
        <Route
          path="/cliente/documento"
          element={
            <Protected roles={['cliente']}>
              <ClienteDocumento />
            </Protected>
          }
        />

        <Route
          path="/analista"
          element={
            <Protected roles={['analista', 'supervisor']}>
              <AnalistaBandeja />
            </Protected>
          }
        />
        <Route
          path="/casos/:traceId"
          element={
            <Protected roles={['analista', 'supervisor']}>
              <AnalistaCaso />
            </Protected>
          }
        />

        <Route
          path="/supervisor"
          element={
            <Protected roles={['supervisor']}>
              <SupervisorDashboard />
            </Protected>
          }
        />
        <Route
          path="/ajustes"
          element={
            <Protected roles={['supervisor']}>
              <Ajustes />
            </Protected>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
