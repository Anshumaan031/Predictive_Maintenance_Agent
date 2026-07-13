# CrestForge Industries — End-to-End Setup Guide

> From zero to a running predictive-maintenance demo on Redis Iris.

---

## Overview

Three phases, roughly 30 minutes end-to-end:

| Phase | What happens | Who does it |
|---|---|---|
| **0 — Redis Cloud** | Create a database, enable Context Retriever + Agent Memory, collect keys | You (console) |
| **1 — Local env** | Install deps, fill `.env` | You (terminal) |
| **2 — Scripts** | Seed data, provision surface, run the agent | Scripts + terminal |

---

## Phase 0 — Redis Cloud Console

### 0.1 Create a database

1. Log in at [cloud.redis.io](https://cloud.redis.io).
2. **New database** → free 30 MB tier is sufficient.
3. Once active, go to **Connect** → **Redis client** and copy the connection string.

```
redis://default:<password>@<host>:<port>
```

Save this as `REDIS_URL` in `.env`.

---

### 0.2 Enable Context Retriever

Context Retriever is the live-data half of Redis Iris — it auto-generates MCP tools from your entity model so the agent can query Redis without hand-written code.

1. In the console sidebar, open **Context Retriever**.
2. Select **Create custom service**, fill in a name and select your database.
3. On the **Define Entities** step, add a placeholder entity to get through the wizard (the configure script will replace it):
   - Entity name: `machine` · Key template: `machine:{id}`
   - Add one placeholder field (`status`, type `text`) so the wizard accepts the form
4. Hit **Create** — once the service is active, go to the **Admin key** tab and copy the key.

| Variable | Where to copy from |
|---|---|
| `CTX_ADMIN_KEY` | Context Retriever service → Admin key tab |

> **Two keys, two purposes.** The admin key (`CTX_ADMIN_KEY`) is used only by the setup script — it can create surfaces, update entity models, and mint keys. After the setup script runs, it mints a narrower **agent key** (`CONTEXT_RETRIEVER_AGENT_KEY`) that can only call the generated query tools. The running agent uses the agent key only; it never sees the admin key. Leave `CONTEXT_RETRIEVER_AGENT_KEY` blank in `.env` for now — `configure_crestforge.py` writes it to `_agentkey.tmp` and you copy it in after Phase 2.2.

---

### 0.3 Enable Agent Memory

Agent Memory is the durable-recall half — fault signatures and past resolutions that persist across shifts and sessions.

1. In the console sidebar, open **Agent Memory**.
2. Create a new service (attach to the same database).
3. Go to the service → **Configuration** and copy all three values.

| Variable | What it is |
|---|---|
| `AGENT_MEMORY_ENDPOINT` | Service base URL |
| `AGENT_MEMORY_STORE_ID` | Store identifier |
| `AGENT_MEMORY_KEY` | Service auth key |

> Leave all three blank and the agent still runs — it just has no long-term memory (Scenario 3 in the demo arc won't work).

---

### 0.4 Get an LLM API key

The agent defaults to `anthropic:claude-sonnet-4-6`. Get a key from [console.anthropic.com](https://console.anthropic.com) and save it as `ANTHROPIC_API_KEY`.

To use a different provider, change `MODEL` in `.env` and set the matching key:

| Model string | Key variable |
|---|---|
| `anthropic:claude-sonnet-4-6` (default) | `ANTHROPIC_API_KEY` |
| `openai:gpt-4o` | `OPENAI_API_KEY` |
| `google-gla:gemini-2.5-pro` | `GEMINI_API_KEY` |

---

## Phase 1 — Local Environment

### 1.1 Install dependencies

```powershell
uv sync
```

A `.venv` is created automatically. All commands below use `uv run` so you never need to activate it manually.

### 1.2 Create your `.env`

```powershell
cp .env.example .env
```

Open `.env` and fill in every value you collected in Phase 0:

```dotenv
# Required for the agent
CONTEXT_RETRIEVER_AGENT_KEY=        # filled in by configure_crestforge.py (Phase 2.2)
ANTHROPIC_API_KEY=sk-ant-...

# Required for demo scripts
REDIS_URL=redis://default:<pw>@<host>:<port>
CTX_ADMIN_KEY=cs_admin_...

# Optional — enables long-term memory (Scenarios 2 and 3)
AGENT_MEMORY_ENDPOINT=https://...
AGENT_MEMORY_STORE_ID=...
AGENT_MEMORY_KEY=...
```

> `CONTEXT_RETRIEVER_AGENT_KEY` is left blank for now — `configure_crestforge.py` mints it and writes it to `_agentkey.tmp`. Copy it in after Phase 2.2.

---

## Phase 2 — Scripts

### 2.1 Seed the CrestForge dataset

Loads all 6 entities into Redis as JSON documents, then seeds the pre-built Agent Memory blobs so the demo starts in "shift 2" with institutional knowledge already in place.

```powershell
uv run python seed_crestforge.py
```

Flags:

| Flag | Effect |
|---|---|
| *(none)* | Additive upsert — safe to rerun |
| `--flush` | FLUSHDB first — wipes everything including Agent Memory keys |
| `--verify` | Print key counts and sample records without writing |

Expected output:

```
  loaded   8 machine keys
  loaded   3 alert keys
  loaded   3 work_order keys
  loaded   4 fault_history keys
  loaded   5 technician keys
  loaded   5 part keys
Loaded 28 JSON keys into Redis.
Seeded 5 long-term memories (M104 ×2, M312, M207, M118, M225).
```

---

### 2.2 Provision the Context Retriever surface

Creates a surface named **"CrestForge Industries"** with 6 entities and the correct field index types, waits for tool generation to complete, then mints a scoped agent key.

```powershell
uv run python configure_crestforge.py
```

Flags:

| Flag | Effect |
|---|---|
| *(none)* | Create or update surface + mint agent key |
| `--probe` | List existing surfaces only, no changes |

Expected output:

```
existing surfaces (0):
entities: ['machine', 'alert', 'work_order', 'fault_history', 'technician', 'part'] | entity_count: 6
created surface id=surf_...
  status=provisioning  tools=0
  status=provisioning  tools=0
  status=active  tools=35
final status: active | tools: 35
agent key minted: cs_agn_...(len 64) -> wrote _agentkey.tmp
```

Once it finishes, copy the agent key into `.env`:

```powershell
# PowerShell
$key = Get-Content _agentkey.tmp
# Open .env and paste as: CONTEXT_RETRIEVER_AGENT_KEY=<key>
```

---

### 2.3 Run the agent

```powershell
uv run redis-iris-agent
```

You should see the tool list load and the prompt appear:

```
iris  35 tools · memory on · user machine-floor
you ›
```

---

## Demo Arc

Run each scenario in order. See `docs/CRESTFORGE_USE_CASE.md` for the full scripted prompts and expected tool call traces.

### Scenario 1 — Critical vibration, memory-driven triage

```
/machine M104
you › M104 just triggered a critical vibration alert. What's wrong and what do we do?
```

**What to watch:** `search_memory` fires before any sensor tools. The agent identifies the bearing failure signature from fault history FH801 rather than guessing spindle — and confirms parts are in stock before recommending a 2-hour swap instead of a full shutdown.

---

### Scenario 2 — Rising temperature, wrong instinct corrected

```
/machine M312
you › Delta Comp is running hot at 87°C. Probably low refrigerant?
```

**What to watch:** The agent overrides the operator's intuition using fault history FH810 — refrigerant was the first guess last time too, and it was wrong (oil seal failure). Then switch to M309 (no fault history) to show graceful adaptation: same question, agent says "no prior history — recommend inspection before diagnosis."

---

### Scenario 3 — Cross-shift recall

```
/newshift
you › This is the afternoon crew. What's the situation on M104?
```

**What to watch:** Brand-new session, conversation history wiped. The agent reconstructs the morning crew's full diagnosis via semantic search over long-term memory, then confirms current work order state via Context Retriever. This is the core Iris pitch: institutional knowledge that survives shift handoffs.

---

## In-Chat Commands

| Command | What it does |
|---|---|
| `/machine <id>` | Set the active machine context (e.g. `/machine M104`) |
| `/newshift` | Reset working memory, long-term memory persists |
| `/tools` | List the 35 Context Retriever tools available |
| `/whoami` | Show current user id, session id, memory status |
| `/clear` | Clear conversation history only |
| `/help` | Show help |
| `/exit` | Quit |

---

## Troubleshooting

**`REDIS_URL is not set`**
Check that `.env` is in the repo root and `REDIS_URL` is uncommented and filled in.

**`surface status=provisioning` stuck for more than 2 minutes**
The surface tool generation is async on Redis Cloud's side. Re-run `configure_crestforge.py --probe` after a minute to check status.

**`35 tools` not showing — agent connects but tool list is short**
The surface may still be provisioning. Run `/tools` in the chat loop to see what's available, or re-run `configure_crestforge.py --probe` to check tool count on the surface.

**`search_memory` never fires**
Agent Memory env vars are missing or incomplete. Check that all three (`AGENT_MEMORY_ENDPOINT`, `AGENT_MEMORY_STORE_ID`, `AGENT_MEMORY_KEY`) are set. Run `/whoami` — it will say `memory off` if any are absent.

**Scenario 3 has no cross-session recall**
Run `seed_crestforge.py` again (additive, safe) — it re-seeds the five pre-built memories. Check `--verify` output to confirm memory keys are present.

---

## Files Created by the Scripts

| File | Git-tracked | Purpose |
|---|---|---|
| `_agentkey.tmp` | No | Agent key output from `configure_crestforge.py` — copy into `.env`, then delete |
| `.env` | No | Your keys — never committed |

---

## Implementation Checklist

- [ ] Redis Cloud database created and `REDIS_URL` copied to `.env`
- [ ] Context Retriever service enabled, `CTX_ADMIN_KEY` copied to `.env`
- [ ] Agent Memory service enabled, all three vars copied to `.env`
- [ ] `ANTHROPIC_API_KEY` set in `.env`
- [ ] `uv sync` ran cleanly
- [ ] `seed_crestforge.py` ran — 28 keys + 5 memories loaded
- [ ] `configure_crestforge.py` ran — surface active with 35 tools
- [ ] `CONTEXT_RETRIEVER_AGENT_KEY` copied from `_agentkey.tmp` into `.env`
- [ ] `uv run redis-iris-agent` shows `35 tools · memory on`
- [ ] Scenario 1 (M104 vibration) produces a memory-backed bearing diagnosis
- [ ] Scenario 2 (M312 temperature) overrides the refrigerant guess
- [ ] Scenario 3 (`/newshift`) recalls morning crew context in a fresh session
