"""VisualizationAgent — stub, to be implemented when Visualization Agent issue lands.

``VisualizationAgent`` is a pass-through stub. Its ``.node()`` method is added
to the outer ``StateGraph`` as a plain function node (not a ``create_agent()``
subgraph). It returns an empty dict so ``WorkflowState`` is unchanged.

Contracts consumed/produced: none (stub). Import
:data:`~app.prompts.visualization_prompt.VISUALIZATION_SYSTEM_PROMPT` is
available in ``app/prompts/visualization_prompt.py`` for the future
implementation.
"""

from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState

logger = log_config.get_logger(__name__)


class VisualizationAgent:
    """Pass-through stub for the Visualization Agent.

    ``.node()`` is added to the outer ``StateGraph`` as a node. It returns
    ``{}`` so ``WorkflowState`` is unchanged until the real implementation lands.

    Attributes:
        None (stub — no compiled agent).
    """

    def __init__(self, llm) -> None:
        """Accept ``llm`` for API-compatibility with future implementation.

        Args:
            llm: Chat model (unused by stub; accepted for constructor parity).
        """
        logger.info("VisualizationAgent (stub) initialized")

    def node(self, state: WorkflowState) -> dict:
        """Pass-through stub node. Returns empty update.

        Args:
            state: Current ``WorkflowState`` (unused).

        Returns:
            Empty dict — no state mutation.
        """
        logger.debug("VisualizationAgent stub node called")
        return {}
