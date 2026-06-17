# Technical Architecture

## 1. Architecture Overview

The Natural Language Analytics Dashboard shall use a layered architecture combined with a LangGraph-based multi-agent workflow.

The architecture separates:

* Presentation Layer
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

LangGraph Workflow

↓

Specialized Agents

↓

Services

↓

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
    └── technical_architecture.md
```

---

# 5. Multi-Agent Architecture

The application shall use specialized agents coordinated through LangGraph.

## SQL Agent

Responsibilities:

* Understand database schema
* Generate SQL
* Correct invalid SQL
* Explain generated SQL

Output:

* SQL query
* Query explanation

The SQL Agent is the only agent allowed to interact with the database.

---

## Visualization Agent

Responsibilities:

* Analyze query result structure
* Select visualization type
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

* Analyze returned data
* Identify trends
* Identify outliers
* Generate actionable business insights

All insights must be grounded in actual returned data.

No fabricated values or unsupported conclusions are permitted.

---

## Follow-Up Agent

Responsibilities:

* Generate relevant follow-up questions
* Support exploratory analytics workflows

---

# 6. LangGraph Workflow

The application shall use a state-driven workflow.

## Workflow State

The workflow state shall contain:

* question
* generated_sql
* query_result
* chart_config
* insights
* followup_questions
* error_message

---

## Workflow Nodes

### SQL Generation Node

Input:

* User Question

Output:

* Generated SQL

---

### SQL Validation Node

Validates generated SQL.

Allowed:

* SELECT

Blocked:

* INSERT
* UPDATE
* DELETE
* DROP
* ALTER
* TRUNCATE

---

### Query Execution Node

Responsibilities:

* Execute validated SQL
* Retrieve results
* Convert results into DataFrames

---

### Parallel Analytics Nodes

After successful query execution:

* Visualization Node
* Insight Node
* Follow-Up Node

shall execute in parallel.

---

### Response Node

Responsibilities:

* Aggregate outputs
* Build final response
* Return response to Streamlit UI

---

# 7. Agent Communication

Agents shall exchange structured Pydantic schemas.

No agent shall exchange unstructured text with another agent.

Structured schemas shall be used for:

* SQL generation output
* Visualization output
* Insight output
* Follow-up output

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

Services shall remain independent of LangGraph.

---

# 10. Prompt Management

Each agent owns a dedicated prompt.

Prompt files shall be stored under:

prompts/

Prompt text shall never be hardcoded inside agent implementations.

---

# 11. Configuration Management

Configuration shall be centralized under:

config/

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

The application shall automatically initialize SQLite on first startup.

Initialization process:

1. Create database
2. Create schema
3. Create tables
4. Generate sample data
5. Seed database

Database initialization utilities shall reside inside:

utils/

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
