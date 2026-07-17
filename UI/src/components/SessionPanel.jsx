import { useEffect, useState, useRef } from 'react'

export default function SessionPanel({ isActive, apiUrl, onSessionUpdate, onConnStatus, onToast }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const machRef = useRef(null)
  const userRef = useRef(null)
  const prevActive = useRef(false)

  const load = async () => {
    setLoading(true); setError(null)
    try {
      const r = await fetch(apiUrl + '/session')
      if (!r.ok) throw new Error(r.statusText)
      const s = await r.json()
      setData(s)
      onSessionUpdate(s)
      onConnStatus(true, 'Connected')
    } catch (e) {
      setError(e.message)
      onConnStatus(false, 'Unreachable')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isActive && !prevActive.current) load()
    prevActive.current = isActive
  }, [isActive])

  const apiFetch = async (path, method = 'POST', body) => {
    const r = await fetch(apiUrl + path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!r.ok) throw new Error(r.statusText)
    return r.json()
  }

  const applyMach = async () => {
    const id = (machRef.current?.value || '').trim().toUpperCase()
    if (!id) { onToast('Enter a machine ID'); return }
    try {
      const s = await apiFetch('/session/machine', 'POST', { machine_id: id })
      onSessionUpdate(s); setData(s); onToast('Machine → ' + s.active_machine, 'ok')
    } catch (e) { onToast('Error: ' + e.message, 'er') }
  }

  const applyUser = async () => {
    const id = (userRef.current?.value || '').trim()
    if (!id) { onToast('Enter an owner ID'); return }
    try {
      const s = await apiFetch('/session/user', 'POST', { owner_id: id })
      onSessionUpdate(s); setData(s); onToast('User → ' + s.owner_id, 'ok')
    } catch (e) { onToast('Error: ' + e.message, 'er') }
  }

  const newShift = async () => {
    try {
      const s = await apiFetch('/session/new-shift', 'POST')
      onSessionUpdate(s); setData(s); onToast('New shift: ' + s.session_id, 'ok')
    } catch (e) { onToast('Error: ' + e.message, 'er') }
  }

  const clearHistory = async () => {
    try {
      await apiFetch('/session/history', 'DELETE')
      onToast('History cleared', 'ok'); load()
    } catch (e) { onToast('Error: ' + e.message, 'er') }
  }

  return (
    <div className={`panel ${isActive ? 'on' : ''}`} id="p-session">
      <div className="ph">
        <div>
          <div className="pt">Session</div>
          <div className="pd">Identity, machine context, and conversation history</div>
        </div>
        <button className="btn btn-secondary" onClick={load}>
          <RefreshIcon />Refresh
        </button>
      </div>
      <div className="pb">
        {loading && <div className="loading-state"><div className="spin" />Loading…</div>}
        {error && <div className="error-state">Failed to load: {error}</div>}
        {data && !loading && (
          <>
            <div className="card">
              <div className="card-h">
                <span className="card-t">Session Info</span>
                <span className="badge badge-dim" style={{ fontFamily: 'var(--mono)', fontSize: '10px' }}>{data.session_id}</span>
              </div>
              <div className="card-b">
                <div className="info-grid">
                  <div className="info-field">
                    <label>Owner</label>
                    <value className="mono">{data.owner_id}</value>
                  </div>
                  <div className="info-field">
                    <label>Active Machine</label>
                    <value className="mono">
                      {data.active_machine
                        ? <span style={{ color: 'var(--text)' }}>{data.active_machine}</span>
                        : <span style={{ color: 'var(--text-3)' }}>None</span>}
                    </value>
                  </div>
                  <div className="info-field">
                    <label>History</label>
                    <value>{data.history_length} messages</value>
                  </div>
                  <div className="info-field">
                    <label>Tools</label>
                    <value>{data.tool_count}</value>
                  </div>
                  <div className="info-field">
                    <label>Memory</label>
                    <value>
                      <span className={`badge ${data.memory_on ? 'badge-ok' : 'badge-dim'}`}>
                        {data.memory_on ? 'Enabled' : 'Disabled'}
                      </span>
                    </value>
                  </div>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-h"><span className="card-t">Active Machine</span></div>
              <div className="card-b">
                <div className="form-group">
                  <label className="form-label">Machine ID</label>
                  <input ref={machRef} className="form-ctrl mono" defaultValue={data.active_machine || ''} placeholder="e.g. M104" />
                </div>
                <div className="btn-row">
                  <button className="btn btn-primary" onClick={applyMach}>Apply</button>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-h"><span className="card-t">User Identity</span></div>
              <div className="card-b">
                <div className="form-group">
                  <label className="form-label">Owner ID</label>
                  <input ref={userRef} className="form-ctrl" defaultValue={data.owner_id} placeholder="e.g. operator" />
                </div>
                <div className="btn-row">
                  <button className="btn btn-primary" onClick={applyUser}>Apply</button>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-h"><span className="card-t">Shift & History</span></div>
              <div className="card-b">
                <p style={{ fontSize: '12.5px', color: 'var(--text-2)', marginBottom: '14px', lineHeight: '1.6' }}>
                  Starting a new shift increments the session ID and clears machine context. Clearing history removes conversation turns only.
                </p>
                <div className="btn-row">
                  <button className="btn btn-secondary" onClick={newShift}>New Shift</button>
                  <button className="btn btn-danger" onClick={clearHistory}>Clear History</button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function RefreshIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 20 20" fill="currentColor">
      <path d="M10 3a7 7 0 00-7 7H1l3 3 3-3H5a5 5 0 115 5 5 5 0 01-4.9-4H3.05A7 7 0 1010 3z" />
    </svg>
  )
}
