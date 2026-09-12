"""octave_engine.py availability and a real sandboxed render. MCP_ENGINES.md
§2, ROADMAP.md Milestone 4 tests.
"""

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

from app.engines import base as engines_base
from app.engines.base import RenderRequest
from app.engines.octave_engine import OctaveEngine
from app.sandbox.bwrap import _octave_data_script, _octave_identifier, cleanup_scratch
from app.schemas import EngineUnavailableError

_OCTAVE_INSTALLED = OctaveEngine().is_available()


@pytest.fixture
def data_path() -> Iterator[Path]:
    fd, path_str = tempfile.mkstemp(suffix=".parquet")
    path = Path(path_str)
    pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]}).to_parquet(path)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    engines_base._ENGINES.clear()
    yield
    engines_base._ENGINES.clear()


def test_octave_identifier_sanitizes_invalid_characters() -> None:
    assert _octave_identifier("total revenue (Rs.)") == "total_revenue__Rs__"
    assert _octave_identifier("2024_total") == "col_2024_total"


def test_octave_data_script_renders_numeric_and_text_columns(tmp_path: Path) -> None:
    path = tmp_path / "data.parquet"
    pd.DataFrame({"district": ["Lucknow", "Kanpur"], "amount": [100.5, 200.0]}).to_parquet(path)
    script = _octave_data_script(path)
    assert 'district = {"Lucknow", "Kanpur"}' in script.replace("\n", "")
    assert "amount = [100.5, 200.0]" in script.replace("\n", "")


def test_is_available_false_when_octave_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.engines.octave_engine.shutil.which", lambda _name: None)
    assert OctaveEngine().is_available() is False


def test_unavailable_octave_skipped_cleanly_by_router(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.engines.octave_engine.shutil.which", lambda _name: None)
    engines_base.register(OctaveEngine())
    assert "octave" not in engines_base.available()
    with pytest.raises(EngineUnavailableError):
        engines_base.get("octave")


@pytest.mark.skipif(
    not _OCTAVE_INSTALLED,
    reason="octave-cli not installed on this box yet — OPERATOR_SETUP.md §Octave",
)
async def test_live_octave_script_renders_png(data_path: Path) -> None:
    engine = OctaveEngine()
    script = "plot(x, y);\nprint(fullfile(OUT, 'chart.png'), '-dpngcairo');\n"
    result = await engine.render(
        RenderRequest(
            script=script,
            data_path=data_path,
            outputs=["png"],
            title="test",
            scratch_dir=data_path.parent,
        )
    )
    try:
        assert "png" in result.files
        assert result.files["png"].exists()
    finally:
        cleanup_scratch(result.files["png"].parent)
