# Redis Iris Agent — Code Review & Improvement Suggestions

> Generated 2026-07-14. Companion to `POC_ROADMAP.md`. Covers bugs found in the
> current source and feature suggestions beyond what the roadmap already defines.

---

## Code Issues to Fix First

These are bugs or gaps in the existing code. Address before building new features.

### 1. `_to_text` bug — `memory.py:143–151`

The `break` inside the `for` loop exits after any exception from
`model_dump_json`, meaning the `.json()` fallback is never reached. The intent
was to fall through to `str(obj)` on failure, but `break` makes it jump out of
the loop immediately after the first exception.

**Fix:** replace `break` with `continue` so the next attribute is tried, or
rewrite as explicit sequential `try/except` blocks.

---

### 2. `/newshift` session-ID increment is fragile — `cli.py:241–244`

The logic `n[0]-{int(n[1]) + 1}` only works when the session ID is exactly
`prefix-<integer>`. A second `/newshift` on a fallback session ID produces
`session-1-2-2` instead of `session-1-3`, breaking the demo.

**Fix:** use a regex to find the trailing integer regardless of prefix depth,
e.g. `re.sub(r'(\d+)$', lambda m: str(int(m.group()) + 1), session_id)`.

---

### 3. `model_provider.py` doesn't call `load_dotenv()`

`build_model()` reads env vars with `os.getenv()` directly. `load_dotenv()` is
only called inside `config.load_settings()`. The ordering in `_run()` happens to
be correct today, but if `build_model()` is ever called standalone (e.g. a test
fixture), it silently reads stale env and produces a confusing `ModelConfigError`.

**Fix:** either call `load_dotenv()` at the top of `build_model()`, or document
the dependency explicitly in its docstring.

---

### 4. No input length guard

User input is passed to the model with no truncation or length check. Pasting a
large log file will silently blow the context window and produce a confusing
provider error rather than a helpful message.

**Fix:** add a guard in the chat loop (e.g. warn and truncate at 8 000 chars)
before calling `agent.run`.

---

## Roadmap Features — Priority Assessment

The roadmap's tiering is sound. Below is a sharper read on sequencing.

### Do first (unlocks the full demo arc)

#### Pre-seed long-term memories *(Demo Data section of roadmap)*

This is effectively Phase 0. Without pre-seeded memories, every cold demo
requires a "session 1" warmup before recall works. Seed C1004 / C1007 / C1010 /
C1012 preferences now so the first demo message already shows memory retrieval.

| Customer | Pre-seed |
|---|---|
| C1004 Jordan Rivera | "Prefers reship over refund when orders are delayed" |
| C1007 Casey Okafor | "Budget-conscious — prefers store credit over cash refund" |
| C1010 Morgan Larsen | "Prefers email follow-up, not phone calls" |
| C1012 Avery Sato | "VIP — always escalate if issue unresolved in 24 h" |

---

#### `/user <id>` switching — *Roadmap feature #3*

**One-line unlock of the multi-tenancy demo.** Memory scoping by `owner_id`
already exists in `memory.py:122`; adding `/user <customer_id>` to the slash
command dispatcher in `cli.py` just updates `identity.owner_id` and clears
`history`.

This proves memory isolation live — two customers, two preference sets — which
is the hardest thing to fake with a static demo and the easiest thing to
implement here.

---

#### Action write-back tools — *Roadmap feature #1*

The single highest-leverage item. The agent currently only reads; that is a
chatbot, not an agent. Four tools, each ~30 lines, using the `redis.Redis`
client pattern already in `seed_northpeak.py`:

- `create_ticket` — open a support ticket linked to customer + order
- `issue_store_credit` — write credit to a customer account
- `reship_order` — create a reshipment record
- `update_ticket_status` — advance a ticket through its lifecycle

Register each as `@agent.tool_plain` closures in `agent.py`, same pattern as
`search_memory` / `store_memory` at `agent.py:125`. Return a confirmation string
the LLM can relay to the user.

---

### High-value additions the roadmap underweights

#### Latency display — *Roadmap feature #6*

Cheap to add (two `time.perf_counter()` calls around `agent.run`) and high
visual impact. Showing `tools: 8ms · LLM: 1.9s` under each response makes the
"sub-5ms Redis retrieval" pitch tangible and contrasts Redis speed vs LLM
latency in a single line.

