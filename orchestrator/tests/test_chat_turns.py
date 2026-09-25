"""Chat's own turn registry (app/main.py) — a turn survives a dropped
connection (the Cloudflare ~100s duration cap, confirmed live on a compound
question) instead of dying with it. MCP_ENGINES.md §Streamed events.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import app.main as main_module
from app.main import (
    AppContext,
    ChatTurnState,
    _sweep_finished_chat_turns,
    _tail_chat_turn,
    chat_turn_cancel,
)
from app.schemas import ChatRequest, ToolCall


@dataclass
class _FakeChunk:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class _FakeOllama:
    """A no-tool-call reply by default — enough to drive run_chat to a DoneEvent
    without touching a real Ollama, the same fake shape test_chat_loop.py uses.
    """

    async def chat_stream(
        self, *, model: str, messages: object, tools: object, usage: object = None
    ) -> AsyncIterator[object]:
        yield _FakeChunk(content="Hi there.")


def _ctx() -> AppContext:
    return AppContext(
        http_client=object(),  # type: ignore[arg-type]
        ollama=_FakeOllama(),  # type: ignore[arg-type]
        pool=object(),  # type: ignore[arg-type]  — _ensure_ready no-ops once pool/schema_card are set
        schema_card="(s)",
    )


def _request(turn_id: str = "t1") -> ChatRequest:
    return ChatRequest(conversation_id="c1", turn_id=turn_id, message="hi")


async def _run_to_completion(ctx: AppContext, request: ChatRequest) -> ChatTurnState:
    state = main_module._start_chat_turn(ctx, request)
    assert state.task is not None
    await state.task
    return state


async def test_a_started_turn_registers_itself_and_buffers_every_event() -> None:
    ctx = _ctx()
    request = _request()
    state = await _run_to_completion(ctx, request)

    assert ctx.chat_turns["t1"] is state
    assert state.done is True
    assert state.finished_at is not None
    assert len(state.buffered) >= 2  # at least a token line and a done line


async def test_tailing_a_finished_turn_replays_its_full_history() -> None:
    ctx = _ctx()
    state = await _run_to_completion(ctx, _request())

    lines = [line async for line in _tail_chat_turn(state)]

    assert lines == state.buffered


async def test_a_second_tail_from_the_start_sees_everything_the_first_one_did() -> None:
    """The whole point of resuming: a request that attaches after the turn is
    already done (or partway through) gets the complete transcript, not just
    whatever arrived after it attached.
    """
    ctx = _ctx()
    state = await _run_to_completion(ctx, _request())

    first_attempt = [line async for line in _tail_chat_turn(state, from_index=0)]
    resumed = [line async for line in _tail_chat_turn(state, from_index=0)]

    assert resumed == first_attempt
    assert len(resumed) > 0


async def test_sweep_evicts_only_turns_past_the_retention_window() -> None:
    ctx = _ctx()
    now = main_module.time.monotonic()
    ctx.chat_turns["stale"] = ChatTurnState(
        done=True, finished_at=now - main_module._CHAT_TURN_RETENTION_S - 1
    )
    ctx.chat_turns["fresh"] = ChatTurnState(done=True, finished_at=now)
    ctx.chat_turns["running"] = ChatTurnState(done=False, finished_at=None)

    _sweep_finished_chat_turns(ctx)

    assert set(ctx.chat_turns) == {"fresh", "running"}


async def test_cancel_stops_a_running_turns_task() -> None:
    ctx = _ctx()

    async def _never_finishes() -> None:
        await asyncio.sleep(3600)

    state = ChatTurnState(task=asyncio.create_task(_never_finishes()))
    ctx.chat_turns["t1"] = state
    main_module.app_context = ctx
    try:
        result = await chat_turn_cancel("t1")
    finally:
        main_module.app_context = None

    assert result == {"cancelled": True}
    assert state.task is not None
    await asyncio.sleep(0)  # let the cancellation actually land
    assert state.task.cancelled() or state.task.done()


async def test_cancel_on_an_unknown_turn_id_is_a_no_op() -> None:
    ctx = _ctx()
    main_module.app_context = ctx
    try:
        result = await chat_turn_cancel("no-such-turn")
    finally:
        main_module.app_context = None

    assert result == {"cancelled": False}
