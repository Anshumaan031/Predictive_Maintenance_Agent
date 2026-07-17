import { useEffect, useState, useRef } from 'react'

export default function ToolsPanel({ isActive, apiUrl, onToast }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState(null)
  const prevActive = useRef(false)

  const load = async () => {
    setLoading(true); setError(null)
    try {
      const r = await fetch(apiUrl + '/tools')
      if (!r.ok) throw new Error(r.statusText)
      setData(await r.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isActive && !prevActive.current) load()
    prevActive.current = isActive
  }, [isActive])

  const tools = data?.tools ?? []
  const filtered = query.trim()
    ? tools.filter(t =>
        t.name.toLowerCase().includes(query.toLowerCase()) ||
        (t.description || '').toLowerCase().includes(query.toLowerCase())
      )
    : tools

  return (
    <div className={`panel ${isActive ? 'on' : ''}`} id="p-tools">
      <div className="ph">
        <div>
          <div className="pt">Tools</div>
          <div className="pd">MCP tools registered with the agent</div>
        </div>
        <button className="btn btn-secondary" onClick={load}>
          <RefreshIcon />Refresh
        </button>
      </div>

      <div className="pb" style={{ padding: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Search + meta bar */}
        <div className="tl-bar">
          <div className="tl-search-wrap">
            <SearchIcon />
            <input
              className="tl-search"
              placeholder="filter tools…"
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
            {query && (
              <button className="tl-clear" onClick={() => setQuery('')}>×</button>
            )}
          </div>
          {data && !loading && (
            <span className="tl-count">
              {query ? `${filtered.length} / ${tools.length}` : tools.length} tools
            </span>
          )}
        </div>

        {/* States */}
        {loading && (
          <div className="tl-state">
            <div className="spin" />Loading tools…
          </div>
        )}
        {error && <div className="tl-state tl-error">Error: {error}</div>}

        {/* Table */}
        {data && !loading && (
          <div className="tl-scroll">
            {!filtered.length ? (
              <div className="tl-state">
                {query ? 'No tools match that filter.' : 'No tools available — check MCP connection.'}
              </div>
            ) : (
              <table className="tl-table">
                <thead>
                  <tr>
                    <th className="tl-th tl-th-idx">#</th>
                    <th className="tl-th tl-th-name">Tool</th>
                    <th className="tl-th tl-th-desc">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((t, i) => {
                    const isOpen = expanded === t.name
                    return (
                      <tr
                        key={t.name}
                        className={`tl-row ${isOpen ? 'tl-row-open' : ''}`}
                        onClick={() => setExpanded(isOpen ? null : t.name)}
                      >
                        <td className="tl-td tl-idx">{String(i + 1).padStart(2, '0')}</td>
                        <td className="tl-td tl-name">{t.name}</td>
                        <td className="tl-td tl-desc">
                          {isOpen
                            ? <span className="tl-desc-full">{t.description || '—'}</span>
                            : <span className="tl-desc-clip">{t.description || '—'}</span>
                          }
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
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

function SearchIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor" style={{ flexShrink: 0, opacity: 0.4 }}>
      <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
    </svg>
  )
}
