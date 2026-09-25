"""FastAPI app: lifespan (asyncpg pool, httpx client), /health, /query.
MCP_ENGINES.md §HTTP surface.
"""

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import uuid4

import httpx
import structlog
from asyncpg import Pool
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse

from app.auth import require_bearer_token
from app.chat.loop import (
    ChartEvent,
    DoneEvent,
    HeartbeatEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    run_chat,
)
from app.config import settings
from app.engines.base import available as available_engines
from app.engines.base import register
from app.engines.matlab_engine import MatlabEngine
from app.engines.octave_engine import OctaveEngine
from app.engines.python_engine import PythonEngine
from app.engines.static_render import get_renderer as get_static_renderer
from app.engines.wolfram_engine import WolframEngine
from app.etl_status import list_ingestion_runs, list_quarantine
from app.kb.retrieve import list_documents as kb_list_documents
from app.kb.retrieve import retrieve as kb_retrieve
from app.llm.client import OllamaClient
from app.pipeline import run_query
from app.sandbox.bwrap import stop_orphaned_sandbox_scopes
from app.schemas import (
    ChartRenderRequest,
    ChatRequest,
    IngestionRunsResponse,
    KbDocumentsResponse,
    KbSearchRequest,
    KbSearchResponse,
    OrchestratorError,
    PostgresUnavailableError,
    QuarantineResponse,
    QueryRequest,
    QueryResponse,
    SchemaSampleResponse,
    SchemaTablesResponse,
    Stage,
)
from app.sql.runner import close_pool, get_pool
from app.sql.schema_card import list_schema_tables, render_schema_card, sample_table

# CLAUDE.md's Python conventions call for "structlog to stdout as JSON lines" — this was
# never actually configured, so it ran on structlog's plain-text defaults instead. journald
# (which systemd captures stdout into) copes fine with either, but JSON lines are what let
# an admin's health screen or a log-shipper parse a request_id/model/tokens back out.
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


@dataclass
class ChatTurnState:
    """One chat turn's own record, independent of any specific HTTP request.

    A Cloudflare-fronted connection can die mid-turn on nothing but its own
    total-duration cap (confirmed live: cloudflared logs "context canceled"
    around the 90-100s mark on a compound question, well after the 15s
    heartbeat has already proven the wire itself is fine) — no idle timeout,
    no app bug, just a ceiling this app cannot configure. `buffered` is the
    turn's full ndjson history so far; a request that attaches after the
    original one died replays it from the start and then keeps reading live,
    rather than losing whatever the turn had already done. Written by exactly
    one task (`_run_chat_turn`), read by however many requests attach — safe
    with no lock under asyncio's single-threaded event loop.
    """

    buffered: list[bytes] = field(default_factory=list)
    done: bool = False
    finished_at: float | None = None
    task: asyncio.Task[None] | None = None


# How long a finished turn stays attachable after it ends — long enough for a
# browser that reconnects a few seconds late to still pick up the answer, short
# enough that a tab closed outright doesn't pin memory forever. Lost entirely
# on an orchestrator restart (chat_turns is in-memory only, same boundary
# ctx.status_store already has for Ask's own polling) — a resume request past
# that point gets a plain 404, same as a turn that never existed.
_CHAT_TURN_RETENTION_S = 300.0


@dataclass
class AppContext:
    http_client: httpx.AsyncClient
    ollama: OllamaClient
    pool: Pool | None = None
    schema_card: str | None = None
    status_store: dict[str, Stage] = field(default_factory=dict)
    chat_turns: dict[str, ChatTurnState] = field(default_factory=dict)


app_context: AppContext | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global app_context
    register(PythonEngine())
    register(OctaveEngine())
    if settings.enable_matlab:
        register(MatlabEngine())
    if settings.enable_wolfram:
        register(WolframEngine())
    try:
        await stop_orphaned_sandbox_scopes()
    except Exception as e:  # noqa: BLE001 — a cleanup sweep failing must not block startup
        logger.warning("orphaned sandbox scope sweep failed", error=str(e))
    http_client = httpx.AsyncClient()
    ollama = OllamaClient(settings.ollama_base_url, http_client)
    ctx = AppContext(http_client=http_client, ollama=ollama)
    try:
        ctx.pool = await get_pool()
        ctx.schema_card = await render_schema_card(ctx.pool, ctx.http_client)
    except Exception as e:  # noqa: BLE001 — startup must not crash if Postgres isn't up yet
        logger.warning("postgres unavailable at startup, will retry per-request", error=str(e))
    try:
        await get_static_renderer().start()
    except Exception as e:  # noqa: BLE001 — static export is a nice-to-have, not required to boot
        logger.warning("static renderer failed to start, static export disabled", error=str(e))
    app_context = ctx
    yield
    await get_static_renderer().stop()
    await http_client.aclose()
    await close_pool()


