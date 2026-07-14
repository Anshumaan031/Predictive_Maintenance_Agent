"""Pydantic schemas for the Redis Iris Agent HTTP API."""

from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class SetMachineRequest(BaseModel):
    machine_id: str


class SetUserRequest(BaseModel):
    owner_id: str


class SessionInfo(BaseModel):
    owner_id: str
    session_id: str
    active_machine: str | None
    memory_on: bool
    history_length: int
    tool_count: int
