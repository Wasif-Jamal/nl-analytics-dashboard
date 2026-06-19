# Implementation Plan — API Layer (FastAPI + Chat Service)

## Codebase State (pre-implementation)

Already landed — consumed, not recreated:

| File | State |
|---|---|
| `app/main.py` | Imports and exports `create_app()` result as `app` — no change needed |
| `app/starter.py` | `create_app()` initializes DB + returns bare `FastAPI` — **will be modified** |
| `app/routes/__init__.py` | Empty package — no change needed |
| `app/orchestration/graph.py` | `AnalyticsGraph(llm, query_service, retry_limit).build()` returns `CompiledStateGraph` — consumed as-is |
| `app/orchestration/state.py` | `WorkflowState(MessagesState)` TypedDict with all fields — consumed as-is |
| `app/services/sql_service.py` | `QueryService(repository?)` + `run_query()` — consumed as-is |
| `app/repositories/query_repository.py` | `QueryRepository(engine?)` with default `engine` from `db_config` — consumed as-is |
| `app/config/llm_config.py` | `get_llm()` factory — called once in `create_app()` |
| `app/config/db_config.py` | `engine` + `SessionLocal` — `QueryRepository` defaults to this engine |
| `app/config/env_config.py` | `settings` singleton — consumed via `AnalyticsGraph` and `SqlAgent` |
| `app/config/log_config.py` | `get_logger(__name__)` — used in every new module |
| `app/schemas/sql_result.py` | `SQLGenerationOutput`, `QueryResult` — consumed by `ChatService` |

Missing — all new files:
- `app/schemas/requests.py`
- `app/schemas/responses.py`
- `app/services/chat_service.py`
- `app/routes/chat_routes.py`
- `app/routes/health.py`
- `tests/services/test_chat_service.py`
- `tests/routes/__init__.py`
- `tests/routes/test_chat_routes.py`

---

## Architecture Decisions

### 1. Class-based router for `chat_routes.py`
CLAUDE.md §10 requires one primary class per module. `ChatRouter` accepts `ChatService` via constructor and exposes `self.router: APIRouter`. This keeps the service dependency explicit, avoids module-level mutation, and makes unit testing straightforward — tests instantiate `ChatRouter(mock_service)` directly.

`health.py` has no dependencies and no state, so it uses a module-level `router` with a plain function. This falls under CLAUDE.md's "thin entry points" exemption and is simpler than a stateless class.

### 2. Graph is invoked with `HumanMessage` seeding the messages channel
`WorkflowState` subclasses `MessagesState` (TypedDict). The supervisor's ReAct loop reads from `messages`. Initial invocation:
```python
graph.invoke({
    "question": request.question,
    "messages": [HumanMessage(content=request.question)],
})
```
Unset Optional fields (`generated_sql`, `chart_config`, etc.) are absent from the initial dict — LangGraph treats missing TypedDict keys as `None`, matching the `Optional[X]` annotations.

### 3. Singleton built in `create_app()`, wired into `ChatRouter`
`AnalyticsGraph.build()` is called once. The compiled graph and `ChatService` instance are constructed there, then passed directly to `ChatRouter.__init__()`. No `app.state`, no module globals. Startup sequence:
```
DatabaseInitializer().initialize()
  → get_llm()
  → QueryService()  (defaults to shared engine from db_config)
  → AnalyticsGraph(llm, query_service).build()
  → ChatService(graph)
  → ChatRouter(chat_service)
  → app.include_router(chat_router.router)
  → app.include_router(health_router)
```

### 4. All errors → HTTP 200 with `error_message`
`ChatService.ask()` wraps the full graph invocation in `try/except Exception`. Workflow-level errors (`error_message` set in state) are read and propagated. Unhandled exceptions are caught, logged via `logger.exception()` (full traceback server-side only), and mapped to `"Unable to retrieve data at this time."` in the response body. HTTP status is always 200.

### 5. Session history is a plain `dict[str, list[str]]`
CPython's GIL + uvicorn's async event loop means concurrent requests don't race on `list.append()`. A plain dict is sufficient for this scope. Only questions with `error_message=None` (after graph returns) are appended. The response always returns `list(session_history)` — a copy — to avoid callers mutating the internal list.

### 6. Test isolation strategy
- **`ChatService` unit tests**: Mock `CompiledStateGraph` via `MagicMock`. Set `mock_graph.invoke.return_value` to a dict representing final `WorkflowState`.
- **Route tests**: Use `fastapi.testclient.TestClient` against a minimal `FastAPI` app assembled from `ChatRouter(mock_service)` + `health_router`. No DB, no real graph. `mock_service.ask.return_value` returns a pre-built `AnalyticsResponse`.

---

## Exact File Shapes

### `app/schemas/requests.py`
```python
class AnalyticsRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_uuid: str
```

### `app/schemas/responses.py`
```python
class AnalyticsResponse(BaseModel):
    question: str
    generated_sql: Optional[str] = None
    sql_explanation: Optional[str] = None
    chart_config: Optional[dict] = None
    insights: Optional[list[str]] = None
    followup_questions: Optional[list[str]] = None
    error_message: Optional[str] = None
    session_history: list[str] = []

class HealthResponse(BaseModel):
    status: str
```

