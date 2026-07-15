"""Builds the Pydantic AI agent wired to the Redis Iris Context Retriever.

The Context Retriever exposes a standard streamable-HTTP MCP server at ``/mcp``,
authenticated with an ``X-API-Key`` header. Pydantic AI's native MCP client
points an ``MCPToolset`` straight at that endpoint — the model then discovers
and calls the auto-generated tools with no per-query code on our side.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

from .config import Settings
from .model_provider import build_model
from .prompts import MEMORY_PROMPT, SYSTEM_PROMPT, WRITE_TOOLS_PROMPT
from .tools import attach_write_tools

if TYPE_CHECKING:
    import redis.asyncio as aioredis

    from .memory import MemoryService


def build_toolset(settings: Settings) -> MCPToolset:
    """Create the Context Retriever MCP toolset."""
    return MCPToolset(
        settings.mcp_url,
        headers={"X-API-Key": settings.agent_key},
    )


def build_agent(
    settings: Settings,
    toolset: MCPToolset,
    memory: "MemoryService | None" = None,
    redis_client: "aioredis.Redis | None" = None,
) -> Agent:
    """Create the Pydantic AI agent backed by the Context Retriever tools.

    When ``memory`` is provided the agent also gets ``search_memory`` /
    ``store_memory`` tools over the user's Agent Memory, plus guidance on when
    to use them.
    """
    instructions = (
        SYSTEM_PROMPT
        + (WRITE_TOOLS_PROMPT if redis_client is not None else "")
        + (MEMORY_PROMPT if memory else "")
    )
    agent = Agent(
        build_model(),
        toolsets=[toolset],
        instructions=instructions,
    )
    if memory is not None:
        _attach_memory_tools(agent, memory)
    if redis_client is not None:
        attach_write_tools(agent, redis_client)
    return agent


def _attach_memory_tools(agent: Agent, memory: "MemoryService") -> None:
    """Register long-term memory as two plain tools bound to the current user.

    Identity (owner/session) lives on ``memory.identity`` — the model never
    passes it, so it cannot read or write another user's memory.
    """

    @agent.tool_plain
    async def search_memory(query: str) -> str:
        """Recall durable facts about the current user from long-term memory
        (their preferences, past decisions, prior context). Use before answering
        anything that depends on who the user is or what they told you before."""
        return await memory.search(query)

    @agent.tool_plain
    async def store_memory(fact: str) -> str:
        """Persist a durable fact about the current user (a stated preference,
        decision, or detail worth remembering next time). One concise line."""
        return await memory.store(fact)
