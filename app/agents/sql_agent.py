"""SQL Agent — a ``create_agent()`` subagent with four explicit internal tools.

``SqlAgent`` is the only component permitted to touch the database (AGENTS.md
§5, §9). It is a ``create_agent()`` instance whose internal tools handle the
full SQL pipeline: ``generate_sql`` (nested structured-output LLM call),
``validate_sql`` (read-only guard), ``execute_sql`` (calls ``POST /api/query``
and writes results to ``WorkflowState``), and ``handle_unidentifiable``
(terminal handler when the question references unknown schema entities).

The compiled agent is exposed via ``self._agent`` and registered with the
supervisor by ``AnalyticsGraph`` using ``create_supervisor``. There is no
``get_tools()`` method — the SQL Agent's internal tools are invisible to the
supervisor (AGENTS.md §5, §6).

Contracts consumed/produced: :class:`~app.schemas.sql_result.SQLGenerationOutput`
(inner structured output) and :class:`~app.schemas.sql_result.QueryResult`
(written to ``WorkflowState.query_result``).
"""

from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config.env_config import settings
from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState
from app.prompts.sql_prompt import SQL_SYSTEM_PROMPT
from app.tools.sql_tools import SqlTools

logger = log_config.get_logger(__name__)


class SqlAgent:
    """SQL pipeline subagent — ``create_agent()`` instance with four internal tools.

    ``self._agent`` is the compiled ``create_agent`` graph, ready to be passed
    to ``create_supervisor`` as a subagent. Its internal tools
    (``generate_sql``, ``validate_sql``, ``execute_sql``,
    ``handle_unidentifiable``) are invisible to the supervisor.

    Attributes:
        _agent: Compiled ``create_agent`` graph with recursion limit bound via
            ``with_config``.
        _retry_limit: Maximum self-correction attempts; bounds ``recursion_limit``
            as ``retry_limit * 2 + 1``.
    """

    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        api_base_url: str | None = None,
        retry_limit: int | None = None,
    ) -> None:
        """Build the SQL Agent's ``create_agent`` instance with four internal tools.

        Instantiates :class:`~app.tools.sql_tools.SqlTools` with the injected
        ``llm`` and ``api_base_url``, then calls ``create_agent`` to compile the
        agent graph. Binds ``recursion_limit = retry_limit * 2 + 1`` via
        ``with_config`` so the retry loop is bounded when the supervisor invokes
        this subagent.

        Args:
            llm: Chat model driving the SQL Agent's ReAct loop and the nested
                ``generate_sql`` structured-output call.
            api_base_url: Base URL of the analytics API for ``execute_sql``'s
                ``POST /api/query`` call. Defaults to ``settings.api_base_url``.
            retry_limit: Maximum self-correction attempts; bounds the agent's
                internal tool-calling recursion. Defaults to
                ``settings.sql_retry_limit`` (the ``SQL_RETRY_LIMIT`` env var).
        """
        self._api_base_url = api_base_url or settings.api_base_url
        self._retry_limit = (
            retry_limit if retry_limit is not None else settings.sql_retry_limit
        )
        logger.info("SqlAgent initializing (retry_limit=%d)", self._retry_limit)

        sql_tools = SqlTools(llm=llm, api_base_url=self._api_base_url)

        self._agent = create_agent(
            model=llm,
            tools=[
                sql_tools.generate_sql,
                sql_tools.validate_sql,
                sql_tools.execute_sql,
                sql_tools.handle_unidentifiable,
            ],
            system_prompt=SQL_SYSTEM_PROMPT,
            state_schema=WorkflowState,
            name="sql_agent",
        ).with_config({"recursion_limit": self._retry_limit * 2 + 1})

        logger.info("SqlAgent compiled (recursion_limit=%d)", self._retry_limit * 2 + 1)
