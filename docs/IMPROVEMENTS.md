# Redis Iris Agent — Improvement Suggestions

> Generated 2026-07-15. Professionalism and repo quality improvements beyond feature additions.

---

## Recommended Additions

| # | Item | Effort | Why |
|---|---|---|---|
| 1 | Docker + Docker Compose | Medium | Makes the project instantly runnable for anyone |
| 2 | GitHub Actions CI Pipeline | Small | Green checkmark on every PR; linting + type check + tests |
| 3 | Unit + Integration Tests | Medium | Most impressive signal for a backend-heavy project |
| 4 | Linting + Formatting (ruff) | Small | Visible code consistency; one config section |
| 5 | `.env.example` File | Small | Standard practice; tells contributors what to configure |
| 6 | Fix `pyproject.toml` Author | Trivial | Currently lists Cole Medin — update before sharing |

---

### Docker + Docker Compose

Your app requires Redis to run, which makes it hard for anyone to clone and try. A `Dockerfile` + `docker-compose.yml` that spins up both the agent/API and Redis together is the single most visible signal of a production-ready project.

```
Dockerfile          # for the agent/API
docker-compose.yml  # redis + agent + api services together
```

Anyone can run `docker compose up` and have a working environment in seconds — no manual Redis setup, no environment guesswork.

---

### GitHub Actions CI Pipeline

A `.github/workflows/ci.yml` that runs on every push and PR:
- Install deps via `uv`
- Run linting (`ruff`)
- Run type checking (`pyright` or `mypy`)
- Run tests (once added)

This produces the green checkmark on your repo that is immediately visible to any visitor and signals that the project is actively maintained.

---

### Unit + Integration Tests

The clean separation between `agent/`, `api/`, and `utils/` makes this very testable. Priorities:

- `tests/unit/test_tools.py` — mock Redis, test each tool in `tools.py` individually
- `tests/unit/test_agent.py` — mock the model, test prompt construction
- `tests/integration/test_api.py` — spin up the FastAPI app with `httpx.AsyncClient` and hit the endpoints

Use `pytest` + `pytest-asyncio`. These are strong signals for a backend-heavy project like this.

---

### Linting + Formatting (ruff)

Add `ruff` to `pyproject.toml` and a pre-commit hook. One config section, zero friction:

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
```

Makes code visibly consistent and catches issues before CI does.

---

### `.env.example` File

A `.env.example` with placeholder values (no secrets) is standard practice and tells contributors exactly what they need to configure — rather than hunting through the README or source code.

```
ANTHROPIC_API_KEY=your-key-here
REDIS_URL=redis://localhost:6379
```

---

### Fix `pyproject.toml` Author

The author is currently listed as `Cole Medin`. Update the `authors` field to yourself before sharing or publishing the repo — it is one of the first things anyone reads in the package metadata.
