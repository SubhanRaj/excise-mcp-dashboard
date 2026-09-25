"""sandbox/bwrap.py against the real bwrap + systemd-run on this box.
SECURITY.md §2. ROADMAP.md Milestone 2 tests: wallclock kill, no network,
no write outside /scratch, memory cap.
"""

import asyncio
import contextlib
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

from app.config import settings
from app.sandbox.bwrap import cleanup_scratch, run_in_sandbox, stop_orphaned_sandbox_scopes
from app.schemas import SandboxTimeoutError, SandboxViolationError


async def _active_sandbox_scopes() -> list[str]:
    proc = await asyncio.create_subprocess_exec(
        "systemctl",
        "--user",
        "list-units",
        "--type=scope",
        "--state=active",
        "--no-legend",
        "--plain",
        "excise-sandbox-*.scope",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout_bytes, _ = await proc.communicate()
    return [line.split()[0] for line in stdout_bytes.decode().splitlines() if line.strip()]


@pytest.fixture
def data_path() -> Iterator[Path]:
    fd, path_str = tempfile.mkstemp(suffix=".parquet")
    path = Path(path_str)
    pd.DataFrame({"a": [1, 2, 3]}).to_parquet(path)
    yield path
    path.unlink(missing_ok=True)


async def test_wallclock_timeout_kills_script(
    data_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


async def test_violation_message_is_the_tracebacks_last_line_only(data_path: Path) -> None:
    # Confirmed live: a make_chart script that referenced a wrong column name came
    # back with pandas/plotly's whole internal traceback as the tool result — dozens
    # of stack frames with no use to a model trying to self-correct, when the one
    # actionable line was already the traceback's own last one.
    script = (
        "def inner():\n"
        "    raise ValueError('the real reason')\n"
        "def outer():\n"
        "    inner()\n"
        "outer()\n"
    )
    with pytest.raises(SandboxViolationError) as excinfo:
        await run_in_sandbox(script=script, data_path=data_path)

    message = str(excinfo.value)
    assert message.endswith("ValueError: the real reason")
    assert "Traceback" not in message
    assert "in inner" not in message
    assert "in outer" not in message


async def test_violation_message_keeps_a_multi_line_exception_from_its_own_start(
    data_path: Path,
) -> None:
    # Confirmed live: a make_chart script's Plotly ValueError (its own schema
    # validation, not a plain exception) printed the real description across
    # several lines, ending in a trailing location pointer ("    chart at line 6
    # column 1") with no "Error:" prefix of its own — the old last-line-only
    # summary grabbed that pointer alone, useless to the model retrying. The
    # summary now starts at the traceback's actual "ValueError: ..." line and
    # keeps what follows, since that's exactly the shape a multi-line message needs.
    script = (
        "raise ValueError(\n"
        "    'Invalid value of type str received for the x property.\\n'\n"
        "    '    Received value: bad\\n'\n"
        "    '\\n'\n"
        "    '    chart at line 6 column 1'\n"
        ")\n"
    )
    with pytest.raises(SandboxViolationError) as excinfo:
        await run_in_sandbox(script=script, data_path=data_path)

    message = str(excinfo.value)
    assert "ValueError: Invalid value of type str received for the x property." in message
    assert "chart at line 6 column 1" in message


async def test_violation_message_finds_the_exception_line_even_past_4000_characters(
    data_path: Path,
) -> None:
    # Confirmed live: a real Plotly schema-validation error (an invalid trace
    # property) runs to several thousand characters on its own -- long enough
    # that its "ValueError: ..." line landed entirely outside the raw stdout's
    # last 4000 characters. The search used to run against that pre-truncated
    # tail, so it found no exception line at all and silently fell back to
    # whatever short fragment happened to survive the cut -- reproducing the
    # exact symptom the multi-line fix above was supposed to close. The search
    # now runs against the untruncated output.
    script = "msg = 'the real reason. ' + ('y' * 4500)\nraise ValueError(msg)\n"
    with pytest.raises(SandboxViolationError) as excinfo:
        await run_in_sandbox(script=script, data_path=data_path)

    message = str(excinfo.value)
    assert "ValueError: the real reason." in message


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


async def test_cancelling_the_render_kills_the_sandboxed_scope(data_path: Path) -> None:
    # A client disconnect or the orchestrator shutting down cancels the awaiting
    # coroutine — confirmed live that this used to leave the scope running (and
    # holding its memory cgroup) until its own 15s wallclock timeout, or forever if
    # the orchestrator itself got SIGKILLed first. run_in_sandbox must kill it
    # immediately on cancellation instead.
    script = "import time\ntime.sleep(30)\n"
    task = asyncio.create_task(run_in_sandbox(script=script, data_path=data_path))
    await asyncio.sleep(1)  # let bwrap actually start before cancelling
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.5)  # give systemd a moment to report the scope as gone
    assert await _active_sandbox_scopes() == []


async def test_stop_orphaned_sandbox_scopes_stops_a_leaked_one() -> None:
    # Simulates what a prior orchestrator's SIGKILL leaves behind: a scope with
    # our naming convention, still running, with nothing left to wait on it.
    leaked = await asyncio.create_subprocess_exec(
        "systemd-run",
        "--user",
        "--scope",
        "--collect",
        "--unit=excise-sandbox-test-leaked.scope",
        "--",
        "sleep",
        "30",
    )
    try:
        await asyncio.sleep(1)
        assert "excise-sandbox-test-leaked.scope" in await _active_sandbox_scopes()
        await stop_orphaned_sandbox_scopes()
        assert await _active_sandbox_scopes() == []
    finally:
        with contextlib.suppress(ProcessLookupError):
            leaked.kill()
            await leaked.wait()


async def test_successful_script_writes_output(data_path: Path) -> None:
    script = 'open(f"{OUT}/chart.plotly.json", "w").write("{}")\n'
    scratch_dir, _stdout_tail = await run_in_sandbox(
        script="OUT = '/scratch'\n" + script, data_path=data_path
    )
    try:
        assert (scratch_dir / "chart.plotly.json").exists()
    finally:
        cleanup_scratch(scratch_dir)
