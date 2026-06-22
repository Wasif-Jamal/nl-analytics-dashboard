# Technical Architecture

## 1. Architecture Overview

The Natural Language Analytics Dashboard shall use a layered architecture combined with a LangGraph supervisor that routes to specialized **agent subagents** (see §5–6 and the ADR in §16). Every agent is a `create_agent()` instance that manages its own internal tools; the supervisor invokes agents as whole units, not atomic tools.

The architecture separates:

* Presentation Layer
* API Layer
* Workflow Orchestration Layer
* Agent Layer
* Service Layer
* Repository Layer
* Persistence Layer

This separation improves maintainability, testability, scalability, and future extensibility.

---

# 2. Technology Stack

## Frontend

* Streamlit

## API Framework

* FastAPI (ASGI, served via Uvicorn)

## LLM Framework

* LangChain

## Workflow Orchestration

* LangGraph

## Database

* SQLite

## ORM

* SQLAlchemy

## Data Processing

* Pandas

## Visualization

* Plotly

## Validation

* Pydantic

---

# 3. High-Level Architecture

User

↓

Streamlit UI

↓

FastAPI (app/routes/)

↓

Chat Service

↓

create_agent Supervisor (ReAct loop)

↓

Agent Subagents (SQL Agent · Visualization Agent · Insight Agent · Follow-Up Agent)

↓ (SQL Agent only, via POST /api/query)

Repositories

↓

SQLite Database

---

# 4. Project Structure

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
    └── technical_architecture.md
