# Iris Agent — Prompt Samples

A set of prompts that exercise every major capability of the agent. Run these
in the CLI (`python -m src.agent.cli`) in the order shown to get a coherent
demo flow. Commands prefixed with `/` are CLI slash commands; everything else
is a natural-language prompt to the model.

---

## 1. Session setup and identity

```
/whoami
```
Confirms the current user, session, and memory status at startup.

```
/machine M104
```
Pins machine M104 as the active context — subsequent prompts automatically
include `[Active machine: M104]` without the user having to type it.

---

## 2. Reading live data via Context Retriever (MCP tools)

```
What is the current status of machine M104?
```
Triggers `get_machine` or equivalent MCP tool. Shows the streaming tool-call
line (`↳ tool  {...}`) before the answer.

```
List all open work orders for M104.
```
Exercises a query/filter tool; verifies multi-result formatting.

```
Which technicians are currently available?
```
Broad query across the `technician` entity. Good for showing tool name
sanitisation in the header.

```
Show me all machines that are in a fault state.
```
Cross-entity query; confirms the agent can filter by field value.

```
/tools
```
Prints the full table of available Context Retriever tools — useful during a
demo to show what the MCP server exposes.

---

## 3. Redis write-back tools

### 3a. Update a work order status

```
Mark work order WO1041 as in progress.
```
Calls `update_work_order_status(work_order_id="WO1041", new_status="in_progress")`.
Response shows the `scheduled → in_progress` transition.

```
WO1041 is done. Close it out.
```
Calls `update_work_order_status` again with `new_status="completed"`. Tests
that the agent infers `completed` from natural language.

```
Cancel work order WO1042.
```
Exercises the `cancelled` status branch.

### 3b. Assign a technician

```
Assign technician T03 to WO1041.
```
Calls `assign_technician`. Shows the previous assignee → new assignee
transition in the confirmation.

```
Reassign WO1041 to T07.
```
Same tool, different technician — demonstrates reassignment and the previous
value being shown.

```
Put a non-existent technician T99 on WO1041.
```
Triggers the "Technician T99 not found" error path without making a write.

### 3c. Create a new work order

```
Open an urgent repair work order for machine M104: bearing noise on the main
drive shaft.
```
Calls `create_work_order(machine_id="M104", order_type="repair",
priority="urgent", description="bearing noise on the main drive shaft")`.
Response includes the new auto-incremented ID (e.g. `Created WO1044`).

```
Create a routine inspection for M201 with low priority.
```
Tests the `inspection` type and `low` priority branches.

```
Open a work order for machine X999.
```
Triggers the "Machine X999 not found" validation path.

### 3d. Flag machine status

```
M104 is now in maintenance mode.
```
Calls `flag_machine_status(machine_id="M104", new_status="maintenance")`.

```
M104 is back up and running.
```
Updates status to `running` — confirms round-trip.

```
Set machine M104 to an invalid state called "broken".
```
Triggers the invalid-status validation error without writing.

---

## 4. Agent memory (long-term persistence)

These prompts require `AGENT_MEMORY_*` env vars to be configured.

```
I prefer temperatures reported in Celsius.
```
Agent calls `store_memory` to persist the preference.

```
What are my preferences?
```
Agent calls `search_memory` — retrieves and echoes stored facts.

```
My name is Jordan and I'm the night-shift lead.
```
Stores a user-identity fact that should surface in future sessions.

Start a new session, then ask:

```
/newsession
Do you remember anything about me?
```
History is cleared but long-term memory persists — the agent surfaces what it
stored in the previous session.

---

## 5. User switching (identity scoping)

```
/user operator-2
```
Switches the active owner to `operator-2`, clears history and machine context.
Memory is now scoped to this new owner.

```
Do you remember anything about me?
```
Should return nothing — `operator-2` has no stored memories yet, demonstrating
memory isolation between users.

```
/user machine-floor
Do you remember anything about me?
```
Switches back — memories stored earlier under `machine-floor` reappear.

---

## 6. Conversation continuity (multi-turn context)

```
Tell me about WO1041.
```

```
Who is currently assigned to it?
```
No work order ID needed — the agent resolves the reference from history.

```
Move them to WO1042 instead.
```
Tests pronoun resolution: the agent maps "them" to the technician from the
previous turn and calls `assign_technician` on WO1042.

---

## 7. Slash-command reference

| Command | What it demonstrates |
|---|---|
| `/help` | Full help text |
| `/whoami` | Current user, session, memory state |
| `/machine <id>` | Pin active machine context |
| `/user <id>` | Switch user identity and scope |
| `/tools` | List all available MCP tools |
| `/clear` | Clear conversation history (memory persists) |
| `/newsession` or `/newshift` | Increment session ID, clear history |
| `/exit` or `/quit` | Exit the CLI |

---

## 8. Error and edge cases

```
Update the status of WO9999 to completed.
```
Work order not found — agent relays the error message cleanly.

```
Set machine M104 to status "offline".
```
Invalid status — validation fires before any Redis call.

```
Assign T03 to WO1041 and then immediately mark WO1041 as completed.
```
Two write operations in a single turn — verifies the agent chains tool calls
correctly.
