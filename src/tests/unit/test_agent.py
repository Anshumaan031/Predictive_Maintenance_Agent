"""Unit tests for agent/agent.py — verifies prompt assembly and tool wiring."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from agent.agent import build_agent, build_toolset
from agent.config import Settings
from agent.prompts import SYSTEM_PROMPT, WRITE_TOOLS_PROMPT, MEMORY_PROMPT


@pytest.fixture
def settings():
    return Settings(agent_key="test-key", mcp_url="https://example.com/mcp")


@pytest.fixture
def mock_toolset():
    return MagicMock()


# --- instruction assembly ---

@patch("agent.agent.Agent")
@patch("agent.agent.build_model")
def test_instructions_minimal(mock_bm, mock_agent_cls, settings, mock_toolset):
    mock_agent_cls.return_value = MagicMock()
    build_agent(settings, mock_toolset)
    instructions = mock_agent_cls.call_args.kwargs["instructions"]
    assert instructions == SYSTEM_PROMPT


@patch("agent.agent.Agent")
@patch("agent.agent.build_model")
def test_instructions_with_redis_adds_write_tools_prompt(mock_bm, mock_agent_cls, settings, mock_toolset):
    mock_agent_cls.return_value = MagicMock()
    build_agent(settings, mock_toolset, redis_client=MagicMock())
    instructions = mock_agent_cls.call_args.kwargs["instructions"]
    assert WRITE_TOOLS_PROMPT in instructions
    assert MEMORY_PROMPT not in instructions


@patch("agent.agent.Agent")
@patch("agent.agent.build_model")
def test_instructions_with_memory_adds_memory_prompt(mock_bm, mock_agent_cls, settings, mock_toolset):
    mock_agent_cls.return_value = MagicMock()
    build_agent(settings, mock_toolset, memory=MagicMock())
    instructions = mock_agent_cls.call_args.kwargs["instructions"]
    assert MEMORY_PROMPT in instructions
    assert WRITE_TOOLS_PROMPT not in instructions


@patch("agent.agent.Agent")
@patch("agent.agent.build_model")
def test_instructions_full_includes_all_prompts(mock_bm, mock_agent_cls, settings, mock_toolset):
    mock_agent_cls.return_value = MagicMock()
    build_agent(settings, mock_toolset, memory=MagicMock(), redis_client=MagicMock())
    instructions = mock_agent_cls.call_args.kwargs["instructions"]
    assert SYSTEM_PROMPT in instructions
    assert WRITE_TOOLS_PROMPT in instructions
    assert MEMORY_PROMPT in instructions


# --- tool registration ---

@patch("agent.agent.attach_write_tools")
@patch("agent.agent.Agent")
@patch("agent.agent.build_model")
def test_attach_write_tools_called_with_redis(mock_bm, mock_agent_cls, mock_attach, settings, mock_toolset):
    redis = MagicMock()
    mock_agent_instance = MagicMock()
    mock_agent_cls.return_value = mock_agent_instance
    build_agent(settings, mock_toolset, redis_client=redis)
    mock_attach.assert_called_once_with(mock_agent_instance, redis)


@patch("agent.agent.attach_write_tools")
@patch("agent.agent.Agent")
@patch("agent.agent.build_model")
def test_attach_write_tools_not_called_without_redis(mock_bm, mock_agent_cls, mock_attach, settings, mock_toolset):
    mock_agent_cls.return_value = MagicMock()
    build_agent(settings, mock_toolset)
    mock_attach.assert_not_called()


# --- build_toolset ---

@patch("agent.agent.MCPToolset")
def test_build_toolset_uses_correct_url_and_key(mock_mcp_cls, settings):
    build_toolset(settings)
    mock_mcp_cls.assert_called_once_with(
        settings.mcp_url,
        headers={"X-API-Key": settings.agent_key},
    )
