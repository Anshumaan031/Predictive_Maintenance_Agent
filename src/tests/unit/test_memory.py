"""Unit tests for agent/memory.py — mocked AgentMemory client."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.memory import MemoryService, Identity, _to_text


@pytest.fixture(autouse=True)
def patch_memory_models():
    """Replace the redis_agent_memory models with a mock so tests run
    regardless of whether the optional package is installed."""
    models = MagicMock()
    models.MessageRole.USER = "USER"
    models.MessageRole.ASSISTANT = "ASSISTANT"
    with patch("agent.memory._memory_models", models):
        yield


@pytest.fixture
def identity():
    return Identity(owner_id="user-1", session_id="session-abc")


@pytest.fixture
def service(identity):
    client = AsyncMock()
    return MemoryService(client, identity), client


# --- health ---

async def test_health_true_when_reachable(service):
    svc, client = service
    assert await svc.health() is True

async def test_health_false_on_exception(service):
    svc, client = service
    client.health_async.side_effect = ConnectionError("down")
    assert await svc.health() is False


# --- log_turn ---

async def test_log_turn_calls_add_session_event(service, identity):
    svc, client = service
    await svc.log_turn("user", "hello")
    client.add_session_event_async.assert_awaited_once()
    kwargs = client.add_session_event_async.call_args.kwargs
    assert kwargs["session_id"] == identity.session_id
    assert kwargs["actor_id"] == identity.owner_id

async def test_log_turn_empty_text_skips_api(service):
    svc, client = service
    await svc.log_turn("user", "")
    client.add_session_event_async.assert_not_awaited()

async def test_log_turn_swallows_exceptions(service):
    svc, client = service
    client.add_session_event_async.side_effect = RuntimeError("boom")
    await svc.log_turn("user", "text")  # must not raise


# --- search ---

async def test_search_passes_owner_filter(service, identity):
    svc, client = service
    client.search_long_term_memory_async.return_value = MagicMock(
        model_dump_json=lambda: '{"results": []}'
    )
    result = await svc.search("machine faults")
    request = client.search_long_term_memory_async.call_args.kwargs["request"]
    assert request["filter"]["owner_id"]["eq"] == identity.owner_id
    assert result == '{"results": []}'


# --- store ---

async def test_store_persists_fact_for_owner(service, identity):
    svc, client = service
    client.bulk_create_long_term_memories_async.return_value = MagicMock(
        model_dump_json=lambda: '{"created": 1}'
    )
    result = await svc.store("user prefers metric units")
    memories = client.bulk_create_long_term_memories_async.call_args.kwargs["memories"]
    assert memories[0]["owner_id"] == identity.owner_id
    assert memories[0]["text"] == "user prefers metric units"
    assert result == '{"created": 1}'


# --- _to_text ---

def test_to_text_uses_model_dump_json():
    obj = MagicMock(spec=["model_dump_json"])
    obj.model_dump_json.return_value = '{"key": "val"}'
    assert _to_text(obj) == '{"key": "val"}'

def test_to_text_falls_back_to_str():
    class Plain:
        def __str__(self): return "plain"
    assert _to_text(Plain()) == "plain"
