# followup-pipeline Specification

## Purpose
TBD - created by archiving change suggested-followup-questions. Update Purpose after archive.
## Requirements
### Requirement: followup-agent

`FollowupAgent` in `app/agents/followup_agent.py` SHALL be a `create_agent()` instance
whose compiled agent is exposed via `self._agent` and uses a private `FollowupAgentState`
(a `MessagesState` subclass with `question`, `query_result`, `followup_questions`). The
agent SHALL use `FOLLOWUP_SYSTEM_PROMPT` from `app/prompts/followup_prompt.py` and
`state_schema=FollowupAgentState`. A `node(state: WorkflowState) -> dict` method SHALL
bridge the outer state to the inner state: it constructs a fresh `FollowupAgentState`
(with a single `HumanMessage` trigger) so the model starts with a clean context,
invokes `self._agent`, and returns only `{"followup_questions": ...}`. The outer
`StateGraph` registers `followup_agent.node` (a function node), NOT `followup_agent._agent`
directly.

Using `state_schema=FollowupAgentState` (not `WorkflowState`) is required: after the SQL
Agent completes, `WorkflowState.messages` contains the full SQL conversation; if the
agent inherited that history it would see a completed exchange and decline to call any tool.

#### Scenario: supervisor routes to FollowupAgent
- **WHEN** the outer graph routes to `"followup_agent"` after a successful SQL Agent run
- **THEN** `FollowupAgent.node()` is called; it invokes `_agent` with a fresh `FollowupAgentState`; the model sees only a single HumanMessage (not the prior SQL conversation); `generate_followup_questions` is invisible to the outer graph

#### Scenario: agent calls generate_followup_questions once
- **WHEN** `FollowupAgent.node()` is called with a non-empty `query_result` in `WorkflowState`
- **THEN** the LLM calls `generate_followup_questions` exactly once; `node()` propagates only `followup_questions` back to `WorkflowState`

---

### Requirement: followup-tools

`FollowupTools` in `app/tools/followup_tools.py` SHALL build one `@tool` closure
(`generate_followup_questions`) in `__init__`, capturing `llm`. The tool SHALL be stored
as `self.generate_followup_questions` and passed directly to `create_agent`.

`generate_followup_questions` tool contract:
- Reads `query_result` and `question` via `Annotated[_FollowupToolState, InjectedState()]`
  where `_FollowupToolState` is a `TypedDict(total=False)` declaring only those two fields.
  Using the full `WorkflowState` type would cause Pydantic validation errors because the
  tool runs under the private `FollowupAgentState`, not `WorkflowState`. The LLM does not
  pass rows as arguments.
- Rows are capped at `_MAX_FOLLOWUP_ROWS = 50` before JSON serialization. When the result
  set exceeds 50 rows, the excess is dropped and a warning is logged.
- When `query_result` is set and `rows` is non-empty: makes a nested
  `llm.with_structured_output(FollowupOutput)` call using `FOLLOWUP_INNER_PROMPT`. Returns
  `Command(update={"followup_questions": result.followup_questions, "messages": [ToolMessage(...)]})`.
- When `query_result` is `None` or `rows` is empty: returns
  `Command(update={"followup_questions": [], "messages": [ToolMessage(content="No data.", ...)]})` 
  without calling the LLM.
- When the LLM call raises: logs the exception, returns `Command(update={"followup_questions": [], ...})`; does NOT set `error_message` (follow-up generation is non-fatal).

#### Scenario: query_result present — questions generated
- **WHEN** `generate_followup_questions` is called and `state["query_result"].rows` is non-empty
- **THEN** the nested `with_structured_output(FollowupOutput)` call returns a `FollowupOutput` with exactly 3 follow-up question strings; `WorkflowState.followup_questions` is set to that list and `error_message` is unchanged

#### Scenario: query_result absent — no LLM call
- **WHEN** `generate_followup_questions` is called and `state["query_result"]` is `None`
- **THEN** `WorkflowState.followup_questions` is set to `[]`; no LLM call is made; `error_message` is unchanged

#### Scenario: LLM call fails — non-fatal
- **WHEN** the nested `with_structured_output` call raises an exception
- **THEN** `WorkflowState.followup_questions` is set to `[]`; the error is logged server-side; `error_message` is NOT set

#### Scenario: rows truncated at 50
- **WHEN** `generate_followup_questions` is called and `state["query_result"].rows` has more than 50 rows
- **THEN** only the first 50 rows are serialized; a warning is logged; the LLM call proceeds normally

---

### Requirement: followup-output-schema

`FollowupOutput` in `app/schemas/followup_result.py` SHALL be a Pydantic `BaseModel`
used exclusively as the structured-output target for the nested LLM call inside
`generate_followup_questions`. The outer `WorkflowState.followup_questions` field type
(`Optional[list[str]]`) is unchanged.

```
FollowupOutput
  followup_questions: list[str]   # exactly 3 relevant follow-up question strings
```

#### Scenario: structured output validated
- **WHEN** the LLM returns a response for `with_structured_output(FollowupOutput)`
- **THEN** Pydantic validates that `followup_questions` is a `list[str]`; if validation fails, LangChain retries automatically

#### Scenario: schema is not stored in WorkflowState
- **WHEN** `generate_followup_questions` writes to `WorkflowState`
- **THEN** it writes `result.followup_questions` (a `list[str]`) to `WorkflowState.followup_questions`, not the `FollowupOutput` object itself

