# AGENTS.md

Single source of truth for AI tools working in this repository. Derived from `docs/FRS.md` (what) and `docs/SDS.md` (how).

> ⚠️ **Early-stage repo.** The package directories below exist (as empty `__init__.py` packages), but the module files within them and the commands are still the **target** from the SDS — implement as you go.

---

## 1. Project Overview

Natural Language Analytics Dashboard: business users ask questions in plain English; the app translates them to read-only SQL, runs the query, and presents the result as the clearest form — an appropriate chart for multi-row data, or a written sentence for a single value. It also generates actionable insights grounded in the returned data and suggests one-click follow-up questions. Built on Streamlit; lets non-SQL users explore an existing business database.

---

## 2. Repository Structure

Single **uv** project — **not** a monorepo, so there is no `/packages/shared`. Package directories exist as empty packages; files listed are the planned modules:

| Path | Contents |
|---|---|
| `app.py`, `starter.py` | Streamlit entry point / app bootstrap *(not yet created)* |
| `config/` | `env_config`, `db_config`, `log_config`, `llm_config` |
| `agents/` | `sql_agent`, `visualization_agent`, `insight_agent`, `followup_agent` |
| `prompts/` | One prompt module per agent (text never hardcoded in agents) |
| `orchestration/` | LangGraph `graph`, `state`, `conditional_edges`, and `nodes/` |
| `orchestration/nodes/` | `sql_generation`, `sql_validation`, `query_execution`, `visualization`, `insight`, `followup`, `response` |
| `services/` | Business logic: `analytics`, `sql`, `visualization`, `insight`, `followup` |
| `repositories/` | `query_repository` — SQL execution + SQLAlchemy sessions only |
| `models/` | SQLAlchemy models: `customer`, `product`, `order`, `order_item` |
| `schemas/` | Pydantic contracts: `requests`, `responses`, `sql_result`, `chart_config`, `workflow_state` |
| `utils/` | `validators`, `sql_helpers`, `chart_helpers`, DB init + sample-data/seed generators |
| `tests/` | `agents/`, `services/`, `repositories/`, `workflows/`, `integration/` |
| `docs/` | FRS, SDS, spec, `decisions/technical_architecture.md` |

---

## 3. Tech Stack

| Concern | Choice |
|---|---|
| Language | Python ≥ 3.12 |
| Package & env management | uv (`pyproject.toml`, `uv.lock`) |
| Frontend / UI | Streamlit |
| LLM framework | LangChain |
| Workflow orchestration | LangGraph (state-driven graph) |
| Database | SQLite |
| ORM | SQLAlchemy |
| Data processing | Pandas |
| Visualization | Plotly |
| Validation / typed contracts | Pydantic |

---

## 4. Key Commands

uv-based (target — wire up as code lands):

```bash
uv sync                              # install/lock dependencies
uv add <package>                     # add a dependency (updates pyproject + uv.lock)
uv run streamlit run app.py          # dev server (the app)
uv run pytest                        # run the test suite
```

`requirements.txt` is **not** used as the primary dependency source. No lint tool is specified yet — add config before assuming one exists.

---

## 5. Architecture Patterns

Layered architecture + a LangGraph state-driven multi-agent workflow. Six layers:

```
User → Streamlit UI → LangGraph Workflow → Agents → Services → Repositories → SQLite
```

Boundary rules (enforce these):
- **Services** contain business logic and stay **independent of LangGraph**.
- **Repositories** only execute SQL / manage sessions / return results — **no business logic**.
- The **SQL Agent is the only component allowed to touch the database**.
- Agents own their prompts (in `prompts/`) and never hardcode prompt text.

---

## 6. Workflow & Agent Contracts

*(This project has no HTTP/REST/GraphQL API. The "interface contract" is the workflow state + Pydantic schemas exchanged between nodes/agents.)*

**Workflow state fields:** `question`, `generated_sql`, `query_result`, `chart_config`, `insights`, `followup_questions`, `error_message`.

**Node flow:**
```
SQL Generation → SQL Validation → Query Execution
                                      ↓ (parallel)
                     Visualization + Insight + Follow-Up
                                      ↓
                                  Response
```
Visualization, Insight, and Follow-Up nodes run **in parallel** after a successful query; the Response node aggregates their outputs for the UI.

**Agent communication:** structured **Pydantic schemas only** — never unstructured text between agents. Typed outputs exist for SQL generation, visualization, insight, and follow-up.

---

## 7. Coding Standards

- **Naming:** snake_case modules; suffix by role — `*_agent.py`, `*_node.py`, `*_service.py`, `*_repository.py`.
- **Typed data:** every inter-agent / inter-layer payload is a Pydantic model in `schemas/`.
- **Prompts:** live in `prompts/`, one per agent; never inline prompt strings in agent code.
- **Config:** centralized in `config/` — no scattered env reads or magic constants.
- **Error handling:** propagate failures via the workflow `error_message`; surface the standard user-facing messages (see §9 / FRS §10) rather than raw exceptions.

---

## 8. Data Model Summary

SQLite database, accessed **read-only**. Planned SQLAlchemy models: `customers`, `products`, `orders`, `order_items`. Business entities referenced by queries: Orders, Products, Customers, Categories, Regions. The database auto-initializes on first startup (create → schema → tables → generate sample data → seed) via `utils/`.

> Column-level schema is provided before implementation (FRS §5) — do **not** invent columns. Model against the real schema when supplied.

---

## 9. Security & Validation

- **Authentication / authorization: out of scope** (FRS §13). Do not build login, sessions, roles, or RBAC.
- **Read-only enforcement:** the SQL Validation node allows `SELECT` only and **blocks** `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`.
- The SQL Agent is the sole database interface.
- **Standard error responses:** invalid question → `Unable to identify requested entities.`; invalid SQL → `Generated query could not be validated.`; empty result → `No data found for the requested query.`; DB error → `Unable to retrieve data at this time.`

---

## 10. Testing Approach

Framework: pytest, run with `uv run pytest`. Tests live under `tests/`:
- **Unit** — `tests/agents/`, `tests/services/`, plus utilities.
- **Integration** — `tests/workflows/`, `tests/integration/` (LangGraph workflow, DB interactions, agent communication).
- **End-to-end** — full flow from NL question → visualization + insights.

---

## 11. Do NOT Do

- ❌ Fabricate insights, figures, or claims not supported by the returned data (FR-9; core product rule).
- ❌ Generate or execute non-`SELECT` SQL, or bypass the SQL Validation node.
- ❌ Let any component other than the SQL Agent touch the database.
- ❌ Hardcode prompt text inside agents — use `prompts/`.
- ❌ Put business logic in repositories, or import LangGraph into services.
- ❌ Exchange unstructured text between agents — use Pydantic schemas.
- ❌ Add forecasting / predictive modeling / autonomous actions (out of scope, FRS §14).
- ❌ Use `requirements.txt` as the dependency source; commit `.env` or `*.db` (both gitignored).

---

## 12. Source of Truth

- `docs/FRS.md` — functional & non-functional requirements (the *what*), requirement IDs FR-1…FR-12.
- `docs/SDS.md` — software design (the *how*), incl. requirements traceability.
- `docs/decisions/technical_architecture.md` — architecture rationale.

No shared packages — this is a single uv project. When this file and the docs disagree, the docs win; update this file to match.
