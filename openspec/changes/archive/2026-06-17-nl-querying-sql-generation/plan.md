# Plan: nl-querying-sql-generation

## Context

Implements FR-1 + FR-2 (issue #1): accept a plain-English question, call a Gemini LLM, and
return a structured SQL generation output (query + explanation + identifiability flag) via a
LangGraph-compatible `SqlGenerationNode`. The data layer from PR #11 is the foundation; this
change adds the intelligence layer on top.

**No DB changes.** No routes. No Chat Service. No graph assembly. Those are issues #2–#10.

---

## Existing Patterns to Reuse

| Pattern | Where It Exists | How Reused |
|---|---|---|
| Constructor injection via kwargs | `QueryRepository(db_engine=engine)` | `SqlAgent(llm=llm)`, `SqlGenerationNode(agent=agent)` |
| Module-level singleton | `engine` in `db_config.py` | `_config = LlmConfig()` in `llm_config.py` |
| `get_logger(__name__)` | All config/repo modules | Same pattern in every new module |
| `SettingsConfigDict` settings | `env_config.py` | Extend `Settings` with two new fields |
| `tmp_path`-isolated fixtures | `conftest.py` | `MagicMock`-based fixtures for LLM in new tests |
| Standalone test functions | All existing tests | Same style for agent/node tests |

---

## Architecture Decisions

| Decision | Choice | Reason |
|---|---|---|
| LLM invocation style | `llm.with_structured_output(SQLGenerationOutput)` | Returns a validated `SQLGenerationOutput` directly; no JSON parsing in agent code |
| Message construction | `[SystemMessage(SQL_SYSTEM_PROMPT), HumanMessage(question)]` | Standard LangChain pattern; separates role from user input |
| Unknown-entity signal | `is_identifiable: bool = True` field on `SQLGenerationOutput` | Cleaner than exceptions for a predictable, expected LLM response path |
| `WorkflowState` scope | Minimal (4 fields only) | Avoids premature design; each issue adds its own fields |
| Prompt location | `app/prompts/sql_prompt.py` module-level constant | AGENTS.md rule: never hardcode prompt text in agent code |
| `LlmConfig` as a class | Class + module-level `get_llm()` wrapper | Matches OOP rule in CLAUDE.md; class is injectable in tests |

---

## Phase 1 — Config & LLM

### `app/config/env_config.py` (modify)

Add two fields to `Settings`. Update docstring.

```python
# Add to Settings docstring:
#   llm_model: Gemini model identifier (default ``gemini-2.0-flash``).
#   llm_temperature: Sampling temperature for the LLM (default 0.0 for determinism).

llm_model: str = "gemini-2.0-flash"
llm_temperature: float = 0.0
```

### `app/config/llm_config.py` (create)

```python
"""LLM client initialization for the Gemini provider."""

from langchain_google_genai import ChatGoogleGenerativeAI
from app.config.env_config import settings
from app.config.log_config import get_logger

logger = get_logger(__name__)


class LlmConfig:
    """Factory for the application LLM client."""

    def get_llm(self) -> ChatGoogleGenerativeAI:
        """Return a configured ChatGoogleGenerativeAI instance."""
        logger.info("Initializing LLM: model=%s temperature=%s",
                    settings.llm_model, settings.llm_temperature)
        return ChatGoogleGenerativeAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            google_api_key=settings.google_api_key,
        )


_config = LlmConfig()


def get_llm() -> ChatGoogleGenerativeAI:
    """Return a configured LLM instance (module-level convenience wrapper)."""
    return _config.get_llm()
```

**Quality gate after Phase 1:**
```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

---

## Phase 2 — Prompt

### `app/prompts/sql_prompt.py` (create)

Module-level string constant `SQL_SYSTEM_PROMPT`. Structure:

```
Role:
  You are an expert SQL analyst. Generate read-only SQLite SELECT queries for
  the Superstore database. Return a JSON object with fields:
  - sql: the SELECT query (empty string if unable to identify entities)
  - explanation: plain-English description of the query or why it failed
  - is_identifiable: true if schema entities were matched, false otherwise

Schema:
  Table: customers
    customer_id   TEXT  PRIMARY KEY
    customer_name TEXT  NOT NULL
    segment       TEXT  NOT NULL  -- values: Consumer, Corporate, Home Office

  Table: products
    product_id    TEXT  PRIMARY KEY
    category      TEXT  NOT NULL  -- values: Furniture, Office Supplies, Technology
    sub_category  TEXT  NOT NULL
    product_name  TEXT  NOT NULL

  Table: orders
    order_id      TEXT  PRIMARY KEY
    order_date    DATE  NOT NULL
    ship_date     DATE  NOT NULL
    ship_mode     TEXT  NOT NULL
    customer_id   TEXT  REFERENCES customers(customer_id)
    country       TEXT  NOT NULL
    city          TEXT  NOT NULL
    state         TEXT  NOT NULL
    postal_code   TEXT  NOT NULL
    region        TEXT  NOT NULL  -- values: East, West, Central, South

  Table: order_items
    row_id        INTEGER  PRIMARY KEY
    order_id      TEXT     REFERENCES orders(order_id)
    product_id    TEXT     REFERENCES products(product_id)
    sales         REAL     NOT NULL
    quantity      INTEGER  NOT NULL
    discount      REAL     NOT NULL
    profit        REAL     NOT NULL

Rules:
  - Write SELECT statements only. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE.
  - Use valid SQLite syntax.
  - Do not include SQL comments in the output.
  - If the question references entities not in this schema, return
    is_identifiable=false, sql="", and explain why in the explanation field.

Examples:
  Question: "Show total sales by region"
  → sql: "SELECT o.region, ROUND(SUM(oi.sales), 2) AS total_sales
           FROM order_items oi JOIN orders o ON oi.order_id = o.order_id
           GROUP BY o.region ORDER BY total_sales DESC"
  → explanation: "Joins order_items with orders and groups by region to sum sales."
  → is_identifiable: true

  Question: "Top 10 products by revenue"
  → sql: "SELECT p.product_name, ROUND(SUM(oi.sales), 2) AS revenue
           FROM order_items oi JOIN products p ON oi.product_id = p.product_id
           GROUP BY p.product_id ORDER BY revenue DESC LIMIT 10"
  → explanation: "Groups order_items by product and sums sales, returning top 10."
  → is_identifiable: true

  Question: "Show dragon sales by galaxy"
  → sql: ""
  → explanation: "The question references 'dragon' and 'galaxy' which are not entities in the schema."
  → is_identifiable: false
```

**Quality gate after Phase 2:**
```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

---

## Phase 3 — Schemas

### `app/schemas/sql_result.py` (create)

```python
"""Pydantic contract for SQL generation output.

Exchanged between SqlAgent and SqlGenerationNode. Agents communicate
via typed schemas only — never unstructured text (AGENTS.md §8).
"""
from pydantic import BaseModel


class SQLGenerationOutput(BaseModel):
    """Structured output from the SQL generation LLM call."""

    sql: str
    """The generated SELECT statement; empty string when is_identifiable=False."""

    explanation: str
    """Plain-English description of the query, or reason for failure."""

    is_identifiable: bool = True
    """False when the question references entities not in the schema."""
```

### `app/schemas/workflow_state.py` (create)

```python
"""Workflow state contract for the LangGraph pipeline.

Defines the minimal TypedDict for issue #1 (SQL generation).
Later issues extend this with their own fields.
"""
from typing import Optional
from typing_extensions import TypedDict


class WorkflowState(TypedDict):
    """State passed between LangGraph nodes."""

    question: str
    generated_sql: str
    sql_explanation: str
    error_message: Optional[str]


def initial_state(question: str) -> WorkflowState:
    """Return a fresh WorkflowState for a new question."""
    return WorkflowState(
        question=question,
        generated_sql="",
        sql_explanation="",
        error_message=None,
    )
```

### `app/schemas/__init__.py` (update)

Export `SQLGenerationOutput`, `WorkflowState`, `initial_state`.

**Quality gate after Phase 3:**
```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

---

## Phase 4 — Orchestration State Shim

### `app/orchestration/state.py` (create)

```python
"""Re-exports WorkflowState and initial_state for orchestration imports."""
from app.schemas.workflow_state import WorkflowState, initial_state

__all__ = ["WorkflowState", "initial_state"]
```

### `app/orchestration/__init__.py` (update)

Export `WorkflowState`, `initial_state`.

**Quality gate after Phase 4:**
```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

---

## Phase 5 — SQL Agent

### `app/agents/sql_agent.py` (create)

```python
"""SQL generation agent.

Translates a natural-language question into a SQL query using the Gemini LLM
with structured output. Returns a typed SQLGenerationOutput; never executes SQL.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.config.llm_config import get_llm
from app.config.log_config import get_logger
from app.prompts.sql_prompt import SQL_SYSTEM_PROMPT
from app.schemas.sql_result import SQLGenerationOutput

logger = get_logger(__name__)


class SqlAgent:
    """Generates SQL from a natural-language question via the LLM."""

    def __init__(self, llm=None) -> None:
        """Inject the LLM client; defaults to the shared app LLM."""
        self._llm = llm or get_llm()

    def generate(self, question: str) -> SQLGenerationOutput:
        """Translate a NL question to a SQLGenerationOutput.

        Args:
            question: The plain-English question from the user.

        Returns:
            A SQLGenerationOutput with sql, explanation, and is_identifiable.
        """
        logger.info("Generating SQL for question: %s", question)
        structured = self._llm.with_structured_output(SQLGenerationOutput)
        result: SQLGenerationOutput = structured.invoke(
            [SystemMessage(content=SQL_SYSTEM_PROMPT), HumanMessage(content=question)]
        )
        logger.info("SQL generation complete: is_identifiable=%s", result.is_identifiable)
        return result
```

### `app/agents/__init__.py` (update)

Export `SqlAgent`.

### `app/prompts/__init__.py` (update)

Export `SQL_SYSTEM_PROMPT`.

### `tests/agents/test_sql_agent.py` (create — write before/alongside implementation)

```python
"""Tests for app.agents.sql_agent.SqlAgent."""
from unittest.mock import MagicMock

from app.agents.sql_agent import SqlAgent
from app.schemas.sql_result import SQLGenerationOutput


def _make_agent(output: SQLGenerationOutput) -> SqlAgent:
    """Return a SqlAgent whose LLM is mocked to return output."""
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.invoke.return_value = output
    return SqlAgent(llm=mock_llm)


def test_generate_returns_sql_generation_output():
    """generate() returns a SQLGenerationOutput on a valid question."""
    expected = SQLGenerationOutput(
        sql="SELECT region FROM orders",
        explanation="Returns all regions.",
        is_identifiable=True,
    )
    agent = _make_agent(expected)
    result = agent.generate("Show all regions")
    assert isinstance(result, SQLGenerationOutput)
    assert result.sql == "SELECT region FROM orders"
    assert result.is_identifiable is True


def test_generate_unidentifiable_question():
    """generate() propagates is_identifiable=False from the LLM."""
    expected = SQLGenerationOutput(
        sql="", explanation="Unknown entities.", is_identifiable=False
    )
    agent = _make_agent(expected)
    result = agent.generate("Show dragon sales by galaxy")
    assert result.is_identifiable is False
    assert result.sql == ""
```

**Quality gate after Phase 5:**
```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

---

## Phase 6 — SQL Generation Node

### `app/orchestration/nodes/sql_generation_node.py` (create)

```python
"""LangGraph node: translate a NL question to SQL."""
from app.agents.sql_agent import SqlAgent
from app.config.log_config import get_logger
from app.orchestration.state import WorkflowState

logger = get_logger(__name__)

_ENTITY_ERROR = "Unable to identify requested entities."


class SqlGenerationNode:
    """LangGraph node that calls SqlAgent and writes SQL into workflow state."""

    def __init__(self, agent: SqlAgent | None = None) -> None:
        """Inject the SQL agent; defaults to SqlAgent()."""
        self._agent = agent or SqlAgent()

    def __call__(self, state: WorkflowState) -> WorkflowState:
        """Generate SQL for state["question"] and return updated state.

        Sets generated_sql + sql_explanation on success.
        Sets error_message on is_identifiable=False or any exception.
        """
        try:
            output = self._agent.generate(state["question"])
            if not output.is_identifiable:
                logger.warning("Question not identifiable: %s", state["question"])
                return {**state, "error_message": _ENTITY_ERROR}
            return {
                **state,
                "generated_sql": output.sql,
                "sql_explanation": output.explanation,
            }
        except Exception:
            logger.exception("SQL generation failed for question: %s", state["question"])
            return {**state, "error_message": _ENTITY_ERROR}
```

### `app/orchestration/nodes/__init__.py` (update)

Export `SqlGenerationNode`.

### `tests/orchestration/__init__.py` (create)

Empty package marker.

### `tests/orchestration/test_sql_generation_node.py` (create)

```python
"""Tests for app.orchestration.nodes.sql_generation_node.SqlGenerationNode."""
from unittest.mock import MagicMock

from app.orchestration.nodes.sql_generation_node import SqlGenerationNode
from app.schemas.sql_result import SQLGenerationOutput
from app.schemas.workflow_state import initial_state


def _make_node(output: SQLGenerationOutput | Exception) -> SqlGenerationNode:
    mock_agent = MagicMock()
    if isinstance(output, Exception):
        mock_agent.generate.side_effect = output
    else:
        mock_agent.generate.return_value = output
    return SqlGenerationNode(agent=mock_agent)


def test_node_success_sets_sql_and_explanation():
    """On success, node writes generated_sql and sql_explanation into state."""
    node = _make_node(SQLGenerationOutput(
        sql="SELECT * FROM orders",
        explanation="Returns all orders.",
        is_identifiable=True,
    ))
    result = node(initial_state("Show all orders"))
    assert result["generated_sql"] == "SELECT * FROM orders"
    assert result["sql_explanation"] == "Returns all orders."
    assert result["error_message"] is None


def test_node_unidentifiable_sets_error_message():
    """When is_identifiable=False, node sets error_message and leaves sql empty."""
    node = _make_node(SQLGenerationOutput(
        sql="", explanation="Unknown entities.", is_identifiable=False
    ))
    result = node(initial_state("Show dragon sales by galaxy"))
    assert result["error_message"] == "Unable to identify requested entities."
    assert result["generated_sql"] == ""


def test_node_exception_sets_error_message():
    """When the agent raises, node sets error_message and does not re-raise."""
    node = _make_node(RuntimeError("LLM quota exceeded"))
    result = node(initial_state("Show sales"))
    assert result["error_message"] == "Unable to identify requested entities."
```

**Final quality gate:**
```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

---

## Summary: Files Touched

| File | Action |
|---|---|
| `app/config/env_config.py` | modify — +2 settings fields |
| `app/config/llm_config.py` | create |
| `app/prompts/sql_prompt.py` | create |
| `app/schemas/sql_result.py` | create |
| `app/schemas/workflow_state.py` | create |
| `app/schemas/__init__.py` | update — exports |
| `app/orchestration/state.py` | create |
| `app/orchestration/__init__.py` | update — exports |
| `app/agents/sql_agent.py` | create |
| `app/agents/__init__.py` | update — exports |
| `app/prompts/__init__.py` | update — exports |
| `app/orchestration/nodes/sql_generation_node.py` | create |
| `app/orchestration/nodes/__init__.py` | update — exports |
| `tests/agents/test_sql_agent.py` | create |
| `tests/orchestration/__init__.py` | create |
| `tests/orchestration/test_sql_generation_node.py` | create |

**No DB changes.** `WorkflowState` is a TypedDict, not a SQLAlchemy model.
