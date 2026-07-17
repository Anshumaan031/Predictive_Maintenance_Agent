"""Dynamic analytics over any Redis dataset stored as JSON documents.

Automatically discovers entity types (key prefixes), infers field types,
detects foreign-key relationships via ``*_id`` naming conventions, and
computes per-entity statistics — all without hardcoded schema knowledge.

All functions are synchronous; call them with ``asyncio.to_thread()`` from
async FastAPI handlers.
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

_LABEL_CANDIDATES = ("name", "title", "label", "description")
_IGNORED_PREFIXES = {"__", "session", "memory"}  # internal Redis key namespaces


def discover(client: "redis.Redis") -> dict[str, list[dict]]:
    """Scan all JSON keys and group documents by entity-type prefix.

    A key ``work_order:WO1041`` belongs to entity type ``work_order``.
    Keys without exactly one ``:`` separator are skipped.
    """
    all_keys: list[str] = list(client.scan_iter(match="*:*", count=5000))
    prefix_to_keys: dict[str, list[str]] = {}
    for key in all_keys:
        parts = key.split(":", 1)
        if len(parts) != 2:
            continue
        prefix = parts[0]
        if any(prefix.startswith(ig) for ig in _IGNORED_PREFIXES):
            continue
        prefix_to_keys.setdefault(prefix, []).append(key)

    entity_data: dict[str, list[dict]] = {}
    for prefix, keys in prefix_to_keys.items():
        pipe = client.pipeline()
        for k in keys:
            pipe.json().get(k)
        raw = pipe.execute()
        # attach the key so we always have a stable record id
        docs = []
        for k, doc in zip(keys, raw):
            if doc is None:
                continue
            if "_key" not in doc:
                doc = {**doc, "_key": k}
            docs.append(doc)
        entity_data[prefix] = docs

    return entity_data


# ---------------------------------------------------------------------------
# Field-type inference
# ---------------------------------------------------------------------------

_NUMERIC_TYPES = (int, float)


def _field_type(values: list[Any]) -> str:
    """Return ``numeric``, ``categorical``, ``id_ref``, or ``text``."""
    non_null = [v for v in values if v is not None and v != ""]
    if not non_null:
        return "unknown"
    if all(isinstance(v, _NUMERIC_TYPES) for v in non_null):
        return "numeric"
    if all(isinstance(v, str) for v in non_null):
        unique_ratio = len(set(non_null)) / len(non_null)
        # high cardinality or long average length → treat as free text
        avg_len = sum(len(v) for v in non_null) / len(non_null)
        if avg_len > 40 or unique_ratio > 0.8:
            return "text"
        return "categorical"
    return "mixed"


def _collect_field_values(docs: list[dict]) -> dict[str, list[Any]]:
    field_values: dict[str, list[Any]] = {}
    for doc in docs:
        for field, value in doc.items():
            if field.startswith("_"):
                continue
            field_values.setdefault(field, []).append(value)
    return field_values


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def get_schema(client: "redis.Redis") -> dict:
    """Return discovered entity types with per-field type annotations and
    foreign-key relationships inferred from ``*_id`` field naming."""
    entity_data = discover(client)
    known_prefixes = set(entity_data.keys())

    schema: dict[str, Any] = {"entity_types": {}, "relationships": []}

    for entity_type, docs in entity_data.items():
        field_values = _collect_field_values(docs)
        fields: dict[str, dict] = {}
        for field, values in field_values.items():
            ftype = _field_type(values)
            entry: dict[str, Any] = {"type": ftype, "nullable": any(v is None for v in values)}
            if ftype == "categorical":
                entry["unique_values"] = sorted(set(v for v in values if v is not None))
            elif ftype == "numeric":
                nums = [v for v in values if v is not None]
                entry["min"] = min(nums)
                entry["max"] = max(nums)
            if field.endswith("_id"):
                ref = field[:-3]
                if ref in known_prefixes:
                    entry["references"] = ref
            fields[field] = entry

        schema["entity_types"][entity_type] = {
            "count": len(docs),
            "fields": fields,
        }

    seen_rels: set[tuple] = set()
    for entity_type, info in schema["entity_types"].items():
        for field, finfo in info["fields"].items():
            if "references" in finfo:
                rel = (entity_type, finfo["references"])
                if rel not in seen_rels:
                    seen_rels.add(rel)
                    schema["relationships"].append({
                        "from_entity": entity_type,
                        "via_field": field,
                        "to_entity": finfo["references"],
                    })

    return schema


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def get_overview(client: "redis.Redis") -> dict:
    """High-level summary: entity counts + categorical distributions."""
    entity_data = discover(client)

    overview: dict[str, Any] = {
        "total_entities": sum(len(docs) for docs in entity_data.values()),
        "entity_counts": {et: len(docs) for et, docs in entity_data.items()},
        "distributions": {},
    }

    for entity_type, docs in entity_data.items():
        field_values = _collect_field_values(docs)
        dists: dict[str, dict] = {}
        for field, values in field_values.items():
            if _field_type(values) == "categorical":
                counts: dict[str, int] = {}
                for v in values:
                    if v is not None:
                        counts[str(v)] = counts.get(str(v), 0) + 1
                dists[field] = counts
        if dists:
            overview["distributions"][entity_type] = dists

    return overview


# ---------------------------------------------------------------------------
# Per-entity analytics
# ---------------------------------------------------------------------------


def get_entity_analytics(client: "redis.Redis") -> dict:
    """Per-entity, per-field statistics: distributions for categoricals,
    descriptive stats (min/max/mean/median/stdev) for numerics."""
    entity_data = discover(client)
    result: dict[str, Any] = {}

    for entity_type, docs in entity_data.items():
        field_values = _collect_field_values(docs)
        fields_out: dict[str, Any] = {}

        for field, values in field_values.items():
            ftype = _field_type(values)
            non_null = [v for v in values if v is not None]

            if ftype == "categorical":
                counts: dict[str, int] = {}
                for v in non_null:
                    counts[str(v)] = counts.get(str(v), 0) + 1
                fields_out[field] = {"type": "categorical", "distribution": counts, "null_count": len(values) - len(non_null)}

            elif ftype == "numeric":
                nums = [float(v) for v in non_null]
                entry: dict[str, Any] = {
                    "type": "numeric",
                    "count": len(nums),
                    "min": min(nums),
                    "max": max(nums),
                    "mean": round(sum(nums) / len(nums), 3),
                    "null_count": len(values) - len(non_null),
                }
                if len(nums) >= 2:
                    entry["median"] = statistics.median(nums)
                    entry["stdev"] = round(statistics.stdev(nums), 3)
                fields_out[field] = entry

        result[entity_type] = {
            "record_count": len(docs),
            "field_stats": fields_out,
        }

    return result


# ---------------------------------------------------------------------------
# All records for an entity type
# ---------------------------------------------------------------------------


def get_entity_records(client: "redis.Redis", entity_type: str) -> list[dict] | None:
    """All documents for the given entity type, sorted by their key."""
    all_keys = list(client.scan_iter(match=f"{entity_type}:*", count=1000))
    if not all_keys:
        return None  # None signals "entity type not found"
    pipe = client.pipeline()
    for k in sorted(all_keys):
        pipe.json().get(k)
    raw = pipe.execute()
    return [
        {**doc, "_key": k} if "_key" not in doc else doc
        for k, doc in zip(sorted(all_keys), raw)
        if doc is not None
    ]


# ---------------------------------------------------------------------------
# Single-record detail (enriched with related documents)
# ---------------------------------------------------------------------------


def get_record_detail(client: "redis.Redis", entity_type: str, record_id: str) -> dict | None:
    """Fetch one document and attach all documents that reference it,
    as well as documents it references — all derived from ``*_id`` fields."""
    key = f"{entity_type}:{record_id}"
    doc = client.json().get(key)
    if doc is None:
        return None

    known_prefixes = _discover_prefixes(client)

    # documents that THIS record points to (outgoing FKs)
    references: dict[str, Any] = {}
    for field, value in doc.items():
        if field.endswith("_id") and isinstance(value, str):
            ref_prefix = field[:-3]
            if ref_prefix in known_prefixes:
                ref_doc = client.json().get(f"{ref_prefix}:{value}")
                if ref_doc:
                    references[field] = ref_doc

    # documents that reference THIS record (incoming FKs)
    referenced_by: dict[str, list[dict]] = {}
    field_name = f"{entity_type}_id"
    for prefix in known_prefixes:
        if prefix == entity_type:
            continue
        candidates = list(client.scan_iter(match=f"{prefix}:*", count=1000))
        if not candidates:
            continue
        pipe = client.pipeline()
        for k in candidates:
            pipe.json().get(k)
        related_docs = [r for r in pipe.execute() if r is not None]
        matched = [
            d for d in related_docs
            if d.get(field_name) == record_id or d.get(f"{entity_type}_id") == record_id
        ]
        if matched:
            referenced_by[prefix] = matched

    return {
        **doc,
        "_key": key,
        "_references": references,
        "_referenced_by": referenced_by,
    }


# ---------------------------------------------------------------------------
# Relationship graph
# ---------------------------------------------------------------------------


def get_relationships_graph(client: "redis.Redis") -> dict:
    """Build a graph of nodes + edges by dynamically inferring ``*_id``
    foreign-key relationships across all discovered entity types."""
    entity_data = discover(client)
    known_prefixes = set(entity_data.keys())

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_edges: set[tuple] = set()

    for entity_type, docs in entity_data.items():
        for doc in docs:
            key = doc.get("_key", f"{entity_type}:{doc.get('id', '?')}")
            # pick a human-readable label
            label = next(
                (str(doc[f]) for f in _LABEL_CANDIDATES if f in doc and doc[f]),
                key,
            )
            node: dict[str, Any] = {
                "id": key,
                "label": label,
                "entity_type": entity_type,
            }
            # include all scalar fields as node metadata
            for field, value in doc.items():
                if not field.startswith("_") and isinstance(value, (str, int, float, bool)):
                    node[field] = value
            nodes.append(node)

            # emit edges for every *_id field that points to a known prefix
            for field, value in doc.items():
                if not field.endswith("_id") or not isinstance(value, str):
                    continue
                ref_prefix = field[:-3]
                if ref_prefix not in known_prefixes:
                    continue
                target_key = f"{ref_prefix}:{value}"
                edge_sig = (key, target_key, field)
                if edge_sig not in seen_edges:
                    seen_edges.add(edge_sig)
                    edges.append({
                        "source": key,
                        "target": target_key,
                        "relation": field,
                    })

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "entity_types": list(known_prefixes),
        "nodes": nodes,
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _discover_prefixes(client: "redis.Redis") -> set[str]:
    prefixes: set[str] = set()
    for key in client.scan_iter(match="*:*", count=2000):
        parts = key.split(":", 1)
        if len(parts) == 2 and not any(parts[0].startswith(ig) for ig in _IGNORED_PREFIXES):
            prefixes.add(parts[0])
    return prefixes
