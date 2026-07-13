# CrestForge Industries — Redis Iris Demo Use Case

> Business use case, schema, asset roster, and scripted demo arc for the POC.

---

## Business Problem

Every unplanned machine stoppage follows the same pattern: a sensor crosses a threshold, an alert fires, someone guesses the cause, and the wrong technician shows up with the wrong part — or a full shutdown is ordered when a 2-hour bearing swap would have sufficed.

The institutional knowledge that would have caught this faster — "last time M104 hit 8 mm/s vibration it was the front bearing, not the spindle" — lives in someone's head and disappears when they retire.

This is the ideal showcase for Redis Iris because a correct diagnosis requires **both** halves simultaneously — live sensor state from Context Retriever and accumulated fault history from Agent Memory — and neither alone is enough.

| KPI | What it demonstrates |
|---|---|
| ~70% of unplanned stoppages have a prior occurrence on file | Scope of the institutional-memory opportunity |
| Sub-5ms Redis retrieval | Live telemetry is never the bottleneck |
| 0 separate RAG pipelines | Agent pulls fault history exactly when needed |
| Cross-session recall | Machine knowledge compounds across shifts and crews |

---

## Redis Iris Component Roles

| Component | Role in this demo |
|---|---|
| **Context Retriever** | Live machine status, active alerts, open work orders, parts inventory — auto-generated MCP tools, no per-query code |
| **Agent Memory** | Durable fault signatures, resolution patterns, and technician preferences across shifts — recalled via semantic similarity |

The demo is constructed so removing either component visibly breaks every answer.

---

## Schema — 6 Entities

Field index type controls which tool gets generated:
- `TEXT` → `search_<entity>_by_text`
- `TAG` → `filter_<entity>_by_<field>`
- `NUMERIC` → `find_<entity>_by_<field>_range`
- key → `get_<entity>_by_id`

### `machine` — `machine:{id}`

| Field | Type |
|---|---|
| `name` | TEXT |
| `type` | TAG (cnc_mill / hydraulic_press / conveyor / compressor / robot_arm) |
| `location` | TAG (zone_a / zone_b / zone_c / zone_d) |
| `status` | TAG (running / idle / fault / maintenance) |
| `vibration_level` | NUMERIC (mm/s) |
| `temperature_c` | NUMERIC |
| `runtime_hours` | NUMERIC (hours since last major service) |

### `alert` — `alert:{id}`

| Field | Type |
|---|---|
| `machine_id` | TAG |
| `type` | TAG (vibration / temperature / pressure / lubrication / current_draw) |
| `severity` | TAG (info / warning / critical) |
| `status` | TAG (open / acknowledged / resolved) |
| `triggered_value` | NUMERIC |
| `threshold` | NUMERIC |

### `work_order` — `work_order:{id}`

| Field | Type |
|---|---|
| `machine_id` | TAG |
| `technician_id` | TAG |
| `type` | TAG (inspection / repair / replacement / lubrication) |
| `status` | TAG (scheduled / in_progress / completed / cancelled) |
| `priority` | TAG (low / medium / high / urgent) |
| `description` | TEXT |

### `fault_history` — `fault_history:{id}`

| Field | Type |
|---|---|
| `machine_id` | TAG |
| `fault_type` | TEXT |
| `root_cause` | TEXT |
| `resolution` | TEXT |
| `downtime_hours` | NUMERIC |

### `technician` — `technician:{id}`

| Field | Type |
|---|---|
| `name` | TEXT |
| `specialty` | TAG (mechanical / electrical / hydraulic / pneumatic) |
| `shift` | TAG (morning / afternoon / night) |
| `availability` | TAG (available / on_job / off_shift) |
| `certifications` | TEXT |

### `part` — `part:{id}`

| Field | Type |
|---|---|
| `name` | TEXT |
| `category` | TAG (bearing / belt / seal / sensor / motor / filter) |
| `compatible_machine_type` | TAG |
| `stock_level` | NUMERIC |
| `reorder_point` | NUMERIC |
| `lead_time_days` | NUMERIC |

---

## Generated Tool Surface (~35 tools)

**get by id** — `get_machine_by_id`, `get_alert_by_id`, `get_work_order_by_id`, `get_fault_history_by_id`, `get_technician_by_id`, `get_part_by_id`

**filter (exact)** — `filter_machine_by_type`, `filter_machine_by_location`, `filter_machine_by_status`, `filter_alert_by_machine_id`, `filter_alert_by_type`, `filter_alert_by_severity`, `filter_alert_by_status`, `filter_work_order_by_machine_id`, `filter_work_order_by_technician_id`, `filter_work_order_by_status`, `filter_work_order_by_priority`, `filter_fault_history_by_machine_id`, `filter_technician_by_specialty`, `filter_technician_by_shift`, `filter_technician_by_availability`, `filter_part_by_category`, `filter_part_by_compatible_machine_type`

