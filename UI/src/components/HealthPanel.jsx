import { useEffect, useState, useRef } from 'react'

export default function HealthPanel({ isActive, apiUrl, onConnStatus, onToast }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const prevActive = useRef(false)

  const load = async () => {
    setLoading(true); setError(null)
    try {
      const r = await fetch(apiUrl + '/health')
      if (!r.ok) throw new Error(r.statusText)
      const d = await r.json()
      setData(d)
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

  const mcpShort = (data?.mcp_url || '').replace(/^https?:\/\//, '').split('/')[0]

  return (
    <div className={`panel ${isActive ? 'on' : ''}`} id="p-health">
      <div className="ph">
        <div>
          <div className="pt">Health</div>
          <div className="pd">API server and connectivity diagnostics</div>
        </div>
        <button className="btn btn-secondary" onClick={load}>
          <RefreshIcon />Refresh
        </button>
      </div>
      <div className="pb">
        {loading && <div className="loading-state"><div className="spin" />Checking…</div>}
        {error && (
          <>
            <div className="h-bar er">
              <span className="h-icon">✕</span>
              <span className="h-text">Cannot reach {apiUrl}</span>
            </div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: '11.5px', color: 'var(--text-2)' }}>{error}</div>
          </>
        )}
        {data && !loading && (
          <>
            <div className="h-bar ok">
              <span className="h-icon">✓</span>
              <span className="h-text">Service operational</span>
            </div>
            <div className="metrics-grid">
              <div className="metric-card">
                <div className="metric-label">Provider</div>
                <div className="metric-value">{data.provider || '—'}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Model</div>
                <div className="metric-value" title={data.model || ''}>{data.model || '—'}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">MCP Host</div>
                <div className="metric-value" title={data.mcp_url || ''}>{mcpShort || data.mcp_url || '—'}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Tool Count</div>
                <div className="metric-value">{data.tool_count ?? '—'}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Memory</div>
                <div className="metric-value">
                  <span className={`badge ${data.memory_on ? 'badge-ok' : 'badge-dim'}`}>
                    {data.memory_on ? 'Enabled' : 'Disabled'}
                  </span>
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
