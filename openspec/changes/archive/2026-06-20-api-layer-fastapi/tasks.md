## 1. Phase 1 — Schemas

Tasks 1.1 and 1.2 are independent — **[PARALLEL]**.

- [x] 1.1 **[PARALLEL]** `app/schemas/requests.py`
  - [x] 1.1.1 `AnalyticsRequest(BaseModel)` with `question: str = Field(..., min_length=1)` and `session_uuid: str`
  - [x] 1.1.2 Module docstring (purpose + Pydantic contract it defines)

- [x] 1.2 **[PARALLEL]** `app/schemas/responses.py`
  - [x] 1.2.1 `AnalyticsResponse(BaseModel)`:
    - `question: str`
    - `generated_sql: Optional[str] = None`
    - `sql_explanation: Optional[str] = None`
    - `chart_config: Optional[dict] = None`
    - `insights: Optional[list[str]] = None`
    - `followup_questions: Optional[list[str]] = None`
    - `error_message: Optional[str] = None`
    - `session_history: list[str] = []`
  - [x] 1.2.2 `HealthResponse(BaseModel)` with `status: str`
  - [x] 1.2.3 Module docstring

**Checkpoint:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## 2. Phase 2 — Core Implementation

### 2.1 Chat Service *(depends on 1.1, 1.2)*

- [x] 2.1 `app/services/chat_service.py` — `ChatService` class
  - [x] 2.1.1 Constructor `__init__(self, graph: CompiledStateGraph) -> None`:
    - Store `self._graph = graph`
    - Initialize `self._history: dict[str, list[str]] = {}`
    - Import `CompiledStateGraph` from `langgraph.graph.state`
  - [x] 2.1.2 `ask(self, request: AnalyticsRequest) -> AnalyticsResponse` — happy path:
    - Invoke `self._graph.invoke({"question": request.question, "messages": [HumanMessage(content=request.question)]})`
    - Read `error_message: str | None = result.get("error_message")`
    - If `error_message` is `None`: `self._history.setdefault(request.session_uuid, []).append(request.question)`
    - Return `AnalyticsResponse` mapping all state fields + `session_history=list(self._history.get(request.session_uuid, []))`
    - Import `HumanMessage` from `langchain_core.messages`
  - [x] 2.1.3 `ask()` — error branch (`try/except Exception`):
    - Log the full exception via `logger.exception("Unhandled error in analytics workflow")`
    - Return `AnalyticsResponse(question=request.question, error_message="Unable to retrieve data at this time.", session_history=list(self._history.get(request.session_uuid, [])))`
    - Question is NOT appended to history on exception
  - [x] 2.1.4 Module docstring (states it is the sole component that invokes the workflow, references SDS §9.3)

### 2.2 Routes *(depends on 1.1, 1.2)* — **[PARALLEL]**

- [x] 2.2 **[PARALLEL]** `app/routes/chat_routes.py` — `ChatRouter` class
  - [x] 2.2.1 `__init__(self, chat_service: ChatService) -> None`:
    - Store `self._chat_service = chat_service`
    - Create `self.router = APIRouter(prefix="/api", tags=["chat"])`
    - Register: `self.router.add_api_route("/chat", self.submit_question, methods=["POST"], response_model=AnalyticsResponse)`
  - [x] 2.2.2 `submit_question(self, request: AnalyticsRequest) -> AnalyticsResponse`:
    - Single line: `return self._chat_service.ask(request)`
    - No business logic in the route
  - [x] 2.2.3 Module docstring

- [x] 2.3 **[PARALLEL]** `app/routes/health.py`
  - [x] 2.3.1 Module-level `router = APIRouter(prefix="/api", tags=["health"])`
  - [x] 2.3.2 `@router.get("/health", response_model=HealthResponse)` function `health() -> HealthResponse` returning `HealthResponse(status="ok")`
  - [x] 2.3.3 Module docstring

**Checkpoint:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## 3. Phase 3 — Integration (`app/starter.py`)

*(depends on 2.1, 2.2, 2.3)*

- [x] 3.1 Add imports to `app/starter.py`:
  - `from app.config.llm_config import get_llm`
  - `from app.orchestration.graph import AnalyticsGraph`
  - `from app.services.chat_service import ChatService`
  - `from app.services.sql_service import QueryService`
  - `from app.routes.chat_routes import ChatRouter`
  - `from app.routes.health import router as health_router`

- [x] 3.2 Inside `create_app()`, after `DatabaseInitializer().initialize()`:
  - [x] 3.2.1 `llm = get_llm()`
  - [x] 3.2.2 `query_service = QueryService()` — uses default `QueryRepository()` → shared `engine` from `db_config`
  - [x] 3.2.3 `graph = AnalyticsGraph(llm, query_service).build()`
  - [x] 3.2.4 `chat_service = ChatService(graph)`
  - [x] 3.2.5 `chat_router = ChatRouter(chat_service)`
  - [x] 3.2.6 `app.include_router(chat_router.router)`
  - [x] 3.2.7 `app.include_router(health_router)`
  - [x] 3.2.8 Add `logger.info("Application startup complete")` before `return app`