**find by range** — `find_machine_by_vibration_level_range`, `find_machine_by_temperature_c_range`, `find_machine_by_runtime_hours_range`, `find_alert_by_triggered_value_range`, `find_fault_history_by_downtime_hours_range`, `find_part_by_stock_level_range`, `find_part_by_lead_time_days_range`

**search (text)** — `search_machine_by_text`, `search_work_order_by_text`, `search_fault_history_by_text`, `search_technician_by_text`, `search_part_by_text`

---

## Key Machines (seed data)

8 machines across 4 zones, each with a distinct demo role. Pre-seeded long-term memories let the demo start in "shift 2" — no need to act out the prior incident live.

| ID | Name | Type | Zone | Status | Active Issue | Pre-seeded memory |
|---|---|---|---|---|---|---|
| M104 | Alpha Mill | cnc_mill | zone_a | fault | A301 vibration critical 9.2 mm/s | Front bearing failure signature at 8+ mm/s — last fix: bearing replacement, 2h downtime |
| M312 | Delta Comp | compressor | zone_c | running | A308 temperature warning 87°C | Rising temp above 85°C precedes oil seal failure — not refrigerant; replace seal first |
| M207 | Beta Press | hydraulic_press | zone_b | maintenance | WO1042 in-progress lubrication | Always requires hydraulic specialist; pneumatic techs have mis-diagnosed 3× |
| M118 | Gamma Belt | conveyor | zone_a | running | none | Belt tension drifts after >500h runtime; pre-emptive check at 480h avoids slippage |
| M225 | Epsilon Arm | robot_arm | zone_b | idle | none | Calibration loses accuracy after firmware updates — always recalibrate after patch |
| M401 | Zeta Mill | cnc_mill | zone_d | running | none | *(no memory — new machine, no fault history)* |
| M309 | Eta Press | hydraulic_press | zone_c | running | none | *(no memory — shows graceful adaptation)* |
| M502 | Theta Conv | conveyor | zone_d | idle | none | *(no memory — recently installed)* |

### Alert records to seed

| Alert | Machine | Type | Severity | Status | Triggered value | Threshold |
|---|---|---|---|---|---|---|
| A301 | M104 | vibration | critical | open | 9.2 mm/s | 8.0 mm/s |
| A308 | M312 | temperature | warning | open | 87°C | 85°C |
| A295 | M207 | lubrication | warning | resolved | 0.4 bar | 0.8 bar |

### Work order records to seed

| WO | Machine | Technician | Type | Status | Priority |
|---|---|---|---|---|---|
| WO1041 | M104 | T03 | repair | scheduled | urgent |
| WO1042 | M207 | T07 | lubrication | in_progress | high |
| WO1038 | M118 | T01 | inspection | completed | low |

### Fault history records to seed

| FH | Machine | Fault type | Root cause | Resolution | Downtime (h) |
|---|---|---|---|---|---|
| FH801 | M104 | High vibration 8.1 mm/s | Front bearing wear | Bearing replacement (SKF 6205) | 2.1 |
| FH802 | M104 | Spindle noise | Loose collet — not bearing | Collet re-torque | 0.5 |
| FH810 | M312 | Overtemperature 91°C | Oil seal failure — not refrigerant | Seal replacement + oil flush | 4.0 |
| FH795 | M207 | Low hydraulic pressure | Pneumatic tech replaced wrong valve | Hydraulic specialist corrected — seal swap | 6.5 |

### Technician records to seed

| ID | Name | Specialty | Shift | Availability |
|---|---|---|---|---|
| T01 | Marcus Webb | mechanical | morning | available |
| T03 | Diana Cruz | mechanical | morning | available |
| T07 | Rajan Patel | hydraulic | morning | on_job |
| T11 | Sofia Lin | electrical | afternoon | off_shift |
| T14 | Owen Brandt | pneumatic | morning | available |

### Part records to seed

| ID | Name | Category | Compatible type | Stock | Reorder point | Lead time (days) |
|---|---|---|---|---|---|---|
| P201 | SKF 6205 Bearing | bearing | cnc_mill | 4 | 2 | 3 |
| P202 | SKF 6305 Bearing | bearing | cnc_mill | 1 | 2 | 3 |
| P310 | Compressor Oil Seal | seal | compressor | 2 | 1 | 5 |
| P411 | Hydraulic Valve Seal | seal | hydraulic_press | 3 | 2 | 4 |
| P508 | Conveyor Drive Belt | belt | conveyor | 2 | 1 | 7 |

