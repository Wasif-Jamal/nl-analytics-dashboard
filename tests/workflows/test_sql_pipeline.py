"""Integration tests for the SQL pipeline against a real SQLite database.

These exercise the *real* validation → QueryService → QueryRepository → SQLite
path using the ``initialized_engine`` fixture. Only the LLM's decisions (which
SQL to attempt, whether the question is identifiable) are scripted via a fake
inner agent; everything downstream of that is real. This is the boundary that
lets us test end-to-end behaviour without network access.

Covers spec scenarios across natural-language-to-sql, read-only-validation,
sql-self-correction-retry, sql-execution, and tool-message-summary.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy import Engine

from app.agents.sql_agent import SqlAgent
from app.repositories.query_repository import QueryRepository
from app.schemas.sql_result import SQLGenerationOutput
from app.services.sql_service import QueryService

_REVENUE_SQL = (
    "SELECT o.region, ROUND(SUM(oi.sales), 2) AS revenue "
    "FROM order_items oi JOIN orders o ON oi.order_id = o.order_id "
    "GROUP BY o.region"
)


class _ScriptedInnerAgent:
    """Fake inner create_agent: runs the real inner tool for each scripted SQL.

    Simulates the autonomous SQL agent's tool-calling loop deterministically —
    each scripted SQL is actually validated and executed against the database —
    then returns the final state dict with the supplied structured response.
    """

    def __init__(self, inner_tool, sqls, structured):
        self._inner_tool = inner_tool
        self._sqls = sqls
        self._structured = structured

    def invoke(self, _input, config=None):
        state = {"structured_response": self._structured}
        for sql in self._sqls:
            command = self._inner_tool.func(sql=sql, tool_call_id="inner")
            state.update(command.update)
        return state


def _pipeline(initialized_engine: Engine, sqls, structured):
    """Build the query_database tool wired to the real DB with a scripted agent."""
    service = QueryService(repository=QueryRepository(db_engine=initialized_engine))
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = SqlAgent(llm, service, retry_limit=3)
    agent._agent = _ScriptedInnerAgent(
        agent._build_validate_and_execute(), sqls, structured
    )
    return agent.get_tools()[0]


def _identifiable(sql: str) -> SQLGenerationOutput:
    return SQLGenerationOutput(sql=sql, explanation="explanation", is_identifiable=True)


def _run(tool, question: str = "show total sales by region") -> dict:
    return tool.func(question=question, tool_call_id="call_1", _state={}).update


def test_happy_path_populates_result(initialized_engine: Engine):
    """A valid question runs real SQL and stores the QueryResult in state."""
    tool = _pipeline(initialized_engine, [_REVENUE_SQL], _identifiable(_REVENUE_SQL))
    update = _run(tool)
    assert update["error_message"] is None
    assert update["generated_sql"] == _REVENUE_SQL
    result = update["query_result"]
    assert result.row_count == 2  # South + East in the sample data
    assert set(result.columns) == {"region", "revenue"}
    assert update["messages"][0].content == "retrieved 2 rows. Columns: region, revenue"


def test_unknown_entities_skips_database(initialized_engine: Engine):
    """An unidentifiable question sets the error and never touches the DB."""
    tool = _pipeline(
        initialized_engine,
        [],
        SQLGenerationOutput(sql="", explanation="no entities", is_identifiable=False),
    )
    update = _run(tool, question="show dragon sales by galaxy")
    assert update["error_message"] == "Unable to identify requested entities."
    assert update["query_result"] is None


def test_execution_retry_recovers(initialized_engine: Engine):
    """A first bad query (real execution failure) then a valid one → result in state."""
    bad_sql = "SELECT revenue_amount FROM orders"  # column does not exist
    tool = _pipeline(
        initialized_engine, [bad_sql, _REVENUE_SQL], _identifiable(_REVENUE_SQL)
    )
    update = _run(tool)
    assert update["error_message"] is None
    assert update["query_result"].row_count == 2


def test_read_only_guard_blocks_write(initialized_engine: Engine):
    """A DELETE is blocked by validation and the database is left unmodified."""
    repo = QueryRepository(db_engine=initialized_engine)
    before = repo.execute_select("SELECT COUNT(*) AS n FROM orders").dataframe.iloc[0][
        "n"
    ]

    tool = _pipeline(
        initialized_engine, ["DELETE FROM orders"], _identifiable("DELETE FROM orders")
    )
    update = _run(tool)

    assert update["error_message"] == "Generated query could not be validated."
    assert update["query_result"] is None
    after = repo.execute_select("SELECT COUNT(*) AS n FROM orders").dataframe.iloc[0][
        "n"
    ]
    assert after == before  # nothing was deleted


def test_database_error_maps_to_retrieve_message(initialized_engine: Engine):
    """A SELECT that passes validation but fails execution → database error message."""
    bad_sql = "SELECT nonexistent_column FROM orders"
    tool = _pipeline(initialized_engine, [bad_sql], _identifiable(bad_sql))
    update = _run(tool)
    assert update["error_message"] == "Unable to retrieve data at this time."
    assert update["query_result"] is None


def test_empty_result_maps_to_no_data(initialized_engine: Engine):
    """A valid SELECT matching no rows → 'no data found' and cleared result."""
    empty_sql = "SELECT * FROM customers WHERE customer_id = 'NONE'"
    tool = _pipeline(initialized_engine, [empty_sql], _identifiable(empty_sql))
    update = _run(tool)
    assert update["error_message"] == "No data found for the requested query."
    assert update["query_result"] is None
