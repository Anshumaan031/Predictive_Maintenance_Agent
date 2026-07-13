"""Provision Context Retriever for CrestForge Industries + mint an agent key.

Uses CTX_ADMIN_KEY to create (or update) a context surface named
"CrestForge Industries" with 6 entities and the correct field index types,
waits for the ~35 MCP tools to generate, then mints a scoped agent key.
The agent key is written to _agentkey.tmp (git-ignored).

Run from the repo dir:
    uv run python configure_crestforge.py --probe   # list existing surfaces only
    uv run python configure_crestforge.py           # create/update + mint agent key
"""
from __future__ import annotations

import asyncio
import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv

from context_surfaces import ContextSurfacesClient
from context_surfaces.context_model import ContextField, ContextModel, export_data_model
from context_surfaces.models import (
    CreateAgentKeyRequest,
    CreateContextSurfaceRequest,
    DataSourceConnectionConfig,
    DataSourceRequest,
    UpdateContextSurfaceRequest,
)

SURFACE_NAME = "CrestForge Industries"
KEY_OUT = os.path.join(os.path.dirname(__file__), "_agentkey.tmp")


# ---------------------------------------------------------------------------
# Entity models — field index type controls the tool that gets generated:
#   TAG     → filter_<entity>_by_<field>        (exact match)
#   TEXT    → search_<entity>_by_text           (full-text)
#   NUMERIC → find_<entity>_by_<field>_range    (range query)
#   key     → get_<entity>_by_id
# ---------------------------------------------------------------------------

class Machine(ContextModel):
    """A CNC mill, press, conveyor, compressor, or robot arm on the shop floor."""
    __redis_key_template__ = "machine:{id}"
    id: str               = ContextField(description="Machine id (e.g. M104)", is_key_component=True)
    name: str             = ContextField(description="Human-readable machine name", index="text")
    type: str             = ContextField(description="cnc_mill / hydraulic_press / conveyor / compressor / robot_arm", index="tag")
    location: str         = ContextField(description="Zone: zone_a / zone_b / zone_c / zone_d", index="tag")
    status: str           = ContextField(description="running / idle / fault / maintenance", index="tag")
    vibration_level: float = ContextField(description="Vibration in mm/s", index="numeric")
    temperature_c: float  = ContextField(description="Temperature in Celsius", index="numeric")
    runtime_hours: float  = ContextField(description="Hours since last major service", index="numeric")


class Alert(ContextModel):
    """A sensor alert triggered when a machine crosses a monitoring threshold."""
    __redis_key_template__ = "alert:{id}"
    id: str              = ContextField(description="Alert id (e.g. A301)", is_key_component=True)
    machine_id: str      = ContextField(description="Machine that triggered the alert", index="tag")
    type: str            = ContextField(description="vibration / temperature / pressure / lubrication / current_draw", index="tag")
    severity: str        = ContextField(description="info / warning / critical", index="tag")
    status: str          = ContextField(description="open / acknowledged / resolved", index="tag")
    triggered_value: float = ContextField(description="Sensor reading that triggered the alert", index="numeric")
    threshold: float     = ContextField(description="Threshold value that was crossed", index="numeric")


class WorkOrder(ContextModel):
    """A maintenance or repair task assigned to a technician."""
    __redis_key_template__ = "work_order:{id}"
    id: str            = ContextField(description="Work order id (e.g. WO1041)", is_key_component=True)
    machine_id: str    = ContextField(description="Machine the work order is for", index="tag")
    technician_id: str = ContextField(description="Assigned technician id", index="tag")
    type: str          = ContextField(description="inspection / repair / replacement / lubrication", index="tag")
    status: str        = ContextField(description="scheduled / in_progress / completed / cancelled", index="tag")
    priority: str      = ContextField(description="low / medium / high / urgent", index="tag")
    description: str   = ContextField(description="Work order description and notes", index="text")


class FaultHistory(ContextModel):
    """A historical fault record — root cause and resolution for a past incident."""
    __redis_key_template__ = "fault_history:{id}"
    id: str             = ContextField(description="Fault history id (e.g. FH801)", is_key_component=True)
    machine_id: str     = ContextField(description="Machine the fault occurred on", index="tag")
    fault_type: str     = ContextField(description="Description of the fault symptom", index="text")
    root_cause: str     = ContextField(description="Confirmed root cause of the fault", index="text")
    resolution: str     = ContextField(description="How the fault was resolved", index="text")
    downtime_hours: float = ContextField(description="Total downtime in hours", index="numeric")


