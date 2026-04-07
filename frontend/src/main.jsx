import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import { Login } from './pages/Login.jsx'
import { useAuth } from './hooks/useAuth.js'

function ProtectedRoute({ children }) {
  const { session, loading } = useAuth()
  if (loading) return <div className="app"><div className="loading">Loading...</div></div>
  if (!session) return <Navigate to="/login" replace />
  return children
}

function LoginRoute() {
  const { session, loading } = useAuth()
  if (loading) return <div className="app"><div className="loading">Loading...</div></div>
  if (session) return <Navigate to="/" replace />
  return <Login />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />
        <Route path="/*" element={<ProtectedRoute><App /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
