# Software Design Specification (SDS)

| Field | Value |
|---|---|
| **Project** | Natural Language Analytics Dashboard |
| **Document** | Software Design Specification |
| **Version** | 1.0 |
| **Date** | 2026-06-17 |
| **Status** | Approved |
| **Source** | Derived from `decisions/technical_architecture.md` |

---

## 1. Introduction

### 1.1 Purpose
This document defines **how** the Natural Language Analytics Dashboard is built. It describes the architecture, components, agents, workflow, and design rules that realize the requirements specified in `FRS.md`.

### 1.2 Scope
The design covers the layered application structure, the FastAPI API layer, the LangGraph `create_agent` tool-calling agent, the technology stack, inter-component contracts, configuration, database initialization, and the testing strategy. Section 15 traces each functional requirement to the component that satisfies it.

### 1.3 Relationship to FRS
This SDS is the design counterpart to `FRS.md`. Every requirement register entry (FR-1…FR-12), the validation rules (FRS §9), and the error-handling rules (FRS §10) map to one or more design elements defined here; see §14.

---

## 2. Architecture Overview

The system uses a **layered architecture** combined with a **LangGraph tool-calling agent**. The architecture separates:

- Presentation Layer (Streamlit UI)
- API Layer (FastAPI routes + Chat Service)
- Workflow Orchestration Layer
- Agent Layer
- Service Layer
- Repository Layer
- Persistence Layer

This separation improves maintainability, testability, scalability, and future extensibility.

The Workflow Orchestration Layer is a LangChain `create_agent` **supervisor** that runs a ReAct loop over the capability **tools** exposed by the specialized agents (§6). It is not a fixed node pipeline: the supervisor decides which tools to call and in what order, calling `query_database` first and — once data is returned — emitting the visualization, insight, and follow-up tools together so the prebuilt `ToolNode` runs them in parallel (§7).

---

## 3. Technology Stack

| Concern | Technology |
|---|---|
| Frontend | Streamlit |
| API Framework | FastAPI (ASGI, served via Uvicorn) |
| LLM Framework | LangChain |
| Workflow Orchestration | LangGraph |
| Database | SQLite |
| ORM | SQLAlchemy |
| Data Processing | Pandas |
| Visualization | Plotly |
| Validation | Pydantic |
| Package & Environment Management | uv (with `pyproject.toml`) |

---

## 4. High-Level Architecture

Request flow:

```text
User
  ↓
Streamlit UI
  ↓
FastAPI (routes/)
  ↓
Chat Service
  ↓
create_agent Supervisor (ReAct loop)
  ↓
Agent Tools (query_database · generate_visualization · generate_insights · suggest_followups)
  ↓
Repositories
  ↓
SQLite Database
```

The Streamlit UI is a client of the FastAPI API; routes delegate to the Chat Service, which invokes the LangGraph workflow. See §9.3.

---

## 5. Project Structure

