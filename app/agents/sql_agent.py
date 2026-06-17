"""SQL generation agent.

Translates a natural-language question into a SQL query using the Gemini LLM
with structured output. Returns a typed :class:`SQLGenerationOutput`; never
executes SQL directly (SQL Agent is the only component allowed to touch the
database — but only via the Repository after validation).
"""

from langchain_core.messages import HumanMessage, SystemMessage

from app.config.llm_config import get_llm
from app.config.log_config import get_logger
from app.prompts.sql_prompt import SQL_SYSTEM_PROMPT
from app.schemas.sql_result import SQLGenerationOutput

logger = get_logger(__name__)


class SqlAgent:
    """Generates SQL from a natural-language question via the LLM.

    Owns the SQL generation prompt and the LLM call. The agent never executes
    SQL; execution is the responsibility of the Repository layer after
    validation (issues #2 and #3).
    """

    def __init__(self, llm=None) -> None:
        """Initialise the agent with an LLM client.

        Args:
            llm: A LangChain chat model. Defaults to the shared app LLM from
                :func:`app.config.llm_config.get_llm`.
        """
        self._llm = llm or get_llm()

    def generate(self, question: str) -> SQLGenerationOutput:
        """Translate a natural-language question into a structured SQL output.

        Args:
            question: The plain-English question submitted by the user.

        Returns:
            A :class:`SQLGenerationOutput` with ``sql``, ``explanation``, and
            ``is_identifiable`` populated by the LLM.
        """
        logger.info("Generating SQL for question: %s", question)
        structured_llm = self._llm.with_structured_output(SQLGenerationOutput)
        result: SQLGenerationOutput = structured_llm.invoke(
            [SystemMessage(content=SQL_SYSTEM_PROMPT), HumanMessage(content=question)]
        )
        logger.info(
            "SQL generation complete: is_identifiable=%s sql_length=%d",
            result.is_identifiable,
            len(result.sql),
        )
        return result
