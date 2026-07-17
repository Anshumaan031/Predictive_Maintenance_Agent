const VIEW_LABELS = { chat: 'Chat', session: 'Session', tools: 'Tools', health: 'Health' }

export default function TopBar({ view, session, connOk }) {
  const hasMachine = session?.active_machine
  const userId = session?.owner_id

  return (
    <header className="topbar">
      <a className="tb-logo" href="#" onClick={e => e.preventDefault()}>
        <div className="tb-eye">
          <svg viewBox="0 0 24 24">
            <path d="M12 5C7 5 2.73 8.11 1 12.5 2.73 16.89 7 20 12 20s9.27-3.11 11-7.5C21.27 8.11 17 5 12 5zm0 12.5a5 5 0 110-10 5 5 0 010 10zm0-8a3 3 0 100 6 3 3 0 000-6z" />
          </svg>
        </div>
        <span className="tb-brand">Iris</span>
      </a>

      <span className="tb-sep">/</span>
      <span className="tb-crumb">{VIEW_LABELS[view] || view}</span>

      <div className="tb-space" />

      <div className="tb-chips">
        <div className={`tb-chip ${hasMachine ? 'active' : ''}`}>
          <span className={`tb-dot ${hasMachine ? 'ok' : ''}`} />
          {hasMachine || 'No machine'}
        </div>
        {userId && (
          <div className="tb-chip">
            {userId}
          </div>
        )}
      </div>
    </header>
  )
}
