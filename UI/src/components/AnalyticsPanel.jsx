import { useEffect, useState, useRef, useCallback, Fragment } from 'react'

// ── Color palette ─────────────────────────────────────────────────────────────
const PALETTE = ['#60A5FA','#A78BFA','#34D399','#FBBF24','#F87171','#FB923C','#38BDF8','#E879F9']

const VALUE_COLORS = {
  running:'#4ade80', ok:'#4ade80', resolved:'#4ade80', completed:'#4ade80',
  fault:'#f87171', critical:'#f87171', error:'#f87171',
  warning:'#fbbf24', maintenance:'#fbbf24', in_progress:'#fbbf24', scheduled:'#fbbf24',
}
const valueColor = v => VALUE_COLORS[String(v).toLowerCase()] ?? 'rgba(255,255,255,0.35)'

// ── Mini horizontal stacked bar (for KPI cards) ───────────────────────────────
function MiniBar({ dist }) {
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1])
  const total = entries.reduce((s, [, n]) => s + n, 0)
  if (!total) return null
  return (
    <div style={{ display:'flex', height:4, borderRadius:2, overflow:'hidden', gap:1, margin:'4px 0' }}>
      {entries.map(([k, v]) => (
        <div key={k} style={{ flex: v/total, background: valueColor(k), opacity:0.85 }} title={`${k}: ${v}`} />
      ))}
    </div>
  )
}

