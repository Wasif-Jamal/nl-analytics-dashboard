# Spec Delta: insights-pipeline (suggested-followup-questions change)

## Delta Summary

Updates the `stub-agents` requirement: `FollowupAgent` is no longer a stub — it is
a `create_agent()` instance defined by the `followup-agent` requirement in the
`followup-pipeline` spec. `VisualizationAgent` remains a stub.

---

## MODIFIED Requirements

### Requirement: stub-agents

`VisualizationAgent` in `app/agents/visualization_agent.py` SHALL be a stub class with
a `.node(state)` method that returns an empty dict and MUST NOT mutate `WorkflowState`.
It SHALL NOT call `create_agent()`. A placeholder prompt module MUST exist at
`app/prompts/visualization_prompt.py`.

`FollowupAgent` is no longer a stub. Its full implementation is defined by the
`followup-agent` requirement in the `followup-pipeline` spec.

#### Scenario: visualization stub node invoked
- **WHEN** the outer graph routes to `"visualization_agent"`
- **THEN** the stub's `.node()` method is called; it returns `{}`; `WorkflowState` is unchanged; the node terminates normally

#### Scenario: placeholder prompt file exists
- **WHEN** the project is checked out
- **THEN** `app/prompts/visualization_prompt.py` exists and exports a prompt constant (may be an empty string)
