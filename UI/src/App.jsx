import { useState, useCallback, useEffect } from 'react'
import GeometricBg from './components/GeometricBg.jsx'
import TopBar from './components/TopBar.jsx'
import Sidebar from './components/Sidebar.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import SessionPanel from './components/SessionPanel.jsx'
import ToolsPanel from './components/ToolsPanel.jsx'
import HealthPanel from './components/HealthPanel.jsx'
import AnalyticsPanel from './components/AnalyticsPanel.jsx'
import Toast from './components/Toast.jsx'

export default function App() {
  const [apiUrl, setApiUrl] = useState(() =>
    (localStorage.getItem('iris_api') || 'http://localhost:8000').replace(/\/$/, '')
  )
  const [view, setView] = useState('chat')
  const [session, setSession] = useState(null)
  const [connStatus, setConnStatus] = useState({ ok: false, msg: 'Connecting…' })
  const [toasts, setToasts] = useState([])

  const addToast = useCallback((msg, type = '') => {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { id, msg, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500)
  }, [])

  const handleSessionUpdate = useCallback((s) => {
    setSession(s)
  }, [])

  const handleConnStatus = useCallback((ok, msg) => {
    setConnStatus({ ok, msg })
  }, [])

  const updateApiUrl = (url) => {
    const clean = url.trim().replace(/\/$/, '')
    setApiUrl(clean)
    localStorage.setItem('iris_api', clean)
  }

  // Initial connectivity probe
  useEffect(() => {
    fetch(apiUrl + '/session')
      .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
      .then(s => { setSession(s); setConnStatus({ ok: true, msg: 'Connected' }) })
      .catch(() => setConnStatus({ ok: false, msg: 'Unreachable' }))
  }, [apiUrl])

  return (
    <div className="shell">
      <GeometricBg />
      <div className="layout">
        <TopBar view={view} session={session} connOk={connStatus.ok} />
        <div className="workspace">
          <Sidebar
            view={view}
            onViewChange={setView}
            connStatus={connStatus}
            apiUrl={apiUrl}
            onApiUrlChange={updateApiUrl}
          />
          <main className="content">
            <ChatPanel
              isActive={view === 'chat'}
              apiUrl={apiUrl}
              session={session}
              onSessionUpdate={handleSessionUpdate}
              onConnStatus={handleConnStatus}
              onToast={addToast}
            />
            <SessionPanel
              isActive={view === 'session'}
              apiUrl={apiUrl}
              onSessionUpdate={handleSessionUpdate}
              onConnStatus={handleConnStatus}
              onToast={addToast}
            />
            <ToolsPanel
              isActive={view === 'tools'}
              apiUrl={apiUrl}
              onToast={addToast}
            />
            <HealthPanel
              isActive={view === 'health'}
              apiUrl={apiUrl}
              onConnStatus={handleConnStatus}
              onToast={addToast}
            />
            <AnalyticsPanel
              isActive={view === 'analytics'}
              apiUrl={apiUrl}
              onToast={addToast}
            />
          </main>
        </div>
      </div>
      <Toast toasts={toasts} />
    </div>
  )
}