**Checkpoint:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## 4. Phase 4 — Tests

Tasks 4.1 and 4.2 are independent — **[PARALLEL]**.

### 4.1 **[PARALLEL]** `tests/services/test_chat_service.py` — `ChatService` unit tests *(spec: chat-service-workflow-bridge, session-history, error-response-safety)*

- [x] 4.1.0 Add `tests/services/__init__.py` if missing (check first)

- [x] 4.1.1 Fixtures:
  - `mock_graph` — `MagicMock()` with `invoke` method
  - `service` — `ChatService(mock_graph)`
  - Helper `make_request(question="Q", session="s1")` — returns `AnalyticsRequest`
  - Helper `make_state(**kwargs)` — returns dict with all `WorkflowState` keys defaulting to `None`; kwargs override

- [x] 4.1.2 *(spec: chat-service-workflow-bridge — successful invocation)*
  `test_success_returns_populated_response`: mock returns state with `generated_sql="SELECT 1"`, `error_message=None` → `resp.error_message is None`, `resp.generated_sql == "SELECT 1"`

- [x] 4.1.3 *(spec: session-history — first question in new session)*
  `test_first_question_appended_to_history`: success response → `resp.session_history == ["Q"]`

- [x] 4.1.4 *(spec: session-history — subsequent questions)*
  `test_subsequent_questions_accumulate`: call `ask()` twice with same session, both succeed → `resp.session_history == ["Q1", "Q2"]`

- [x] 4.1.5 *(spec: chat-service-workflow-bridge — workflow sets error_message)*
  `test_workflow_error_not_appended`: mock returns state with `error_message="Unable to identify requested entities."` → `resp.error_message == "Unable to identify requested entities."`, `resp.session_history == []`

- [x] 4.1.6 *(spec: session-history — errored question is not appended)*
  `test_error_does_not_pollute_existing_history`: one success then one workflow error → second response's `session_history` contains only the first question

- [x] 4.1.7 *(spec: chat-service-workflow-bridge — unhandled exception)*
  `test_exception_returns_safe_error`: `mock_graph.invoke.side_effect = RuntimeError("boom")` → `resp.error_message == "Unable to retrieve data at this time."`, `resp.session_history == []`

- [x] 4.1.8 *(spec: error-response-safety — no stack trace)*
  `test_exception_error_message_is_standard_string`: verify `resp.error_message` is exactly `"Unable to retrieve data at this time."` (not the raw exception message)

### 4.2 **[PARALLEL]** `tests/routes/test_chat_routes.py` — API route tests *(spec: submit-question-endpoint, health-endpoint, request-schema, error-response-safety)*

- [x] 4.2.0 `tests/routes/__init__.py` — empty package file

- [x] 4.2.1 Fixtures:
  - `mock_service` — `MagicMock(spec=ChatService)`
  - `client` — `TestClient(FastAPI())` assembled with `ChatRouter(mock_service).router` + `health_router` (no DB, no real graph)

- [x] 4.2.2 *(spec: submit-question-endpoint — successful question submission)*
  `test_post_chat_success`: `mock_service.ask.return_value = AnalyticsResponse(question="Q", session_history=["Q"])` → `POST /api/chat` returns `200`, body has `question == "Q"`

- [x] 4.2.3 *(spec: request-schema — missing required field `question`)*
  `test_missing_question_returns_422`: `POST /api/chat` with `{"session_uuid": "s1"}` → `422`

- [x] 4.2.4 *(spec: request-schema — empty question string)*
  `test_empty_question_returns_422`: `POST /api/chat` with `{"question": "", "session_uuid": "s1"}` → `422`

- [x] 4.2.5 *(spec: request-schema — missing `session_uuid`)*
  `test_missing_session_uuid_returns_422`: `POST /api/chat` with `{"question": "Q"}` → `422`

- [x] 4.2.6 *(spec: health-endpoint)*
  `test_health_returns_ok`: `GET /api/health` → `200`, `{"status": "ok"}`

- [x] 4.2.7 *(spec: submit-question-endpoint — unknown route)*
  `test_unknown_route_returns_404`: `GET /api/unknown` → `404`

- [x] 4.2.8 *(spec: error-response-safety — workflow error is still HTTP 200)*
  `test_workflow_error_is_http_200`: `mock_service.ask.return_value = AnalyticsResponse(question="Q", error_message="Unable to identify requested entities.", session_history=[])` → `POST /api/chat` returns `200`, `error_message` in body

- [x] 4.2.9 *(spec: submit-question-endpoint — route contains no business logic)*
  `test_route_delegates_to_service`: after a successful call, assert `mock_service.ask.call_count == 1` and the `AnalyticsRequest` passed has `question="Q"` and `session_uuid="s1"`

**Checkpoint (final gate):**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## 5. Phase 5 — Finalize

- [x] 5.1 `openspec validate api-layer-fastapi` passes
- [x] 5.2 All quality gates green; deviations from the plan reconciled into `plan.md`