class Technician(ContextModel):
    """A floor technician with a specialty, shift, and current availability."""
    __redis_key_template__ = "technician:{id}"
    id: str            = ContextField(description="Technician id (e.g. T03)", is_key_component=True)
    name: str          = ContextField(description="Technician full name", index="text")
    specialty: str     = ContextField(description="mechanical / electrical / hydraulic / pneumatic", index="tag")
    shift: str         = ContextField(description="morning / afternoon / night", index="tag")
    availability: str  = ContextField(description="available / on_job / off_shift", index="tag")
    certifications: str = ContextField(description="Certifications and qualified systems", index="text")


class Part(ContextModel):
    """A spare part in the warehouse inventory."""
    __redis_key_template__ = "part:{id}"
    id: str                     = ContextField(description="Part id (e.g. P201)", is_key_component=True)
    name: str                   = ContextField(description="Part name", index="text")
    category: str               = ContextField(description="bearing / belt / seal / sensor / motor / filter", index="tag")
    compatible_machine_type: str = ContextField(description="Machine type this part fits", index="tag")
    stock_level: int            = ContextField(description="Units currently in stock", index="numeric")
    reorder_point: int          = ContextField(description="Stock level that triggers a reorder", index="numeric")
    lead_time_days: int         = ContextField(description="Supplier lead time in days", index="numeric")


ENTITIES = [Machine, Alert, WorkOrder, FaultHistory, Technician, Part]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _surfaces_of(resp: object) -> list:
    for attr in ("context_surfaces", "surfaces", "items", "data", "results"):
        v = getattr(resp, attr, None)
        if isinstance(v, list):
            return v
    return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> int:
    load_dotenv()
    admin_key = os.getenv("CTX_ADMIN_KEY", "").strip()
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not admin_key or not redis_url:
        print("Need CTX_ADMIN_KEY and REDIS_URL in the environment.")
        return 2

    probe = "--probe" in sys.argv

    async with ContextSurfacesClient() as client:
        existing = await client.list_context_surfaces(admin_key=admin_key)
        surfaces = _surfaces_of(existing)
        print(f"existing surfaces ({len(surfaces)}):")
        for s in surfaces:
            print(f"  - {getattr(s, 'name', '?')}  id={getattr(s, 'id', '?')}  "
                  f"status={getattr(s, 'status', '?')}  tools={len(getattr(s, 'tools', []) or [])}")
        if probe:
            return 0

        u = urlparse(redis_url)
        conn = DataSourceConnectionConfig(
            addr=f"{u.hostname}:{u.port}",
            username=u.username or "default",
            password=u.password or "",
            tls_enabled=(u.scheme == "rediss"),
        )
        data_model = export_data_model(
            "CrestForge Industries",
            "Predictive-maintenance data for the CrestForge Industries factory floor.",
            entities=ENTITIES,
        )
        print("entities:", [e["name"] for e in data_model["entities"]],
              "| entity_count:", data_model["entity_count"])
        data_source = DataSourceRequest(type="redis", connection_config=conn)

        match = next((s for s in surfaces if getattr(s, "name", None) == SURFACE_NAME), None)
        if match:
            surface = await client.update_context_surface(
                match.id,
                UpdateContextSurfaceRequest(data_model=data_model, data_source=data_source),
                admin_key=admin_key,
            )
            print(f"updated surface id={surface.id}")
        else:
            surface = await client.create_context_surface(
                CreateContextSurfaceRequest(
                    name=SURFACE_NAME,
                    description="CrestForge Industries predictive-maintenance surface.",
                    data_model=data_model,
                    data_source=data_source,
                ),
                admin_key=admin_key,
            )
            print(f"created surface id={surface.id}")

        # Poll until tool generation completes (async on the server side).
        for _ in range(40):
            st = getattr(surface, "status", None)
            n_tools = len(getattr(surface, "tools", []) or [])
            print(f"  status={st}  tools={n_tools}")
            if st == "active":
                break
            await asyncio.sleep(2)
            surface = await client.get_context_surface(surface.id, admin_key=admin_key)

        print("final status:", getattr(surface, "status", "?"),
              "| tools:", len(getattr(surface, "tools", []) or []))

        agent_key = await client.create_agent_key(
            surface.id, CreateAgentKeyRequest(name="crestforge-agent"), admin_key=admin_key,
        )
        key_val = agent_key.key or ""
        with open(KEY_OUT, "w", encoding="ascii") as f:
            f.write(key_val)
        print(f"agent key minted: {key_val[:6]}...(len {len(key_val)}) -> wrote {os.path.basename(KEY_OUT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
