"""A persistent, isolated headless-browser renderer for Plotly's static
image export (PNG/SVG/PDF). SECURITY.md §Code-execution sandbox.

This runs outside `sandbox/bwrap.py` entirely, on purpose: unlike a chart
*script*, which is LLM-authored and untrusted, this only ever rasterizes an
already-produced, schema-shaped `chart.plotly.json` — no LLM-authored code
ever executes here. One browser is started once and reused for every render
instead of a fresh sandboxed launch per chart, which is what was repeatedly
OOM-killing the render sandbox (`python_engine.py`'s own history).

Isolation from the operator's real browser: `choreographer` (kaleido's
browser driver) always launches with a fresh `--user-data-dir` per process,
so this never reads or writes the operator's actual Chrome profile,
cookies, or signed-in Google account — that holds regardless of which
binary is launched. `_find_browser_path()` additionally prefers an
open-source Chromium binary over Google Chrome when the operator has
installed one (`OPERATOR_SETUP.md` §Chart rendering), falling back to the
box's existing Chrome only if Chromium isn't present.

`enable_sandbox=False` (`--no-sandbox`) is chromium's own default here, not
a weakening this module adds: Chrome's *internal* sandbox exists to protect
the host from a hostile *webpage* — it doesn't apply to a fixed local HTML
harness rendering a JSON chart spec with no network access and no
navigation, and it routinely fails to initialize inside an outer namespace
sandbox like `bwrap`'s anyway (the same reason Docker/CI headless-Chrome
setups disable it). The real boundary here is that this process never
navigates anywhere and never runs model-authored code.

ponytail: not run under its own bwrap network-namespace wrapper — it never
executes model output and kaleido bundles plotly.js locally, so it has
nothing to reach out to. Add one if that assumption ever needs enforcing
rather than trusting the absence of a script that calls out.
"""

import json
import shutil
from pathlib import Path

import structlog
from kaleido import Kaleido

logger = structlog.get_logger()

_CHROMIUM_EXE_NAMES = ("chromium", "chromium-browser")
_CHROME_FALLBACK_PATHS = (
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
    "/opt/google/chrome/google-chrome",
)


def _find_browser_path() -> str | None:
    for name in _CHROMIUM_EXE_NAMES:
        found = shutil.which(name)
        if found:
            return found
    for path in _CHROME_FALLBACK_PATHS:
        if Path(path).is_file():
            return path
    return None


class StaticRenderer:
    def __init__(self) -> None:
        self._kaleido: Kaleido | None = None

    def is_available(self) -> bool:
        return self._kaleido is not None

    async def start(self) -> None:
        if self._kaleido is not None:
            return
        path = _find_browser_path()
        if path is None:
            logger.warning("no chromium/chrome binary found — static chart export disabled")
            return
        kaleido = Kaleido(path=path, headless=True, enable_sandbox=False)
        await kaleido.open()
        self._kaleido = kaleido
        logger.info("static renderer started", browser_path=path)

    async def stop(self) -> None:
        if self._kaleido is not None:
            await self._kaleido.close()
            self._kaleido = None

    async def render(self, plotly_json: str, fmt: str) -> bytes:
        if self._kaleido is None:
            raise RuntimeError("StaticRenderer.start() was not called or found no browser")
        fig = json.loads(plotly_json)
        result: bytes = await self._kaleido.calc_fig(fig, opts={"format": fmt})
        return result


_renderer: StaticRenderer | None = None


def get_renderer() -> StaticRenderer:
    global _renderer
    if _renderer is None:
        _renderer = StaticRenderer()
    return _renderer