```

---

# 5. Multi-Agent Architecture

The application shall use specialized agents, each invoked as a **subagent** by the supervisor. Every agent is a `create_agent()` instance with its own LLM, prompt, and internal tools. The supervisor does not call atomic tools directly — only subagents.

## SQL Agent

Responsibilities:

* Understand database schema
* Generate SQL (internal `generate_sql` tool)
* Validate SQL is read-only (internal `validate_sql` tool)
* Execute SQL via `POST /api/query` (internal `execute_sql` tool)
* Correct invalid SQL through a bounded retry loop driven by the agent's own LLM
* Explain generated SQL

Output: `generated_sql`, `sql_explanation`, `query_result` written to `WorkflowState`.

The SQL Agent is the only agent allowed to interact with the database (via `execute_sql` → `POST /api/query` → `QueryRouter` → `QueryRepository`).

---

## Visualization Agent

Responsibilities:

* Analyze query result structure (reads `query_result` from `WorkflowState`)
* Select visualization type using its own LLM and internal tools
* Generate chart configuration

Supported visualizations:

* Bar Chart
* Line Chart
* Pie Chart
* Scatter Plot
* Table

---

## Insight Agent

Responsibilities:

* Analyze returned data using its own data-grounded LLM and internal tools
* Identify trends
* Identify outliers
* Generate actionable business insights

All insights must be grounded in actual returned data. No fabricated values or unsupported conclusions are permitted.

---

## Follow-Up Agent

Responsibilities:

* Generate relevant follow-up questions using its own LLM and internal tools (operates over question + returned data)
* Support exploratory analytics workflows

---

# 6. LangGraph Workflow

The application uses a LangGraph supervisor that routes to agent subagents. `AnalyticsGraph` (`app/orchestration/graph.py`) builds the supervisor graph. Every agent is a `create_agent()` instance; agents are invoked as subagents, not individual tools.

## Workflow State

`WorkflowState` subclasses `MessagesState` (inheriting `messages` and its reducer) and adds:

* question
* generated_sql
* sql_explanation
* query_result
* chart_config
* insights
* followup_questions
* error_message

Tools update these fields by returning a `Command`.

---

## Agent Loop

The supervisor routes to agent subagents in sequence:

1. **SQL Agent** — internal tools `generate_sql` → `validate_sql` → `execute_sql` (→ `POST /api/query` → SQLite) with a bounded retry loop driven by the agent's own LLM. Sets `generated_sql` / `sql_explanation` / `query_result`, or an `error_message`.
2. If the SQL Agent succeeds, the supervisor invokes **Visualization Agent**, **Insight Agent**, and **Follow-Up Agent** in parallel; their `Command` updates merge into state.
3. When the supervisor has no further subagents to invoke, it ends. The Chat Service reads the final aggregated state and returns it to the API layer, which serves the Streamlit UI.

If the SQL Agent reports it could not answer (unidentifiable question, empty result, or DB error), the supervisor stops without invoking the analysis subagents.

---

# 7. Agent Communication

Agent **outputs** shall be structured Pydantic schemas, written to typed workflow-state fields via `Command`. No agent exchanges unstructured data with another agent.

Structured schemas shall be used for:

* SQL generation output (`SQLGenerationOutput`)
* Visualization output (`ChartConfig`)
* Insight output (`InsightOutput`)
* Follow-up output (`FollowupOutput`)

The supervisor coordinates the agents over the LangGraph messages channel (the ReAct loop). The `ToolMessage`s it receives are brief control summaries that drive routing — not data passed between agents; the data lives in the typed state fields above.

---

# 8. Repository Layer

Responsibilities:

* Execute SQL queries
* Manage SQLAlchemy sessions
* Return structured query results

Repositories shall not contain business logic.

---

# 9. Service Layer

Responsibilities:

* Business logic
* Data transformation
* Validation
* Chart generation support
* Insight preparation
* Workflow support

The domain services (`sql_service`, `visualization_service`, `insight_service`, `followup_service`) shall remain independent of LangGraph. The Chat Service (`app/services/chat_service.py`) is the exception — it is the single component that invokes the workflow; see §15.

---

# 10. Prompt Management

Each agent owns a dedicated prompt.

Prompt files shall be stored under:

app/prompts/

Prompt text shall never be hardcoded inside agent implementations.

---

# 11. Configuration Management

Configuration shall be centralized under:

app/config/

## env_config.py

Responsibilities:

* Environment variable loading
* Application settings

## db_config.py

Responsibilities:

* SQLite configuration
* SQLAlchemy engine creation
* Session management

## log_config.py

Responsibilities:

* Logging configuration
* Log formatting
* Log levels

## llm_config.py

Responsibilities:

* Model selection
* Temperature settings
* Token limits
* LLM client initialization

---

# 12. Database Initialization

The application shall initialize SQLite on startup via the bootstrap (`app/starter.py` → `create_app`).

Initialization process:

1. Create database (`data/superstore.db`)
2. Create tables from the SQLAlchemy models
3. Load `data/database.csv` into the normalized tables — once, only if the database is empty

The wide Superstore CSV is normalized into `customers`, `products`, `orders`, and `order_items`. The initializer (`DatabaseInitializer`) shall reside inside:

app/utils/

---

# 13. Testing Strategy

## Unit Tests

* Agents
* Services
* Utilities

## Integration Tests

* LangGraph workflow
* Database interactions
* Agent communication

## End-to-End Tests

Validate complete user workflows from natural language query to final visualization and insights.

# 14. Development Environment

The project shall use uv for Python package and virtual environment management.

Responsibilities:

- Dependency management
- Virtual environment management
- Lock file generation
- Reproducible builds

Project metadata and dependencies shall be maintained in pyproject.toml.

requirements.txt shall not be used as the primary dependency source.

---

# 15. API Layer and Chat Service

The application exposes an HTTP API built with **FastAPI**. The backend lives entirely under `app/`; the Streamlit UI under `website/` is a **client** of this API and does not invoke the workflow in-process.

## FastAPI Routes (`app/routes/`)

Responsibilities:

* Define the HTTP endpoints (routers) — submit a question, return the analytics response, health check.
* Validate request/response payloads using the Pydantic schemas in `app/schemas/` (`requests.py`, `responses.py`).
* Contain no business logic — routes delegate to the Chat Service.

The FastAPI ASGI application is assembled in `app/main.py` and served via Uvicorn (`uv run uvicorn app.main:app`).

## Chat Service (`app/services/chat_service.py`)

Responsibilities:

* Act as the application entry point that the API routes call.
* Bridge the API layer and the LangGraph workflow: invoke the workflow (graph) with the user question and return the aggregated response.

The domain services (`sql_service`, `visualization_service`, `insight_service`, `followup_service`) remain **independent of LangGraph**. The Chat Service is the single sanctioned component that runs the workflow.

## Request Flow

```text
User → Streamlit UI → FastAPI (routes/) → Chat Service → supervisor
     → agent subagents (SQL Agent · Visualization Agent · Insight Agent · Follow-Up Agent)
     → SQL Agent only: POST /api/query → Repositories → SQLite
