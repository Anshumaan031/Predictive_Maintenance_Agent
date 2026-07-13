# API Testing Guide — Redis Iris Agent

Covers every endpoint exposed by the FastAPI server (`src/api/app.py`).  
Start the server first, then work through the sections below.

---

## Start the server

```bash
python -m uvicorn src.api.app:app --reload
```

Server listens on `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs` (Swagger UI).

---

## 1. Health check

Confirm the server started and the agent is wired up correctly.

**Request**
```
GET /health
```

**curl**
```bash
curl http://localhost:8000/health
```

**Expected response**
```json
{
  "status": "ok",
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "mcp_url": "...",
  "memory_on": true,
  "tool_count": 35
}
```

If `status` is not `"ok"` or `tool_count` is 0, check your `.env` and Redis connection before continuing.

---

## 2. List available tools

Verify the Context Retriever MCP surface loaded all expected tools.

**Request**
```
GET /tools
```

**curl**
```bash
curl http://localhost:8000/tools
```

**Expected response** (abbreviated)
```json
{
  "count": 35,
  "tools": [
    { "name": "get_machine_by_id", "description": "Get a machine by its ID" },
    { "name": "search_alert",      "description": "Search alerts by filter" },
    ...
  ]
}
```

---

## 3. Session state

### 3a. Get current session

```
GET /session
```

```bash
curl http://localhost:8000/session
```

```json
{
  "owner_id": "machine-floor",
  "session_id": "session-1",
  "active_machine": null,
  "memory_on": true,
  "history_length": 0,
  "tool_count": 35
}
```

### 3b. Set active machine

Prepends `[Active machine: <id>]` to every subsequent prompt automatically.

```
POST /session/machine
Content-Type: application/json
```

```bash
curl -X POST http://localhost:8000/session/machine \
     -H "Content-Type: application/json" \
     -d '{"machine_id": "M104"}'
```

`active_machine` in the response will now be `"M104"`.

### 3c. Clear conversation history

Wipes in-memory message history without changing the session ID or long-term memory.

```
DELETE /session/history
```

```bash
curl -X DELETE http://localhost:8000/session/history
```

```json
{ "cleared": true, "session_id": "session-1" }
```

### 3d. Start a new shift

Increments the session ID, clears history and active machine.  
Long-term Agent Memory is preserved across the shift boundary.

```
POST /session/new-shift
```

```bash
curl -X POST http://localhost:8000/session/new-shift
```

`session_id` in the response will advance from `session-1` → `session-2`, and so on.

---

## 4. Chat — sync (Swagger UI / Postman / curl)

`/chat/sync` is the easiest way to test the agent: it blocks until the agent finishes and returns plain JSON.

**Request**
```
POST /chat/sync
Content-Type: application/json
```

**curl**
```bash
curl -X POST http://localhost:8000/chat/sync \
     -H "Content-Type: application/json" \
     -d '{"message": "What is the current status of machine M104?"}'
```

**Response**
```json
{
  "text": "Machine M104 (Alpha Mill) is currently in a fault state...",
  "tool_calls": [
    { "name": "get_machine_by_id", "args": { "id": "M104" } }
  ],
  "session": {
    "owner_id": "machine-floor",
    "session_id": "session-1",
    "active_machine": "M104",
    "memory_on": true,
    "history_length": 2,
    "tool_count": 35
  }
}
```

`tool_calls` shows every Context Retriever tool the agent invoked to answer the question.

### Test in Swagger UI

1. Open `http://localhost:8000/docs`
2. Expand `POST /chat/sync` → **Try it out**
3. Paste `{"message": "List all machines in fault state"}` into the body
4. Click **Execute** — the response appears inline

---

## 5. Chat — SSE stream

`/chat` streams events as they happen. Use this when building a UI.

**Request**
```
POST /chat
Content-Type: application/json
```

### curl (reads the stream in the terminal)

```bash
curl -N -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "Show me recent alerts for M312"}'
```

The `-N` flag disables curl's output buffering so events print as they arrive.

**Event stream**
```
data: {"type": "thinking"}

data: {"type": "tool_call", "name": "search_alert", "args": {"machine_id": "M312"}}

data: {"type": "text", "content": "Machine M312 has two open alerts…"}

data: {"type": "done", "session": {"session_id": "session-1", "history_length": 2, …}}
```

### Event types

| `type` | When | Extra fields |
|---|---|---|
| `thinking` | Immediately — agent has started | — |
| `tool_call` | Each tool the agent calls | `name`, `args` |
| `text` | Agent's final answer | `content` |
| `done` | Stream complete | `session` (full session dict) |
| `error` | Agent threw an exception | `message` |

### Postman

1. New request → `POST` → `http://localhost:8000/chat`
2. Body → raw → JSON: `{"message": "What parts are low on stock?"}`
3. Send — Postman renders the SSE event stream in the response pane natively

---

## 6. Recommended test sequence

A quick end-to-end smoke test that exercises every layer:

```bash
# 1. Server is alive
curl http://localhost:8000/health

# 2. Tools loaded
curl http://localhost:8000/tools | python -m json.tool | grep count

# 3. Focus on a machine
curl -X POST http://localhost:8000/session/machine \
     -H "Content-Type: application/json" \
     -d '{"machine_id": "M104"}'

# 4. Ask a question (sync)
curl -X POST http://localhost:8000/chat/sync \
     -H "Content-Type: application/json" \
     -d '{"message": "What faults does this machine have?"}'

# 5. Check history grew
curl http://localhost:8000/session

# 6. Cross-shift: rotate session, confirm history reset
curl -X POST http://localhost:8000/session/new-shift
curl http://localhost:8000/session

# 7. Ask again — long-term memory should surface prior fault knowledge
curl -X POST http://localhost:8000/chat/sync \
     -H "Content-Type: application/json" \
     -d '{"message": "Any known history on M104?"}'
```

---

## 7. Error cases

| Scenario | Expected response |
|---|---|
| Server still starting up | `503 Agent not initialized.` |
| MCP connection lost | `502` from `GET /tools`; chat requests will return `{"type":"error","message":"..."}` in SSE or `500` in sync |
| Message > 8 000 characters | Silently truncated to 8 000 chars before the agent sees it |
| Agent runtime exception | SSE: `{"type":"error","message":"..."}` / sync: `500` with `detail` |
