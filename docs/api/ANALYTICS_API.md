# Analytics API

The `/data/*` endpoints expose the Redis dataset directly to the UI for visualisation and exploration. Unlike the agent chat endpoints, these are synchronous REST calls that query Redis without going through the LLM.

All endpoints require `REDIS_URL` to be set in `.env`. If the connection is unavailable they return `503`.

---

## How it works

The analytics layer is fully schema-free. At each request it:

1. **Discovers** all entity types by scanning Redis keys and grouping them by prefix (`machine:M104` → entity type `machine`).
2. **Infers field types** from actual values — numeric, categorical (low-cardinality strings), or free text.
3. **Detects relationships** from field naming: any field ending in `_id` whose prefix matches a known entity type is treated as a foreign key (`machine_id` → `machine`).

Adding a new table or a new FK field requires no code changes — it appears automatically in every endpoint.

---

## Endpoints

### `GET /data/entities`

Lightweight list of all discovered entity types and their record counts.

**Response**
```json
{
  "entity_types": [
    { "name": "machine",      "count": 8 },
    { "name": "alert",        "count": 3 },
    { "name": "work_order",   "count": 3 },
    { "name": "fault_history","count": 4 },
    { "name": "technician",   "count": 5 },
    { "name": "part",         "count": 5 }
  ]
}
```

**UI use:** populate a sidebar entity browser or dashboard chip row.

---

### `GET /data/schema`

Full structural discovery: entity types, per-field type annotations, unique categorical values, numeric ranges, and inferred FK relationships.

**Response shape**
```json
{
  "entity_types": {
    "machine": {
      "count": 8,
      "fields": {
        "id":              { "type": "categorical", "unique_values": ["M104", "M118", ...] },
        "status":          { "type": "categorical", "unique_values": ["fault", "idle", "maintenance", "running"] },
        "vibration_level": { "type": "numeric", "min": 0.0, "max": 9.2 },
        "machine_id":      { "type": "categorical", "references": "machine" }
      }
    },
    "alert": { ... }
  },
  "relationships": [
    { "from_entity": "alert",      "via_field": "machine_id",    "to_entity": "machine" },
    { "from_entity": "work_order", "via_field": "machine_id",    "to_entity": "machine" },
    { "from_entity": "work_order", "via_field": "technician_id", "to_entity": "technician" },
    { "from_entity": "fault_history", "via_field": "machine_id", "to_entity": "machine" }
  ]
}
```

**UI use:** drive dynamic table column rendering, filter dropdowns, and a schema diagram.

---

### `GET /data/overview`

High-level counts and categorical value distributions across every entity type.

**Response shape**
```json
{
  "total_entities": 28,
  "entity_counts": {
    "machine": 8,
    "alert":   3,
    ...
  },
  "distributions": {
    "machine": {
      "status":   { "running": 5, "fault": 1, "maintenance": 1, "idle": 2 },
      "type":     { "cnc_mill": 2, "compressor": 1, "conveyor": 2, "hydraulic_press": 2, "robot_arm": 1 },
      "location": { "zone_a": 2, "zone_b": 2, "zone_c": 2, "zone_d": 2 }
    },
    "alert": {
      "severity": { "critical": 1, "warning": 2 },
      "status":   { "open": 2, "resolved": 1 }
    },
    ...
  }
}
```

**UI use:** dashboard stat cards, pie/bar charts for status and severity breakdowns.

---

### `GET /data/analytics`

Per-entity, per-field descriptive statistics. Categoricals get value-count distributions; numerics get min/max/mean/median/stdev.

**Response shape**
```json
{
  "machine": {
    "record_count": 8,
    "field_stats": {
      "status": {
        "type": "categorical",
        "distribution": { "running": 5, "fault": 1, "maintenance": 1, "idle": 1 },
        "null_count": 0
      },
      "vibration_level": {
        "type": "numeric",
        "count": 8,
        "min": 0.0,
        "max": 9.2,
        "mean": 1.762,
        "median": 0.7,
        "stdev": 3.041,
        "null_count": 0
      },
      "runtime_hours": {
        "type": "numeric",
        "count": 8,
        "min": 12,
        "max": 891,
        "mean": 276.75,
        "median": 267.0,
        "stdev": 274.3,
        "null_count": 0
      }
    }
  },
  ...
}
```

**UI use:** sensor distribution histograms, box plots, outlier highlighting (e.g. flag machines above mean + 1 stdev vibration).

---

### `GET /data/relationships`

Full graph payload for visualisation. Nodes are individual records; edges are FK links inferred from `*_id` fields.

**Response shape**
```json
{
  "node_count": 28,
  "edge_count": 12,
  "entity_types": ["machine", "alert", "work_order", "fault_history", "technician", "part"],
  "nodes": [
    {
      "id":          "machine:M104",
      "label":       "Alpha Mill",
      "entity_type": "machine",
      "status":      "fault",
      "type":        "cnc_mill",
      "location":    "zone_a",
      "vibration_level": 9.2,
      "temperature_c":   68.0,
      "runtime_hours":   512
    },
    ...
  ],
  "edges": [
    { "source": "machine:M104", "target": "alert:A301",     "relation": "machine_id" },
    { "source": "machine:M104", "target": "work_order:WO1041", "relation": "machine_id" },
    { "source": "technician:T03", "target": "work_order:WO1041", "relation": "technician_id" },
    ...
  ]
}
```

**UI use:** force-directed graph, adjacency matrix, or network diagram showing machine → alert → work order → technician chains.

---

### `GET /data/entity/{entity_type}`

All records for a given entity type, sorted by key.

**Example:** `GET /data/entity/machine`

**Response:** array of raw JSON documents with an added `_key` field.

**UI use:** sortable/filterable data tables per entity type.

---

### `GET /data/entity/{entity_type}/{record_id}`

Single record enriched with two relationship layers derived automatically from FK fields:

- `_references` — documents this record points to (outgoing FKs).
- `_referenced_by` — documents from other entity types that point back to this record (incoming FKs).

**Example:** `GET /data/entity/machine/M104`

**Response shape**
```json
{
  "id": "M104",
  "name": "Alpha Mill",
  "status": "fault",
  "vibration_level": 9.2,
  "_key": "machine:M104",
  "_references": {},
  "_referenced_by": {
    "alert": [
      { "id": "A301", "severity": "critical", "status": "open", ... }
    ],
    "work_order": [
      { "id": "WO1041", "status": "scheduled", "priority": "urgent", ... }
    ],
    "fault_history": [
      { "id": "FH801", "downtime_hours": 2.1, ... },
      { "id": "FH802", "downtime_hours": 0.5, ... }
    ]
  }
}
```

**Example:** `GET /data/entity/work_order/WO1041`

```json
{
  "id": "WO1041",
  "machine_id": "M104",
  "technician_id": "T03",
  "_references": {
    "machine_id":    { "id": "M104", "name": "Alpha Mill", ... },
    "technician_id": { "id": "T03",  "name": "Diana Cruz", ... }
  },
  "_referenced_by": {}
}
```

**UI use:** record detail panels showing full context — a machine page that auto-loads its alerts, work orders, and fault history without any hardcoded joins.

---

## Error responses

| Status | Condition |
|--------|-----------|
| `503`  | `REDIS_URL` not set or Redis unreachable at startup |
| `404`  | Entity type or record ID not found in Redis |

---

## Adding new data

Because discovery is key-scan based, any new entity type written as `{prefix}:{id}` JSON keys in Redis will appear in every endpoint automatically on the next request. Foreign keys are picked up as long as the field name follows the `{entity_type}_id` convention.
