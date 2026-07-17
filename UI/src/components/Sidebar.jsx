const NAV_ITEMS = [
  {
    id: 'chat', label: 'Chat',
    icon: <path d="M4 2h12a1 1 0 011 1v9a1 1 0 01-1 1H9.4L5 16.5V13H4a1 1 0 01-1-1V3a1 1 0 011-1z" />,
  },
  {
    id: 'session', label: 'Session',
    icon: <path d="M10 10a4 4 0 100-8 4 4 0 000 8zm-7 8a7 7 0 0114 0H3z" />,
  },
  {
    id: 'tools', label: 'Tools',
    icon: <path d="M10.5 2a8.5 8.5 0 100 17 8.5 8.5 0 000-17zm0 2a6.5 6.5 0 110 13 6.5 6.5 0 010-13zm0 2a4.5 4.5 0 100 9 4.5 4.5 0 000-9zm0 2a2.5 2.5 0 110 5 2.5 2.5 0 010-5z" />,
  },
  {
    id: 'health', label: 'Health',
    icon: <path d="M2 10h3.5l2-5 3 10 2.5-6.5L15 10H18v2h-4l-1.5-3-2.5 6.5-3-10-1.5 4.5H2v-2z" />,
  },
  {
    id: 'analytics', label: 'Analytics',
    icon: <path d="M3 17h2V9H3v8zm4 0h2V5H7v12zm4 0h2v-6h-2v6zm4 0h2V1h-2v16z" />,
  },
]

export default function Sidebar({ view, onViewChange, connStatus, apiUrl, onApiUrlChange }) {
  return (
    <nav className="sidebar">
      <div className="nav-section">
        <div className="nav-label">Workspace</div>
        {NAV_ITEMS.map(item => (
          <div
            key={item.id}
            className={`nav-item ${view === item.id ? 'active' : ''}`}
            onClick={() => onViewChange(item.id)}
          >
            <svg className="nav-icon" viewBox="0 0 20 20">{item.icon}</svg>
            {item.label}
          </div>
        ))}
      </div>

      <div className="sb-footer">
        <div className="conn-row">
          <div className={`conn-dot ${connStatus.ok ? 'ok' : 'er'}`} />
          <span className="conn-text">{connStatus.msg}</span>
        </div>
        <input
          className="api-input"
          defaultValue={apiUrl}
          placeholder="http://localhost:8000"
          onBlur={e => onApiUrlChange(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { onApiUrlChange(e.target.value); e.target.blur() } }}
        />
      </div>
    </nav>
  )
}