```

---

# 16. ADR — Pivot to a tool-calling agent (2026-06-18)

**Status:** Superseded by ADR-2 below.

**Context.** The original design (§5–6 as first written) specified a hand-wired seven-node LangGraph pipeline (SQL generation → validation → execution → parallel visualization/insight/follow-up → response). LangChain 1.x ships `create_agent`, a supervisor harness that builds the agent node, the prebuilt `ToolNode`, and the routing condition for us, and runs a ReAct loop over tools.

**Decision.** Replace the node pipeline with a `create_agent` supervisor over four capability **tools**, one per specialized agent:

* **`query_database`** keeps the SQL Agent's own LLM and self-corrects invalid SQL through a bounded retry loop — leveraging the ReAct loop instead of a separate correction node.
* **`generate_insights`** / **`suggest_followups`** run each agent's own data-grounded LLM call (reading the result from state via `InjectedState`) — they *compute* results rather than storing supervisor-authored text, which strengthens the FR-9 anti-fabrication guarantee.
* **`generate_visualization`** is deterministic (result-shape → chart-type rules), so it needs no LLM.

State is a `MessagesState` subclass; tools return `Command` updates.

**Consequences.**
* Less orchestration code — no `nodes/` package or `conditional_edges`; `AnalyticsGraph` just assembles tools and calls `create_agent`.
* Parallel analytics is preserved: the supervisor emits the three analysis tools in one turn and `ToolNode` runs them in parallel.
* SQL self-correction is a natural product of the loop.
* Functional behavior (FR-1…FR-12), the read-only rule (FRS §9), and the standard error messages (FRS §10) are unchanged — this is a "how", not a "what".

---

# 17. ADR-2 — Pivot to supervisor-over-subagents (2026-06-22)

**Status:** Accepted.

**Context.** ADR-1 (§16) introduced a flat `create_agent` supervisor with four atomic tools (`query_database`, `generate_visualization`, `generate_insights`, `suggest_followups`). Two problems emerged: (1) the SQL Agent's retry logic was hidden inside a nested inner `create_agent`, creating two invisible ReAct loops with no observable nodes; (2) all agents except SQL Agent had no LLM of their own — the Visualization Agent was deterministic, which limited its adaptability.

**Decision.** Pivot to a **supervisor-over-subagents** architecture:

* Every agent (`SqlAgent`, `VisualizationAgent`, `InsightAgent`, `FollowupAgent`) is a `create_agent()` instance with its own LLM, prompt, and internal tools. The supervisor does not call atomic tools directly.
* The SQL Agent's internal tools are `generate_sql`, `validate_sql`, and `execute_sql` (which calls `POST /api/query`). The agent's own LLM drives the generate → validate → execute → retry loop.
* The Visualization Agent is promoted from a deterministic function to a full `create_agent()` instance with its own LLM and internal tools — no longer hard-coded chart-type rules.
* Each analysis agent (Visualization, Insight, Follow-up) is invoked in parallel by the supervisor after the SQL Agent succeeds.
* SQL execution is decoupled via HTTP: `execute_sql` calls `POST /api/query` (a FastAPI endpoint backed by `QueryService`), eliminating direct agent → repository coupling.

**Consequences.**
* Each agent's logic is explicit, testable, and independently evolvable.
* Visualization Agent gains LLM-driven adaptability — chart selection is no longer purely rule-based.
* SQL retry logic is visible (named tools, observable in traces) rather than a hidden inner loop.
* The `POST /api/query` endpoint introduces one HTTP hop for SQL execution but enables clean separation between the agent layer and the data layer.
* Functional behavior (FR-1…FR-12), the read-only rule (FRS §9), and the standard error messages (FRS §10) are unchanged.
