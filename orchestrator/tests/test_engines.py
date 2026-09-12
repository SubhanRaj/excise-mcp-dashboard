"""engines/base.py registry + engines/python_engine.py availability."""

import pytest

from app.engines import base as engines_base
from app.engines.matlab_engine import MatlabEngine
from app.engines.python_engine import PythonEngine
from app.engines.wolfram_engine import WolframEngine
from app.schemas import EngineUnavailableError


class _UnavailableEngine:
    name = "unavailable"
    supported_outputs: frozenset[str] = frozenset()

    def is_available(self) -> bool:
        return False

    async def render(self, req: object) -> object:  # pragma: no cover - never reached
        raise AssertionError("should not be called")


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    engines_base._ENGINES.clear()
    yield
    engines_base._ENGINES.clear()


def test_python_engine_is_available() -> None:
    assert PythonEngine().is_available() is True


def test_get_registered_available_engine() -> None:
    engines_base.register(PythonEngine())
    engine = engines_base.get("python")
    assert engine.name == "python"


def test_get_unregistered_engine_raises_typed_error() -> None:
    with pytest.raises(EngineUnavailableError):
        engines_base.get("octave")


def test_get_registered_but_unavailable_engine_raises_typed_error() -> None:
    engines_base.register(_UnavailableEngine())  # type: ignore[arg-type]
    with pytest.raises(EngineUnavailableError):
        engines_base.get("unavailable")


def test_available_lists_only_available_engines() -> None:
    engines_base.register(PythonEngine())
    engines_base.register(_UnavailableEngine())  # type: ignore[arg-type]
    assert engines_base.available() == ["python"]


async def test_matlab_stub_is_unavailable_and_raises_on_render() -> None:
    engine = MatlabEngine()
    assert engine.is_available() is False
    with pytest.raises(EngineUnavailableError):
        await engine.render(object())  # type: ignore[arg-type]


async def test_wolfram_stub_is_unavailable_and_raises_on_render() -> None:
    engine = WolframEngine()
    assert engine.is_available() is False
    with pytest.raises(EngineUnavailableError):
        await engine.render(object())  # type: ignore[arg-type]
