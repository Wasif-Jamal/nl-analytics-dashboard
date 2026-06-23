"""FollowupAgent — stub, to be implemented when Follow-Up Agent issue lands.

``FollowupAgent`` is a pass-through stub. Its ``.node()`` method is added
to the outer ``StateGraph`` as a plain function node (not a ``create_agent()``
subgraph). It returns an empty dict so ``WorkflowState`` is unchanged.

Contracts consumed/produced: none (stub). Import
:data:`~app.prompts.followup_prompt.FOLLOWUP_SYSTEM_PROMPT` is available
in ``app/prompts/followup_prompt.py`` for the future implementation.
"""

from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState

logger = log_config.get_logger(__name__)


class FollowupAgent:
    """Pass-through stub for the Follow-Up Agent.

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
        logger.info("FollowupAgent (stub) initialized")

    def node(self, state: WorkflowState) -> dict:
        """Pass-through stub node. Returns empty update.

        Args:
            state: Current ``WorkflowState`` (unused).

        Returns:
            Empty dict — no state mutation.
        """
        logger.debug("FollowupAgent stub node called")
        return {}
