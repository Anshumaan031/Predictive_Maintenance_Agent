# Redis Iris Agent — Project Overview

## What This Project Is

A **Pydantic AI** agent that demonstrates Redis Iris — the unified, real-time context engine for AI agents launched by Redis on May 18, 2026. The agent wires together two Redis Iris services into one conversational CLI:

- **Context Retriever** — governs live business data as auto-generated MCP tools the LLM can call at runtime.
- **Agent Memory** — provides short-term (session) and long-term (cross-session, cross-user) memory backed by semantic vector search.

The combination lets an agent answer questions that require both *who the user is* (memory) and *what the live data says* (business records) — in a single response, across sessions.

---

## Why Redis Iris Exists

Traditional RAG pre-fills context into the pipeline before the agent runs. Iris inverts this: the agent is handed a set of tools and decides at runtime what data it needs. Redis CEO Rowan Trollope described it as:

> *"A flip to let the agent pull the data instead of presupposing and stuffing it into the pipeline."*

The four problems Iris solves at production scale:

| Problem | Iris solution |
|---|---|
| Fragmented data across many systems | Context Retriever creates a single governed view |
| Stale data | RDI syncs changes from source DBs in seconds via CDC |
| Slow retrieval latency | Redis in-memory + Flex SSD tier, sub-5ms |
| Stateless agents | Agent Memory stores and recalls facts across sessions |

---

## Architecture

```
                 ┌─────────────────────────────┐
                 │      Pydantic AI Agent       │
   you  ───────► │        (LLM, e.g. Claude)    │
                 └───────┬──────────────┬───────┘
        toolsets=[MCPToolset]      tool_plain
                 │                      │
                 ▼                      ▼
      Context Retriever          Agent Memory
      (MCP, X-API-Key)           (search_memory / store_memory
      auto-generated tools        + per-turn session logging)
      over your Redis data        long-term recall across sessions
                 │                      │
                 └───────► Redis Cloud ◄┘
```

**Context Retriever** publishes a streamable-HTTP MCP endpoint at `/mcp`, authenticated with an `X-API-Key` header. Pydantic AI's native MCP client consumes it as an `MCPToolset` — no per-query code needed.

**Agent Memory** is the managed `redis-agent-memory` SDK, wrapped as two plain tools (`search_memory` / `store_memory`) registered directly on the agent.

---

## Redis Iris Components Used

| Component | Role in this project |
|---|---|
| **Context Retriever** (Preview) | Exposes 5 data entities as ~29 auto-generated MCP tools. Agents call tools like `get_customer_by_id`, `filter_order_by_status`, `find_order_by_total_range`, `search_ticket_by_subject`. |
| **Agent Memory** (Preview) | Stores per-turn session events (short-term). Automatically promotes durable facts to long-term memory in the background. Recalled via semantic similarity search. |
| **Redis Search** (GA) | Powers retrieval for both Context Retriever (structured + vector) and Agent Memory (semantic recall). |

---

## Project Layout

```
src/redis_iris_agent/
  config.py          # env loading + validation (Settings dataclass)
  agent.py           # Pydantic AI Agent, MCPToolset, memory tool registration
  memory.py          # MemoryService wrapper (Identity, session log, search, store)
  cli.py             # Rich/prompt-toolkit chat REPL with /commands

seed_northpeak.py    # Loads 134 fictitious support records into Redis (customers,
                     # products, orders, shipments, tickets)
configure_surface.py # Provisions the Context Retriever surface (5 entities, ~29
                     # tools) and mints an agent key via the admin API
demo_hero.py         # Scripted two-session demo: store a preference, recall it in
                     # a new session together with live order data

docs/
  redis-iris-notes.md    # In-depth notes on every Redis Iris component
  PROJECT_OVERVIEW.md    # This file
```

---

## Key Source Files

### `config.py` — Settings

Loads everything from environment variables (`.env`). The only required value is `CONTEXT_RETRIEVER_AGENT_KEY`. Agent Memory is optional — all three `AGENT_MEMORY_*` variables must be set for memory to activate.

```python
@dataclass(slots=True)
class Settings:
    agent_key: str
    mcp_url: str
    model: str
    memory_endpoint: str | None = None
    memory_store_id: str | None = None
    memory_key: str | None = None

    @property
    def memory_enabled(self) -> bool:
        return bool(self.memory_endpoint and self.memory_store_id and self.memory_key)
```

### `agent.py` — Agent Construction

Builds the `MCPToolset` pointing at the Context Retriever MCP endpoint, then constructs the Pydantic AI `Agent` with that toolset. If memory is enabled, two plain tools (`search_memory`, `store_memory`) are attached as closures that close over the user's `MemoryService`.

Tool name sanitization handles a quirk: Context Retriever derives tool names from entity names. An entity with a space (e.g. "job queue") produces `get_job queue_by_id` — invalid for Anthropic's tool name regex. `safe_name_map()` renames these client-side before handing the toolset to the model.

### `memory.py` — MemoryService

Wraps the `redis-agent-memory` SDK with an `Identity` dataclass (`owner_id` + `session_id`). The session id is mutable so `/newsession` in the CLI rotates it while keeping the same user — this is what demonstrates cross-session long-term recall.

- `log_turn(role, text)` — appends each conversation turn to working memory; failures are swallowed so they never break the chat.
- `search(query)` — semantic search over the *current user's* long-term memories only (filtered by `owner_id`).
- `store(fact)` — immediately persists a durable fact to long-term memory.

### `cli.py` — Chat REPL

