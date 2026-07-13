# Redis Iris Agent

A [Pydantic AI](https://ai.pydantic.dev) agent that gives an LLM a real **context layer** with [Redis Iris](https://redis.io/iris/):

- **Context Retriever** — live business data exposed as auto-generated MCP tools (`get_*_by_id`, `filter_*_by_*`, `search_*_by_text`, `find_*_by_*_range`). No per-query code, no hand-written API layer.
- **Agent Memory** — short-term (session) and long-term (cross-session) memory backed by semantic vector search. Durable facts are auto-promoted from conversation history and recalled via `search_memory` / `store_memory`.

Shipped with a **CrestForge Industries** predictive-maintenance demo: eight machines, fault history, open alerts, work orders, technicians, and parts — all queryable in plain English.

> Context Retriever and Agent Memory are in preview. This is a proof-of-concept, not a production template.

---

## Demo

```
iris › What's the status on M104?
  ↳ get_machine_by_id          {"id": "M104"}
  ↳ search_memory              {"query": "M104 fault history"}

M104 (Alpha Mill) is currently in a fault state with a critical bearing
failure. Based on your shift memory, this is a recurring issue — the same
bearing failed six weeks ago. Work order WO-2204 is already open and assigned
to technician T03 (Marco Rivera).
```

One answer combining **Agent Memory** (the prior fault recalled from a previous shift) with **Context Retriever** (live machine state and open work orders).

---

## Architecture

```
                 ┌─────────────────────────────┐
                 │      Pydantic AI Agent       │
   you  ───────► │        (your LLM)            │
                 └───────┬──────────────┬───────┘
        toolsets=[MCPToolset]      tool_plain
                 │                      │
                 ▼                      ▼
      Context Retriever          Agent Memory
      (MCP, X-API-Key)           (search_memory / store_memory
      auto-generated tools        + per-turn session logging)
      over your Redis data        long-term recall across shifts
                 │                      │
                 └───────► Redis Cloud ◄┘
```

Context Retriever publishes a streamable-HTTP MCP endpoint. Pydantic AI's native MCP client wraps it as an `MCPToolset` — one line of config. Agent Memory is the `redis-agent-memory` SDK, registered as two plain tools on the agent.

---

## Project layout

```
src/
├── agent/
│   ├── agent.py          ← Pydantic AI Agent + MCPToolset construction
│   ├── cli.py            ← Rich/prompt-toolkit chat REPL
│   ├── config.py         ← env loading + Settings dataclass
│   ├── memory.py         ← MemoryService wrapper (session log, search, store)
│   ├── model_provider.py ← multi-provider model builder (Anthropic, OpenAI, etc.)
│   └── prompts.py        ← system prompt, memory prompt, /help text
├── api/
│   ├── app.py            ← FastAPI server (all routes, SSE streaming, lifespan)
│   ├── state.py          ← singleton AppState for the HTTP server
│   └── models.py         ← Pydantic request/response schemas
├── crestforge/
│   ├── configure.py      ← provision the Context Retriever surface + mint agent key
│   └── seed.py           ← seed 28 Redis records + 6 pre-built long-term memories
└── utils/
    └── tool_names.py     ← safe_name_map() for sanitizing MCP tool names

docs/
├── api/TESTING_GUIDE.md  ← how to test every HTTP endpoint
├── CRESTFORGE_USE_CASE.md
└── CRESTFORGE_SETUP_GUIDE.md
```

---

## Prerequisites

1. A **Redis Cloud** database (free 30 MB tier is enough).
2. A **Context Retriever service** over that database — created in the Redis Cloud console, or provisioned by `crestforge-config` (see [Setup](#setup)).
3. A **Context Retriever agent key** (scoped read key for the running agent).
4. An **LLM provider API key** (Anthropic, OpenAI, Google, or OpenRouter).
5. *(Optional)* **Agent Memory** service — endpoint, store id, and key.
6. [`uv`](https://docs.astral.sh/uv/) installed.

---

## Setup

```bash
uv sync
cp .env.example .env   # fill in your keys (see Configuration below)
```

### Run the CrestForge demo from scratch

```bash
# 1. Seed Redis: 8 machines, alerts, work orders, fault history, technicians, parts
#    + 6 pre-built long-term memories so the demo starts with institutional knowledge
uv run crestforge-seed

# 2. Provision the Context Retriever surface (~35 tools) and mint an agent key.
#    The key is written to _agentkey.tmp — copy it to .env as CONTEXT_RETRIEVER_AGENT_KEY
uv run crestforge-config

# 3. Chat
uv run iris-agent
```

### Point it at your own Context Retriever service

Set `CONTEXT_RETRIEVER_AGENT_KEY` (and an LLM key) in `.env` and run:

```bash
uv run iris-agent
```

---

## Running as an HTTP API

The agent also ships as a FastAPI server with SSE streaming — useful for driving a web UI.

```bash
python -m uvicorn src.api.app:app --reload
# or: uv run iris-api
```

Interactive docs at `http://localhost:8000/docs`.

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat` | SSE stream: `thinking` → `tool_call`(s) → `text` → `done` |
| `POST` | `/chat/sync` | Same result as `/chat` but plain JSON — use in Swagger UI / Postman |
| `GET` | `/session` | Current owner, session ID, active machine, memory status |
| `POST` | `/session/machine` | Set active machine (`{"machine_id": "M104"}`) |
| `POST` | `/session/new-shift` | Rotate session ID, clear history (long-term memory persists) |
| `DELETE` | `/session/history` | Clear conversation history only |
| `GET` | `/tools` | List all Context Retriever MCP tools |
| `GET` | `/health` | Provider, model, tool count, memory status |

See [`docs/api/TESTING_GUIDE.md`](docs/api/TESTING_GUIDE.md) for curl examples and a recommended test sequence.

---

## CLI commands

| Command | Effect |
|---|---|
| `/machine <id>` | Focus on a machine — prepended to every prompt automatically |
| `/newshift` | New shift: clear history and active machine, rotate session ID. Long-term memory persists. |
| `/tools` | List all Context Retriever MCP tools |
| `/whoami` | Show owner ID, session ID, active machine, memory status |
| `/clear` | Clear conversation history |
| `/help` | Show all commands |
| `/exit` | Quit (also `/quit` or Ctrl-D) |

---

## Configuration

All values are loaded from `.env`.

### Agent (required)

| Variable | Purpose |
|---|---|
| `CONTEXT_RETRIEVER_AGENT_KEY` | Agent key sent as `X-API-Key` to the MCP endpoint |
| `PROVIDER` | LLM provider: `anthropic`, `openai`, `google`, or `openrouter` |
| `MODEL_NAME` | Model name for the chosen provider (e.g. `claude-sonnet-4-6`) |
| `API_KEY` | API key for the chosen provider |

### Agent (optional)

| Variable | Default | Purpose |
|---|---|---|
| `CTX_MCP_URL` | `https://gcp-us-east4.context-surfaces.redis.io/mcp` | Context Retriever endpoint |

### Agent Memory (optional — set all three to enable)

| Variable | Purpose |
|---|---|
| `AGENT_MEMORY_ENDPOINT` | Agent Memory service base URL |
| `AGENT_MEMORY_STORE_ID` | Agent Memory store ID |
| `AGENT_MEMORY_KEY` | Agent Memory service key |

### Setup scripts only (`crestforge-config` / `crestforge-seed`)

| Variable | Purpose |
|---|---|
| `REDIS_URL` | Direct Redis connection string |
| `CTX_ADMIN_KEY` | Context Retriever admin key (manages surfaces, mints agent keys) |

### Multi-provider example

```env
# Anthropic
PROVIDER=anthropic
MODEL_NAME=claude-sonnet-4-6
API_KEY=sk-ant-...

# OpenRouter
PROVIDER=openrouter
MODEL_NAME=meta-llama/llama-3.3-70b-instruct
API_KEY=sk-or-...

# Google
PROVIDER=google
MODEL_NAME=gemini-2.5-pro
API_KEY=AIza...
```

---

## Notes

- **MCP connection is opened once** (`async with agent:`), not per-turn — avoids reconnect latency on every message.
- **Memory never breaks the chat** — `log_turn` swallows exceptions silently so a memory outage doesn't crash the conversation.
- **Memory is scoped server-side** by `owner_id` — the agent cannot read or write another user's memories.
- **Tool name sanitization** — Anthropic requires tool names matching `^[a-zA-Z0-9_-]{1,128}$`. Context Retriever derives names from entity names, so entities with spaces produce invalid names. `safe_name_map()` renames them transparently before the model sees them.

---

## License

MIT — see [LICENSE](LICENSE).
