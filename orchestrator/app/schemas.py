"""Pydantic v2 request/response models, structured-output schemas, and typed
errors for the one-shot pipeline. MCP_ENGINES.md §HTTP surface, §Pipeline stages.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class QueryRequest(BaseModel):
    conversation_id: str
    question: str
    history: list[Turn] = Field(default_factory=list)
    engine_hint: Literal["python", "octave"] | None = None
    model: str | None = None
    row_limit: int = 5000


class ChatTurn(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str


class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    history: list[ChatTurn] = Field(default_factory=list)
    model: str | None = None


class Stage(BaseModel):
    name: Literal["plan_sql", "guard_sql", "run_sql", "plan_plot", "render", "summarize"]
    status: Literal["running", "ok", "error"]
    ms: int | None = None
    detail: str | None = None


class SqlPlan(BaseModel):
    sql: str
    rationale: str
    expected_columns: list[str]


class PlotPlan(BaseModel):
    engine: str
    script: str
    outputs: list[Literal["plotly_json", "png", "svg", "pdf"]]
    title: str


class ChartArtifact(BaseModel):
    plotly_json: str | None = None
    files: dict[str, str] = Field(default_factory=dict)


class ToolCall(BaseModel):
    name: Literal["search_knowledge", "run_sql_query", "make_chart"]
    arguments: dict[str, object]


class ToolResult(BaseModel):
    ok: bool
    summary: str
    chart: ChartArtifact | None = None


class KbChunk(BaseModel):
    content: str
    heading_path: str | None
    title: str
    source_url: str | None
    doc_type: str | None
    rank: float


class KbSearchRequest(BaseModel):
    query: str
    k: int = 6


class KbSearchResponse(BaseModel):
    chunks: list[KbChunk]


class KbDocument(BaseModel):
    id: int
    title: str
    doc_type: str | None
    source_url: str | None
    ingested_at: datetime
    withdrawn_at: datetime | None


class KbDocumentsResponse(BaseModel):
    documents: list[KbDocument]
    total: int


class QueryResponse(BaseModel):
    request_id: str
    sql: str
    row_count: int
    rows_preview: list[dict[str, object]]
    chart: ChartArtifact | None
    summary: str
    engine: str
    model: str
    timings_ms: dict[str, int]
    stages: list[Stage]


# --- Typed errors -----------------------------------------------------------
# Every externally-triggered failure maps to one of these; main.py's exception
# handler turns it into {error, request_id, stage} at a documented HTTP status.
# ARCHITECTURE.md §Failure behavior.


class OrchestratorError(Exception):
    def __init__(self, message: str, *, stage: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.http_status = http_status


class OllamaUnreachableError(OrchestratorError):
    def __init__(self, message: str = "Ollama unreachable", *, stage: str = "plan_sql") -> None:
        super().__init__(message, stage=stage, http_status=502)


class ModelNotAllowedError(OrchestratorError):
    def __init__(self, model: str) -> None:
        super().__init__(f"model not in registry: {model}", stage="plan_sql", http_status=400)


class LLMStructuredOutputError(OrchestratorError):
    def __init__(self, model_name: str, stage: str, errors: str) -> None:
        super().__init__(
            f"{model_name} failed structured-output validation twice: {errors}",
            stage=stage,
            http_status=502,
        )


class SqlRejectedError(OrchestratorError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"SQL rejected: {reason}", stage="guard_sql", http_status=400)


class SqlExecutionError(OrchestratorError):
    def __init__(self, message: str) -> None:
        super().__init__(message, stage="run_sql", http_status=502)


class QueryTimeoutError(OrchestratorError):
    def __init__(self) -> None:
        super().__init__("query timeout", stage="run_sql", http_status=504)


class EngineUnavailableError(OrchestratorError):
    def __init__(self, name: str, reason: str) -> None:
        super().__init__(
            f"engine '{name}' unavailable: {reason}", stage="plan_plot", http_status=400
        )


class SandboxTimeoutError(OrchestratorError):
    def __init__(self) -> None:
        super().__init__("sandbox timeout", stage="render", http_status=504)


class SandboxViolationError(OrchestratorError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"sandbox violation: {detail}", stage="render", http_status=502)


class RenderEmptyError(OrchestratorError):
    def __init__(self, stdout_tail: str = "") -> None:
        super().__init__(
            f"render produced no output: {stdout_tail[-500:]}", stage="render", http_status=502
        )


class ChatToolLoopExceededError(OrchestratorError):
    def __init__(self) -> None:
        super().__init__("too many tool calls", stage="tool_loop", http_status=400)


class ChatToolArgumentError(OrchestratorError):
    def __init__(self, tool: str, detail: str) -> None:
        super().__init__(f"{tool}: {detail}", stage="tool_call", http_status=400)


class PostgresUnavailableError(OrchestratorError):
    def __init__(self, message: str = "Postgres unavailable") -> None:
        super().__init__(message, stage="plan_sql", http_status=503)


class InternalError(OrchestratorError):
    def __init__(self, message: str) -> None:
        super().__init__(message, stage="internal", http_status=500)
