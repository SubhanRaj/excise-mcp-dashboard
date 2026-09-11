"""sandbox/bwrap.py against the real bwrap + systemd-run on this box.
SECURITY.md §2. ROADMAP.md Milestone 2 tests: wallclock kill, no network,
no write outside /scratch, memory cap.
"""

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

from app.config import settings
from app.sandbox.bwrap import cleanup_scratch, run_in_sandbox
from app.schemas import SandboxTimeoutError, SandboxViolationError


@pytest.fixture
def data_path() -> Iterator[Path]:
    fd, path_str = tempfile.mkstemp(suffix=".parquet")
    path = Path(path_str)
    pd.DataFrame({"a": [1, 2, 3]}).to_parquet(path)
    yield path
    path.unlink(missing_ok=True)


async def test_wallclock_timeout_kills_script(data_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sandbox_wallclock_seconds", 2)
    script = "import time\ntime.sleep(30)\n"
    with pytest.raises(SandboxTimeoutError):
        await run_in_sandbox(script=script, data_path=data_path)


async def test_no_network(data_path: Path) -> None:
    script = (
        "import socket\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "s.settimeout(2)\n"
        "s.connect(('8.8.8.8', 53))\n"
    )
    with pytest.raises(SandboxViolationError):
        await run_in_sandbox(script=script, data_path=data_path)


async def test_write_outside_scratch_fails(data_path: Path) -> None:
    script = "open('/usr/should-not-be-writable.txt', 'w').write('x')\n"
    with pytest.raises(SandboxViolationError):
        await run_in_sandbox(script=script, data_path=data_path)


async def test_memory_cap(data_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sandbox_memory_mb", 64)
    # b"1" * n forces real page commits (unlike bytearray(n), which CPython
    # backs with the shared zero page until written and so never touches the
    # cgroup's memory.max) — 300MB of real pages against a 64MB cap.
    script = "x = bytearray(b'1' * (300 * 1024 * 1024))\n"
    # a cgroup OOM-kill and the wallclock `timeout --signal=KILL` both exit via
    # SIGKILL, so this can surface as either typed error — see bwrap.py's
    # _TIMEOUT_EXIT_CODES note.
    with pytest.raises((SandboxTimeoutError, SandboxViolationError)):
        await run_in_sandbox(script=script, data_path=data_path)


async def test_successful_script_writes_output(data_path: Path) -> None:
    script = 'open(f"{OUT}/chart.plotly.json", "w").write("{}")\n'
    scratch_dir, _stdout_tail = await run_in_sandbox(
        script="OUT = '/scratch'\n" + script, data_path=data_path
    )
    try:
        assert (scratch_dir / "chart.plotly.json").exists()
    finally:
        cleanup_scratch(scratch_dir)
