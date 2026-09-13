"""engines/python_engine.py's write_image() guard, and the persistent
static-render wiring that replaces it (engines/static_render.py).
"""

from pathlib import Path

import pytest

from app.engines.base import RenderRequest
from app.engines.python_engine import PythonEngine
from app.schemas import SandboxViolationError


async def test_write_image_is_rejected_before_touching_the_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_if_called(**kwargs: object) -> object:
        raise AssertionError("run_in_sandbox should not be called for a write_image() script")

    monkeypatch.setattr("app.engines.python_engine.run_in_sandbox", fail_if_called)

    req = RenderRequest(
        script='fig.write_image(f"{OUT}/chart.png")',
        data_path=Path("/tmp/does-not-matter.parquet"),
        outputs=["png"],
        title="x",
        scratch_dir=Path("/tmp"),
    )

    with pytest.raises(SandboxViolationError):
        await PythonEngine().render(req)


async def test_a_plotly_script_gets_static_outputs_from_the_persistent_renderer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "chart.plotly.json").write_text('{"data": [], "layout": {}}')

    async def fake_run_in_sandbox(**kwargs: object) -> tuple[Path, str]:
        return tmp_path, ""

    monkeypatch.setattr("app.engines.python_engine.run_in_sandbox", fake_run_in_sandbox)

    rendered: list[str] = []

    class FakeRenderer:
        def is_available(self) -> bool:
            return True

        async def render(self, plotly_json: str, fmt: str) -> bytes:
            rendered.append(fmt)
            return b"fake-image-bytes"

    monkeypatch.setattr("app.engines.python_engine.get_static_renderer", lambda: FakeRenderer())

    req = RenderRequest(
        script='fig.write_json(f"{OUT}/chart.plotly.json")',
        data_path=Path("/tmp/does-not-matter.parquet"),
        outputs=["plotly_json", "png"],
        title="x",
        scratch_dir=tmp_path,
    )

    result = await PythonEngine().render(req)

    assert rendered == ["png"]
    assert result.files["png"].read_bytes() == b"fake-image-bytes"


async def test_static_output_is_skipped_when_no_renderer_is_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "chart.plotly.json").write_text('{"data": [], "layout": {}}')

    async def fake_run_in_sandbox(**kwargs: object) -> tuple[Path, str]:
        return tmp_path, ""

    monkeypatch.setattr("app.engines.python_engine.run_in_sandbox", fake_run_in_sandbox)

    class UnavailableRenderer:
        def is_available(self) -> bool:
            return False

    monkeypatch.setattr(
        "app.engines.python_engine.get_static_renderer", lambda: UnavailableRenderer()
    )

    req = RenderRequest(
        script='fig.write_json(f"{OUT}/chart.plotly.json")',
        data_path=Path("/tmp/does-not-matter.parquet"),
        outputs=["plotly_json", "png"],
        title="x",
        scratch_dir=tmp_path,
    )

    result = await PythonEngine().render(req)

    assert "png" not in result.files
    assert result.plotly_json == '{"data": [], "layout": {}}'
