"""Unit tests for agent/tools.py — mocked Redis, no live connection needed."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from agent.tools import attach_write_tools


class CapturingAgent:
    """Minimal stand-in for a Pydantic AI agent that records tools registered
    via ``tool_plain`` so tests can invoke them directly by name."""

    def __init__(self) -> None:
        self._tools: dict = {}

    def tool_plain(self, fn):
        """Record and return ``fn`` so it can be awaited by tests as a tool."""
        self._tools[fn.__name__] = fn
        return fn


async def _async_keys(*keys: str):
    """Yield keys one at a time, mimicking ``redis.scan_iter`` async iteration."""
    for k in keys:
        yield k


@pytest.fixture
def mock_redis():
    """Build a MagicMock Redis client with an async ``json()`` command group
    and a ``scan_iter`` returning an empty async iterator."""
    client = MagicMock()
    json_cmd = AsyncMock()
    client.json.return_value = json_cmd
    client.scan_iter = lambda pattern: _async_keys()
    return client


@pytest.fixture
def tools(mock_redis):
    """Attach the write tools to a :class:`CapturingAgent` and return the
    ``(tool_functions, redis_client, json_cmd)`` tuple used by tests."""
    agent = CapturingAgent()
    attach_write_tools(agent, mock_redis)
    json_cmd = mock_redis.json()
    return agent._tools, mock_redis, json_cmd


# --- update_work_order_status ---

async def test_update_wo_status_success(tools):
    """Updating a known work order reflects both prior and new status."""
    fns, _, json_cmd = tools
    json_cmd.get.return_value = {"status": "scheduled"}
    result = await fns["update_work_order_status"]("WO1001", "in_progress")
    assert "scheduled" in result and "in_progress" in result

async def test_update_wo_status_invalid(tools):
    """An unrecognized status value is rejected with an invalid message."""
    fns, _, _ = tools
    result = await fns["update_work_order_status"]("WO1001", "broken")
    assert "Invalid status" in result

async def test_update_wo_status_not_found(tools):
    """Updating a missing work order reports it as not found."""
    fns, _, json_cmd = tools
    json_cmd.get.return_value = None
    result = await fns["update_work_order_status"]("WO9999", "in_progress")
    assert "not found" in result


# --- assign_technician ---

async def test_assign_technician_success(tools):
    """Assigning a known technician to a known work order names both in the result."""
    fns, _, json_cmd = tools
    json_cmd.get.side_effect = [{"technician_id": "T00"}, {"name": "Alice"}]
    result = await fns["assign_technician"]("WO1001", "T01")
    assert "T00" in result and "T01" in result and "Alice" in result

async def test_assign_technician_wo_not_found(tools):
    """Assigning to a missing work order reports it as not found."""
    fns, _, json_cmd = tools
    json_cmd.get.return_value = None
    result = await fns["assign_technician"]("WO9999", "T01")
    assert "not found" in result

async def test_assign_technician_tech_not_found(tools):
    """Assigning an unknown technician reports the technician as not found."""
    fns, _, json_cmd = tools
    json_cmd.get.side_effect = [{"technician_id": None}, None]
    result = await fns["assign_technician"]("WO1001", "T99")
    assert "not found" in result


# --- create_work_order ---

async def test_create_work_order_success(tools):
    """Creating a work order assigns the next sequential work-order id."""
    fns, mock_redis, json_cmd = tools
    json_cmd.get.return_value = {"name": "Lathe"}
    mock_redis.scan_iter = lambda pattern: _async_keys("work_order:WO1001", "work_order:WO1042")
    result = await fns["create_work_order"]("M104", "repair", "high", "Fix belt")
    assert "WO1043" in result

async def test_create_work_order_invalid_type(tools):
    """An invalid work-order type is rejected with an invalid message."""
    fns, _, _ = tools
    result = await fns["create_work_order"]("M104", "deep_clean", "low", "desc")
    assert "Invalid type" in result

async def test_create_work_order_machine_not_found(tools):
    """Creating a work order for an unknown machine reports not found."""
    fns, _, json_cmd = tools
    json_cmd.get.return_value = None
    result = await fns["create_work_order"]("M999", "repair", "low", "desc")
    assert "not found" in result


# --- flag_machine_status ---

async def test_flag_machine_status_success(tools):
    """Flagging a known machine reports its previous and new status."""
    fns, _, json_cmd = tools
    json_cmd.get.return_value = {"status": "running", "name": "Lathe"}
    result = await fns["flag_machine_status"]("M104", "fault")
    assert "running" in result and "fault" in result

async def test_flag_machine_status_invalid(tools):
    """An invalid machine status value is rejected with an invalid message."""
    fns, _, _ = tools
    result = await fns["flag_machine_status"]("M104", "broken")
    assert "Invalid status" in result

async def test_flag_machine_status_not_found(tools):
    """Flagging an unknown machine reports it as not found."""
    fns, _, json_cmd = tools
    json_cmd.get.return_value = None
    result = await fns["flag_machine_status"]("M999", "idle")
    assert "not found" in result
