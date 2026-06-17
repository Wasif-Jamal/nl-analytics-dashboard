## ADDED Requirements

### Requirement: Natural-language question to SQL (FR-1, FR-2)
The system SHALL accept a plain-English question and translate it into a SELECT query targeting
the known Superstore schema (customers, products, orders, order_items). The generated SQL and a
plain-English explanation MUST be stored in workflow state for downstream nodes and eventual UI display.

#### Scenario: Valid business question
- **WHEN** a user submits a question that maps to known schema entities (e.g. "Show total sales by region")
- **THEN** `SqlGenerationNode` returns updated workflow state with non-empty `generated_sql`,
  non-empty `sql_explanation`, and `error_message` is `None`

#### Scenario: Unknown schema entities
- **WHEN** a user submits a question whose entities cannot be matched to the schema
  (e.g. "Show dragon sales by galaxy")
- **THEN** `SqlGenerationNode` sets `error_message = "Unable to identify requested entities."`,
  `generated_sql` remains empty, and no SQL is passed to downstream nodes

#### Scenario: LLM call fails
- **WHEN** the LLM call raises an exception (network error, quota exceeded, invalid API key)
- **THEN** `SqlGenerationNode` sets `error_message = "Unable to identify requested entities."`,
  logs the exception, and does not re-raise

### Requirement: Structured SQL generation output contract (SDS §6.1, §8)
The SQL agent MUST produce a `SQLGenerationOutput` Pydantic model; agents SHALL communicate via
typed schemas only — never unstructured text.

#### Scenario: Identifiable question
- **WHEN** `SqlAgent.generate(question)` is called with a question referencing known entities
- **THEN** it returns `SQLGenerationOutput` with non-empty `sql`, non-empty `explanation`,
  and `is_identifiable=True`

#### Scenario: Unidentifiable question
- **WHEN** `SqlAgent.generate(question)` is called with a question referencing unknown entities
- **THEN** it returns `SQLGenerationOutput` with `sql=""`, `is_identifiable=False`,
  and a non-empty `explanation`
