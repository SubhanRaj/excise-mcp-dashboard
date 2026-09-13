"""engines/static_render.py: browser-path preference and a real render.
SECURITY.md §Static image export.
"""

import json

import pytest

from app.engines.static_render import StaticRenderer, _find_browser_path, get_renderer

_BROWSER_PATH = _find_browser_path()


def test_prefers_chromium_over_chrome(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.engines.static_render.shutil.which",
        lambda name: "/usr/bin/chromium" if name == "chromium" else None,
    )
    monkeypatch.setattr("app.engines.static_render.Path.is_file", lambda self: True)
    assert _find_browser_path() == "/usr/bin/chromium"


def test_falls_back_to_chrome_when_no_chromium_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.engines.static_render.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "app.engines.static_render.Path.is_file",
        lambda self: str(self) == "/usr/bin/google-chrome-stable",
    )
    assert _find_browser_path() == "/usr/bin/google-chrome-stable"


def test_returns_none_when_nothing_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.engines.static_render.shutil.which", lambda name: None)
    monkeypatch.setattr("app.engines.static_render.Path.is_file", lambda self: False)
    assert _find_browser_path() is None


async def test_render_before_start_raises() -> None:
    renderer = StaticRenderer()
    with pytest.raises(RuntimeError):
        await renderer.render(json.dumps({"data": [], "layout": {}}), "png")


def test_get_renderer_returns_the_same_singleton() -> None:
    assert get_renderer() is get_renderer()


@pytest.mark.skipif(_BROWSER_PATH is None, reason="no chromium/chrome binary on this box")
async def test_live_render_produces_real_png_bytes() -> None:
    renderer = StaticRenderer()
    try:
        await renderer.start()
        assert renderer.is_available()
        fig = {"data": [{"type": "bar", "x": ["a", "b"], "y": [1, 2]}], "layout": {}}
        png_bytes = await renderer.render(json.dumps(fig), "png")
        assert png_bytes.startswith(b"\x89PNG")
        assert len(png_bytes) > 100
    finally:
        await renderer.stop()
