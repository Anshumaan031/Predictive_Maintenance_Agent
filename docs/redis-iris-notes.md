# Redis Iris — In-Depth Notes

---

## 1. What Is Redis Iris?

Redis Iris is a **unified, real-time context engine** for AI agents, launched by Redis on **May 18, 2026**. It is not a database — it is an **agent-facing platform layer** that sits between an AI agent and the data it needs to act on, delivering fresh, relevant, and navigable context at production scale.

> **Core idea:** LLMs are inherently stateless — every interaction starts from zero unless something external provides continuity. Redis Iris is that external continuity layer.

Agents fail in production not because they lack data, but because enterprise data is:
- **Fragmented** across CRMs, order systems, shipping providers, ticketing tools, etc.
- **Stale** — retrieved context may already be outdated by the time it's used
- **Slow** — latency compounds across multi-step workflows
- **Difficult to navigate** — raw data is not agent-readable

Redis Iris solves all four problems in one unified runtime.

---

## 2. Why Redis Iris Exists — The Problem It Solves

### The Shift from RAG to Context Architecture

Traditional RAG (Retrieval-Augmented Generation) was designed for human-scale queries — a developer or analyst running dozens of queries per day. AI agents at production scale generate **orders of magnitude more data requests**, breaking retrieval pipelines that were never built for that volume.

In classic RAG, developers **pre-fill context** for the agent: they predict what is relevant, stuff it into the pipeline, and hand it off. Redis Iris inverts this model entirely. As Redis CEO Rowan Trollope described it:

> *"It's just a flip to let the agent pull the data instead of presupposing and stuffing it into the pipeline."*

Now, agents are handed **a set of tools** and decide at runtime what context they need. The agent calls the Iris tool layer; the tool layer handles retrieval, memory, and freshness.

### Market Signal

- Redis is already used by **43% of enterprise AI agent stacks** in their runtime layer
- VentureBeat's Q1 2026 RAG Infrastructure Market Tracker: buyer intent for **hybrid retrieval tripled** from 10.3% → 33.3% between January and March 2026
- Retrieval optimisation overtook model evaluation as the **#1 enterprise AI investment priority** for the first time

---

## 3. Architecture Overview

Redis Iris is composed of **five tools**, all running on top of Redis as the underlying database:

| Tool | Status (at launch) | Role |
|---|---|---|
| **Redis Context Retriever** | Preview | Structured, governed access to business data |
| **Redis Agent Memory** | Preview | Short- and long-term memory across sessions |
| **Redis Data Integration (RDI)** | General Availability | Real-time data sync from source systems |
| **Redis LangCache** | GA | Semantic caching for LLM responses |
| **Redis Search** | GA | Vector, structured, and unstructured search |

**Key architectural constraint:** The agent **never touches operational systems directly** — not the database, not the ORM, not the CRM. The agent only talks to Redis, through Iris tools. Everything else is abstracted away.

---

## 4. Core Tools — Deep Dive

---

### 4.1 Redis Context Retriever

**What it does:** Turns fragmented business data into structured, governed tools that AI agents can reliably call at runtime.

**How it works:**
- Developers define a **semantic data model** once — specifying the entities that matter (e.g., `Customer`, `Order`, `Shipment`, `Policy`) and the fields agents need
- Context Retriever **automatically generates the MCP (Model Context Protocol) tools** agents use to query and navigate that data
- Agents never write raw queries — they call named, typed tools
- **Row-level access controls** are enforced server-side; agents only see data their access tags permit

**Key capabilities:**
- Define once, reuse across all agents (no per-agent rediscovery)
- Auto-generated tool surface exposed via MCP or CLI
- Access governed by agent keys and data tags
- Schema changes in source databases require corresponding updates to entity models

**Example use case:** A customer support bot needs to answer *"Why is my order late?"* — the answer may live across a customer database, order system, shipping provider, ticketing tool, and policy document. Context Retriever creates a single, governed, agent-readable view that pulls it all together in one flow.

#### Row-Level Security (RLS) via Agent Keys — How It Actually Works

