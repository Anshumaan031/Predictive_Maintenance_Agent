# Write Tools — How They Work

`src/agent/tools.py` registers four Redis write-back tools on the Pydantic AI
agent. Unlike the Context Retriever MCP tools, which are auto-generated from
your live data model, these tools carry their schema knowledge statically in
code. This document explains the design and the trade-offs.

---

## How tools get attached

`attach_write_tools(agent, redis_client)` is called in `build_agent` only when
`REDIS_URL` is set in `.env`. Pydantic AI's `@agent.tool_plain` decorator
registers each inner function as a callable tool that the LLM can invoke by
name. The `redis_client` is closed over, so the model never touches it directly.

```
.env  →  Settings.redis_enabled  →  build_agent passes redis_client
                                           ↓
                                   attach_write_tools(agent, redis_client)
                                           ↓
                         @agent.tool_plain  ×4  (closures over redis_client)
```

---

## The four tools

| Tool | What it writes | Key it touches |
|---|---|---|
| `create_work_order` | New JSON doc | `work_order:WO<n>` |
| `update_work_order_status` | `$.status` field | `work_order:<id>` |
| `assign_technician` | `$.technician_id` field | `work_order:<id>` |
| `flag_machine_status` | `$.status` field | `machine:<id>` |

---

## Where the "schema" lives

There is no runtime schema discovery. All structural knowledge is encoded
directly in the source file in three places.

### 1. Validation frozensets

```python
_VALID_WO_STATUSES   = frozenset({"scheduled", "in_progress", "completed", "cancelled"})
_VALID_MACHINE_STATUSES = frozenset({"running", "fault", "maintenance", "idle"})
_VALID_WO_TYPES      = frozenset({"repair", "inspection", "lubrication", "maintenance"})
_VALID_PRIORITIES    = frozenset({"low", "normal", "high", "urgent"})
```

These are checked before any Redis call. If the model passes a value not in the
set, the function returns an error string — Redis is never touched.

### 2. Key naming conventions

Every function builds Redis keys from the id arguments using a fixed pattern:

```python
f"work_order:{work_order_id.upper()}"   # → work_order:WO1041
f"machine:{machine_id.upper()}"         # → machine:M104
f"technician:{technician_id.upper()}"   # → technician:T03
```

These patterns must match whatever convention your seed data uses. If your
keys are lowercase or use a different separator, the `json().get()` calls will
return `None` and every tool will report "not found."

### 3. JSONPath strings

Field updates target specific paths inside the JSON doc:

```python
redis_client.json().set(key, "$.status",        new_status)
redis_client.json().set(key, "$.technician_id", technician_id)
```

This assumes the JSON stored at each key has a `status` or `technician_id`
field at the root level. If your schema nests those fields differently, the
path must change here.

---

## How the model learns about the schema

The model never reads `tools.py`. It learns the schema from two sources:

**Tool docstrings** — each function has an `Args:` block that lists valid
values explicitly:

```
new_status: Target status — one of: scheduled, in_progress, completed, cancelled.
```

Pydantic AI passes these docstrings to the LLM as the tool description, so the
model knows what values are legal before it calls the tool.

**`WRITE_TOOLS_PROMPT`** in `prompts.py` — tells the model the four tools
exist and what kind of user requests should trigger them. Without this, the
model may ignore the tools even though they are registered (the system prompt's
read-only naming convention description would otherwise dominate).

---

## What happens on a write request (end-to-end)

```
User: "Create a routine inspection for M201 with low priority."
         ↓
LLM reads WRITE_TOOLS_PROMPT  →  knows create_work_order exists
         ↓
LLM calls: create_work_order(machine_id="M201", order_type="inspection",
                              priority="low", description="Routine inspection")
         ↓
tools.py: "inspection" ∈ _VALID_WO_TYPES  ✓
          "low"        ∈ _VALID_PRIORITIES ✓
         ↓
redis_client.json().get("machine:M201")  →  exists ✓
         ↓
scan_iter("work_order:WO*")  →  finds highest existing WO number
new id = WO<max+1>
         ↓
redis_client.json().set("work_order:WO<n>", "$", { id, machine_id, type, ... })
         ↓
returns: "Created WO1044 (type=inspection, priority=low) for machine M201."
         ↓
LLM relays confirmation to user
```

---

## What to update when your schema changes

| Change | What to update in tools.py |
|---|---|
| New work order status value | Add to `_VALID_WO_STATUSES` |
| New machine status value | Add to `_VALID_MACHINE_STATUSES` |
| New work order type | Add to `_VALID_WO_TYPES` |
| New priority level | Add to `_VALID_PRIORITIES` |
| Redis key prefix changes | Update the f-string in each affected function |
| JSON field renamed/nested | Update the JSONPath string in `json().set()` |
| New writable field | Add a new `@agent.tool_plain` function in `tools.py` and describe it in `WRITE_TOOLS_PROMPT` |

---

## Contrast with Context Retriever MCP tools

| | Context Retriever MCP | Write tools (`tools.py`) |
|---|---|---|
| Schema source | Live introspection of Redis data model at startup | Hardcoded in source |
| Tool generation | Automatic (`get_`, `filter_`, `search_`, `find_`) | Manual (`@agent.tool_plain`) |
| Adapts to schema changes | Yes, on restart | No, requires code change |
| Direction | Read-only | Write-only |
| How model discovers them | Tool names + MCP descriptions | Docstrings + `WRITE_TOOLS_PROMPT` |
