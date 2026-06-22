@AGENTS.md

# CLAUDE.md

Claude Code operating rules for this repo. **Project facts live in `AGENTS.md`** (imported above) — this file is *only* how Claude should work here. On any conflict about project facts, AGENTS.md wins.

## 1. Permission Model — ask vs proceed

- **Proceed without asking:** read-only exploration (read / grep / list); running tests, `ruff check`, `ruff format --check`; creating or editing source & test files within the package layout; editing docs.
- **Ask first** (outward-facing or hard to reverse): `git commit`, `git push`, dependency changes, file/dir deletion, running the long-lived dev server, anything writing outside the repo or hitting the network.

## 2. Commands Requiring `[y/n]` Permission

`git commit` · `git push` · `uv add` / `uv remove` / `uv sync --upgrade` · `rm` and other destructive file ops · `uv run streamlit run website/app.py` / `uv run uvicorn app.main:app` (long-running) · any global/system install.
Commit & push **only when the user asks** — never autonomously.

## 3. Context Management

Proactively compact/clear at **~60k tokens**. Before clearing, write a short progress summary (done / next / open decisions) so work resumes cleanly.

## 4. Thinking Depth

- **Think deeper for:** architecture or LangGraph workflow changes, agent-contract/schema design, debugging test failures, multi-file refactors.
- **Minimal thinking for:** doc edits, typos/renames, single-line changes, adding an `__init__.py`.

## 5. Commit Message Format

Conventional Commits: `type(scope): subject` — imperative, ≤72 chars.
Types: `feat` · `fix` · `docs` · `refactor` · `test` · `chore`. Example scopes: `sql-agent`, `orchestration`, `schemas`.
End Claude commits with:

```
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

## 6. Branch Naming

`type/short-desc` — e.g. `feat/sql-agent`, `fix/validation-bypass`, `docs/agents-md`. Don't commit feature work directly to `main`; branch first.

## 7. Quality Gates (in order, before any commit)

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uv run pytest`

All must pass — don't claim done or commit on red. No build step (Streamlit). `ruff` and `pytest` are installed as dev dependencies.

## 8. Docstrings

Every module, public class, and public function/method gets a triple-quoted docstring. Agents/tools/services state purpose + inputs/outputs and name the Pydantic contract they consume/return. Skip trivial one-liners and dunder methods. Keep docstrings current when behavior changes.

## 9. Logging

Always use the centralized logger from `app/config/log_config.py`:

```python
from app.config.log_config import get_logger
logger = get_logger(__name__)
```

Never `print()` for diagnostics; never configure logging ad-hoc in modules. Log at meaningful boundaries — SQL generation/validation/execution, node transitions, errors — and never log secrets or full result sets.

## 10. Class-Based / OOP

Implement application code as **classes** — agents, services, and repositories are classes with one clear responsibility; inject dependencies via the constructor; one primary class per module. Functional code is fine only for: Pydantic models in `app/schemas/`, prompt constants in `app/prompts/`, thin entry points (`app/main.py` / `website/app.py` / `app/starter.py`), small pure helpers in `app/utils/`, and the **`@tool`-decorated callables** that form an agent's internal tools (closures built in `_build_tools()` that capture constructor-injected deps and use `InjectedState` / `Command`). The agent stays a class; only the tool callables it provides are functions.

**Agent pattern** — every agent (`SqlAgent`, `VisualizationAgent`, `InsightAgent`, `FollowupAgent`) is a `create_agent()` instance built in `__init__` with its own LLM, prompt, and `@tool`-decorated internal tools. Internal tools are invisible to the supervisor; the supervisor invokes each agent as a subagent. See `AGENTS.md §6` and `docs/issues/04-sql-agent-subagent.md` for the canonical shape.