Persistent connection: the `async with agent:` block opens the MCP connection once and keeps it alive for the whole session (avoids per-turn reconnect overhead). After each agent response, tool calls are printed with `↳ tool_name  {args}` annotations so it's visible what Context Retriever (and memory) tools fired.

Slash commands:

| Command | Effect |
|---|---|
| `/tools` | Lists all available Context Retriever MCP tools |
| `/clear` | Clears conversation history |
| `/newsession` | Rotates session id (same user — demonstrates long-term recall) |
| `/whoami` | Shows current user/session id and memory status |
| `/help` | Shows command help |
| `/exit` / `/quit` | Quit |

---

## Demo Dataset — Northpeak Outfitters

A fictitious outdoor-gear retailer with 134 records across 5 entities:

| Entity | Key template | Notable fields |
|---|---|---|
| `customer` | `customer:{id}` | name (text), email (tag), tier (tag), city (tag), lifetime_orders (numeric) |
| `product` | `product:{id}` | name (text), category (tag), price (numeric) |
| `order` | `order:{id}` | customer_id (tag), product_id (tag), status (tag), total (numeric) |
| `shipment` | `shipment:{id}` | order_id (tag), carrier (tag), status (tag), eta (tag) |
| `ticket` | `ticket:{id}` | customer_id (tag), order_id (tag), subject (text), status (tag) |

The field index type controls which tool gets generated:
- **tag** → `filter_<entity>_by_<field>` (exact match)
- **text** → `search_<entity>_by_text` (full-text / keyword)
- **numeric** → `find_<entity>_by_<field>_range`
- **key component** → `get_<entity>_by_id`

---

## Hero Demo Flow

```
Session 1  (user = C1004 / Jordan Rivera)
  you › "I always prefer a reship over a refund when things go wrong."
    ↳ store_memory  {"fact": "Prefers reship over refund"}
  iris › Got it — noted for future interactions.

/newsession   ← working memory cleared; long-term memory persists

Session 2  (same user, new session)
  you › "It's Jordan Rivera, customer C1004. Why is my order late, and can you handle it like last time?"
    ↳ search_memory               {"query": "Jordan Rivera C1004 preferences"}
    ↳ get_customer_by_id          {"id": "C1004"}
    ↳ filter_order_by_customer_id {"value": "C1004"}
    ↳ filter_shipment_by_order_id {"value": "O5099"}
  iris › Your Summit 2-Person Tent (O5099) is 4 days delayed with UPS. Per your
         saved preference, I'm arranging an expedited reship — no action needed.
```

This is the core demonstration: one answer combining a durable user preference (stored in Session 1) with live order and shipment data — across a session boundary.

---

## Configuration

All values come from `.env` (copy from `.env.example`):

**Required:**

| Variable | Purpose |
|---|---|
| `CONTEXT_RETRIEVER_AGENT_KEY` | Agent key sent as `X-API-Key` to the MCP endpoint |
| `ANTHROPIC_API_KEY` (or equivalent) | LLM provider key matching `MODEL` |

**Optional:**

| Variable | Default | Purpose |
|---|---|---|
| `CTX_MCP_URL` | `https://gcp-us-east4.context-surfaces.redis.io/mcp` | Context Retriever endpoint (region) |
| `MODEL` | `anthropic:claude-sonnet-4-6` | Any Pydantic AI model string |
| `AGENT_MEMORY_ENDPOINT` | — | Agent Memory service URL |
| `AGENT_MEMORY_STORE_ID` | — | Agent Memory store id |
| `AGENT_MEMORY_KEY` | — | Agent Memory key |

**Demo scripts only:**

| Variable | Purpose |
|---|---|
| `REDIS_URL` | Direct Redis connection for `seed_northpeak.py` |
| `CTX_ADMIN_KEY` | Admin key for `configure_surface.py` |

---

## Running

```bash
uv sync                        # install dependencies

# Option A — point at your own Context Retriever service
uv run redis-iris-agent

# Option B — run the full Northpeak demo
uv run python seed_northpeak.py        # load 134 records into Redis
uv run python configure_surface.py    # provision 5 entities, mint agent key
uv run python demo_hero.py             # scripted two-session hero flow
uv run redis-iris-agent               # or chat freely
```

---

## Dependencies

| Package | Role |
|---|---|
| `pydantic-ai-slim[anthropic,mcp,openai]` | Agent framework + MCP client |
| `redis-context-retriever` | Admin SDK for provisioning surfaces |
| `redis-agent-memory` | Agent Memory client SDK |
| `redis` | Direct Redis connection (demo seed script) |
| `rich` | Terminal rendering (panels, tables, markdown) |
| `prompt-toolkit` | Async prompt with in-session history |
| `python-dotenv` | `.env` loading |

Requires Python ≥ 3.11.

---

## Key Design Decisions

1. **MCP connection is opened once** (`async with agent:`), not per-turn — avoids the latency of reconnecting to the Context Retriever on every message.

2. **Memory never breaks the chat loop** — `log_turn` swallows exceptions, so a memory service outage is silently tolerated rather than crashing the conversation.

3. **Memory is scoped server-side by `owner_id`** — the model never passes the user identity; it's baked into the `MemoryService` closure. An agent cannot read or write another user's memory.

4. **Tool name sanitization is client-side** — providers like Anthropic require tool names matching `^[a-zA-Z0-9_-]{1,128}$`. Context Retriever derives names from entity names, so entities with spaces produce invalid names; `safe_name_map()` renames them transparently before the model sees them.

5. **`/newsession` rotates only the session id**, keeping `owner_id` constant — this is the mechanism that demonstrates long-term memory persisting across sessions while working memory (the Pydantic AI `message_history`) is cleared.