```text
nl-analytics-dashboard/
│
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env
├── .env.example
│
├── app/                          # complete backend
│   ├── main.py                   # FastAPI ASGI entry (uv run uvicorn app.main:app)
│   ├── starter.py                # app bootstrap / factory
│   │
│   ├── routes/
│   │   ├── chat_routes.py
│   │   └── health.py
│   │
│   ├── config/
│   │   ├── env_config.py
│   │   ├── db_config.py
│   │   ├── log_config.py
│   │   └── llm_config.py
│   │
│   ├── agents/
│   │   ├── sql_agent.py
│   │   ├── visualization_agent.py
│   │   ├── insight_agent.py
│   │   └── followup_agent.py
│   │
│   ├── prompts/
│   │   ├── sql_prompt.py
│   │   ├── orchestrator_prompt.py   # supervisor prompt (visualization is deterministic — no prompt)
│   │   ├── insight_prompt.py
│   │   └── followup_prompt.py
│   │
│   ├── orchestration/
│   │   ├── graph.py               # AnalyticsGraph — assembles tools, returns create_agent(...)
│   │   └── state.py               # WorkflowState (MessagesState subclass) + initial_state
│   │
│   ├── services/
│   │   ├── chat_service.py
│   │   ├── analytics_service.py
│   │   ├── sql_service.py
│   │   ├── visualization_service.py
│   │   ├── insight_service.py
│   │   └── followup_service.py
│   │
│   ├── repositories/
│   │   └── query_repository.py
│   │
│   ├── models/
│   │   ├── base.py
│   │   ├── customer.py
│   │   ├── product.py
│   │   ├── order.py
│   │   └── order_item.py
│   │
│   ├── schemas/
│   │   ├── entities.py
│   │   ├── requests.py
│   │   ├── responses.py
│   │   ├── sql_result.py
│   │   ├── chart_config.py
│   │   └── workflow_state.py
│   │
│   └── utils/
│       ├── validators.py
│       ├── sql_helpers.py
│       ├── chart_helpers.py
│       └── database_initializer.py
│
├── website/                      # Streamlit UI (API client)
│   └── app.py                    # uv run streamlit run website/app.py
│
├── tests/
│   ├── agents/
│   ├── services/
│   ├── repositories/
│   ├── workflows/
│   └── integration/
│
└── docs/
    ├── FRS.md
    ├── SDS.md
    ├── nl-analytics-dashboard-spec.md
    └── decisions/
        └── technical_architecture.md
```

---

## 6. Multi-Agent Design

The application uses specialized agents that each **expose a capability tool** (via `get_tools()`) to the `create_agent` supervisor (§2, §7). The supervisor sequences the tools; each tool does real work and returns a typed `Command` that updates the shared workflow state (§7.1). Tools read the prior result from state via `InjectedState`, so the supervisor never has to serialize the dataset back into a tool call.

### 6.1 SQL Agent — `query_database` tool
**Responsibilities:** understand database schema · generate SQL · correct invalid SQL · explain generated SQL.
**Output:** SQL query · query explanation · query result (DataFrame, serialized into state).
The SQL Agent keeps its **own LLM** and prompt. The tool generates SQL, validates it is read-only (§9 / `app/utils/validators.py`), executes it through the Repository, and **self-corrects** by feeding any validation or execution error back into a bounded retry loop. The SQL Agent is the **only** agent allowed to interact with the database.

### 6.2 Visualization Agent — `generate_visualization` tool
**Responsibilities:** analyze query result structure · select visualization type · generate chart configuration.
**Supported visualizations:** Bar Chart · Line Chart · Pie Chart · Scatter Plot · Table.
Selection is **deterministic** (no LLM): the tool reads the result from state and applies the result-shape → chart-type rules (FRS §6.3) via `app/utils/chart_helpers.py`.

### 6.3 Insight Agent — `generate_insights` tool
**Responsibilities:** analyze returned data · identify trends · identify outliers · generate actionable business insights.
The Insight Agent runs its **own data-grounded LLM** call over the returned rows. All insights must be grounded in actual returned data. No fabricated values or unsupported conclusions are permitted.

### 6.4 Follow-Up Agent — `suggest_followups` tool
**Responsibilities:** generate relevant follow-up questions · support exploratory analytics workflows.
The Follow-Up Agent runs its **own LLM** call over the original question and the returned data.

---

## 7. LangGraph Workflow

The application uses a state-driven **tool-calling agent** built with LangChain's `create_agent`. `create_agent` compiles the agent node, the prebuilt `ToolNode`, and the routing condition internally — there are **no hand-written workflow nodes**. `AnalyticsGraph` (`app/orchestration/graph.py`) assembles the four capability tools (§6) and returns the compiled graph.

### 7.1 Workflow State
The state is a `MessagesState` subclass (`WorkflowState`), so the message history and its reducer come for free; the analytics fields are added on top:

