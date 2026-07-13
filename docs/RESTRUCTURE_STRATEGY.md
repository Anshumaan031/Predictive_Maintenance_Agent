# Codebase Restructure Strategy

## Goal

Replace `src/redis_iris_agent/` with a clean, PEP 8-compliant, modular package layout under `src/` where every sub-package is runnable directly as a Python module and all internal imports are relative.

---

## New Directory Layout

```
src/
├── __init__.py
├── __main__.py                  ← python -m src  → launches the agent CLI
│
├── agent/
│   ├── __init__.py              ← exports: build_agent, build_toolset
│   ├── __main__.py              ← python -m src.agent  → same as above
│   ├── agent.py                 ← Agent wiring (no prompts inline)
│   ├── cli.py                   ← Rich/prompt-toolkit REPL loop
│   ├── config.py                ← Settings dataclass + load_settings()
│   ├── memory.py                ← MemoryService + Identity dataclass
│   ├── model_provider.py        ← build_model() dispatcher
│   └── prompts.py               ← SYSTEM_PROMPT, MEMORY_PROMPT, HELP text (NEW)
│
├── crestforge/
│   ├── __init__.py
│   ├── __main__.py              ← python -m src.crestforge  → usage hint
│   ├── configure.py             ← moved from top-level configure_crestforge.py
│   └── seed.py                  ← moved from top-level seed_crestforge.py
│
└── utils/
    ├── __init__.py
    └── tool_names.py            ← safe_name_map() extracted from agent.py
```

---

## Module-by-Module Changes

### `src/agent/prompts.py` (new file)

Extract all string literals that are prompts or user-facing copy out of `agent.py` and `cli.py`:

| Constant | Moved from |
|---|---|
| `SYSTEM_PROMPT` | `agent.py` |
| `MEMORY_PROMPT` | `agent.py` |
| `HELP` | `cli.py` |
| `BANNER_TITLE` | `cli.py` inline string |

`agent.py` and `cli.py` then import from `.prompts`.

### `src/utils/tool_names.py` (new file)

Extract `safe_name_map()` from `agent.py` — it is a pure utility with no agent coupling and belongs in utilities. `agent.py` imports it with `from ..utils.tool_names import safe_name_map`.

### `src/agent/config.py`

No logic changes; only PEP 8 pass: blank lines between methods, type hints on all signatures, `ConfigError` docstring tightened.

### `src/agent/model_provider.py`

No logic changes; ensure `ModelConfigError` inherits `ValueError` (already does), each provider branch is its own named helper function (`_anthropic_model`, `_openai_model`, etc.) so `build_model` is a thin dispatcher.

### `src/agent/memory.py`

- Move `Identity` to a `dataclasses.dataclass` with a `__post_init__` validator.
- All methods that swallow exceptions should `logger.debug` the traceback rather than silently ignore — keeps PEP 8 logging practice.

### `src/agent/agent.py`

After extraction:
- Imports `SYSTEM_PROMPT`, `MEMORY_PROMPT` from `.prompts`.
- Imports `safe_name_map` from `..utils.tool_names`.
- `build_toolset` and `build_agent` remain; `_attach_memory_tools` becomes a module-level private function.

### `src/crestforge/configure.py`

Exact move of `configure_crestforge.py`; add `if __name__ == "__main__": main()` guard (already present) and a `__main__.py` so `python -m src.crestforge.configure` works.

### `src/crestforge/seed.py`

Exact move of `seed_crestforge.py`; same treatment.

### Top-level `configure_crestforge.py` and `seed_crestforge.py`

Reduce to thin shims that forward to the new modules — kept temporarily for backwards compatibility, removed after confirming entry points work:

```python
# configure_crestforge.py (shim — delete after migration)
from src.crestforge.configure import main
if __name__ == "__main__":
    main()
```

---

## Import Convention

All imports inside `src/` use **relative imports**:

```python
# inside src/agent/agent.py
from .config import Settings
from .prompts import SYSTEM_PROMPT, MEMORY_PROMPT
from ..utils.tool_names import safe_name_map
```

No `src.` prefix anywhere inside the package. This lets the package work whether it is installed via `pip install -e .` or run with `python -m src.*`.

---

## Entry Points

### Running from project root

```bash
# Agent CLI
python -m src.agent

# Configure CrestForge surface
python -m src.crestforge.configure

# Seed CrestForge data
python -m src.crestforge.seed
```

### `src/__main__.py` (convenience)

```python
from src.agent.cli import main
main()
```

Allows `python -m src` from the project root as the primary shorthand.

### `pyproject.toml` — update `[project.scripts]`

```toml
[project.scripts]
iris-agent          = "src.agent.cli:main"
crestforge-config   = "src.crestforge.configure:main"
crestforge-seed     = "src.crestforge.seed:main"
```

---

## PEP 8 Checklist (applied everywhere)

- [ ] Max line length 99 characters (matches Black default).
- [ ] All public functions and classes have single-line docstrings.
- [ ] No mutable default arguments.
- [ ] Logging via `logging.getLogger(__name__)` instead of `print` for non-CLI output.
- [ ] Type annotations on every function signature.
- [ ] `dataclass(slots=True, frozen=True)` for value objects (e.g. `Settings`); `slots=True` only for mutable ones (e.g. `Identity`).
- [ ] Exception chains: `raise X from e` everywhere.
- [ ] Constants at module top in `SCREAMING_SNAKE_CASE`.
- [ ] No bare `except:` — always catch a named exception.

---

## File Deletion Plan

After migration and verification:

1. Delete `src/redis_iris_agent/` (all 6 files).
2. Delete top-level `configure_crestforge.py` and `seed_crestforge.py` shims once CI/entry points confirmed.

---

## Migration Order

1. Create `src/utils/tool_names.py` — extract `safe_name_map`.
2. Create `src/agent/prompts.py` — extract all prompt/copy constants.
3. Port each module in dependency order: `config` → `model_provider` → `memory` → `agent` → `cli`.
4. Add `__init__.py` and `__main__.py` files.
5. Port `configure.py` and `seed.py` into `src/crestforge/`.
6. Update `pyproject.toml` entry points.
7. Smoke-test: `python -m src`, `python -m src.crestforge.configure --probe`, `python -m src.crestforge.seed --verify`.
8. Delete `src/redis_iris_agent/` and top-level shims.
