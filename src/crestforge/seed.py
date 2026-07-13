"""Seed the CrestForge Industries predictive-maintenance dataset into Redis.

Entities (stored as RedisJSON docs):
    machine:{id}        shop-floor machines
    alert:{id}          active sensor alerts
    work_order:{id}     open / recent work orders
    fault_history:{id}  historical fault records
    technician:{id}     floor technicians
    part:{id}           spare-parts inventory

Also seeds 6 pre-built long-term memories so the demo starts in "shift 2" with
institutional fault knowledge already in place (requires AGENT_MEMORY_* vars).

Run:
    python -m src.crestforge.seed                # upsert — safe to rerun
    python -m src.crestforge.seed --flush        # FLUSHDB first (wipes Agent Memory too)
    python -m src.crestforge.seed --verify       # count + print samples, no writes
    python -m src.crestforge.seed --no-memory    # skip Agent Memory seeding
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from dotenv import load_dotenv

try:
    import redis
except ModuleNotFoundError:
    print("The 'redis' package isn't installed. Run:  uv add redis")
    raise SystemExit(1)

# ---------------------------------------------------------------------------
# Seed data — all values match docs/CRESTFORGE_USE_CASE.md
# ---------------------------------------------------------------------------

MACHINES = [
    {
        "id": "M104", "name": "Alpha Mill", "type": "cnc_mill",
        "location": "zone_a", "status": "fault",
        "vibration_level": 9.2, "temperature_c": 68.0, "runtime_hours": 512,
    },
    {
        "id": "M312", "name": "Delta Comp", "type": "compressor",
        "location": "zone_c", "status": "running",
        "vibration_level": 1.1, "temperature_c": 87.0, "runtime_hours": 330,
    },
    {
        "id": "M207", "name": "Beta Press", "type": "hydraulic_press",
        "location": "zone_b", "status": "maintenance",
        "vibration_level": 0.3, "temperature_c": 42.0, "runtime_hours": 891,
    },
    {
        "id": "M118", "name": "Gamma Belt", "type": "conveyor",
        "location": "zone_a", "status": "running",
        "vibration_level": 0.8, "temperature_c": 38.0, "runtime_hours": 487,
    },
    {
        "id": "M225", "name": "Epsilon Arm", "type": "robot_arm",
        "location": "zone_b", "status": "idle",
        "vibration_level": 0.0, "temperature_c": 29.0, "runtime_hours": 204,
    },
    {
        "id": "M401", "name": "Zeta Mill", "type": "cnc_mill",
        "location": "zone_d", "status": "running",
        "vibration_level": 2.1, "temperature_c": 55.0, "runtime_hours": 103,
    },
    {
        "id": "M309", "name": "Eta Press", "type": "hydraulic_press",
        "location": "zone_c", "status": "running",
        "vibration_level": 0.6, "temperature_c": 44.0, "runtime_hours": 67,
    },
    {
        "id": "M502", "name": "Theta Conv", "type": "conveyor",
        "location": "zone_d", "status": "idle",
        "vibration_level": 0.0, "temperature_c": 31.0, "runtime_hours": 12,
    },
]

ALERTS = [
    {
        "id": "A301", "machine_id": "M104", "type": "vibration",
        "severity": "critical", "status": "open",
        "triggered_value": 9.2, "threshold": 8.0,
    },
    {
        "id": "A308", "machine_id": "M312", "type": "temperature",
        "severity": "warning", "status": "open",
        "triggered_value": 87.0, "threshold": 85.0,
    },
    {
        "id": "A295", "machine_id": "M207", "type": "lubrication",
        "severity": "warning", "status": "resolved",
        "triggered_value": 0.4, "threshold": 0.8,
    },
]

WORK_ORDERS = [
    {
        "id": "WO1041", "machine_id": "M104", "technician_id": "T03",
        "type": "repair", "status": "scheduled", "priority": "urgent",
        "description": (
            "Critical vibration alert A301 — suspected front bearing failure. "
            "Inspect and replace SKF 6205 bearing."
        ),
    },
    {
        "id": "WO1042", "machine_id": "M207", "technician_id": "T07",
        "type": "lubrication", "status": "in_progress", "priority": "high",
        "description": (
            "Low hydraulic pressure resolved via alert A295. Lubrication service "
            "in progress by hydraulic specialist."
        ),
    },
    {
        "id": "WO1038", "machine_id": "M118", "technician_id": "T01",
        "type": "inspection", "status": "completed", "priority": "low",
        "description": (
            "Routine belt tension inspection — runtime approaching 500h threshold."
        ),
    },
]

FAULT_HISTORY = [
    {
        "id": "FH801", "machine_id": "M104",
        "fault_type": "High vibration 8.1 mm/s",
        "root_cause": "Front bearing wear",
        "resolution": "Bearing replacement (SKF 6205)",
        "downtime_hours": 2.1,
    },
    {
        "id": "FH802", "machine_id": "M104",
        "fault_type": "Spindle noise",
        "root_cause": "Loose collet — not bearing",
        "resolution": "Collet re-torque",
        "downtime_hours": 0.5,
    },
    {
        "id": "FH810", "machine_id": "M312",
        "fault_type": "Overtemperature 91°C",
        "root_cause": "Oil seal failure — not refrigerant",
        "resolution": "Seal replacement + oil flush",
        "downtime_hours": 4.0,
    },
    {
        "id": "FH795", "machine_id": "M207",
        "fault_type": "Low hydraulic pressure",
        "root_cause": "Pneumatic tech replaced wrong valve",
        "resolution": "Hydraulic specialist corrected — seal swap",
        "downtime_hours": 6.5,
    },
]

TECHNICIANS = [
    {
        "id": "T01", "name": "Marcus Webb", "specialty": "mechanical",
        "shift": "morning", "availability": "available",
        "certifications": "Millwright Level 3, Conveyor Systems",
    },
    {
        "id": "T03", "name": "Diana Cruz", "specialty": "mechanical",
        "shift": "morning", "availability": "available",
        "certifications": "CNC Machining, Bearing & Drive Systems",
    },
    {
        "id": "T07", "name": "Rajan Patel", "specialty": "hydraulic",
        "shift": "morning", "availability": "on_job",
        "certifications": "Hydraulic Systems Level 4, Fluid Power",
    },
    {
        "id": "T11", "name": "Sofia Lin", "specialty": "electrical",
        "shift": "afternoon", "availability": "off_shift",
        "certifications": "PLC Programming, Motor Controls",
    },
    {
        "id": "T14", "name": "Owen Brandt", "specialty": "pneumatic",
        "shift": "morning", "availability": "available",
        "certifications": "Pneumatic Systems, Valve Maintenance",
    },
]

PARTS = [
    {
        "id": "P201", "name": "SKF 6205 Bearing", "category": "bearing",
        "compatible_machine_type": "cnc_mill",
        "stock_level": 4, "reorder_point": 2, "lead_time_days": 3,
    },
    {
        "id": "P202", "name": "SKF 6305 Bearing", "category": "bearing",
        "compatible_machine_type": "cnc_mill",
        "stock_level": 1, "reorder_point": 2, "lead_time_days": 3,
    },
    {
        "id": "P310", "name": "Compressor Oil Seal", "category": "seal",
        "compatible_machine_type": "compressor",
        "stock_level": 2, "reorder_point": 1, "lead_time_days": 5,
    },
    {
        "id": "P411", "name": "Hydraulic Valve Seal", "category": "seal",
        "compatible_machine_type": "hydraulic_press",
        "stock_level": 3, "reorder_point": 2, "lead_time_days": 4,
    },
    {
        "id": "P508", "name": "Conveyor Drive Belt", "category": "belt",
        "compatible_machine_type": "conveyor",
        "stock_level": 2, "reorder_point": 1, "lead_time_days": 7,
    },
]

DATASET: dict[str, list[dict]] = {
    "machine": MACHINES,
    "alert": ALERTS,
    "work_order": WORK_ORDERS,
    "fault_history": FAULT_HISTORY,
    "technician": TECHNICIANS,
    "part": PARTS,
}

# ---------------------------------------------------------------------------
# Pre-built long-term memories — "shift 1" institutional knowledge
# ---------------------------------------------------------------------------

# owner_id used for all pre-seeded memories. Must match DEFAULT_OWNER_ID in
# cli.py so pre-seeded memories are found when the agent calls search_memory.
MEMORY_OWNER = "machine-floor"

LONG_TERM_MEMORIES = [
    {
        "id": "mem-M104-bearing",
        "owner_id": MEMORY_OWNER,
        "text": (
            "M104 Alpha Mill: when vibration exceeds 8 mm/s the root cause is "
            "almost always front bearing wear (FH801), NOT a spindle issue (FH802 "
            "was a collet and resolved in 30 min). Fix: SKF 6205 bearing replacement, "
            "~2h downtime. Diana Cruz (T03, mechanical) is the preferred technician."
        ),
    },
    {
        "id": "mem-M104-parts",
        "owner_id": MEMORY_OWNER,
        "text": (
            "M104 Alpha Mill bearing replacement requires SKF 6205 (P201). "
            "As of last check 4 units in stock — enough for immediate dispatch "
            "without waiting on a reorder."
        ),
    },
    {
        "id": "mem-M312-seal",
        "owner_id": MEMORY_OWNER,
        "text": (
            "M312 Delta Comp: rising temperature above 85°C is an oil seal failure "
            "signature (FH810), NOT low refrigerant — that was the wrong first guess "
            "last time and made things worse. Fix: compressor oil seal (P310) + oil "
            "flush, ~4h downtime. Always inspect the seal before touching refrigerant."
        ),
    },
    {
        "id": "mem-M207-hydraulic",
        "owner_id": MEMORY_OWNER,
        "text": (
            "M207 Beta Press: always assign a hydraulic specialist (Rajan Patel T07) "
            "for any pressure or valve fault. FH795 shows a pneumatic tech replaced "
            "the wrong valve — that turned a 2h job into a 6.5h incident."
        ),
    },
    {
        "id": "mem-M118-belt",
        "owner_id": MEMORY_OWNER,
        "text": (
            "M118 Gamma Belt: belt tension drifts after 500+ runtime hours. "
            "Schedule a pre-emptive tension check at 480h to avoid slippage. "
            "Conveyor Drive Belt P508 in stock (2 units)."
        ),
    },
    {
        "id": "mem-M225-calibration",
        "owner_id": MEMORY_OWNER,
        "text": (
            "M225 Epsilon Arm: loses positional accuracy after firmware updates. "
            "Always schedule a full recalibration immediately after any firmware patch — "
            "skipping it has caused repeated mis-picks on Zone B line."
        ),
    },
]


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------


def get_client() -> "redis.Redis":
    load_dotenv()
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        print("REDIS_URL is not set. Add your Redis Cloud connection string to .env")
        raise SystemExit(2)
    client = redis.from_url(url, decode_responses=True)
    client.ping()
    return client


def load(client: "redis.Redis", flush: bool) -> None:
    if flush:
        client.flushdb()
        print("FLUSHDB done.")
    total = 0
    for entity, rows in DATASET.items():
        for row in rows:
            client.json().set(f"{entity}:{row['id']}", "$", row)
            total += 1
        print(f"  loaded {len(rows):>3} {entity} keys")
    print(f"Loaded {total} JSON keys into Redis.")


def verify(client: "redis.Redis") -> None:
    print("\n=== verify ===")
    for entity in DATASET:
        keys = list(client.scan_iter(match=f"{entity}:*", count=1000))
        print(f"  {entity:<15} {len(keys):>3} keys")
    print("\nSample — machine:M104:")
    print(" ", client.json().get("machine:M104"))
    print("\nSample — alert:A301:")
    print(" ", client.json().get("alert:A301"))


# ---------------------------------------------------------------------------
# Agent Memory seeding (async)
# ---------------------------------------------------------------------------


async def seed_memories() -> None:
    load_dotenv()
    endpoint = os.getenv("AGENT_MEMORY_ENDPOINT", "").strip()
    store_id = os.getenv("AGENT_MEMORY_STORE_ID", "").strip()
    api_key = os.getenv("AGENT_MEMORY_KEY", "").strip()

    if not all([endpoint, store_id, api_key]):
        print("Agent Memory env vars not set — skipping memory seed.")
        print("  (set AGENT_MEMORY_ENDPOINT, AGENT_MEMORY_STORE_ID, AGENT_MEMORY_KEY)")
        return

    try:
        from redis_agent_memory import AgentMemory
    except ModuleNotFoundError:
        print("redis-agent-memory not installed — skipping memory seed. Run: uv sync")
        return

    client = AgentMemory(endpoint, store_id=store_id, api_key=api_key)

    # Fixed ids make reruns idempotent — the service deduplicates by id.
    ts = int(time.time() * 1000)
    memories = [
        {"id": f"{mem['id']}-{ts}-{i}", "owner_id": mem["owner_id"], "text": mem["text"]}
        for i, mem in enumerate(LONG_TERM_MEMORIES)
    ]

    await client.bulk_create_long_term_memories_async(memories=memories)
    print(f"Seeded {len(memories)} long-term memories (M104 ×2, M312, M207, M118, M225).")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    args = set(sys.argv[1:])
    client = get_client()

    if "--verify" in args:
        verify(client)
        return 0

    load(client, flush="--flush" in args)
    verify(client)

    if "--no-memory" not in args:
        asyncio.run(seed_memories())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