---

## Scripted Demo Arc (3 scenarios, ~4 minutes)

### Scenario 1 — Critical vibration alert, memory-driven triage

**Machine:** Alpha Mill (M104) · `/machine M104`

```
you › M104 just triggered a critical vibration alert. What's wrong and what do we do?
  ↳ search_memory                     {"query": "M104 Alpha Mill vibration fault history"}
  ↳ get_machine_by_id                 {"id": "M104"}
  ↳ filter_alert_by_machine_id        {"value": "M104"}
  ↳ filter_fault_history_by_machine_id{"value": "M104"}
  ↳ filter_part_by_category           {"value": "bearing"}
iris › M104 is reading 9.2 mm/s — above the 8.0 threshold.
       Per fault history, this exact pattern (vibration crossing 8 mm/s)
       was a front bearing failure twice before — not a spindle issue.
       The fix was SKF 6205 bearing replacement, 2h downtime.
       4 units in stock. Recommend dispatching Diana Cruz (mechanical,
       available now) rather than a full shutdown.
```

**Point out:** Without the memory hit, the agent sees "critical vibration" and has two equally plausible causes: bearing or spindle. The wrong call means a 6-hour teardown vs a 2-hour swap. Agent Memory turned ambiguous telemetry into a confident diagnosis. Context Retriever confirmed parts are in stock before recommending the fix.

---

### Scenario 2 — Rising temperature, wrong instinct corrected by memory

**Machine:** Delta Comp (M312) · `/machine M312`

```
you › Delta Comp is running hot at 87°C. Probably low refrigerant?
  ↳ search_memory                     {"query": "M312 Delta Comp temperature overheating"}
  ↳ get_machine_by_id                 {"id": "M312"}
  ↳ filter_alert_by_machine_id        {"value": "M312"}
  ↳ filter_fault_history_by_machine_id{"value": "M312"}
  ↳ filter_part_by_category           {"value": "seal"}
iris › Actually, no — fault history FH810 shows that last time M312
       overheated (91°C), refrigerant was the first guess but the root
       cause was an oil seal failure. Refrigerant topping made it worse.
       The fix was seal replacement + oil flush, 4h downtime.
       2 compressor oil seals in stock (P310). Recommend seal inspection
       before touching refrigerant.
```

**Point out:** The operator's initial hypothesis was the intuitive one — and wrong. Switch to M309 (no fault history seeded) to show the contrast — same rising temperature, same question, and the agent says "I don't have prior fault history for this machine; recommend inspection before diagnosis."

---

### Scenario 3 — Cross-shift recall

**Machine:** Alpha Mill (M104) · `/newshift`

```
% newshift   ← working memory cleared, long-term memory persists

you › This is the afternoon crew. What's the situation on M104?
  ↳ search_memory                     {"query": "M104 Alpha Mill bearing repair dispatch"}
  ↳ get_machine_by_id                 {"id": "M104"}
  ↳ filter_work_order_by_machine_id   {"value": "M104"}
  ↳ get_technician_by_id              {"id": "T03"}
iris › M104 had a critical vibration alert at 9.2 mm/s this morning.
       Morning crew identified it as a front bearing failure (per prior
       fault history) and scheduled WO1041 with Diana Cruz for a
       SKF 6205 bearing swap — 2h job. WO1041 is currently scheduled,
       not yet started. Diana is still listed as available.
```

**Point out:** Brand-new shift — conversation history wiped. The agent reconstructed the full morning-crew diagnosis via semantic search over long-term memory, then confirmed current work order state via Context Retriever. This is the core Iris pitch: institutional machine knowledge that survives shift handoffs.

---

## Implementation Order

| # | Step | File | Unlocks |
|---|---|---|---|
| 1 | Add all 6 entities to seed script | `seed_crestforge.py` | Schema complete |
| 2 | Provision all 6 entities in Context Retriever | `configure_surface.py` | ~35 tools available |
| 3 | Bulk-seed long-term memories for M104, M312, M207, M118, M225 | `seed_crestforge.py` | Scenarios 1–3 ready |
| 4 | Add `/machine <id>` and `/newshift` slash commands | `src/redis_iris_agent/cli.py` | Multi-machine switching + shift reset |
| 5 | Add action tools: `dispatch_technician`, `create_work_order`, `update_work_order_status`, `reserve_part` | `src/redis_iris_agent/agent.py` | Agent acts, not just diagnoses |
