# Redis Iris Agent — Improvement Suggestions

> Generated 2026-07-14. Companion to `POC_ROADMAP.md`. Covers feature suggestions
> beyond what the roadmap already defines.

---

## Roadmap Features — Priority Assessment

The roadmap's tiering is sound. Below is a sharper read on sequencing.

### Do first (unlocks the full demo arc)

#### `/user <id>` switching — *Roadmap feature #3*

**One-line unlock of the multi-tenancy demo.** Memory scoping by `owner_id`
already exists in `memory.py:122`; adding `/user <customer_id>` to the slash
command dispatcher in `cli.py` just updates `identity.owner_id` and clears
`history`.

This proves memory isolation live — two users, two memory sets — which
is the hardest thing to fake with a static demo and the easiest thing to
implement here.

---

#### Action write-back tools — *Roadmap feature #1*

The single highest-leverage item. The agent currently only reads; that is a
chatbot, not an agent. Tools using the `redis.Redis` client pattern already in
`seed.py`:

- `update_work_order_status` — advance a work order through its lifecycle
- `assign_technician` — assign or reassign a technician to a work order
- `create_work_order` — open a new repair/inspection order for a machine
- `flag_machine_status` — update a machine's status (e.g. fault → maintenance)

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
  ↳ get_machine_by_id  {"id": "M104"}
  ↳ filter_alert_by_machine_id  {"value": "M104"}

  iris ›  Alpha Mill has a critical vibration alert (A301)…

  [dim]  1.9 s  ·  LLM 1.8 s  ·  tools 38 ms  ·  3 262 tokens[/dim]
```

---

#### Streaming responses — *Roadmap feature #7*

Swap `agent.run` for `agent.run_stream` in the CLI. The spinner-then-dump UX
reads as scripted; streaming makes the agent feel live. Pydantic AI's streaming
API is close to a drop-in replacement in the chat loop. (The API already streams
via SSE — this is CLI only.)

---

#### `OWNER_ID` / `SESSION_ID` env vars

Currently there is no way to configure the demo identity without editing source
(`DEFAULT_OWNER_ID = "machine-floor"` is hardcoded in `cli.py:41` and
`api/state.py`). Add these as optional env vars read in `load_settings()` with
the hardcoded values as fallbacks. Trivial change, significant usability win for
anyone running the demo against a different dataset.

---

#### `escalate_to_human` tool — *Roadmap feature #2, simplified*

The roadmap frames escalation as a combined "score + route" pipeline with a
keyword scorer. A leaner cut: add one `escalate_to_human(machine_id, reason,
priority)` write-back tool that creates an `escalation:{id}` record, and let the
system prompt describe *when* the model should call it (critical severity,
unresolved after N turns, no available technician). The model's judgment replaces
the keyword scorer — which is actually more honest to the "agent decides" pitch
and requires far less code.

---

#### `/export` command + audit log — *Roadmap feature #5*

Underrated for interviews. Being able to paste a `logs/session-<id>.jsonl` file
and say "here's every tool call, every token count, every latency" answers the
"how would you govern this in production?" question cold.

Append each turn to JSONL in the chat loop:

```json
{
  "ts": "2026-07-14T14:23:01Z",
  "session_id": "session-1",
  "owner_id": "machine-floor",
  "user_msg": "what's wrong with M104?",
  "tool_calls": [
    {"name": "get_machine_by_id",          "args": {"id": "M104"}},
    {"name": "filter_alert_by_machine_id", "args": {"value": "M104"}},
    {"name": "search_memory",              "args": {"query": "M104 fault history"}}
  ],
  "assistant_msg": "Alpha Mill has a critical vibration alert (A301)…",
  "latency_ms": {"llm": 1840, "tools": 38},
  "tokens":     {"prompt": 3120, "completion": 142}
}
```

Add `/export` to dump the current session to a shareable file.

---

#### Eval / test harness — *Roadmap feature #4*

Two tests alone prove the core correctness claim:

- `test_tool_routing.py` — "what's wrong with M104" → asserts `filter_alert_by_machine_id` fired
- `test_memory_recall.py` — cross-session bearing knowledge recall → asserts `search_memory` fired and key fact appears in response

Pydantic AI's `TestModel` + captured transcripts make these cheap; no real LLM
or live Redis needed in CI.

---

## Recommended Implementation Order

| # | Item | Effort | Why now |
|---|---|---|---|
| 1 | `/user <id>` switching | Small | One-line multi-identity proof |
| 2 | Action write-back tools (×4) | Medium | Turns chatbot into agent |
| 3 | Latency display | Small | Makes Redis speed pitch concrete |
| 4 | Streaming responses (CLI) | Small | Makes demo feel real |
| 5 | `OWNER_ID`/`SESSION_ID` env vars | Tiny | Removes hardcoded demo identity |
| 6 | `escalate_to_human` tool | Small | Human-in-the-loop story |
| 7 | `/export` + audit log | Medium | Governance / traceability story |
| 8 | Eval harness (`tests/`) | Medium | Engineering rigor signal |
| 9 | FastAPI web UI | Large | Visual wow for non-dev audience |
| 10 | One-command setup + Makefile | Small | Friction-free evaluation |
| 11 | GitHub Actions CI | Small | Free credibility (green badge) |
| 12 | README + demo GIF | Medium | Audience-facing polish |