Row-level access is enforced **server-side**, transparently to the agent. There is no client-side filter the LLM could forget or bypass — the agent simply receives fewer rows than an unrestricted caller would. The mechanism has three moving parts:

1. **Data tags (the lock).** Every row written into Redis carries one or more *access tags* declared as part of the surface's semantic data model. Tags are written at seed time and travel with the row. They are the policy: *whoever holds a key allowing tag X may read rows tagged X*.

2. **Agent keys (the key).** An admin uses the `CTX_ADMIN_KEY` to mint a scoped agent key against a surface (`src/crestforge/configure.py:299`, `client.create_agent_key(...)`). The minted key is bound to an allow-list of access tags — that binding is the key's authority. One surface can have many keys, each scoped to a different slice of the data; minting a new key is how you create a new trust boundary (tenant, zone, role, etc.) without changing any query code.

3. **`X-API-Key` on every tool call (the channel).** The agent sends this key as the `X-API-Key` header on every request to the Context Retriever MCP endpoint (`README.md` Configuration → `CONTEXT_RETRIEVER_AGENT_KEY`). Every one of the ~35 auto-generated tools — `get_<entity>_by_id`, `filter_<entity>_by_<field>`, `find_<entity>_by_<field>_range`, `search_<entity>_by_text` — goes through that same authenticated endpoint.

4. **Server-side intersection (the enforcement).** On each tool call, Context Retriever intersects the key's allowed tags with each row's tags and returns only the matching rows. From the LLM's point of view the tool simply returns fewer results — there is no model-side filtering step to get wrong. That is what the README calls "server-side isolation" (`README.md:22`, `README.md:47`) and what Section 9 of this document lists as "Row-level access control ✅ Built-in via access tags".

**Why this shape matters:**

- **No query rewriting per user/tenant.** The same MCP tools serve every agent; only the key differs. A "Zone A technician" agent gets a key tagged `zone_a`; a "Zone B" agent gets `zone_b`; a supervisor gets both. The tool surface is identical — the data visible through it changes.
- **Policy lives with the data, not the prompt.** Because tags are written into Redis alongside the row, access policy survives schema changes, prompt edits, and model swaps. The LLM cannot "prompt-inject" its way past a tag it doesn't hold.
- **One key per trust boundary.** Rotating, narrowing, or broadening access = minting/revoking a key, not editing per-tool code. Revoke the key and the agent is instantly blind to those rows.
- **Composable with Agent Memory isolation.** Context Retriever RLS (agent keys + data tags) controls *structured data* visibility; Agent Memory's `owner_id` scoping (see §4.2) controls *memory* visibility. Together they give full per-user isolation: one user can never read another user's rows or memories.

**Where the wiring shows up in this repo:**

| Step | File / location | What happens |
|---|---|---|
| Entity schema + tag-able fields declared | `src/crestforge/configure.py:50` (and the other `ContextModel` classes) | `ContextField(...)` declarations define which fields are indexed and taggable on the surface |
| Surface created/updated with the data model | `src/crestforge/configure.py:274` (`create_context_surface`) / `:265` (`update_context_surface`) | Pushes the entity model + data source to Context Retriever; tools auto-generate from it |
| Agent key minted against the surface | `src/crestforge/configure.py:299` (`create_agent_key`) | Produces a scoped key bound to the surface's access tags; written to `_agentkey.tmp` |
| Key loaded into the agent's env | `.env` → `CONTEXT_RETRIEVER_AGENT_KEY` (`README.md:333`) | Runtime config consumed by `src/agent/agent.py` / `src/agent/config.py` |
| Key sent on every MCP call | `src/agent/agent.py` (MCPToolset construction) | Pydantic AI's MCP client attaches `X-API-Key` to each Context Retriever request |
| Server enforces tag intersection | Context Retriever service (Redis Cloud) | Returns only rows whose tags match the key's allow-list |

---

### 4.2 Redis Agent Memory

