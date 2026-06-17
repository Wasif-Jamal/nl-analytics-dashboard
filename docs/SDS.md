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
The design covers the layered application structure, the LangGraph-based multi-agent workflow, the technology stack, inter-component contracts, configuration, database initialization, and the testing strategy. Section 14 traces each functional requirement to the component that satisfies it.

### 1.3 Relationship to FRS
This SDS is the design counterpart to `FRS.md`. Every requirement register entry (FR-1…FR-12), the validation rules (FRS §9), and the error-handling rules (FRS §10) map to one or more design elements defined here; see §14.

---

## 2. Architecture Overview

The system uses a **layered architecture** combined with a **LangGraph-based multi-agent workflow**. The architecture separates:

- Presentation Layer
- Workflow Orchestration Layer
- Agent Layer
- Service Layer
- Repository Layer
- Persistence Layer

This separation improves maintainability, testability, scalability, and future extensibility.

---

## 3. Technology Stack

| Concern | Technology |
|---|---|
| Frontend | Streamlit |
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
LangGraph Workflow
  ↓
Specialized Agents
  ↓
Services
  ↓
Repositories
  ↓
SQLite Database
```

---

## 5. Project Structure

```text
nl-analytics-dashboard/
│
├── pyproject.toml
├── uv.lock
├── .python-version
├── starter.py
├── app.py
│
├── .env
├── .env.example
│
├── config/
│   ├── env_config.py
│   ├── db_config.py
│   ├── log_config.py
│   └── llm_config.py
│
├── agents/
│   ├── sql_agent.py
│   ├── visualization_agent.py
│   ├── insight_agent.py
│   └── followup_agent.py
│
├── prompts/
│   ├── sql_prompt.py
│   ├── visualization_prompt.py
│   ├── insight_prompt.py
│   └── followup_prompt.py
│
├── orchestration/
│   ├── graph.py
│   ├── state.py
│   ├── conditional_edges.py
│   │
│   └── nodes/
│       ├── sql_generation_node.py
│       ├── sql_validation_node.py
│       ├── query_execution_node.py
│       ├── visualization_node.py
│       ├── insight_node.py
│       ├── followup_node.py
│       └── response_node.py
│
├── services/
│   ├── analytics_service.py
│   ├── sql_service.py
│   ├── visualization_service.py
│   ├── insight_service.py
│   └── followup_service.py
│
├── repositories/
│   └── query_repository.py
│
├── models/
│   ├── customer.py
│   ├── product.py
│   ├── order.py
│   └── order_item.py
│
├── schemas/
│   ├── requests.py
│   ├── responses.py
│   ├── sql_result.py
│   ├── chart_config.py
│   └── workflow_state.py
│
├── utils/
│   ├── validators.py
│   ├── sql_helpers.py
│   ├── chart_helpers.py
│   ├── database_initializer.py
│   ├── sample_data_generator.py
│   └── seed_generator.py
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

The application uses specialized agents coordinated through LangGraph.

### 6.1 SQL Agent
**Responsibilities:** understand database schema · generate SQL · correct invalid SQL · explain generated SQL.
**Output:** SQL query · query explanation.
The SQL Agent is the **only** agent allowed to interact with the database.

### 6.2 Visualization Agent
**Responsibilities:** analyze query result structure · select visualization type · generate chart configuration.
**Supported visualizations:** Bar Chart · Line Chart · Pie Chart · Scatter Plot · Table.

### 6.3 Insight Agent
**Responsibilities:** analyze returned data · identify trends · identify outliers · generate actionable business insights.
All insights must be grounded in actual returned data. No fabricated values or unsupported conclusions are permitted.

### 6.4 Follow-Up Agent
**Responsibilities:** generate relevant follow-up questions · support exploratory analytics workflows.

---

## 7. LangGraph Workflow

The application uses a state-driven workflow.

### 7.1 Workflow State
The workflow state contains:

