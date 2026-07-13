"""Colorful conversational CLI for the Redis Iris Context Retriever agent.

Keeps full conversation history in memory (Pydantic AI ``message_history``),
shows which Context Retriever MCP tools the agent called for each answer, and
supports a set of slash commands.

Run:
    python -m src.agent.cli
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import ModelMessage, ToolCallPart
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .agent import build_agent, build_toolset
from .config import ConfigError, Settings, load_settings
from .memory import Identity, MemoryService
from .model_provider import ModelConfigError
from .prompts import HELP
from ..utils.tool_names import safe_name_map

console = Console()

# Demo identity. In a real multi-user app these come from your auth layer; here
# one user is hardcoded and the session id is rotated with /newsession.
# Must match the owner_id in seed_crestforge so pre-seeded memories are found.
DEFAULT_OWNER_ID = "machine-floor"
DEFAULT_SESSION_ID = "session-1"

_MAX_INPUT = 8_000


def _banner(settings: Settings, identity: Identity, memory_on: bool) -> Panel:
    provider = os.getenv("PROVIDER", "?")
    model_name = os.getenv("MODEL_NAME", "?")
    body = Text()
    body.append("Redis Iris ", style="bold red")
    body.append("agent\n", style="bold white")
    body.append(
        "Ask about your data in plain English. Live data comes through "
        "the Context Retriever MCP tools; ",
        style="white",
    )
    if memory_on:
        body.append(
            "what you tell it is remembered across sessions via Agent Memory.\n\n",
            style="white",
        )
    else:
        body.append("Agent Memory is off (data only).\n\n", style="white")
    body.append("model    ", style="dim")
    body.append(f"{provider}:{model_name}\n", style="cyan")
    body.append("data     ", style="dim")
    body.append(f"Context Retriever  {settings.mcp_url}\n", style="cyan")
    body.append("memory   ", style="dim")
    if memory_on:
        body.append(f"Agent Memory  (user={identity.owner_id})\n", style="cyan")
    else:
        body.append("off\n", style="yellow")
    body.append("\nType ", style="dim")
    body.append("/help", style="cyan")
    body.append(" for commands.", style="dim")
    return Panel(body, border_style="red", title="[bold]iris[/bold]", expand=False)


def _render_tool_calls(new_messages: list[ModelMessage]) -> None:
    """Print a dim line for each Context Retriever tool the agent invoked."""
    calls: list[ToolCallPart] = [
        part
        for message in new_messages
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolCallPart)
    ]
    for call in calls:
        args = call.args_as_dict() if hasattr(call, "args_as_dict") else call.args
        console.print(
            Text.assemble(
                ("  ↳ ", "dim"),
                (call.tool_name, "green"),
                (f"  {args}", "dim"),
            )
        )


async def _list_tools(toolset) -> None:
    try:
        tools = await toolset.list_tools()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not list tools:[/red] {exc}")
        return

    if not tools:
        console.print(
            "[yellow]No tools available.[/yellow] "
            "Is the Context Retriever service configured with entities?"
        )
        return

    table = Table(
        title=f"Context Retriever tools ({len(tools)})",
        title_style="bold red",
        border_style="dim",
        show_lines=False,
    )
    table.add_column("Tool", style="green", no_wrap=True)
    table.add_column("Description", style="white")
    for tool in tools:
        desc = (getattr(tool, "description", "") or "").strip().split("\n")[0]
        table.add_row(getattr(tool, "name", "?"), desc)
    console.print(table)


async def _run() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        console.print(
            Panel(str(exc), title="[red]Configuration needed[/red]", border_style="red")
        )
        return 1
    except ModelConfigError as exc:
        console.print(
            Panel(
                str(exc),
                title="[red]Model configuration needed[/red]",
                border_style="red",
            )
        )
        return 1

    toolset = build_toolset(settings)

    tool_names: list[str] | None = None
    connect_error: str | None = None
    try:
        tool_names = [t.name for t in await toolset.list_tools()]
    except Exception as exc:  # noqa: BLE001
        connect_error = str(exc)

    name_map = safe_name_map(tool_names) if tool_names else {}
    agent_toolset = toolset.renamed(name_map) if name_map else toolset

    identity = Identity(owner_id=DEFAULT_OWNER_ID, session_id=DEFAULT_SESSION_ID)
    active_machine: str | None = None
    memory: MemoryService | None = None
    memory_note = ""
    if settings.memory_enabled:
        try:
            memory = MemoryService.from_settings(settings, identity)
            reachable = await memory.health()
            if not reachable:
                memory_note = (
                    "  [yellow](memory endpoint not reachable — check "
                    "AGENT_MEMORY_* values)[/yellow]"
                )
        except Exception as exc:  # noqa: BLE001
            memory = None
            memory_note = f"  [yellow](memory disabled: {exc})[/yellow]"

    try:
        agent = build_agent(settings, agent_toolset, memory=memory)
    except (UserError, ModelConfigError) as exc:
        console.print(
            Panel(
                f"{exc}\n\n"
                "Check that PROVIDER, MODEL_NAME, and API_KEY are set correctly in your .env.",
                title="[red]Model configuration needed[/red]",
                border_style="red",
            )
        )
        return 1

    console.print(_banner(settings, identity, memory_on=memory is not None))
    if memory_note:
        console.print(memory_note)

    if tool_names is not None:
        sanitised_note = (
            f"  [dim]({len(name_map)} name(s) sanitised for the model)[/dim]"
            if name_map
            else ""
        )
        console.print(
            f"[dim]Connected. [green]{len(tool_names)}[/green] "
            f"Context Retriever tools available.[/dim]{sanitised_note}\n"
        )
    else:
        auth_hint = ""
        if connect_error and ("401" in connect_error or "403" in connect_error):
            auth_hint = (
                "  [dim]Looks like an auth failure — check "
                "CONTEXT_RETRIEVER_AGENT_KEY (and CTX_MCP_URL region).[/dim]"
            )
        console.print(
            f"[yellow]Could not reach the Context Retriever:[/yellow] "
            f"{connect_error}{auth_hint}\n"
        )

    session: PromptSession[str] = PromptSession(history=InMemoryHistory())
    history: list[ModelMessage] = []

    async with agent:
        while True:
            try:
                user_input = (await session.prompt_async("you › ")).strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]bye[/dim]")
                return 0

            if not user_input:
                continue

            lowered = user_input.lower()

            if lowered in ("/exit", "/quit"):
                console.print("[dim]bye[/dim]")
                return 0

            if lowered == "/help":
                console.print(HELP)
                continue

            if lowered == "/clear":
                history = []
                console.print("[dim]conversation history cleared[/dim]\n")
                continue

            if lowered.startswith("/machine"):
                parts = user_input.split(None, 1)
                if len(parts) < 2 or not parts[1].strip():
                    console.print(
                        "[yellow]Usage: /machine <id>  (e.g. /machine M104)[/yellow]\n"
                    )
                else:
                    active_machine = parts[1].strip().upper()
                    console.print(
                        f"[dim]active machine set to[/dim] [cyan]{active_machine}[/cyan]\n"
                    )
                continue

            if lowered == "/whoami":
                machine_str = (
                    f"  [dim]machine[/dim] [cyan]{active_machine}[/cyan]"
                    if active_machine
                    else ""
                )
                console.print(
                    f"[dim]user[/dim] [cyan]{identity.owner_id}[/cyan]  "
                    f"[dim]session[/dim] [cyan]{identity.session_id}[/cyan]"
                    f"  [dim]memory[/dim] "
                    f"{'[green]on[/green]' if memory else '[yellow]off[/yellow]'}"
                    f"{machine_str}\n"
                )
                continue

            if lowered in ("/newshift", "/newsession"):
                history = []
                active_machine = None
                nxt = (
                    re.sub(
                        r"(\d+)$",
                        lambda m: str(int(m.group()) + 1),
                        identity.session_id,
                    )
                    if re.search(r"\d+$", identity.session_id)
                    else f"{identity.session_id}-2"
                )
                identity.session_id = nxt
                if memory:
                    console.print(
                        f"[dim]new shift started — session[/dim] [cyan]{nxt}[/cyan]"
                        f"[dim] — working memory cleared, long-term memory "
                        f"persists. Ask it what it remembers.[/dim]\n"
                    )
                else:
                    console.print(
                        f"[dim]new shift — session[/dim] [cyan]{nxt}[/cyan] "
                        f"[yellow](memory off — nothing persists)[/yellow]\n"
                    )
                continue

            if lowered == "/tools":
                await _list_tools(toolset)
                continue

            if len(user_input) > _MAX_INPUT:
                console.print(
                    f"[yellow]Input truncated to {_MAX_INPUT} characters "
                    f"(was {len(user_input)}).[/yellow]"
                )
                user_input = user_input[:_MAX_INPUT]

            prompt = (
                f"[Active machine: {active_machine}]\n{user_input}"
                if active_machine
                else user_input
            )

            if memory:
                await memory.log_turn("user", user_input)

            try:
                with console.status("[red]thinking…[/red]", spinner="dots"):
                    result = await agent.run(prompt, message_history=history)
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]Error:[/red] {exc}\n")
                continue

            _render_tool_calls(result.new_messages())
            console.print()
            console.print(Text("iris ›", style="bold red"))
            console.print(Markdown(result.output))
            console.print()

            if memory:
                await memory.log_turn("assistant", result.output)

            history = result.all_messages()


def main() -> None:
    """Console-script entry point."""
    # The Context Retriever server doesn't implement the optional MCP
    # session-DELETE endpoint, so the client logs a harmless "Session
    # termination failed: 404" on close. Silence it.
    logging.getLogger("mcp.client.streamable_http").setLevel(logging.ERROR)
    try:
        raise SystemExit(asyncio.run(_run()))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
