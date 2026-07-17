import { useState, useRef, useEffect, useCallback } from 'react'
import { renderMD } from '../utils/markdown.js'

const WELCOME_PROMPTS = [
  'What machines have open alerts?',
  "Summarize today's work orders",
  'Which technicians are available?',
]

function ToolChip({ name, args }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div
      className={`tool-chip ${expanded ? 'expanded' : ''}`}
      onClick={() => setExpanded(x => !x)}
    >
      {expanded ? (
        <>
          <span><span className="chip-fn">⚡</span>{name}</span>
          <div className="chip-args">{JSON.stringify(args, null, 2)}</div>
        </>
      ) : (
        <>
          <span className="chip-fn">⚡</span>
          <span>{name}</span>
        </>
      )}
    </div>
  )
}

function Message({ msg }) {
  if (msg.type === 'user') {
    return (
      <div className="msg-row user">
        <div className="avatar user">YOU</div>
        <div className="msg-main">
          <div className="msg-sender">you</div>
          <div className="bub user">{msg.text}</div>
        </div>
      </div>
    )
  }

  return (
    <div className="msg-row iris">
      <div className="avatar iris">I</div>
      <div className="msg-main">
        <div className="msg-sender">iris</div>
        {msg.chips?.length > 0 && (
          <div className="tools-row">
            {msg.chips.map((c, i) => <ToolChip key={i} name={c.name} args={c.args} />)}
          </div>
        )}
        {msg.thinking && (
          <div className="thinking">
            <div className="t-dots">
              <div className="td" /><div className="td" /><div className="td" />
            </div>
            <span className="tk-lbl">Analyzing…</span>
          </div>
        )}
        {msg.streaming && !msg.thinking && (
          <div className="stream-bub">
            {msg.text}<span className="s-cursor" />
          </div>
        )}
        {msg.final && (
          <div className="bub iris md" dangerouslySetInnerHTML={{ __html: renderMD(msg.text) }} />
        )}
        {msg.error && (
          <div className="bub error">⚠ {msg.error}</div>
        )}
      </div>
    </div>
  )
}