**What it does:** Provides persistent short-term and long-term memory so agents can carry context across sessions, users, and tasks — without re-deriving it on every turn.

**Memory tiers:**

| Tier | Description | Storage |
|---|---|---|
| **Session Memory** (short-term / working) | Current conversation state and session metadata | Configurable TTL-based expiration |
| **Long-term Memory** | User preferences, learned patterns, extracted insights from past sessions | Text + vector embeddings for semantic retrieval |

**How promotion works:**
- As a conversation progresses, the service **asynchronously extracts and stores** important information in the background (non-blocking)
- Promotion from session → long-term memory is **automatic**
- Long-term memories can also be created directly via API (bulk imports, external knowledge)

**Search:** Long-term memory uses **semantic similarity search** — queries don't need to exactly match stored memory text; they match on intent

**Available as:** REST API and Python SDK

---

### 4.3 Redis Data Integration (RDI)

**What it does:** Keeps Redis Cloud continuously synced with an organization's existing relational databases using **Change Data Capture (CDC)** — so agents always have access to current, accurate data without hitting slow primary databases directly.

**Supported data sources:**
- PostgreSQL (via Debezium / logical replication — most production-proven path)
- Oracle (via LogMiner)
- MySQL
- SQL Server
- MongoDB (via change streams)
- Snowflake
- Databricks

**How it works:**
- RDI uses CDC pipelines to detect changes at the source database in real time
- Changed data is synced into Redis Cloud in formats **optimized for agent access**
- Creates a continuously updated **operational data plane** that separates systems of record from agent-facing retrieval
- Data freshness: changes are reflected in Redis **within seconds**

**Important note:** At launch, RDI was GA but with varying CDC maturity by source; Postgres via Debezium is the most battle-tested path.

---

### 4.4 Redis LangCache

**What it does:** A **semantic caching** service that stores and reuses LLM responses for prompts that are semantically similar — even if not word-for-word identical.

**How it works:**
- On each incoming prompt, LangCache computes embeddings and checks for **semantically similar** cached responses
- On a **cache hit**: returns the response immediately, no LLM call needed
- On a **cache miss**: the LLM is called, and the response is stored for future use
- Manages embeddings automatically (no manual embedding pipeline required)

**Configuration options:**
- **Similarity threshold**: Higher = more precise matches; lower = higher hit rate but potentially less relevant
- **TTL (Time to Live)**: How long cache entries are kept
- **Eviction policies**: Control how stale entries are removed
- **Attributes / Scoping tags**: Up to 5 tags to organize and scope cached data

**Benefits:**
- Up to **90% reduction in token costs** for repeated/similar queries
- Response latency drops from seconds (LLM call) to **milliseconds** (cache hit)
- Works for: AI assistants, chatbots, RAG applications, AI agents, centralized AI gateway services

---

### 4.5 Redis Search

**What it does:** The **retrieval backbone** underneath the entire Iris context engine — handles vector, structured, unstructured, and real-time data retrieval.

**Capabilities:**
- Vector similarity search (semantic search over embeddings)
- Full-text and structured query support
- Hybrid retrieval (combining keyword + vector)
- Real-time filtering on live data
- Powers the retrieval layer for both Context Retriever and Agent Memory

---

## 5. The Four Pillars of Great Context

Redis defines four requirements a context engine must meet for agents to function at scale:

1. **Navigable** — Agents must traverse relationships, understand entities, discover context, and access it through consistent interfaces (not raw SQL)
2. **Current (Fresh)** — Data must be accurate up to the instant; apps change state, CRMs update, events don't stop
3. **Fast** — Latency has a snowball effect; one slow step can collapse an entire multi-step workflow
4. **Compounding (Improving over time)** — As the system is used, it becomes more personalized, more relevant, and more informed by prior interactions

---

## 6. Redis Flex — The Infrastructure Enabler

Alongside Iris, Redis launched **Redis Flex**, an SSD-based storage tier designed to make Iris economically viable at enterprise scale.

**The problem:** Running all context data in RAM is fast but extremely expensive at scale. If you want to take a company's entire data estate and make a working subset available to agents, that subset could still be very large.