### `app/services/chat_service.py`
```python
class ChatService:
    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph
        self._history: dict[str, list[str]] = {}

    def ask(self, request: AnalyticsRequest) -> AnalyticsResponse:
        try:
            result = self._graph.invoke({
                "question": request.question,
                "messages": [HumanMessage(content=request.question)],
            })
            error_message: str | None = result.get("error_message")
            session_history = self._history.setdefault(request.session_uuid, [])
            if not error_message:
                session_history.append(request.question)
            return AnalyticsResponse(
                question=request.question,
                generated_sql=result.get("generated_sql"),
                sql_explanation=result.get("sql_explanation"),
                chart_config=result.get("chart_config"),
                insights=result.get("insights"),
                followup_questions=result.get("followup_questions"),
                error_message=error_message,
                session_history=list(session_history),
            )
        except Exception:
            logger.exception("Unhandled error in analytics workflow")
            return AnalyticsResponse(
                question=request.question,
                error_message="Unable to retrieve data at this time.",
                session_history=list(self._history.get(request.session_uuid, [])),
            )
```

### `app/routes/chat_routes.py`
```python
class ChatRouter:
    def __init__(self, chat_service: ChatService) -> None:
        self._chat_service = chat_service
        self.router = APIRouter(prefix="/api", tags=["chat"])
        self.router.add_api_route(
            "/chat",
            self.submit_question,
            methods=["POST"],
            response_model=AnalyticsResponse,
        )

    def submit_question(self, request: AnalyticsRequest) -> AnalyticsResponse:
        return self._chat_service.ask(request)
```

### `app/routes/health.py`
```python
router = APIRouter(prefix="/api", tags=["health"])

@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
```

### `app/starter.py` (additions highlighted)
```python
def create_app() -> FastAPI:
    logger.info("Bootstrapping application — initializing database")
    DatabaseInitializer().initialize()

    app = FastAPI(title="Natural Language Analytics Dashboard API")

    # --- new: build singleton, register routers ---
    llm = get_llm()
    query_service = QueryService()
    graph = AnalyticsGraph(llm, query_service).build()
    chat_service = ChatService(graph)

    chat_router = ChatRouter(chat_service)
    app.include_router(chat_router.router)
    app.include_router(health_router)          # module-level from health.py
    logger.info("Application startup complete")
    # --- end new ---

    return app
```

---

## Test Shapes

### `tests/services/test_chat_service.py`
```python
@pytest.fixture
def mock_graph():
    return MagicMock()

@pytest.fixture
def service(mock_graph):
    return ChatService(mock_graph)

# 5.1.1 happy path
def test_success(service, mock_graph):
    mock_graph.invoke.return_value = {
        "generated_sql": "SELECT 1",
        "sql_explanation": "...",
        "query_result": ...,
        "chart_config": None, "insights": None, "followup_questions": None,
        "error_message": None,
    }
    resp = service.ask(AnalyticsRequest(question="Q", session_uuid="s1"))
    assert resp.error_message is None
    assert resp.session_history == ["Q"]

# 5.1.2 workflow error
def test_workflow_error(service, mock_graph):
    mock_graph.invoke.return_value = {"error_message": "Unable to identify...", ...}
    resp = service.ask(AnalyticsRequest(question="Q", session_uuid="s1"))
    assert resp.error_message == "Unable to identify..."
    assert resp.session_history == []        # not appended

# 5.1.3 unhandled exception
def test_exception(service, mock_graph):
    mock_graph.invoke.side_effect = RuntimeError("boom")
    resp = service.ask(AnalyticsRequest(question="Q", session_uuid="s1"))
    assert resp.error_message == "Unable to retrieve data at this time."
    assert resp.session_history == []
```

### `tests/routes/test_chat_routes.py`
```python
@pytest.fixture
def mock_service():
    return MagicMock(spec=ChatService)

@pytest.fixture
def client(mock_service):
    from app.routes.health import router as health_router
    app = FastAPI()
    app.include_router(ChatRouter(mock_service).router)
    app.include_router(health_router)
    return TestClient(app)

# 5.2.1 happy path POST /api/chat
def test_submit_question_success(client, mock_service):
    mock_service.ask.return_value = AnalyticsResponse(
        question="Q", session_history=["Q"]
    )
    resp = client.post("/api/chat", json={"question": "Q", "session_uuid": "s1"})
    assert resp.status_code == 200
    assert resp.json()["question"] == "Q"

# 5.2.2 missing question → 422
def test_missing_question(client):
    resp = client.post("/api/chat", json={"session_uuid": "s1"})
    assert resp.status_code == 422

# 5.2.7 workflow error → still 200
def test_workflow_error_is_200(client, mock_service):
    mock_service.ask.return_value = AnalyticsResponse(
        question="Q", error_message="Unable to identify requested entities.",
        session_history=[]
    )
    resp = client.post("/api/chat", json={"question": "Q", "session_uuid": "s1"})
    assert resp.status_code == 200
    assert "Unable to identify" in resp.json()["error_message"]
```

---

## DB / Schema Changes

**None.** This change adds only HTTP transport and in-memory session state. No new SQLAlchemy models, no schema migrations, no changes to `database_initializer.py`.

---

## Quality Gates

Run in order after each phase:
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

All three must be green before committing. No build step.

---

## Open Questions / Risks

1. **`AnalyticsGraph.build()` during test startup**: Tests for routes mock `ChatService` directly, so the graph is never built in those tests. `ChatService` unit tests mock the graph. No real LLM call in any test file under this change.

2. **`starter.py` in integration tests**: Any test that imports `create_app()` will try to call `get_llm()` and `AnalyticsGraph.build()`. Existing tests don't import `create_app()` (they use `initialized_engine` fixture). If future tests need the full app, they'll need a fixture that patches `get_llm` and `AnalyticsGraph.build`.

3. **`session_history` is lost on server restart**: This is by design (FRS §11 says session-level; SDS §15 says in-memory only; never written to DB). The Streamlit UI's `session_uuid` is generated on page load and is therefore also lost on UI reload — both halves reset together.
