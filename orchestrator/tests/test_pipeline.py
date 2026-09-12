"""pipeline.py's output-resolution guard. ROADMAP.md Milestone 4: the
pipeline falls back to a static chart when a no-Plotly-JSON engine is chosen.
"""

from app.pipeline import _resolve_outputs


def test_keeps_outputs_the_engine_supports() -> None:
    assert _resolve_outputs(["png", "svg"], frozenset({"png", "svg", "pdf"})) == ["png", "svg"]


def test_drops_plotly_json_for_an_engine_that_cannot_produce_it() -> None:
    # e.g. the LLM picks octave but still asks for plotly_json — octave's
    # supported_outputs has no "plotly_json", so it's dropped.
    assert _resolve_outputs(["plotly_json"], frozenset({"png", "svg", "pdf"})) == ["png"]


def test_falls_back_to_png_when_nothing_requested_is_supported() -> None:
    assert _resolve_outputs([], frozenset({"png", "svg", "pdf"})) == ["png"]