**Redis Flex:**
- Stores **99% of data on SSD** (flash), with hot data in RAM
- **~10x cheaper** than pure in-memory storage
- Optimized for flash as a native storage medium (not a bolt-on)
- Tested at **petabyte scale** with **sub-5 millisecond latency**
- Described by the Redis team as "the fastest flash-based data structure server in the world"

Flex is the storage layer underpinning Agent Memory — making large context windows and long agent memories feasible without blowing up infrastructure budgets.

---

## 7. Deployment & Access

- All four Iris services are **fully managed on Redis Cloud** via REST API
- **No database setup or management required**
- Available on **AWS, Azure, and Google Cloud** (multi-cloud)
- Also available in the **Snowflake Marketplace** (native connectors at launch)
- Works with **any agent framework** (no hyperscaler lock-in)
- **MCP (Model Context Protocol)** support: tools are exposed as MCP endpoints agents can discover and call
- **Python SDK** available for Agent Memory; REST API for all services

---

## 8. Integrations & Ecosystem

| Integration | Details |
|---|---|
| **LangSmith / LangChain** | Partnership: Redis Iris + LangSmith Context Hub for versioned agent memory |
| **LangGraph** | Official sample demos using Agent Memory + LangGraph |
| **Snowflake** | Native marketplace launch with Snowflake connectors |
| **MCP (Model Context Protocol)** | Context Retriever generates MCP tools for agent consumption |
| **Character.ai** | Early adopter; uses Redis for fast, low-latency intelligent search |
| **Safe in Home** | Uses Redis Agent Memory for real-time API monitoring agents |

---

## 9. Key Differentiators vs. Alternatives

| Capability | Redis Iris | Naive RAG / Vector DBs |
|---|---|---|
| Agent Memory (persistent) | ✅ Short + long-term, semantic | ❌ Stateless by default |
| Semantic Caching | ✅ LangCache (90% cost savings) | ❌ Typically not included |
| Real-time data sync | ✅ CDC via RDI (seconds of lag) | ❌ Usually batch / manual |
| Auto-generated agent tools | ✅ MCP tools from data model | ❌ Hand-coded per agent |
| Row-level access control | ✅ Built-in via access tags | ❌ Usually application-level |
| Cost efficiency at scale | ✅ Redis Flex SSD tier | ❌ Full RAM or expensive managed |
| Vendor lock-in | ❌ Multi-cloud, any agent framework | ⚠️ Often cloud-specific |

---

## 10. Typical Use Cases

1. **Customer Support Agents** — Pull live order status, shipping info, policy docs, and prior tickets into one coherent response
2. **Coding Agents** — Preserve engineering decisions, bug context, and development history across sessions and team members
3. **Voice Agents** — Sub-millisecond latency critical for real-time voice turn-taking
4. **Fraud Scoring Agents** — Real-time operational state for instant decisions
5. **Personalized User Experiences** — Long-term memory enables experiences that improve across sessions
6. **Enterprise AI Assistants** — Governed, role-filtered access to business data via typed MCP tools

---

## 11. Availability Summary (at Launch — May 2026)

| Tool | Availability |
|---|---|
| Redis LangCache | Generally Available |
| Redis Search | Generally Available |
| Redis Data Integration (RDI) | Generally Available (contact Redis for evaluation) |
| Redis Context Retriever | Preview |
| Redis Agent Memory | Preview (REST API + Python SDK) |
| Redis Flex (SSD tier) | Generally Available |

---

## 12. Quick Reference

- **Announced:** May 18, 2026
- **Official page:** redis.io/iris
- **Docs:** redis.io/docs/latest/develop/ai/context-engine/
- **Getting started tutorial:** redis.io/tutorials/getting-started-with-redis-iris/
- **Built on top of:** Redis Cloud (fully managed)
- **Underlying database:** Redis (open source)
- **SDK languages:** Python (Agent Memory); REST API for all services
- **Agent protocol support:** MCP (Model Context Protocol)
