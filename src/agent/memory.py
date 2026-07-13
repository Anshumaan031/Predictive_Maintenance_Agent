"""Redis Iris Agent Memory integration for the Pydantic AI agent.

Context Retriever gives the agent *business data* (live records). Agent Memory
gives it *conversation* memory:

* **Session (working / short-term) memory** — an ordered log of the current
  conversation's events, scoped by ``session_id``, with a TTL. The managed
  service automatically summarises/trims it and, in the background,
  **promotes** high-signal facts into long-term memory.
* **Long-term memory** — cross-session facts persisted per user and retrieved
  by semantic (vector) search + metadata filters, regardless of session.

Long-term memory is exposed to the model as two ordinary tools
(``search_memory`` / ``store_memory``) so recall/write appear as tool calls
alongside the Context Retriever tools — one context layer, all tools. Each turn
is also logged as a session event so the service's background extractor can
promote durable facts without any promotion code on our side.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:  # optional dependency — Context Retriever works without it
    from redis_agent_memory import AgentMemory, models as _memory_models

    _IMPORT_ERROR: Exception | None = None
except Exception as exc:  # noqa: BLE001
    AgentMemory = None  # type: ignore[assignment]
    _memory_models = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc

from .config import Settings


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class Identity:
    """Whose memory we read/write.

    Mutable on purpose: ``/newsession`` rotates ``session_id`` while keeping the
    same ``owner_id``, demonstrating cross-session recall — facts stored under
    one session are recalled in the next because long-term memory is keyed on
    the *user*, not the session.
    """

    owner_id: str
    session_id: str


class MemoryService:
    """Thin wrapper over the managed Agent Memory client, bound to an identity."""

    def __init__(self, client: "AgentMemory", identity: Identity) -> None:
        self._client = client
        self.identity = identity

    @classmethod
    def from_settings(cls, settings: Settings, identity: Identity) -> "MemoryService":
        """Instantiate from resolved settings. Raises ``RuntimeError`` if the
        ``redis-agent-memory`` package is not importable."""
        if AgentMemory is None:
            raise RuntimeError(
                "Agent Memory is configured but the 'redis-agent-memory' package "
                f"is not importable: {_IMPORT_ERROR!r}. Run `uv sync`."
            ) from _IMPORT_ERROR
        client = AgentMemory(
            settings.memory_endpoint,
            store_id=settings.memory_store_id,
            api_key=settings.memory_key,
        )
        return cls(client, identity)

    async def health(self) -> bool:
        """Best-effort reachability check; never raises."""
        try:
            await self._client.health_async()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("Agent Memory health check failed: %s", exc)
            return False

    async def log_turn(self, role: str, text: str) -> None:
        """Append one conversation event to session (working) memory.

        ``role`` is ``"user"`` or ``"assistant"``. Failures are swallowed so
        memory logging never interrupts the chat loop.
        """
        if not text:
            return
        try:
            msg_role = (
                _memory_models.MessageRole.USER
                if role == "user"
                else _memory_models.MessageRole.ASSISTANT
            )
            await self._client.add_session_event_async(
                session_id=self.identity.session_id,
                actor_id=self.identity.owner_id,
                role=msg_role,
                content=[{"text": text}],
                created_at=_now_ms(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("log_turn failed (role=%s): %s", role, exc)

    async def search(self, query: str) -> str:
        """Semantic search over THIS user's long-term memory. Returns JSON text."""
        res = await self._client.search_long_term_memory_async(
            request={
                "text": query,
                "filter": {"owner_id": {"eq": self.identity.owner_id}},
            }
        )
        return _to_text(res)

    async def store(self, fact: str) -> str:
        """Persist a durable fact to THIS user's long-term memory (immediate)."""
        memory_id = f"{self.identity.owner_id}-{_now_ms()}"
        res = await self._client.bulk_create_long_term_memories_async(
            memories=[
                {
                    "id": memory_id,
                    "owner_id": self.identity.owner_id,
                    "text": fact,
                }
            ]
        )
        return _to_text(res)


def _to_text(obj: object) -> str:
    """Coerce an SDK response (pydantic model or plain) into a string for the LLM."""
    for attr in ("model_dump_json", "json"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                logger.debug("_to_text: %s() failed: %s", attr, exc)
    return str(obj)
