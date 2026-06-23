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

The Workflow Orchestration Layer uses a **supervisor-over-subagents** pattern:

- **Supervisor** — routes to agent subagents (SQL Agent first, then Visualization Agent, Insight Agent, and Follow-up Agent in parallel after the SQL Agent succeeds). The supervisor does not call atomic tools directly.
- **Agent subagents** — every agent (`SqlAgent`, `VisualizationAgent`, `InsightAgent`, `FollowupAgent`) is a `create_agent()` instance with its own LLM, prompt, and internal tools. Internal tools are invisible to the supervisor; each agent's LLM drives its own tool-calling loop.

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
Supervisor
  ↓
Agent Subagents (SQL Agent · Visualization Agent · Insight Agent · Follow-Up Agent)
  ↓                    ↓ (SQL Agent only, via POST /api/query)
  ↓               Repositories → SQLite Database
  ↓
WorkflowState (aggregated results)
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
│   │   ├── query_routes.py
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
│   │   ├── orchestrator_prompt.py   # supervisor prompt
│   │   ├── visualization_prompt.py
│   │   ├── insight_prompt.py
│   │   └── followup_prompt.py
│   │
│   ├── orchestration/
│   │   ├── graph.py               # AnalyticsGraph — builds supervisor that routes to agent subagents
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

The application uses specialized agents that are each invoked as a subgraph node by the outer `StateGraph`. Every agent is a `create_agent()` instance that manages its own internal tools and returns a typed `Command` updating the shared workflow state (§7.1). The outer graph never serializes the full dataset back into a subagent call — analysis agents receive the prior state fields they need when the supervisor routes to them.

### 6.1 SQL Agent
**Responsibilities:** understand database schema · generate SQL · validate SQL · execute SQL · correct invalid SQL · explain generated SQL.
**Output:** `generated_sql`, `sql_explanation`, `query_result` written to `WorkflowState`.

The SQL Agent is a `create_agent()` instance. Its internal tools are:

| Tool | Responsibility |
|---|---|
| `generate_sql` | LLM call that produces `SQLGenerationOutput` (sql, explanation, is_identifiable). On retries, includes the previous SQL and error type as context. |
| `validate_sql` | Validates SQL is read-only (`app/utils/validators.py`) — allows `SELECT` only; blocks `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER`/`TRUNCATE`. |
| `execute_sql` | Calls `POST /api/query` via `httpx`. Returns rows as a `QueryResult`. On failure, signals an error type for retry. |

The agent's internal LLM decides which tools to call and drives the generate → validate → execute → retry loop. The SQL Agent is the **only** agent allowed to interact with the database (via `execute_sql` → `POST /api/query` → `QueryRouter` → `QueryService` → `QueryRepository`).

### 6.2 Visualization Agent
**Responsibilities:** analyze query result structure · select visualization type · generate chart configuration.
**Supported visualizations:** Bar Chart · Line Chart · Pie Chart · Scatter Plot · Table.
The Visualization Agent is a `create_agent()` instance with its own LLM and internal tools. It reads `query_result` from `WorkflowState` and produces a `ChartConfig`.

### 6.3 Insight Agent
**Responsibilities:** analyze returned data · identify trends · identify outliers · generate actionable business insights.
The Insight Agent is a `create_agent()` instance. Its LLM call is data-grounded: all insights must be derived from the actual rows in `query_result`. No fabricated values or unsupported conclusions are permitted.

### 6.4 Follow-Up Agent
**Responsibilities:** generate relevant follow-up questions · support exploratory analytics workflows.
The Follow-Up Agent is a `create_agent()` instance whose LLM call operates over the original question and the returned data.

---

## 7. LangGraph Workflow

The application uses two layers of LangGraph:

**Supervisor layer:** `AnalyticsGraph` (`app/orchestration/graph.py`) builds the supervisor graph, which routes to the four agent subagents. The supervisor itself does not call atomic tools — only subagents.

