"""Redis write-back tools for the Iris agent.

Each tool is registered as an @agent.tool_plain closure so the model never
receives the Redis client directly — it just calls the function by name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from pydantic_ai import Agent


_VALID_WO_STATUSES = frozenset({"scheduled", "in_progress", "completed", "cancelled"})
_VALID_MACHINE_STATUSES = frozenset({"running", "fault", "maintenance", "idle"})
_VALID_WO_TYPES = frozenset({"repair", "inspection", "lubrication", "maintenance"})
_VALID_PRIORITIES = frozenset({"low", "normal", "high", "urgent"})


def attach_write_tools(agent: "Agent", redis_client: "aioredis.Redis") -> None:
    """Register the four Redis write-back tools on *agent*."""

    @agent.tool_plain
    async def update_work_order_status(work_order_id: str, new_status: str) -> str:
        """Advance a work order through its lifecycle.

        Args:
            work_order_id: The work order to update (e.g. WO1041).
            new_status: Target status — one of: scheduled, in_progress,
                completed, cancelled.

        Returns:
            Confirmation string showing the old → new transition, or an
            error message if the work order does not exist or the status
            value is invalid.
        """
        new_status = new_status.lower()
        if new_status not in _VALID_WO_STATUSES:
            return f"Invalid status '{new_status}'. Choose from: {sorted(_VALID_WO_STATUSES)}."

        work_order_key = f"work_order:{work_order_id.upper()}"
        work_order = await redis_client.json().get(work_order_key)
        if work_order is None:
            return f"Work order {work_order_id} not found."

        previous_status = work_order.get("status", "unknown")
        await redis_client.json().set(work_order_key, "$.status", new_status)
        return f"WO {work_order_id.upper()}: status updated {previous_status} → {new_status}."


    @agent.tool_plain
    async def assign_technician(work_order_id: str, technician_id: str) -> str:
        """Assign or reassign a technician to a work order.

        Args:
            work_order_id: The work order to update (e.g. WO1041).
            technician_id: The technician to assign (e.g. T03).

        Returns:
            Confirmation string showing the previous and new assignee, or
            an error message if either the work order or technician is not
            found in Redis.
        """
        work_order_key = f"work_order:{work_order_id.upper()}"
        technician_key = f"technician:{technician_id.upper()}"

        work_order = await redis_client.json().get(work_order_key)
        if work_order is None:
            return f"Work order {work_order_id} not found."

        technician = await redis_client.json().get(technician_key)
        if technician is None:
            return f"Technician {technician_id} not found."

        previous_technician = work_order.get("technician_id") or "unassigned"
        await redis_client.json().set(work_order_key, "$.technician_id", technician_id.upper())
        return (
            f"WO {work_order_id.upper()}: technician changed {previous_technician} → "
            f"{technician_id.upper()} ({technician.get('name', technician_id)})."
        )


    @agent.tool_plain
    async def create_work_order(
        machine_id: str,
        order_type: str,
        priority: str,
        description: str,
    ) -> str:
        """Open a new work order for a machine.

        Args:
            machine_id: The machine this order covers (e.g. M104).
            order_type: Kind of work — one of: repair, inspection,
                lubrication, maintenance.
            priority: Urgency level — one of: low, normal, high, urgent.
            description: Free-text description of the work to be done.

        Returns:
            The newly created work order ID (e.g. "Created WO1044 …"),
            or an error message if the machine is not found or any
            argument value is invalid.
        """
        order_type = order_type.lower()
        priority = priority.lower()

        if order_type not in _VALID_WO_TYPES:
            return f"Invalid type '{order_type}'. Choose from: {sorted(_VALID_WO_TYPES)}."
        if priority not in _VALID_PRIORITIES:
            return f"Invalid priority '{priority}'. Choose from: {sorted(_VALID_PRIORITIES)}."

        machine = await redis_client.json().get(f"machine:{machine_id.upper()}")
        if machine is None:
            return f"Machine {machine_id} not found."

        existing_wo_numbers = []
        async for existing_key in redis_client.scan_iter("work_order:WO*"):
            try:
                existing_wo_numbers.append(int(existing_key.split("WO")[-1]))
            except ValueError:
                pass

        new_work_order_id = f"WO{max(existing_wo_numbers, default=1000) + 1}"
        new_work_order = {
            "id": new_work_order_id,
            "machine_id": machine_id.upper(),
            "technician_id": None,
            "type": order_type,
            "status": "scheduled",
            "priority": priority,
            "description": description,
        }
        await redis_client.json().set(f"work_order:{new_work_order_id}", "$", new_work_order)
        return (
            f"Created {new_work_order_id} (type={order_type}, priority={priority}) "
            f"for machine {machine_id.upper()}."
        )


    @agent.tool_plain
    async def flag_machine_status(machine_id: str, new_status: str) -> str:
        """Update a machine's operational status.

        Args:
            machine_id: The machine to update (e.g. M104).
            new_status: Target status — one of: running, fault,
                maintenance, idle.

        Returns:
            Confirmation string showing the old → new transition, or an
            error message if the machine does not exist or the status
            value is invalid.
        """
        new_status = new_status.lower()
        if new_status not in _VALID_MACHINE_STATUSES:
            return f"Invalid status '{new_status}'. Choose from: {sorted(_VALID_MACHINE_STATUSES)}."

        machine_key = f"machine:{machine_id.upper()}"
        machine = await redis_client.json().get(machine_key)
        if machine is None:
            return f"Machine {machine_id} not found."

        previous_status = machine.get("status", "unknown")
        await redis_client.json().set(machine_key, "$.status", new_status)
        return (
            f"Machine {machine_id.upper()} ({machine.get('name', '')}): "
            f"status updated {previous_status} → {new_status}."
        )
