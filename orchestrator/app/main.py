"""FastAPI app: lifespan (asyncpg pool, httpx client), /health, /query.
MCP_ENGINES.md §HTTP surface.
"""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import uuid4

import httpx
import structlog
from asyncpg import Pool
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.auth import require_bearer_token
from app.config import settings
from app.engines.base import available as available_engines
from app.engines.base import register
from app.engines.matlab_engine import MatlabEngine
from app.engines.octave_engine import OctaveEngine
from app.engines.python_engine import PythonEngine
from app.engines.wolfram_engine import WolframEngine
from app.kb.retrieve import retrieve as kb_retrieve
from app.llm.client import OllamaClient
from app.pipeline import run_query
from app.schemas import (
    KbSearchRequest,
    KbSearchResponse,
    OrchestratorError,
    PostgresUnavailableError,
    QueryRequest,
    QueryResponse,
    Stage,
)
from app.sql.runner import close_pool, get_pool
from app.sql.schema_card import render_schema_card

logger = structlog.get_logger()


@dataclass
class AppContext:
    http_client: httpx.AsyncClient
    ollama: OllamaClient
    pool: Pool | None = None
    schema_card: str | None = None
    status_store: dict[str, Stage] = field(default_factory=dict)


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
    http_client = httpx.AsyncClient()
    ollama = OllamaClient(settings.ollama_base_url, http_client)
    ctx = AppContext(http_client=http_client, ollama=ollama)
    try:
        ctx.pool = await get_pool()
        ctx.schema_card = await render_schema_card(ctx.pool)
    except Exception as e:  # noqa: BLE001 — startup must not crash if Postgres isn't up yet
        logger.warning("postgres unavailable at startup, will retry per-request", error=str(e))
    app_context = ctx
    yield
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
        ctx.schema_card = await render_schema_card(ctx.pool)
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
    return KbSearchResponse(chunks=await kb_retrieve(request.query, request.k))


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
            await queue.put(result)
        except OrchestratorError as e:
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


@app.get("/query/{request_id}/status", dependencies=[Depends(require_bearer_token)])
async def query_status(request_id: str) -> dict[str, object]:
    stage = _ctx().status_store.get(request_id)
    if stage is None:
        raise HTTPException(status_code=404, detail="unknown request_id")
    return {"stage": stage.model_dump()}
