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

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic_ai.messages import ToolCallPart

from ..agent.config import ConfigError
from ..agent.model_provider import ModelConfigError
from .models import ChatRequest, SessionInfo, SetMachineRequest
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
        result = await state.agent.run(prompt, message_history=state.history)
    except Exception as exc:  # noqa: BLE001
        yield _emit({"type": "error", "message": str(exc)})
        return

    # Emit each Context Retriever (and memory) tool call the agent made.
    for msg in result.new_messages():
        for part in getattr(msg, "parts", []):
            if isinstance(part, ToolCallPart):
                args = part.args_as_dict() if hasattr(part, "args_as_dict") else {}
                yield _emit({"type": "tool_call", "name": part.tool_name, "args": args})

    yield _emit({"type": "text", "content": result.output})

    if state.memory:
        await state.memory.log_turn("assistant", result.output)

    state.history = result.all_messages()

    yield _emit({"type": "done", "session": _session_dict(state)})


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
