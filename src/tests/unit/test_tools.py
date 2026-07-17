"""Unit tests for agent/tools.py — mocked Redis, no live connection needed."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from agent.tools import attach_write_tools


class CapturingAgent:
    def __init__(self) -> None:
        self._tools: dict = {}

    def tool_plain(self, fn):
        self._tools[fn.__name__] = fn
        return fn


async def _async_keys(*keys: str):
    for k in keys:
        yield k


@pytest.fixture
def mock_redis():
    client = MagicMock()
    json_cmd = AsyncMock()
    client.json.return_value = json_cmd
    client.scan_iter = lambda pattern: _async_keys()
    return client


@pytest.fixture
def tools(mock_redis):
    agent = CapturingAgent()
    attach_write_tools(agent, mock_redis)
    json_cmd = mock_redis.json()
    return agent._tools, mock_redis, json_cmd


# --- update_work_order_status ---

async def test_update_wo_status_success(tools):
    fns, _, json_cmd = tools
    json_cmd.get.return_value = {"status": "scheduled"}
    result = await fns["update_work_order_status"]("WO1001", "in_progress")
    assert "scheduled" in result and "in_progress" in result

async def test_update_wo_status_invalid(tools):
    fns, _, _ = tools
    result = await fns["update_work_order_status"]("WO1001", "broken")
    assert "Invalid status" in result

async def test_update_wo_status_not_found(tools):
    fns, _, json_cmd = tools
    json_cmd.get.return_value = None
    result = await fns["update_work_order_status"]("WO9999", "in_progress")
    assert "not found" in result


# --- assign_technician ---

async def test_assign_technician_success(tools):
    fns, _, json_cmd = tools
    json_cmd.get.side_effect = [{"technician_id": "T00"}, {"name": "Alice"}]
    result = await fns["assign_technician"]("WO1001", "T01")
    assert "T00" in result and "T01" in result and "Alice" in result

async def test_assign_technician_wo_not_found(tools):
    fns, _, json_cmd = tools
    json_cmd.get.return_value = None
    result = await fns["assign_technician"]("WO9999", "T01")
    assert "not found" in result

async def test_assign_technician_tech_not_found(tools):
    fns, _, json_cmd = tools
    json_cmd.get.side_effect = [{"technician_id": None}, None]
    result = await fns["assign_technician"]("WO1001", "T99")
    assert "not found" in result


# --- create_work_order ---

async def test_create_work_order_success(tools):
    fns, mock_redis, json_cmd = tools
    json_cmd.get.return_value = {"name": "Lathe"}
    mock_redis.scan_iter = lambda pattern: _async_keys("work_order:WO1001", "work_order:WO1042")
    result = await fns["create_work_order"]("M104", "repair", "high", "Fix belt")
    assert "WO1043" in result

async def test_create_work_order_invalid_type(tools):
    fns, _, _ = tools
    result = await fns["create_work_order"]("M104", "deep_clean", "low", "desc")
    assert "Invalid type" in result

async def test_create_work_order_machine_not_found(tools):
    fns, _, json_cmd = tools
    json_cmd.get.return_value = None
    result = await fns["create_work_order"]("M999", "repair", "low", "desc")
    assert "not found" in result


# --- flag_machine_status ---

async def test_flag_machine_status_success(tools):
    fns, _, json_cmd = tools
    json_cmd.get.return_value = {"status": "running", "name": "Lathe"}
    result = await fns["flag_machine_status"]("M104", "fault")
    assert "running" in result and "fault" in result

async def test_flag_machine_status_invalid(tools):
    fns, _, _ = tools
    result = await fns["flag_machine_status"]("M104", "broken")
    assert "Invalid status" in result

async def test_flag_machine_status_not_found(tools):
    fns, _, json_cmd = tools
    json_cmd.get.return_value = None
    result = await fns["flag_machine_status"]("M999", "idle")
    assert "not found" in result
