"""Singleton session state for the Redis Iris Agent API.

One global AppState is created at startup and shared across all requests.
This is intentional for a single-user demo: history, active machine, and
identity all live here and mutate in place as the conversation progresses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelMessage

from agent.agent import build_agent, build_toolset
from agent.config import Settings, load_settings
from agent.memory import Identity, MemoryService
from utils.tool_names import safe_name_map

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    settings: Settings
    toolset: MCPToolset
    agent: Agent
    memory: MemoryService | None
    identity: Identity
    name_map: dict[str, str]
    tool_names: list[str]
    redis_client: "redis.Redis | None"
    active_machine: str | None = None
    history: list[ModelMessage] = field(default_factory=list)


def _connect_redis(url: str) -> "redis.Redis":
    import redis as redis_lib
    client = redis_lib.from_url(url, decode_responses=True)
    client.ping()
    return client


async def create_state() -> tuple[AppState, list[str]]:
    """Build settings, toolset, agent, and memory. Returns ``(state, warnings)``."""
    warnings: list[str] = []
    settings = load_settings()

    toolset = build_toolset(settings)
    tool_names: list[str] = []
    try:
        tool_names = [t.name for t in await toolset.list_tools()]
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Could not connect to Context Retriever: {exc}")
        logger.warning("Could not list tools: %s", exc)

    name_map = safe_name_map(tool_names) if tool_names else {}
    agent_toolset = toolset.renamed(name_map) if name_map else toolset

    identity = Identity(owner_id=settings.owner_id, session_id=settings.session_id)
    memory: MemoryService | None = None
    if settings.memory_enabled:
        try:
            memory = MemoryService.from_settings(settings, identity)
            if not await memory.health():
                warnings.append("Agent Memory endpoint not reachable — memory disabled.")
                memory = None
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Memory disabled: {exc}")
            logger.warning("Memory init failed: %s", exc)

    agent = build_agent(settings, agent_toolset, memory=memory)

    redis_client = None
    if settings.redis_url:
        try:
            redis_client = _connect_redis(settings.redis_url)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Redis direct connection failed — /data endpoints unavailable: {exc}")
            logger.warning("Redis connection failed: %s", exc)

    return (
        AppState(
            settings=settings,
            toolset=toolset,
            agent=agent,
            memory=memory,
            identity=identity,
            name_map=name_map,
            tool_names=tool_names,
            redis_client=redis_client,
        ),
        warnings,
    )