**Agent layer:** Every agent (`SqlAgent`, `VisualizationAgent`, `InsightAgent`, `FollowupAgent`) is a `create_agent()` instance built with its own LLM, internal tools, prompt, and private state schema. Internal tools are invisible to the supervisor; each agent decides which tools to call based on its own LLM.

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

### 7.2 Agent Subagents

The supervisor routes to agent subagents. Each subagent is a `create_agent()` instance that manages its own internal tools.

| Subagent | Input (from WorkflowState) | Output / Responsibility |
|---|---|---|
| SQL Agent (§6.1) | User question | Internal tools: `generate_sql` → `validate_sql` → `execute_sql` (POST /api/query → SQLite) → conditional retry. Returns `Command{generated_sql, sql_explanation, query_result}` or sets `error_message`. |
| Visualization Agent (§6.2) | `query_result` | LLM-driven chart config → `Command{chart_config}` |
| Insight Agent (§6.3) | `query_result` | Data-grounded insights → `Command{insights}` |
| Follow-Up Agent (§6.4) | `question` + `query_result` | Suggested follow-up questions → `Command{followup_questions}` |

### 7.3 Parallel Analytics
There is no dedicated Response node. After the SQL Agent succeeds, the supervisor invokes the Visualization Agent, Insight Agent, and Follow-Up Agent **in parallel**; their `Command` updates merge into state. The Chat Service reads the final aggregated state and returns it to the API layer, which serves the Streamlit UI.

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

- **FastAPI routes (`app/routes/`)** — define HTTP endpoints (submit a question, execute SQL, return the analytics response, health check); validate payloads with the `app/schemas/` models (`requests`, `responses`); contain no business logic and delegate to services. The ASGI app is assembled in `app/main.py` (served via Uvicorn: `uv run uvicorn app.main:app`). `query_routes.py` exposes `POST /api/query` which the SQL Agent calls via `httpx` to execute validated SQL (§6.1).
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
| FR-2 — generate SQL | SQL Agent (§6.1) `generate_sql` internal tool (§7.2) |
| FR-3 — validate SQL before execution | SQL Agent `validate_sql` internal tool + `QueryRouter.execute_query` both call `app/utils/validators.py` (defense-in-depth) |
| FR-4 — execute valid SQL | SQL Agent `execute_sql` internal tool calls `POST /api/query`; `QueryRouter` → `QueryService` → `QueryRepository` (§9.1) |
| FR-5 — display data in table | Streamlit `st.dataframe(width="stretch", height=400)` in `website/app.py`; virtual scrolling satisfies FRS §6.6 pagination intent; native column-header sort; `query_result` state |
| FR-6 — select presentation by result shape | Visualization Agent (§6.2) subagent (§7.2) |
| FR-7 — render charts | Visualization Agent + Plotly; `chart_config` state; `app/utils/chart_helpers.py` |
| FR-8 — single-value plain-language answer | Visualization Agent written-answer path (single 1×1 result → sentence) |
| FR-9 — actionable insights grounded in data | Insight Agent (§6.3) subagent (§7.2) |
| FR-10 — suggested follow-up questions | Follow-Up Agent (§6.4) subagent (§7.2) |
| FR-11 — session query history | Streamlit UI generates a UUID4 `session_uuid` on first load (`st.session_state`) and includes it in every API request; `app/services/chat_service.py` holds an in-memory `dict[session_uuid → list[question]]` and appends each successfully answered question; history is never written to the database; response payload includes the session history list for the UI to render |
| FR-12 — export results as CSV | `st.download_button` in `website/app.py` multi-row path; exports `query_results_<timestamp>.csv` (UTF-8, no row index); absent for single-scalar (1×1) metric path |
| API transport (all FRs) | FastAPI routes (`app/routes/`) + Chat Service (`app/services/chat_service.py`) (§9.3) |
| Validation (FRS §9) — block non-read-only SQL | SQL Agent `validate_sql` internal tool + `app/utils/validators.py`; allows `SELECT` only |
| Error handling (FRS §10) | Workflow `error_message` state set inside subagents; supervisor stops invoking further subagents on error; surfaced via API + UI |
