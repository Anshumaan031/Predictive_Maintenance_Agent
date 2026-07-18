# Redis Iris Agent

An adaptive agent that acts as a second brain for industrial machine operations: it combines live plant data with durable, cross-shift institutional memory to diagnose faults, triage alerts, and recommend the right action in plain English.

Built with [Pydantic AI](https://ai.pydantic.dev) on [Redis Iris](https://redis.io/iris/), it comes pre-loaded with a **CrestForge Industries** predictive-maintenance demo: eight machines, fault history, open alerts, work orders, technicians, and parts.

> Context Retriever and Agent Memory are in preview. This is a proof-of-concept, not a production template.

---

## Introduction

Industrial operations lose time and money on the same pattern every day: a sensor crosses a threshold, an alert fires, and someone guesses the cause. The wrong technician shows up with the wrong part, or a full shutdown gets ordered when a 2-hour bearing swap would have sufficed. The institutional knowledge that would have caught it faster lives in someone's head and disappears when they retire.

This agent removes that bottleneck. It understands the live state of every machine, part, technician, and work order in the plant, and it remembers what happened on each asset across shifts, crews, and conversations. Ask it a question in plain English and it pulls the right structured records, recalls the relevant fault history, and answers with a confident recommendation rather than a guess.

Core capabilities:

- **Live context over structured and unstructured data.** Machine status, active alerts, open work orders, parts inventory, fault history, technician rosters, and free-text notes are all queryable through a single tool surface. No per-query code, no hand-written API layer.
- **Short-term and long-term memory scoped by user and session.** Conversation state is kept per session; durable fault signatures, resolution patterns, and technician preferences persist across shifts and users via semantic vector search. Memory is automatically promoted from session to long-term storage in the background, non-blocking.
- **Adaptive retrieval.** Instead of pre-filling a prompt with retrieved context, the agent decides at runtime what to pull. It calls named, typed tools only when a question actually needs them, so latency stays low and answers stay current.
- **Server-side isolation.** Memory is scoped by `owner_id` and data access is enforced by agent keys and data tags, so one user can never read or write another user's context.

The agent never touches operational systems directly. It only talks to Redis, through the Iris tool layer, and everything else is abstracted away.

---

## What is new here

### Context Retriever as an MCP tool layer

Instead of pre-filling a prompt with retrieved context, the agent is handed a set of tools and decides at runtime what to pull. You define a semantic data model once (entities, fields, and access tags), and Context Retriever **automatically generates the MCP tools** the agent calls at runtime. No per-query code, no hand-written API layer.

For the CrestForge demo, a six-entity schema produces roughly 35 tools:

| Tool family | Pattern | Example |
|---|---|---|
| Get by id | `get_<entity>_by_id` | `get_machine_by_id` |
| Filter (exact match) | `filter_<entity>by_<field>` | `filter_alert_by_severity` |
| Find by numeric range | `find_<entity>by_<field>_range` | `find_machine_by_vibration_level_range` |
| Search (free text) | `search_<entity>by_text` | `search_fault_history_by_text` |

Field type controls which tool is generated: `TEXT` produces a search tool, `TAG` produces a filter tool, `NUMERIC` produces a range tool, and the key produces a get-by-id tool.

### Structured and unstructured data at scale

The same tool surface covers both structured fields (status, severity, stock level, vibration in mm/s) and unstructured fields (fault descriptions, root causes, resolutions, technician notes). The agent queries them through typed, named tools rather than raw SQL or hand-rolled retrieval code. Row-level access is enforced server-side via agent keys and data tags, so the agent only sees what its access tags permit.

### Retrieval that compounds across shifts

Because retrieval happens on demand against live Redis data, the agent never works from a stale snapshot. Combined with semantic memory (below), each query adds to the institutional knowledge base and makes the next diagnosis faster and more confident.

---

## Agent Memory

Agent Memory gives the agent continuity across two time horizons, both scoped server-side by `owner_id` so one user can never read or write another user's memories.

| Tier | Scope | Storage |
|---|---|---|
| Session memory (short-term) | Current conversation state and session metadata | TTL-based expiration |
| Long-term memory | Durable fault signatures, resolution patterns, technician preferences across shifts and users | Text plus vector embeddings for semantic retrieval |

**Promotion is automatic.** As a conversation progresses, the service asynchronously extracts and stores important information in the background, non-blocking. Long-term memories can also be created directly via the API, which is how the CrestForge demo is pre-seeded with six institutional memories (machines M104, M312, M207, M118, M225) so shift 2 starts with prior knowledge already in place.

**Search is semantic.** Long-term memory uses similarity search over embeddings, so queries do not need to match stored text exactly. They match on intent. Asking "what do we know about M104 vibration" surfaces a memory written as "front bearing failure signature at 8+ mm/s".

**Memory never breaks the chat.** `log_turn` swallows exceptions silently, so a memory outage degrades gracefully rather than crashing the conversation.

---

## Use case: CrestForge Industries

Every unplanned machine stoppage follows the same pattern: a sensor crosses a threshold, an alert fires, someone guesses the cause, and the wrong technician shows up with the wrong part. A full shutdown gets ordered when a 2-hour bearing swap would have sufficed.

The institutional knowledge that would have caught this faster, "last time M104 hit 8 mm/s vibration it was the front bearing, not the spindle", lives in someone's head and disappears when they retire.

This is the ideal showcase for Redis Iris because a correct diagnosis requires **both** halves simultaneously: live sensor state from Context Retriever and accumulated fault history from Agent Memory. Neither alone is enough.

| KPI | What it demonstrates |
|---|---|
| ~70% of unplanned stoppages have a prior occurrence on file | Scope of the institutional-memory opportunity |
| Sub-5ms Redis retrieval | Live telemetry is never the bottleneck |
| 0 separate retrieval pipelines | The agent pulls fault history exactly when needed |
| Cross-session recall | Machine knowledge compounds across shifts and crews |

### Demo arc

Three scripted scenarios, roughly four minutes end to end:

1. **Critical vibration alert, memory-driven triage.** M104 reads 9.2 mm/s. Without memory, the agent sees "critical vibration" and has two equally plausible causes: bearing or spindle. The wrong call means a 6-hour teardown versus a 2-hour swap. Agent Memory turns ambiguous telemetry into a confident diagnosis, and Context Retriever confirms the SKF 6205 bearing is in stock before recommending the fix.
2. **Rising temperature, wrong instinct corrected by memory.** Delta Comp (M312) is running hot at 87C. The operator's first guess is low refrigerant. Fault history FH810 shows the last overheating event was an oil seal failure, and refrigerant top-ups made it worse. The agent recommends seal inspection before touching refrigerant.
3. **Cross-shift recall.** A new shift starts with conversation history wiped. The agent reconstructs the full morning-crew diagnosis via semantic search over long-term memory, then confirms the current work order state via Context Retriever. Institutional machine knowledge survives shift handoffs.

See [`docs/CRESTFORGE_USE_CASE.md`](docs/CRESTFORGE_USE_CASE.md) for the full schema, asset roster, and demo script.

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

Context Retriever publishes a streamable-HTTP MCP endpoint. Pydantic AI's native MCP client wraps it as an `MCPToolset`, one line of config. Agent Memory is the `redis-agent-memory` SDK, registered as two plain tools on the agent.

For a deeper look at the Iris platform (Context Retriever, Agent Memory, RDI, LangCache, Redis Search, and Redis Flex), see [`docs/redis-iris-notes.md`](docs/redis-iris-notes.md).

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
├── testing/DOCKER.md     ← how to run the stack with Docker
├── UI/DEV.md             ← how to run the React UI dev server
├── CRESTFORGE_USE_CASE.md
├── CRESTFORGE_SETUP_GUIDE.md
└── redis-iris-notes.md   ← in-depth notes on the Redis Iris platform
```

---

## Prerequisites

1. A **Redis Cloud** database (free 30 MB tier is enough).
2. A **Context Retriever service** over that database, created in the Redis Cloud console or provisioned by `crestforge-config` (see Setup).
3. A **Context Retriever agent key** (scoped read key for the running agent).
4. An **LLM provider API key** (Anthropic, OpenAI, Google, or OpenRouter).
5. *(Optional)* **Agent Memory** service: endpoint, store id, and key.
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
#    The key is written to _agentkey.tmp. Copy it to .env as CONTEXT_RETRIEVER_AGENT_KEY
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

The agent also ships as a FastAPI server with SSE streaming, useful for driving a web UI.

```bash
python -m uvicorn src.api.app:app --reload
# or: uv run iris-api
```

Interactive docs at `http://localhost:8000/docs`.

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat` | SSE stream: `thinking` → `tool_call`(s) → `text` → `done` |
| `POST` | `/chat/sync` | Same result as `/chat` but plain JSON. Use in Swagger UI / Postman |
| `GET` | `/session` | Current owner, session ID, active machine, memory status |
| `POST` | `/session/machine` | Set active machine (`{"machine_id": "M104"}`) |
| `POST` | `/session/new-shift` | Rotate session ID, clear history (long-term memory persists) |
| `DELETE` | `/session/history` | Clear conversation history only |
| `GET` | `/tools` | List all Context Retriever MCP tools |
| `GET` | `/health` | Provider, model, tool count, memory status |

See [`docs/api/TESTING_GUIDE.md`](docs/api/TESTING_GUIDE.md) for curl examples and a recommended test sequence.

---

## Running with Docker

Start Redis + API together with networking pre-configured. See [`docs/testing/DOCKER.md`](docs/testing/DOCKER.md).

### Option 1: Docker Compose (recommended)

```bash
# Build and start all services
docker compose up --build

# Run in detached (background) mode
docker compose up --build -d

# Stop everything
docker compose down
```

### Option 2: Manual build + run

Requires a running Redis instance separately.

```bash
# Build the image
docker build -t machine-iris-agent .

# Run the container
docker run --rm -p 8000:8000 --env-file .env -e REDIS_URL=redis://host.docker.internal:6379 machine-iris-agent
```

### Useful commands

```bash
# View logs (detached mode)
docker compose logs -f api

# Rebuild without cache
docker compose build --no-cache api
```

### Endpoints

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| RedisInsight | http://localhost:8001 |

---

## Running the UI

React + Vite frontend for the Iris agent. Connects to the FastAPI backend at `http://localhost:8000` by default (configurable in the sidebar). See [`docs/UI/DEV.md`](docs/UI/DEV.md).

### Setup

```bash
cd UI
npm install
```

### Run

```bash
# Start backend first (from project root)
uvicorn src.api.app:app --reload

# Then start the UI dev server
cd UI
npm run dev
```

Opens at `http://localhost:5173`.

### Build

```bash
npm run build      # outputs to UI/dist/
npm run preview    # preview the production build locally
```

### API URL

The backend URL can be changed at runtime via the input at the bottom of the sidebar. It persists in `localStorage` as `iris_api`.

---

## CLI commands

| Command | Effect |
|---|---|
| `/machine <id>` | Focus on a machine. Prepended to every prompt automatically |
| `/newshift` | New shift: clear history and active machine, rotate session ID. Long-term memory persists |
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

### Agent Memory (optional, set all three to enable)

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

- **MCP connection is opened once** (`async with agent:`), not per-turn. Avoids reconnect latency on every message.
- **Memory is scoped server-side** by `owner_id`. The agent cannot read or write another user's memories.
- **Tool name sanitization.** Anthropic requires tool names matching `^[a-zA-Z0-9_-]{1,128}$`. Context Retriever derives names from entity names, so entities with spaces produce invalid names. `safe_name_map()` renames them transparently before the model sees them.

---

## License

MIT, see [LICENSE](LICENSE).