export default function ChatPanel({ isActive, apiUrl, session, onSessionUpdate, onConnStatus, onToast }) {
  const [messages, setMessages] = useState([])
  const [inputText, setInputText] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [qsOpen, setQsOpen] = useState(false)
  const [qsInput, setQsInput] = useState('')

  const abortRef = useRef(null)
  const streamIdRef = useRef(null)
  const msgsEndRef = useRef(null)
  const taRef = useRef(null)
  const onSessionUpdateRef = useRef(onSessionUpdate)
  onSessionUpdateRef.current = onSessionUpdate

  useEffect(() => {
    msgsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleEvent = useCallback((ev) => {
    const id = streamIdRef.current
    switch (ev.type) {
      case 'tool_call':
        setMessages(prev => prev.map(m =>
          m.id === id ? { ...m, chips: [...(m.chips || []), { name: ev.name, args: ev.args || {} }] } : m
        ))
        break
      case 'token':
        setMessages(prev => prev.map(m =>
          m.id === id
            ? { ...m, thinking: false, streaming: true, text: (m.text || '') + (ev.content || '') }
            : m
        ))
        break
      case 'text':
        setMessages(prev => prev.map(m =>
          m.id === id
            ? { ...m, thinking: false, streaming: false, text: ev.content || '', final: true }
            : m
        ))
        break
      case 'done':
        if (ev.session) onSessionUpdateRef.current(ev.session)
        break
      case 'error':
        setMessages(prev => prev.map(m =>
          m.id === id ? { ...m, thinking: false, error: ev.message || 'Unknown error' } : m
        ))
        break
      default:
        break
    }
  }, [])

  const doSend = async () => {
    const msg = inputText.trim()
    if (!msg || isStreaming) return

    setInputText('')
    setIsStreaming(true)
    if (taRef.current) { taRef.current.style.height = '' }

    const userId = Date.now() * 2
    const irisId = userId + 1
    streamIdRef.current = irisId

    setMessages(prev => [
      ...prev,
      { id: userId, type: 'user', text: msg },
      { id: irisId, type: 'iris', chips: [], thinking: true, streaming: false, text: '', final: false, error: null },
    ])

    try {
      abortRef.current = new AbortController()
      const resp = await fetch(apiUrl + '/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
        signal: abortRef.current.signal,
      })
      if (!resp.ok) {
        const t = await resp.text().catch(() => '')
        throw new Error(`${resp.status}: ${t || resp.statusText}`)
      }
      const reader = resp.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() ?? ''
        for (const part of parts) {
          const ln = part.trim()
          if (!ln.startsWith('data: ')) continue
          try { handleEvent(JSON.parse(ln.slice(6))) }
          catch (e) { console.warn('SSE parse error', e) }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        const id = streamIdRef.current
        setMessages(prev => prev.map(m =>
          m.id === id ? { ...m, thinking: false, error: String(err) } : m
        ))
      }
    } finally {
      setIsStreaming(false)
      streamIdRef.current = null
      taRef.current?.focus()
    }
  }

  const taKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend() }
  }
  const autosize = (el) => {
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  const applyMach = async () => {
    const id = qsInput.trim().toUpperCase()
    setQsOpen(false)
    if (!id) { onToast('Enter a machine ID'); return }
    try {
      const r = await fetch(apiUrl + '/session/machine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ machine_id: id }),
      })
      if (!r.ok) throw new Error(r.statusText)
      const s = await r.json()
      onSessionUpdate(s)
      onToast('Machine → ' + s.active_machine, 'ok')
    } catch (e) {
      onToast('Error: ' + e.message, 'er')
    }
  }

  const activeMachine = session?.active_machine
  const hasMessages = messages.length > 0

  return (
    <div className={`panel ${isActive ? 'on' : ''}`} id="p-chat">
      <div className="chat-msgs">
        {!hasMessages && (
          <div className="welcome">
            <div className="welcome-mark">
              <svg viewBox="0 0 24 24">
                <path d="M12 5C7 5 2.73 8.11 1 12.5 2.73 16.89 7 20 12 20s9.27-3.11 11-7.5C21.27 8.11 17 5 12 5zm0 12.5a5 5 0 110-10 5 5 0 010 10zm0-8a3 3 0 100 6 3 3 0 000-6z" />
              </svg>
            </div>
            <div className="welcome-title">Machine Intelligence</div>
            <div className="welcome-sub">Ask Iris about machine status, alerts, work orders, and maintenance across your facility.</div>
            <div className="welcome-pills">
              {WELCOME_PROMPTS.map(p => (
                <div key={p} className="welcome-pill" onClick={() => { setInputText(p); taRef.current?.focus() }}>
                  {p}
                </div>
              ))}
            </div>
          </div>
        )}
        {messages.map(msg => <Message key={msg.id} msg={msg} />)}
        <div ref={msgsEndRef} />
      </div>

      <div className="chat-input-area">
        <div className="chat-meta">
          <div
            className={`mach-badge ${activeMachine ? 'set' : ''}`}
            onClick={() => { setQsOpen(x => !x); setQsInput(activeMachine || '') }}
          >
            <svg width="10" height="10" viewBox="0 0 20 20" fill="currentColor">
              <rect x="1" y="1" width="7" height="7" rx="1" />
              <rect x="12" y="1" width="7" height="7" rx="1" />
              <rect x="1" y="12" width="7" height="7" rx="1" />
              <rect x="12" y="12" width="7" height="7" rx="1" />
            </svg>
            {activeMachine || 'Set active machine'}
          </div>

          {qsOpen && (
            <div className="qs-row">
              <input
                className="qs-input"
                value={qsInput}
                placeholder="Machine ID"
                maxLength={20}
                onChange={e => setQsInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') applyMach()
                  if (e.key === 'Escape') setQsOpen(false)
                }}
                autoFocus
              />
              <button className="btn btn-primary" style={{ padding: '4px 10px', fontSize: '11px' }} onClick={applyMach}>Set</button>
              <button className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: '11px' }} onClick={() => setQsOpen(false)}>Cancel</button>
            </div>
          )}
        </div>

        <div className="input-row">
          <div className="ta-wrap">
            <textarea
              ref={taRef}
              className="chat-ta"
              rows={1}
              placeholder="Ask about machines, alerts, work orders…"
              value={inputText}
              disabled={isStreaming}
              onChange={e => { setInputText(e.target.value); autosize(e.target) }}
              onKeyDown={taKey}
            />
          </div>
          <button className="send-btn" disabled={isStreaming || !inputText.trim()} onClick={doSend}>
            <svg viewBox="0 0 16 16">
              <path d="M15.964.686a.5.5 0 0 0-.65-.65L.767 5.855a.75.75 0 0 0-.124 1.329l4.995 3.178 1.6 4.823a.75.75 0 0 0 1.33.12l8.4-13.4a.5.5 0 0 0-.004-.619z" />
            </svg>
            Send
          </button>
        </div>
        <div className="chat-hint">Enter to send · Shift+Enter for new line</div>
      </div>
    </div>
  )
}