// ── Vertical bar chart ────────────────────────────────────────────────────────
function BarChart({ dist }) {
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]).slice(0, 9)
  const max = Math.max(...entries.map(([, v]) => v))
  if (!max) return null
  const H = 64

  return (
    <div className="an-barchart">
      {entries.map(([k, v]) => {
        const col = valueColor(k)
        const barH = Math.max(2, Math.round((v / max) * H))
        return (
          <div key={k} className="an-barcol">
            <span className="an-barcol-val">{v}</span>
            <div style={{ height: H - barH, flexShrink: 0 }} />
            <div className="an-barcol-fill" style={{ height: barH, background: col }} />
            <span className="an-barcol-label">{k.replace(/_/g,' ')}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── Numeric range stat ────────────────────────────────────────────────────────
function NumStat({ label, stats, color }) {
  const { min, max, mean, median, stdev, count } = stats
  const range = max - min || 1
  const meanPct = Math.min(100, Math.max(0, ((mean - min) / range) * 100))
  const fmt = n => n == null ? '—' : (Number.isInteger(n) ? n : n.toFixed(2))
  return (
    <div className="an-numstat">
      <div className="an-numstat-label">{label}</div>
      <div className="an-numstat-track">
        <div className="an-numstat-fill" style={{ width:`${meanPct}%`, background: color || 'rgba(255,255,255,0.35)' }} />
        <div className="an-numstat-pin" style={{ left:`${meanPct}%` }} title={`mean ${fmt(mean)}`} />
      </div>
      <div className="an-numstat-range">
        <span>{fmt(min)}</span>
        <span>{fmt(max)}</span>
      </div>
      <div className="an-numstat-stats">
        <span className="an-numstat-stat"><span className="an-ns-k">μ</span>{fmt(mean)}</span>
        {stdev  != null && <span className="an-numstat-stat"><span className="an-ns-k">σ</span>{fmt(stdev)}</span>}
        {median != null && <span className="an-numstat-stat"><span className="an-ns-k">med</span>{fmt(median)}</span>}
        {count  != null && <span className="an-numstat-stat"><span className="an-ns-k">n</span>{count}</span>}
      </div>
    </div>
  )
}

// ── Value badge ───────────────────────────────────────────────────────────────
function ValBadge({ value }) {
  const col = valueColor(value)
  if (!VALUE_COLORS[String(value).toLowerCase()]) return <span>{String(value)}</span>
  return <span className="an-vbadge" style={{ color: col, borderColor: col + '80' }}>{String(value)}</span>
}

// ── KPI card ──────────────────────────────────────────────────────────────────
function KpiCard({ entityType, count, overview, color }) {
  const dists = overview?.distributions?.[entityType]
  const primaryDist = dists?.status || (dists && Object.values(dists)[0]) || null
  const dominant = primaryDist ? Object.entries(primaryDist).sort((a, b) => b[1] - a[1])[0] : null
  return (
    <div className="an-kpi2" style={{ borderLeftColor: color }}>
      <div className="an-kpi2-top">
        <span className="an-kpi2-entity">{entityType.replace(/_/g,' ')}</span>
        {dominant && (
          <span className="an-vbadge" style={{ color: valueColor(dominant[0]), borderColor: valueColor(dominant[0]) + '80', fontSize: 9 }}>
            {dominant[0]}
          </span>
        )}
      </div>
      <div className="an-kpi2-num" style={{ color }}>{count}</div>
      {primaryDist && <MiniBar dist={primaryDist} />}
      <div className="an-kpi2-sub">
        <span className="an-kpi2-unit">records</span>
        {dists && Object.keys(dists).length > 0 && (
          <span className="an-kpi2-cats">{Object.keys(dists).join(' · ')}</span>
        )}
      </div>
    </div>
  )
}

// ── Schema ERD ────────────────────────────────────────────────────────────────
function SchemaERD({ schema, entityTypes }) {
  if (!schema) return null
  const allTypes = entityTypes
  const relationships = schema.relationships || []

  const COLS = Math.min(3, allTypes.length)
  const ROWS = Math.ceil(allTypes.length / COLS)
  const NODE_W = 192
  const NODE_H = 128
  const GAP_X = 88
  const GAP_Y = 56
  const PAD = 28

  const SVG_W = PAD * 2 + COLS * NODE_W + (COLS - 1) * GAP_X
  const SVG_H = PAD * 2 + ROWS * NODE_H + (ROWS - 1) * GAP_Y

  const pos = {}
  allTypes.forEach((et, i) => {
    const col = i % COLS
    const row = Math.floor(i / COLS)
    pos[et] = { x: PAD + col * (NODE_W + GAP_X), y: PAD + row * (NODE_H + GAP_Y) }
  })

  const getEdge = (from, to) => {
    const s = pos[from], t = pos[to]
    if (!s || !t || from === to) return null
    const sCx = s.x + NODE_W / 2, sCy = s.y + NODE_H / 2
    const tCx = t.x + NODE_W / 2, tCy = t.y + NODE_H / 2
    const dx = tCx - sCx, dy = tCy - sCy
    let x1, y1, x2, y2, cx1, cy1, cx2, cy2
    if (Math.abs(dx) >= Math.abs(dy)) {
      if (dx >= 0) { x1 = s.x + NODE_W; y1 = sCy; x2 = t.x; y2 = tCy }
      else          { x1 = s.x;           y1 = sCy; x2 = t.x + NODE_W; y2 = tCy }
      const mX = (x1 + x2) / 2
      cx1 = mX; cy1 = y1; cx2 = mX; cy2 = y2
    } else {
      if (dy >= 0) { x1 = sCx; y1 = s.y + NODE_H; x2 = tCx; y2 = t.y }
      else          { x1 = sCx; y1 = s.y;           x2 = tCx; y2 = t.y + NODE_H }
      const mY = (y1 + y2) / 2
      cx1 = x1; cy1 = mY; cx2 = x2; cy2 = mY
    }
    return { x1, y1, x2, y2, cx1, cy1, cx2, cy2 }
  }

  return (
    <div className="an-erd-wrap" style={{ width: SVG_W, height: SVG_H }}>
      {/* SVG edges */}
      <svg width={SVG_W} height={SVG_H} className="an-erd-svg">
        <defs>
          <marker id="erd-arr" markerWidth="7" markerHeight="5" refX="6" refY="2.5" orient="auto">
            <polygon points="0 0, 7 2.5, 0 5" fill="rgba(255,255,255,0.28)" />
          </marker>
        </defs>
        {relationships.map((rel, i) => {
          const edge = getEdge(rel.from_entity, rel.to_entity)
          if (!edge) return null
          const { x1, y1, x2, y2, cx1, cy1, cx2, cy2 } = edge
          const col = PALETTE[allTypes.indexOf(rel.from_entity) % PALETTE.length]
          // bezier midpoint at t=0.5
          const lx = x1/8 + cx1*3/8 + cx2*3/8 + x2/8
          const ly = y1/8 + cy1*3/8 + cy2*3/8 + y2/8
          return (
            <g key={i}>
              <path
                d={`M ${x1} ${y1} C ${cx1} ${cy1} ${cx2} ${cy2} ${x2} ${y2}`}
                fill="none" stroke={col} strokeWidth="1.5" strokeOpacity="0.5"
                markerEnd="url(#erd-arr)"
              />
              <rect x={lx - 26} y={ly - 10} width={52} height={14} rx={3}
                fill="rgba(0,0,0,0.72)" />
              <text x={lx} y={ly + 1} textAnchor="middle"
                fontSize="7" fontFamily="JetBrains Mono, Consolas, monospace"
                fill="rgba(255,255,255,0.5)" letterSpacing="0.04em"
              >{rel.via_field}</text>
            </g>
          )
        })}
      </svg>

      {/* Entity nodes */}
      {allTypes.map((et, i) => {
        const p = pos[et]
        const info = schema.entity_types[et]
        if (!info) return null
        const color = PALETTE[i % PALETTE.length]
        const fields = Object.entries(info.fields)
          .filter(([k]) => k !== 'id' && !k.startsWith('_'))
          .slice(0, 4)

        return (
          <div key={et} className="an-erd-node"
            style={{ left: p.x, top: p.y, width: NODE_W, height: NODE_H, borderColor: color + '55' }}
          >
            <div className="an-erd-node-hd" style={{ background: color + '18', borderBottomColor: color + '40' }}>
              <span className="an-erd-node-type" style={{ color }}>{et.replace(/_/g,' ')}</span>
              <span className="an-erd-node-count" style={{ background: color + '25', color }}>{info.count}</span>
            </div>
            <div className="an-erd-node-body">
              {fields.map(([field, finfo]) => (
                <div key={field} className="an-erd-field-row">
                  <span className="an-erd-field-name">{field}</span>
                  <span className={`an-erd-field-type${finfo.references ? ' an-erd-fk' : ''}`}>
                    {finfo.references ? `→ ${finfo.references}` : finfo.type}
                  </span>
                </div>
              ))}
              {Object.keys(info.fields).length > 4 && (
                <div className="an-erd-field-more">+{Object.keys(info.fields).length - 4} more fields</div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Record detail ─────────────────────────────────────────────────────────────
function RecordDetail({ detail }) {
  const { _references = {}, _referenced_by = {}, _key, ...fields } = detail
  const hasRefs = Object.keys(_references).length > 0
  const hasBack = Object.keys(_referenced_by).length > 0
  return (
    <div className="an-detail">
      <div className="an-detail-cols">
        <div className="an-detail-col">
          <div className="an-detail-col-label">Fields</div>
          <div className="an-detail-fields">
            {Object.entries(fields).map(([k, v]) => (
              <div key={k} className="an-detail-field">
                <span className="an-detail-fk">{k}</span>
                <span className="an-detail-fv"><ValBadge value={v} /></span>
              </div>
            ))}
          </div>
        </div>
        {hasRefs && (
          <div className="an-detail-col">
            <div className="an-detail-col-label">References</div>
            {Object.entries(_references).map(([field, ref]) => (
              <div key={field} className="an-detail-ref-card">
                <div className="an-detail-ref-label">{field}</div>
                {Object.entries(ref).filter(([k]) => !k.startsWith('_')).slice(0, 5).map(([k, v]) => (
                  <div key={k} className="an-detail-field">
                    <span className="an-detail-fk">{k}</span>
                    <span className="an-detail-fv">{String(v)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
        {hasBack && (
          <div className="an-detail-col">
            <div className="an-detail-col-label">Referenced By</div>
            {Object.entries(_referenced_by).map(([entity, recs]) => (
              <div key={entity} className="an-detail-ref-card">
                <div className="an-detail-ref-label">{entity} <span className="an-detail-ref-count">({recs.length})</span></div>
                {recs.slice(0, 3).map((r, i) => (
                  <div key={i} className="an-detail-back-row">
                    {Object.entries(r).filter(([k]) => !k.startsWith('_')).slice(0, 3).map(([k, v]) => (
                      <span key={k} className="an-detail-back-chip">
                        <span className="an-detail-fk">{k}</span> {String(v)}
                      </span>
                    ))}
                  </div>
                ))}
                {recs.length > 3 && <div className="an-detail-more">+{recs.length - 3} more</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main panel ────────────────────────────────────────────────────────────────
export default function AnalyticsPanel({ isActive, apiUrl, onToast }) {
  const [overview, setOverview] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [schema, setSchema] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [activeEntity, setActiveEntity] = useState(null)
  const [entityRecords, setEntityRecords] = useState(null)
  const [loadingRecords, setLoadingRecords] = useState(false)
  const [expandedId, setExpandedId] = useState(null)
  const [recordDetail, setRecordDetail] = useState({})
  const [loadingDetail, setLoadingDetail] = useState({})

  const prevActive = useRef(false)

  const loadData = async () => {
    setLoading(true); setError(null)
    try {
      const [ov, an, sc] = await Promise.all([
        fetch(apiUrl + '/data/overview').then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() }),
        fetch(apiUrl + '/data/analytics').then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() }),
        fetch(apiUrl + '/data/schema').then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() }),
      ])
      setOverview(ov); setAnalytics(an); setSchema(sc)
      const first = Object.keys(ov.entity_counts ?? {})[0]
      if (first && !activeEntity) setActiveEntity(first)
    } catch (e) {
      setError(e.message)
      onToast?.('Analytics load failed: ' + e.message, 'er')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isActive && !prevActive.current) loadData()
    prevActive.current = isActive
  }, [isActive])

  const loadEntity = useCallback(async (entityType) => {
    setActiveEntity(entityType)
    setEntityRecords(null)
    setExpandedId(null)
    setLoadingRecords(true)
    try {
      const r = await fetch(apiUrl + `/data/entity/${entityType}`)
      if (!r.ok) throw new Error(r.statusText)
      setEntityRecords(await r.json())
    } catch (e) {
      onToast?.('Could not load ' + entityType + ': ' + e.message, 'er')
    } finally {
      setLoadingRecords(false)
    }
  }, [apiUrl])

  const toggleRecord = async (entityType, rec) => {
    const key = rec._key ?? rec.id
    if (expandedId === key) { setExpandedId(null); return }
    setExpandedId(key)
    if (recordDetail[key]) return
    const id = rec.id ?? key.split(':')[1]
    setLoadingDetail(d => ({ ...d, [key]: true }))
    try {
      const r = await fetch(apiUrl + `/data/entity/${entityType}/${id}`)
      if (!r.ok) throw new Error(r.statusText)
      const detail = await r.json()
      setRecordDetail(d => ({ ...d, [key]: detail }))
    } catch (e) {
      onToast?.('Detail load failed: ' + e.message, 'er')
    } finally {
      setLoadingDetail(d => ({ ...d, [key]: false }))
    }
  }

  useEffect(() => {
    if (activeEntity && isActive) loadEntity(activeEntity)
  }, [activeEntity])

  const entityTypes = overview ? Object.keys(overview.entity_counts ?? {}) : []
  const distributions = overview?.distributions ?? {}
  const numericSections = analytics
    ? Object.entries(analytics).flatMap(([entity, info]) =>
        Object.entries(info.field_stats ?? {})
          .filter(([, fs]) => fs.type === 'numeric')
          .map(([field, fs]) => ({ entity, field, stats: fs }))
      )
    : []

  const HIDDEN = new Set(['_key','_references','_referenced_by'])
  const tableCols = entityRecords?.length
    ? [...new Set(entityRecords.flatMap(r => Object.keys(r)))].filter(k => !HIDDEN.has(k))
    : []

  return (
    <div className={`panel ${isActive ? 'on' : ''}`} id="p-analytics">
      <div className="ph">
        <div>
          <div className="pt">Analytics</div>
          <div className="pd">Redis data dashboard</div>
        </div>
        <button className="btn btn-secondary" onClick={loadData} disabled={loading}>
          <RefreshIcon /> Refresh
        </button>
      </div>

      <div className="an-scroll">
        {loading && <div className="an-center-state"><div className="spin" /> Loading data…</div>}
        {error && <div className="an-center-state an-err">Error: {error}</div>}

        {overview && !loading && (
          <>
            {/* ── KPI Row ── */}
            <section className="an-section">
              <div className="an-section-label">Overview</div>
              <div className="an-kpi2-row">
                {entityTypes.map((et, i) => (
                  <KpiCard key={et} entityType={et}
                    count={overview.entity_counts[et]}
                    overview={overview}
                    color={PALETTE[i % PALETTE.length]}
                  />
                ))}
                <div className="an-kpi2 an-kpi2-total">
                  <div className="an-kpi2-top">
                    <span className="an-kpi2-entity">total</span>
                  </div>
                  <div className="an-kpi2-num" style={{ color:'var(--text)' }}>{overview.total_entities}</div>
                  <div className="an-kpi2-sub">
                    <span className="an-kpi2-unit">{entityTypes.length} entity types</span>
                  </div>
                </div>
              </div>
            </section>

            {/* ── Schema ERD ── */}
            {schema && (schema.relationships?.length > 0) && (
              <section className="an-section">
                <div className="an-section-label">
                  <span>Entity Relationships</span>
                  <span className="an-section-meta">{schema.relationships.length} FK links · {entityTypes.length} types</span>
                </div>
                <div className="an-erd-scroll">
                  <SchemaERD schema={schema} entityTypes={entityTypes} />
                </div>
              </section>
            )}

            {/* ── Field Distributions ── */}
            {Object.entries(distributions).some(([, f]) => Object.keys(f).length) && (
              <section className="an-section">
                <div className="an-section-label">Field Distributions</div>
                <div className="an-dist-grid">
                  {Object.entries(distributions).flatMap(([entity, fields]) =>
                    Object.entries(fields).map(([field, dist]) => (
                      <div key={`${entity}_${field}`} className="an-dist-card">
                        <div className="an-dist-title">
                          <span className="an-dist-entity" style={{ color: PALETTE[entityTypes.indexOf(entity) % PALETTE.length] }}>
                            {entity}
                          </span>
                          <span className="an-dist-sep">/</span>
                          <span className="an-dist-field">{field}</span>
                        </div>
                        <BarChart dist={dist} />
                      </div>
                    ))
                  )}
                </div>
              </section>
            )}

            {/* ── Numeric Stats ── */}
            {numericSections.length > 0 && (
              <section className="an-section">
                <div className="an-section-label">Numeric Fields</div>
                <div className="an-num-grid">
                  {numericSections.map(({ entity, field, stats }) => {
                    const color = PALETTE[entityTypes.indexOf(entity) % PALETTE.length]
                    return (
                      <div key={`${entity}_${field}`} className="an-num-card">
                        <div className="an-num-entity" style={{ color }}>{entity}</div>
                        <NumStat label={field} stats={stats} color={color} />
                      </div>
                    )
                  })}
                </div>
              </section>
            )}

            {/* ── Entity Explorer ── */}
            <section className="an-section">
              <div className="an-section-label">Entity Explorer</div>
              <div className="an-entity-tabs">
                {entityTypes.map((et, i) => {
                  const color = PALETTE[i % PALETTE.length]
                  const isAct = activeEntity === et
                  return (
                    <button key={et}
                      className={`an-etab ${isAct ? 'active' : ''}`}
                      style={isAct ? { borderColor: color, color } : {}}
                      onClick={() => !isAct && loadEntity(et)}
                    >
                      {et.replace(/_/g,' ')}
                      <span className="an-etab-count">{overview.entity_counts[et]}</span>
                    </button>
                  )
                })}
              </div>

              <div className="an-table-wrap">
                {loadingRecords && (
                  <div className="an-center-state"><div className="spin" /> Loading {activeEntity}…</div>
                )}
                {!loadingRecords && entityRecords && (
                  entityRecords.length === 0
                    ? <div className="an-center-state">No records found.</div>
                    : (
                      <table className="an-table">
                        <thead>
                          <tr>
                            <th className="an-th an-th-expand" />
                            {tableCols.map(col => <th key={col} className="an-th">{col}</th>)}
                          </tr>
                        </thead>
                        <tbody>
                          {entityRecords.map(rec => {
                            const key = rec._key ?? rec.id
                            const isOpen = expandedId === key
                            const detail = recordDetail[key]
                            const detailLoading = loadingDetail[key]
                            return (
                              <Fragment key={key}>
                                <tr
                                  className={`an-tr ${isOpen ? 'an-tr-open' : ''}`}
                                  onClick={() => toggleRecord(activeEntity, rec)}
                                >
                                  <td className="an-td an-td-expand">
                                    <span className={`an-chevron ${isOpen ? 'open' : ''}`}>›</span>
                                  </td>
                                  {tableCols.map(col => (
                                    <td key={col} className="an-td">
                                      {rec[col] != null ? <ValBadge value={rec[col]} /> : <span className="an-null">—</span>}
                                    </td>
                                  ))}
                                </tr>
                                {isOpen && (
                                  <tr className="an-tr-detail">
                                    <td colSpan={tableCols.length + 1}>
                                      {detailLoading && <div className="an-detail-loading"><div className="spin" /> Loading detail…</div>}
                                      {detail && !detailLoading && <RecordDetail detail={detail} />}
                                    </td>
                                  </tr>
                                )}
                              </Fragment>
                            )
                          })}
                        </tbody>
                      </table>
                    )
                )}
              </div>
            </section>
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