app = FastAPI(title="excise-orchestrator", lifespan=lifespan)


def _ctx() -> AppContext:
    assert app_context is not None, "lifespan did not run"
    return app_context


async def _ensure_ready(ctx: AppContext) -> None:
    if ctx.pool is not None and ctx.schema_card is not None:
        return
    try:
        ctx.pool = await get_pool()
        ctx.schema_card = await render_schema_card(ctx.pool, ctx.http_client)
    except Exception as e:
        raise PostgresUnavailableError(str(e)) from e


@app.get("/health")
async def health() -> dict[str, object]:
    ctx = _ctx()
    pulled = await ctx.ollama.pulled_models()
    models = [
        {"key": key, "label": key, "role": settings.model_role(key), "pulled": key in pulled}
        for key in settings.allowed_models
    ]
    postgres_status = "down"
    kb_docs = 0
    if ctx.pool is not None:
        try:
            await ctx.pool.fetchval("SELECT 1")
            postgres_status = "ok"
            kb_docs = int(await ctx.pool.fetchval("SELECT count(*) FROM kb.documents") or 0)
        except Exception:  # noqa: BLE001 — health check degrades to "error", never crashes
            postgres_status = "error"
    return {
        "status": "ok",
        "ollama": "ok" if pulled else "unreachable",
        "postgres": postgres_status,
        "engines": available_engines(),
        "models": models,
        "kb_docs": kb_docs,
        "embeddings": settings.kb_embeddings_enabled,
    }


@app.post("/kb/search", dependencies=[Depends(require_bearer_token)])
async def kb_search(request: KbSearchRequest) -> KbSearchResponse:
    await _ensure_ready(_ctx())
    return KbSearchResponse(chunks=await kb_retrieve(request.query, request.k, request.states))


@app.get("/kb/documents", dependencies=[Depends(require_bearer_token)])
async def kb_documents(page: int = 1, per_page: int = 20) -> KbDocumentsResponse:
    await _ensure_ready(_ctx())
    documents, total = await kb_list_documents(page, per_page)
    return KbDocumentsResponse(documents=documents, total=total)


@app.post("/chart/render", dependencies=[Depends(require_bearer_token)])
async def chart_render(request: ChartRenderRequest) -> Response:
    """Rasterizes an already-produced Plotly figure — the chart export button
    on a finished query or chat turn, not a fresh render (that's /query and
    /chat). Reuses the same persistent-browser renderer python_engine.py
    calls for a plot's own static outputs.
    """
    renderer = get_static_renderer()
    if not renderer.is_available():
        raise HTTPException(status_code=503, detail="static chart export unavailable")
    media_type = {"png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf"}[
        request.format
    ]
    data = await renderer.render(json.dumps(request.spec), request.format)
    return Response(content=data, media_type=media_type)


@app.get("/etl/runs", dependencies=[Depends(require_bearer_token)])
async def etl_runs(page: int = 1, per_page: int = 20) -> IngestionRunsResponse:
    await _ensure_ready(_ctx())
    runs, total = await list_ingestion_runs(page, per_page)
    return IngestionRunsResponse(runs=runs, total=total)


@app.get("/etl/quarantine", dependencies=[Depends(require_bearer_token)])
async def etl_quarantine(
    page: int = 1, per_page: int = 20, run_id: int | None = None
) -> QuarantineResponse:
    await _ensure_ready(_ctx())
    rows, total = await list_quarantine(page, per_page, run_id)
    return QuarantineResponse(rows=rows, total=total)


@app.get("/schema/tables", dependencies=[Depends(require_bearer_token)])
async def schema_tables() -> SchemaTablesResponse:
    ctx = _ctx()
    await _ensure_ready(ctx)
    assert ctx.pool is not None
    return SchemaTablesResponse(tables=await list_schema_tables(ctx.pool, ctx.http_client))


