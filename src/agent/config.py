"""Configuration loading for the Redis Iris Context Retriever agent.

All settings come from environment variables (loaded from a local ``.env`` via
python-dotenv). The only *required* value is the Context Retriever agent key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Default MCP endpoint for the Context Retriever. Override with CTX_MCP_URL if
# your service lives in a different region.
DEFAULT_MCP_URL = "https://gcp-us-east4.context-surfaces.redis.io/mcp"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


DEFAULT_OWNER_ID = "machine-floor"
DEFAULT_SESSION_ID = "session-1"


@dataclass(slots=True)
class Settings:
    """Resolved runtime settings."""

    agent_key: str
    mcp_url: str
    owner_id: str = DEFAULT_OWNER_ID
    session_id: str = DEFAULT_SESSION_ID
    # Agent Memory — all three must be present to enable memory. When any is
    # missing the agent runs Context-Retriever-only and memory tools are not
    # registered.
    memory_endpoint: str | None = None
    memory_store_id: str | None = None
    memory_key: str | None = None

    redis_url: str | None = None

    @property
    def memory_enabled(self) -> bool:
        """True only when all three Agent Memory values are present."""
        return bool(self.memory_endpoint and self.memory_store_id and self.memory_key)

    @property
    def redis_enabled(self) -> bool:
        return bool(self.redis_url)


def load_settings() -> Settings:
    """Load and validate settings from the environment / .env file."""
    load_dotenv()

    agent_key = os.getenv("CONTEXT_RETRIEVER_AGENT_KEY", "").strip()
    if not agent_key:
        raise ConfigError(
            "CONTEXT_RETRIEVER_AGENT_KEY is not set.\n"
            "Create a Context Retriever agent key in the Redis Cloud console "
            "(your service page -> 'Agent key' tab -> 'New Agent Key'), then add "
            "it to a .env file:\n\n"
            "    CONTEXT_RETRIEVER_AGENT_KEY=your-agent-key-here\n\n"
            "See .env.example for the full template."
        )

    return Settings(
        agent_key=agent_key,
        mcp_url=os.getenv("CTX_MCP_URL", "").strip() or DEFAULT_MCP_URL,
        owner_id=os.getenv("OWNER_ID", "").strip() or DEFAULT_OWNER_ID,
        session_id=os.getenv("SESSION_ID", "").strip() or DEFAULT_SESSION_ID,
        memory_endpoint=os.getenv("AGENT_MEMORY_ENDPOINT", "").strip() or None,
        memory_store_id=os.getenv("AGENT_MEMORY_STORE_ID", "").strip() or None,
        memory_key=os.getenv("AGENT_MEMORY_KEY", "").strip() or None,
        redis_url=os.getenv("REDIS_URL", "").strip() or None,
    )
