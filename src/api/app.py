"""FastAPI server for the Redis Iris agent.

Each POST /chat request streams Server-Sent Events in this order:
    {"type": "thinking"}
    {"type": "tool_call", "name": "...", "args": {...}}   ← one per tool invoked
    {"type": "text", "content": "..."}                    ← full agent answer
    {"type": "done", "session": {...}}

Run:
    python -m uvicorn src.api.app:app --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic_ai import (
    AgentRunResultEvent,
    FunctionToolCallEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPartDelta,
)
from pydantic_ai.messages import TextPart, ToolCallPart

from agent.config import ConfigError
from agent.model_provider import ModelConfigError
from . import analytics
from .models import ChatRequest, SessionInfo, SetMachineRequest, SetUserRequest
from .state import AppState, create_state

logger = logging.getLogger(__name__)

_state: AppState | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _state
    try:
        state, warnings = await create_state()
    except (ConfigError, ModelConfigError) as exc:
        logger.error("Startup failed — check your .env: %s", exc)
        raise RuntimeError(str(exc)) from exc

    for w in warnings:
        logger.warning(w)

    # Keep the MCP connection open for the server lifetime.
    async with state.agent:
        _state = state
        yield
        _state = None


app = FastAPI(title="Redis Iris Agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_state() -> AppState:
    if _state is None:
        raise HTTPException(status_code=503, detail="Agent not initialized.")
    return _state


def _session_dict(state: AppState) -> dict:
    return {
        "owner_id": state.identity.owner_id,
        "session_id": state.identity.session_id,
        "active_machine": state.active_machine,
        "memory_on": state.memory is not None,
        "history_length": len(state.history),
        "tool_count": len(state.tool_names),
    }


# ---------------------------------------------------------------------------
# Chat — SSE
# ---------------------------------------------------------------------------


async def _chat_sse(state: AppState, message: str) -> AsyncGenerator[str, None]:
    def _emit(event: dict) -> str:
        return f"data: {json.dumps(event)}\n\n"

    if len(message) > 8_000:
        message = message[:8_000]

    prompt = (
        f"[Active machine: {state.active_machine}]\n{message}"
        if state.active_machine
        else message
    )

    yield _emit({"type": "thinking"})

    if state.memory:
        await state.memory.log_turn("user", message)

    try:
        async with state.agent.run_stream_events(prompt, message_history=state.history) as events:
            async for event in events:
                if isinstance(event, FunctionToolCallEvent):
                    args = (
                        event.part.args_as_dict()
                        if hasattr(event.part, "args_as_dict")
                        else event.part.args
                    )
                    yield _emit({"type": "tool_call", "name": event.part.tool_name, "args": args})
                elif isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                    if event.part.content:
                        yield _emit({"type": "token", "content": event.part.content})
                elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    if event.delta.content_delta:
                        yield _emit({"type": "token", "content": event.delta.content_delta})
                elif isinstance(event, AgentRunResultEvent):
                    full_text = event.result.output
                    if state.memory:
                        await state.memory.log_turn("assistant", full_text)
                    state.history = event.result.all_messages()
                    yield _emit({"type": "text", "content": full_text})
                    yield _emit({"type": "done", "session": _session_dict(state)})
    except Exception as exc:  # noqa: BLE001
        yield _emit({"type": "error", "message": str(exc)})


@app.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    state = _require_state()
    return StreamingResponse(
        _chat_sse(state, req.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Chat — sync (for Swagger UI / Postman testing)
# ---------------------------------------------------------------------------


@app.post("/chat/sync")
async def chat_sync(req: ChatRequest) -> dict:
    state = _require_state()
    message = req.message[:8_000]
    prompt = (
        f"[Active machine: {state.active_machine}]\n{message}"
        if state.active_machine
        else message
    )

    if state.memory:
        await state.memory.log_turn("user", message)

    try:
        result = await state.agent.run(prompt, message_history=state.history)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    tool_calls = [
        {
            "name": part.tool_name,
            "args": part.args_as_dict() if hasattr(part, "args_as_dict") else {},
        }
        for msg in result.new_messages()
        for part in getattr(msg, "parts", [])
        if isinstance(part, ToolCallPart)
    ]

    if state.memory:
        await state.memory.log_turn("assistant", result.output)

    state.history = result.all_messages()

    return {
        "text": result.output,
        "tool_calls": tool_calls,
        "session": _session_dict(state),
    }


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@app.get("/session", response_model=SessionInfo)
async def get_session() -> SessionInfo:
    return SessionInfo(**_session_dict(_require_state()))


@app.post("/session/user", response_model=SessionInfo)
async def set_user(req: SetUserRequest) -> SessionInfo:
    state = _require_state()
    state.identity.owner_id = req.owner_id.strip()
    state.history = []
    state.active_machine = None
    return SessionInfo(**_session_dict(state))


@app.post("/session/machine", response_model=SessionInfo)
async def set_machine(req: SetMachineRequest) -> SessionInfo:
    state = _require_state()
    state.active_machine = req.machine_id.strip().upper()
    return SessionInfo(**_session_dict(state))


@app.post("/session/new-shift", response_model=SessionInfo)
async def new_shift() -> SessionInfo:
    state = _require_state()
    state.history = []
    state.active_machine = None
    nxt = (
        re.sub(
            r"(\d+)$",
            lambda m: str(int(m.group()) + 1),
            state.identity.session_id,
        )
        if re.search(r"\d+$", state.identity.session_id)
        else f"{state.identity.session_id}-2"
    )
    state.identity.session_id = nxt
    return SessionInfo(**_session_dict(state))


@app.delete("/session/history")
async def clear_history() -> dict:
    state = _require_state()
    state.history = []
    return {"cleared": True, "session_id": state.identity.session_id}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@app.get("/tools")
async def list_tools() -> dict:
    state = _require_state()
    try:
        tools = await state.toolset.list_tools()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "count": len(tools),
        "tools": [
            {
                "name": getattr(t, "name", "?"),
                "description": (
                    (getattr(t, "description", "") or "").strip().split("\n")[0]
                ),
            }
            for t in tools
        ],
    }


# ---------------------------------------------------------------------------
# Data — dynamic Redis analytics
# ---------------------------------------------------------------------------


def _require_redis(state: AppState):
    if state.redis_client is None:
        raise HTTPException(
            status_code=503,
            detail="Redis direct connection unavailable. Set REDIS_URL in .env.",
        )
    return state.redis_client


@app.get("/data/schema")
async def data_schema() -> dict:
    """Discovered entity types, field types, and inferred FK relationships."""
    redis = _require_redis(_require_state())
    return await asyncio.to_thread(analytics.get_schema, redis)


@app.get("/data/overview")
async def data_overview() -> dict:
    """Entity counts and categorical field distributions across all entities."""
    redis = _require_redis(_require_state())
    return await asyncio.to_thread(analytics.get_overview, redis)


@app.get("/data/analytics")
async def data_analytics() -> dict:
    """Per-entity, per-field statistics: distributions for categoricals,
    descriptive stats (min/max/mean/median/stdev) for numerics."""
    redis = _require_redis(_require_state())
    return await asyncio.to_thread(analytics.get_entity_analytics, redis)


@app.get("/data/relationships")
async def data_relationships() -> dict:
    """Graph payload — nodes and edges inferred from foreign-key fields
    across all entity types. Suitable for force-directed graph renderers."""
    redis = _require_redis(_require_state())
    return await asyncio.to_thread(analytics.get_relationships_graph, redis)


@app.get("/data/entities")
async def data_entities() -> dict:
    """List all discovered entity types and their record counts."""
    redis = _require_redis(_require_state())
    schema = await asyncio.to_thread(analytics.get_schema, redis)
    return {
        "entity_types": [
            {"name": et, "count": info["count"]}
            for et, info in schema["entity_types"].items()
        ]
    }


@app.get("/data/entity/{entity_type}")
async def data_entity_records(entity_type: str) -> list:
    """All documents for the given entity type."""
    redis = _require_redis(_require_state())
    records = await asyncio.to_thread(analytics.get_entity_records, redis, entity_type)
    if records is None:
        raise HTTPException(status_code=404, detail=f"Entity type '{entity_type}' not found.")
    return records


@app.get("/data/entity/{entity_type}/{record_id}")
async def data_entity_detail(entity_type: str, record_id: str) -> dict:
    """Single document enriched with all documents it references and all
    documents that reference it — derived entirely from FK field naming."""
    redis = _require_redis(_require_state())
    detail = await asyncio.to_thread(analytics.get_record_detail, redis, entity_type, record_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"{entity_type}:{record_id} not found.")
    return detail


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    state = _require_state()
    return {
        "status": "ok",
        "provider": os.getenv("PROVIDER", "?"),
        "model": os.getenv("MODEL_NAME", "?"),
        "mcp_url": state.settings.mcp_url,
        "memory_on": state.memory is not None,
        "tool_count": len(state.tool_names),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Console-script entry point: ``iris-api``."""
    import uvicorn

    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
