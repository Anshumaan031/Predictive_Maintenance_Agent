"""Utilities for sanitising MCP tool names for LLM provider APIs.

Anthropic and OpenAI both require tool names matching ``^[a-zA-Z0-9_-]{1,128}$``.
Context Retriever derives names from entity names, so an entity called
"job queue" yields "get_job queue_by_id" (space included), which is rejected.
``safe_name_map`` detects and renames such tools before they reach the model.
"""

from __future__ import annotations

import re

_SAFE_TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def safe_name_map(tool_names: list[str]) -> dict[str, str]:
    """Return ``{safe_name: original_name}`` for every name an LLM would reject.

    Only entries that need renaming are included; pass the result to
    ``toolset.renamed(...)`` — unmapped tools pass through unchanged.
    """
    used: set[str] = set(tool_names)
    name_map: dict[str, str] = {}
    for original in tool_names:
        if _SAFE_TOOL_NAME.match(original):
            continue
        base = re.sub(r"[^a-zA-Z0-9_-]", "_", original)[:128] or "tool"
        candidate, counter = base, 2
        while candidate in used or candidate in name_map:
            suffix = f"_{counter}"
            candidate = base[: 128 - len(suffix)] + suffix
            counter += 1
        name_map[candidate] = original
        used.add(candidate)
    return name_map
