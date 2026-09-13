"""engines/python_engine.py's write_image() guard. A live render showed
Plotly's own static export (fig.write_image, via kaleido's headless Chrome)
repeatedly OOM-killing the sandbox cgroup instead of just erroring — this
rejects that script before a sandboxed process ever runs.
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