@app.get("/schema/tables/{table_name}/sample", dependencies=[Depends(require_bearer_token)])
async def schema_table_sample(table_name: str) -> SchemaSampleResponse:
    ctx = _ctx()
    await _ensure_ready(ctx)
    assert ctx.pool is not None
    try:
        rows = await sample_table(ctx.pool, table_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return SchemaSampleResponse(rows=rows)


@app.post("/query", dependencies=[Depends(require_bearer_token)])
async def query(request: QueryRequest) -> StreamingResponse:
    if request.model is not None and request.model not in settings.allowed_models:
        raise HTTPException(status_code=400, detail=f"model not in registry: {request.model}")
    request_id = uuid4().hex
    return StreamingResponse(
        _stream_query(_ctx(), request, request_id), media_type="application/x-ndjson"
    )


async def _stream_query(
    ctx: AppContext, request: QueryRequest, request_id: str
) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[Stage | QueryResponse | OrchestratorError | None] = asyncio.Queue()

    async def on_stage(stage: Stage) -> None:
        ctx.status_store[request_id] = stage
        await queue.put(stage)

    async def runner() -> None:
        try:
            await _ensure_ready(ctx)
            assert ctx.pool is not None
            assert ctx.schema_card is not None
            result = await run_query(
                request,
                request_id=request_id,
                pool=ctx.pool,
                ollama=ctx.ollama,
                schema_card=ctx.schema_card,
                on_stage=on_stage,
            )
            logger.info(
                "query complete",
                request_id=request_id,
                model=result.model,
                engine=result.engine,
                row_count=result.row_count,
                timings_ms=result.timings_ms,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )
            await queue.put(result)
        except OrchestratorError as e:
            logger.warning("query failed", request_id=request_id, stage=e.stage, error=e.message)
            await queue.put(e)
        except Exception as e:  # noqa: BLE001 — last resort so the stream always terminates
            logger.exception("unhandled error in /query pipeline", request_id=request_id)
            await queue.put(OrchestratorError(str(e), stage="internal", http_status=500))
        finally:
            await queue.put(None)

    task = asyncio.create_task(runner())
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Stage):
                yield (json.dumps({"stage": item.model_dump()}) + "\n").encode()
            elif isinstance(item, OrchestratorError):
                yield (
                    json.dumps(
                        {"error": item.message, "request_id": request_id, "stage": item.stage}
                    )
                    + "\n"
                ).encode()
            else:
                yield (json.dumps({"result": item.model_dump()}) + "\n").encode()
    finally:
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@app.post("/chat", dependencies=[Depends(require_bearer_token)])
async def chat(request: ChatRequest) -> StreamingResponse:
    if request.model is not None and request.model not in settings.allowed_models:
        raise HTTPException(status_code=400, detail=f"model not in registry: {request.model}")
    ctx = _ctx()
    # A turn_id already in the registry means this is a resumed connection for a
    # turn still running (or just finished) rather than a fresh question — attach
    # to it instead of starting a duplicate turn. web/'s resend of the same
    # message/history on a resume is otherwise unused; run_chat only ever sees
    # them on the call that actually starts the turn.
    state = ctx.chat_turns.get(request.turn_id) or _start_chat_turn(ctx, request)
    return StreamingResponse(_tail_chat_turn(state), media_type="application/x-ndjson")


@app.post("/chat/turn/{turn_id}/cancel", dependencies=[Depends(require_bearer_token)])
async def chat_turn_cancel(turn_id: str) -> dict[str, bool]:
    """The chat Stop button's real cancellation, now that a dropped connection
    no longer cancels a turn on its own (below) — Stop has to say so explicitly.
    """
    state = _ctx().chat_turns.get(turn_id)
    if state is None or state.task is None or state.task.done():
        return {"cancelled": False}
    state.task.cancel()
    return {"cancelled": True}


def _sweep_finished_chat_turns(ctx: AppContext) -> None:
    now = time.monotonic()
    stale = [
        turn_id
        for turn_id, state in ctx.chat_turns.items()
        if state.finished_at is not None and now - state.finished_at > _CHAT_TURN_RETENTION_S
    ]
    for turn_id in stale:
        del ctx.chat_turns[turn_id]