- `question`
- `generated_sql`
- `query_result`
- `chart_config`
- `insights`
- `followup_questions`
- `error_message`

### 7.2 Workflow Nodes

| Node | Input | Output / Responsibility |
|---|---|---|
| **SQL Generation Node** | User question | Generated SQL |
| **SQL Validation Node** | Generated SQL | Validates SQL — allows `SELECT`; blocks `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE` |
| **Query Execution Node** | Validated SQL | Executes SQL, retrieves results, converts results into DataFrames |
| **Visualization Node** | Query result | Chart configuration (runs in parallel) |
| **Insight Node** | Query result | Insights grounded in data (runs in parallel) |
| **Follow-Up Node** | Query result | Suggested follow-up questions (runs in parallel) |
| **Response Node** | All prior outputs | Aggregates outputs, builds final response, returns response to Streamlit UI |

### 7.3 Parallel Analytics
After successful query execution, the **Visualization Node**, **Insight Node**, and **Follow-Up Node** execute in **parallel**. The **Response Node** aggregates their outputs into the final response.

---

## 8. Agent Communication

Agents exchange **structured Pydantic schemas**. No agent exchanges unstructured text with another agent.

Structured schemas are used for:

- SQL generation output
- Visualization output
- Insight output
- Follow-up output

---

## 9. Layered Design

### 9.1 Repository Layer
**Responsibilities:** execute SQL queries · manage SQLAlchemy sessions · return structured query results.
Repositories shall not contain business logic.

### 9.2 Service Layer
**Responsibilities:** business logic · data transformation · validation · chart generation support · insight preparation · workflow support.
Services shall remain independent of LangGraph.

---

## 10. Prompt Management

Each agent owns a dedicated prompt. Prompt files are stored under `prompts/`. Prompt text shall never be hardcoded inside agent implementations.

---

## 11. Configuration Management

Configuration is centralized under `config/`.

| Module | Responsibilities |
|---|---|
| `env_config.py` | Environment variable loading · application settings |
| `db_config.py` | SQLite configuration · SQLAlchemy engine creation · session management |
| `log_config.py` | Logging configuration · log formatting · log levels |
| `llm_config.py` | Model selection · temperature settings · token limits · LLM client initialization |

---

## 12. Database Initialization

The application automatically initializes SQLite on first startup:

1. Create database
2. Create schema
3. Create tables
4. Generate sample data
5. Seed database

Database initialization utilities reside under `utils/`.

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
| FR-1 — submit NL questions | Streamlit UI (Question Input, Execute Button); workflow `question` state |
| FR-2 — generate SQL | SQL Agent (§6.1); SQL Generation Node (§7.2) |
| FR-3 — validate SQL before execution | SQL Validation Node (§7.2); `utils/validators.py` |
| FR-4 — execute valid SQL | Query Execution Node (§7.2); Repository Layer (§9.1) |
| FR-5 — display data in table | Streamlit Results Table; Response Node aggregation |
| FR-6 — select presentation by result shape | Visualization Agent (§6.2); Visualization Node (§7.2) |
| FR-7 — render charts | Visualization Agent + Plotly; `chart_config` state; `utils/chart_helpers.py` |
| FR-8 — single-value plain-language answer | Visualization Agent / Response Node written-answer path |
| FR-9 — actionable insights grounded in data | Insight Agent (§6.3); Insight Node (§7.2) |
| FR-10 — suggested follow-up questions | Follow-Up Agent (§6.4); Follow-Up Node (§7.2) |
| FR-11 — session query history | Streamlit session state (Query History Panel); `query_repository.py` |
| FR-12 — export results as CSV | Streamlit download action over query result DataFrame |
| Validation (FRS §9) — block non-read-only SQL | SQL Validation Node (§7.2); allows `SELECT` only |
| Error handling (FRS §10) | Workflow `error_message` state; conditional edges (`orchestration/conditional_edges.py`); Response Node |