- `messages` (inherited from `MessagesState` — the ReAct conversation)
- `question`
- `generated_sql`
- `sql_explanation`
- `query_result`
- `chart_config`
- `insights`
- `followup_questions`
- `error_message`

Tools update these fields by returning a `Command`.

`WorkflowState` is an **in-process execution state** and is not required to be JSON-serializable. `query_result` is stored as a `pd.DataFrame` — keeping it as a DataFrame avoids a serialize/deserialize round-trip and lets the downstream visualization, insight, and follow-up tools work directly against the native Pandas API for efficient analytics processing.

### 7.2 Agent Loop & Tools

The supervisor runs the ReAct loop: **model → (tool calls?) → `ToolNode` → model → … → end**.

| Tool (provider) | Input (from state / args) | Output / Responsibility |
|---|---|---|
| `query_database` (SQL Agent) | User question | Generate SQL, validate read-only (`SELECT` only; blocks `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER`/`TRUNCATE`), execute, retry-correct on error → `Command{generated_sql, sql_explanation, query_result}` or an `error_message` |
| `generate_visualization` (Visualization Agent) | `query_result` (InjectedState) | Deterministic chart config → `Command{chart_config}` |
| `generate_insights` (Insight Agent) | `query_result` (InjectedState) | Data-grounded insights → `Command{insights}` |
| `suggest_followups` (Follow-Up Agent) | `question` + `query_result` (InjectedState) | Suggested follow-up questions → `Command{followup_questions}` |

### 7.3 Parallel Analytics
There is no dedicated Response node. After `query_database` succeeds, the supervisor emits `generate_visualization`, `generate_insights`, and `suggest_followups` **in a single turn**; the prebuilt `ToolNode` executes those tool calls **in parallel** and their `Command` updates merge into state. The Chat Service reads the final aggregated state and returns it to the API layer, which serves the Streamlit UI.

---

## 8. Agent Communication

Agent **outputs** are **structured Pydantic schemas**, written into typed workflow-state fields via `Command` — agents never pass unstructured text payloads to one another.

Structured schemas are used for:

- SQL generation output (`SQLGenerationOutput`)
- Visualization output (`ChartConfig`)
- Insight output (`InsightOutput`)
- Follow-up output (`FollowupOutput`)

The supervisor coordinates the agents over the LangGraph **messages channel** (the ReAct loop): it issues tool calls and receives short `ToolMessage` summaries. These summaries are control signals for the loop (e.g. "retrieved 12 rows: category, sales"), **not** data exchanged between agents — the actual data lives in the typed state fields above.

---

## 9. Layered Design

### 9.1 Repository Layer
**Responsibilities:** execute SQL queries · manage SQLAlchemy sessions · return structured query results.
Repositories shall not contain business logic.

### 9.2 Service Layer
**Responsibilities:** business logic · data transformation · validation · chart generation support · insight preparation · workflow support.
The domain services (`sql_service`, `visualization_service`, `insight_service`, `followup_service`) shall remain independent of LangGraph.

### 9.3 API Layer & Chat Service
The backend is exposed over HTTP with **FastAPI**; the Streamlit UI (`website/app.py`) is a client of this API and does not invoke the workflow in-process.

- **FastAPI routes (`app/routes/`)** — define HTTP endpoints (submit a question, return the analytics response, health check); validate payloads with the `app/schemas/` models (`requests`, `responses`); contain no business logic and delegate to the Chat Service. The ASGI app is assembled in `app/main.py` (served via Uvicorn: `uv run uvicorn app.main:app`).
- **Chat Service (`app/services/chat_service.py`)** — the application entry point the routes call; it bridges the API layer and the LangGraph workflow by invoking the graph with the user question and returning the aggregated response. It is the **single sanctioned component that runs the workflow**; the domain services (§9.2) stay LangGraph-independent.

---

## 10. Prompt Management