def _chat_event_line(item: object) -> bytes:
    line: dict[str, object]
    if isinstance(item, TokenEvent):
        line = {"token": item.delta}
    elif isinstance(item, ToolCallEvent):
        line = {"tool_call": {"name": item.name, "arguments": item.arguments}}
    elif isinstance(item, ToolResultEvent):
        line = {"tool_result": {"name": item.name, "ok": item.ok, "summary": item.summary}}
    elif isinstance(item, ChartEvent):
        line = {"chart": item.chart.model_dump()}
    elif isinstance(item, HeartbeatEvent):
        line = {"ping": True}
    elif isinstance(item, DoneEvent):
        line = {
            "done": {
                "tool_calls_count": item.tool_calls_count,
                "prompt_tokens": item.prompt_tokens,
                "completion_tokens": item.completion_tokens,
            }
        }
    else:
        assert isinstance(item, OrchestratorError)
        line = {"error": {"stage": item.stage, "message": item.message}}
    return (json.dumps(line) + "\n").encode()


async def _run_chat_turn(ctx: AppContext, request: ChatRequest, state: ChatTurnState) -> None:
    """Runs the turn to completion and appends every event to `state.buffered`
    as it goes — the one place anything writes to it, so any number of
    requests can safely tail it (`_tail_chat_turn`) with no lock needed.

    Deliberately *not* tied to any particular HTTP request's own cancellation
    the way this used to be — a dropped connection used to cancel the whole
    turn outright (a genuine feature for a user's own Stop click), but that
    made a Cloudflare-side disconnect indistinguishable from one, killing a
    turn that was still making real progress. Cancellation is now only ever
    explicit, via /chat/turn/{turn_id}/cancel.
    """
    try:
        await _ensure_ready(ctx)
        assert ctx.pool is not None
        assert ctx.schema_card is not None
        async for event in run_chat(
            request, pool=ctx.pool, ollama=ctx.ollama, schema_card=ctx.schema_card
        ):
            if isinstance(event, DoneEvent):
                logger.info(
                    "chat turn complete",
                    conversation_id=request.conversation_id,
                    turn_id=request.turn_id,
                    model=request.model,
                    tool_calls_count=event.tool_calls_count,
                    prompt_tokens=event.prompt_tokens,
                    completion_tokens=event.completion_tokens,
                )
            state.buffered.append(_chat_event_line(event))
    except OrchestratorError as e:
        logger.warning(
            "chat turn failed",
            conversation_id=request.conversation_id,
            turn_id=request.turn_id,
            stage=e.stage,
            error=e.message,
        )
        state.buffered.append(_chat_event_line(e))
    except asyncio.CancelledError:
        logger.info(
            "chat turn cancelled", conversation_id=request.conversation_id, turn_id=request.turn_id
        )
        raise
    except Exception as e:  # noqa: BLE001 — last resort so the stream always terminates
        logger.exception(
            "unhandled error in /chat loop",
            conversation_id=request.conversation_id,
            turn_id=request.turn_id,
        )
        state.buffered.append(
            _chat_event_line(OrchestratorError(str(e), stage="internal", http_status=500))
        )
    finally:
        state.done = True
        state.finished_at = time.monotonic()


def _start_chat_turn(ctx: AppContext, request: ChatRequest) -> ChatTurnState:
    _sweep_finished_chat_turns(ctx)
    state = ChatTurnState()
    state.task = asyncio.create_task(_run_chat_turn(ctx, request, state))
    ctx.chat_turns[request.turn_id] = state
    return state


async def _tail_chat_turn(state: ChatTurnState, *, from_index: int = 0) -> AsyncIterator[bytes]:
    """Replays whatever the turn already produced, then keeps polling for more
    until it's done. A plain poll, not a queue a consumer could starve of, since
    more than one request may need to tail the same state in turn (the original
    connection, then a resume) with nothing already consumed to make up for.
    """
    i = from_index
    while True:
        if i < len(state.buffered):
            yield state.buffered[i]
            i += 1
            continue
        if state.done:
            return
        await asyncio.sleep(0.05)


@app.get("/query/{request_id}/status", dependencies=[Depends(require_bearer_token)])
async def query_status(request_id: str) -> dict[str, object]:
    stage = _ctx().status_store.get(request_id)
    if stage is None:
        raise HTTPException(status_code=404, detail="unknown request_id")
    return {"stage": stage.model_dump()}