```
  ↳ get_customer_by_id  {"id": "C1004"}
  ↳ filter_order_by_customer_id  {"value": "C1004"}

  iris ›  Your Summit 2-Person Tent (O5099) is 4 days delayed…

  [dim]  1.9 s  ·  LLM 1.8 s  ·  tools 38 ms  ·  3 262 tokens[/dim]
```

---

#### Streaming responses — *Roadmap feature #7*

Swap `agent.run` for `agent.run_stream`. The spinner-then-dump UX reads as
scripted; streaming makes the agent feel live. Pydantic AI's streaming API is
close to a drop-in replacement in the chat loop.

---

#### `OWNER_ID` / `SESSION_ID` env vars

Currently there is no way to configure the demo identity without editing source
(`DEFAULT_OWNER_ID = "machine-floor"` is hardcoded in `cli.py:35`). Add these
as optional env vars read in `load_settings()` with the hardcoded values as
fallbacks. Trivial change, significant usability win for anyone running the demo.

---

#### `escalate_to_human` tool — *Roadmap feature #2, simplified*

The roadmap frames escalation as a combined "score + route" pipeline with a
keyword scorer. A leaner cut: add one `escalate_to_human(ticket_id, reason,
priority)` write-back tool that creates an `escalation:{id}` record, and let the
system prompt describe *when* the model should call it (VIP tier, frustrated
tone, unresolved after N turns). The model's judgment replaces the keyword
scorer — which is actually more honest to the "agent decides" pitch and requires
far less code.

---

#### `/export` command + audit log — *Roadmap feature #5*

Underrated for interviews. Being able to paste a `logs/session-<id>.jsonl` file
and say "here's every tool call, every token count, every latency" answers the
"how would you govern this in production?" question cold.

Append each turn to JSONL in the chat loop:

```json
{
  "ts": "2026-07-10T14:23:01Z",
  "session_id": "support-2",
  "owner_id": "C1004",
  "user_msg": "why is my order late?",
  "tool_calls": [
    {"name": "search_memory",               "args": {"query": "Jordan Rivera preferences"}},
    {"name": "get_customer_by_id",          "args": {"id": "C1004"}},
    {"name": "filter_order_by_customer_id", "args": {"value": "C1004"}}
  ],
  "assistant_msg": "Your Summit 2-Person Tent (O5099) is 4 days delayed…",
  "latency_ms": {"llm": 1840, "tools": 38},
  "tokens":     {"prompt": 3120, "completion": 142}
}
```

Add `/export` to dump the current session to a shareable file.

---

#### Eval / test harness — *Roadmap feature #4*

Two tests alone prove the core correctness claim:

- `test_tool_routing.py` — "where's my order" → asserts `filter_order_by_customer_id` fired
- `test_memory_recall.py` — cross-session preference recall → asserts `search_memory` fired and key fact appears in response

Pydantic AI's `TestModel` + captured transcripts make these cheap; no real LLM
or live Redis needed in CI.

---

## Recommended Implementation Order

| # | Item | Effort | Why now |
|---|---|---|---|
| 1 | Fix `_to_text` bug | Tiny | Silent memory recall failures |
| 2 | Fix `/newshift` increment | Tiny | Demo breaks on second shift |
| 3 | Pre-seed long-term memories | Small | Required for cold demo |
| 4 | `/user <id>` switching | Small | One-line multi-tenancy proof |
| 5 | Action write-back tools (×4) | Medium | Turns chatbot into agent |
| 6 | Latency display | Small | Makes Redis speed pitch concrete |
| 7 | Streaming responses | Small | Makes demo feel real |
| 8 | `OWNER_ID`/`SESSION_ID` env vars | Tiny | Removes hardcoded demo identity |
| 9 | `escalate_to_human` tool | Small | Human-in-the-loop story |
| 10 | `/export` + audit log | Medium | Governance / traceability story |
| 11 | Eval harness (`tests/`) | Medium | Engineering rigor signal |
| 12 | FastAPI web UI | Large | Visual wow for non-dev recruiters |
| 13 | One-command setup + Makefile | Small | Friction-free evaluation |
| 14 | GitHub Actions CI | Small | Free credibility (green badge) |
| 15 | README + demo GIF | Medium | Recruiter-facing polish |
