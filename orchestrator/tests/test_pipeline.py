"""pipeline.py's output-resolution guard. ROADMAP.md Milestone 4: the
pipeline falls back to a static chart when a no-Plotly-JSON engine is chosen.
"""

import json

import httpx
import pytest

from app import pipeline
from app.llm.client import OllamaClient
from app.pipeline import _resolve_outputs
from app.schemas import QueryRequest


def test_keeps_outputs_the_engine_supports() -> None:
    assert _resolve_outputs(["png", "svg"], frozenset({"png", "svg", "pdf"})) == ["png", "svg"]


def test_drops_plotly_json_for_an_engine_that_cannot_produce_it() -> None:
    # e.g. the LLM picks octave but still asks for plotly_json — octave's
    # supported_outputs has no "plotly_json", so it's dropped.
    assert _resolve_outputs(["plotly_json"], frozenset({"png", "svg", "pdf"})) == ["png"]


def test_falls_back_to_png_when_nothing_requested_is_supported() -> None:
    assert _resolve_outputs([], frozenset({"png", "svg", "pdf"})) == ["png"]


async def test_a_zero_row_result_skips_the_narration_call(monkeypatch: pytest.MonkeyPatch) -> None:
    # A question that matches nothing (or isn't really a data question, like "hi")
    # must not hand the model an empty result set to narrate — it invents a trend
    # from nothing rather than saying there isn't one.
    sql_plan = json.dumps(
        {"sql": "SELECT 1", "rationale": "x", "expected_columns": ["1"]}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": sql_plan})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ollama = OllamaClient("http://fake-ollama", http_client)

    async def fake_run_sql(sql: str, row_limit: int) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(pipeline, "run_sql", fake_run_sql)

    called_generate_text = False

    async def fail_if_called(*args: object, **kwargs: object) -> str:
        nonlocal called_generate_text
        called_generate_text = True
        return "hallucinated narration"

    monkeypatch.setattr(ollama, "generate_text", fail_if_called)

    response = await pipeline.run_query(
        QueryRequest(conversation_id="c1", question="hi"),
        request_id="r1",
        pool=None,  # type: ignore[arg-type] — unused: run_sql is monkeypatched above
        ollama=ollama,
        schema_card="(schema)",
    )

    assert called_generate_text is False
    assert response.summary == "No rows matched this question."
    assert response.row_count == 0