Each agent owns a dedicated prompt. Prompt files are stored under `app/prompts/`. Prompt text shall never be hardcoded inside agent implementations.

---

## 11. Configuration Management

Configuration is centralized under `app/config/`.

| Module | Responsibilities |
|---|---|
| `env_config.py` | Environment variable loading · application settings |
| `db_config.py` | SQLite configuration · SQLAlchemy engine creation · session management |
| `log_config.py` | Logging configuration · log formatting · log levels |
| `llm_config.py` | Model selection · temperature settings · token limits · LLM client initialization |

---

## 12. Database Initialization

On startup the bootstrap (`app/starter.py` → `create_app`) initializes SQLite:

1. Create the database (`data/superstore.db`)
2. Create tables from the SQLAlchemy models
3. Load `data/database.csv` into the normalized tables — **once**, only if the database is empty

The wide, denormalized Superstore CSV is split into `customers`, `products`, `orders`, and `order_items`. The initializer (`DatabaseInitializer`) resides under `app/utils/`.

---

## 13. Testing Strategy

| Level | Targets |
|---|---|
| **Unit Tests** | Agents · Services · Utilities |
| **Integration Tests** | LangGraph workflow · Database interactions · Agent communication |
| **End-to-End Tests** | Complete user workflows from natural-language query to final visualization and insights |

---

## 14. Development Environment

The project uses **uv** for Python package and virtual environment management.

**Responsibilities:** dependency management · virtual environment management · lock file generation (`uv.lock`) · reproducible builds.

Project metadata and dependencies are maintained in `pyproject.toml`. The active interpreter is pinned in `.python-version`. `requirements.txt` shall not be used as the primary dependency source.

---

## 15. Requirements Traceability

Mapping each `FRS.md` requirement to the design element that satisfies it.

| FRS Requirement | Design Element(s) |
|---|---|
| FR-1 — submit NL questions | Streamlit UI (`website/app.py`) → FastAPI route (`app/routes/`) → Chat Service (§9.3); workflow `question` state |
| FR-2 — generate SQL | SQL Agent (§6.1) via the `query_database` tool (§7.2) |
| FR-3 — validate SQL before execution | `query_database` tool validates read-only before executing; `app/utils/validators.py` |
| FR-4 — execute valid SQL | `query_database` tool (§7.2); Repository Layer (§9.1) |
| FR-5 — display data in table | Streamlit results table (`website/`); `query_result` state |
| FR-6 — select presentation by result shape | Visualization Agent (§6.2) via the `generate_visualization` tool (§7.2) |
| FR-7 — render charts | Visualization Agent + Plotly; `chart_config` state; `app/utils/chart_helpers.py` |
| FR-8 — single-value plain-language answer | Visualization Agent written-answer path (single 1×1 result → sentence) |
| FR-9 — actionable insights grounded in data | Insight Agent (§6.3) via the `generate_insights` tool (§7.2) |
| FR-10 — suggested follow-up questions | Follow-Up Agent (§6.4) via the `suggest_followups` tool (§7.2) |
| FR-11 — session query history | Streamlit UI generates a UUID4 `session_uuid` on first load (`st.session_state`) and includes it in every API request; `app/services/chat_service.py` holds an in-memory `dict[session_uuid → list[question]]` and appends each successfully answered question; history is never written to the database; response payload includes the session history list for the UI to render |
| FR-12 — export results as CSV | Streamlit download action (`website/`) over query result DataFrame |
| API transport (all FRs) | FastAPI routes (`app/routes/`) + Chat Service (`app/services/chat_service.py`) (§9.3) |
| Validation (FRS §9) — block non-read-only SQL | `query_database` tool + `app/utils/validators.py`; allows `SELECT` only |
| Error handling (FRS §10) | Workflow `error_message` state set inside the tools; `create_agent` ReAct loop ends when no further tool calls; surfaced via API + UI |
