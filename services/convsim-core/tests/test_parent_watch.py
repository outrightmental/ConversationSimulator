# SPDX-License-Identifier: Apache-2.0
"""Tests for the launcher-exit watch (issue #485).

The desktop shell spawns convsim-core with a pipe on stdin and holds the write
end for its own lifetime. When the shell goes away the kernel closes it, the
read side reports EOF, and the engine must shut itself down gracefully — that
teardown is what stops the supervised sidecars instead of orphaning them and
leaving Steam convinced the game is still running.
"""
from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
import threading

import pytest

from convsim_core import parent_watch

#: Generous upper bound for a thread that is only waiting on a closed pipe.
_WAIT = 5.0

_ENABLED = {parent_watch.ENV_VAR: "1"}


def _pipe() -> tuple[io.BufferedReader, io.BufferedWriter]:
    """A real OS pipe, as the launcher would hand us."""
    read_fd, write_fd = os.pipe()
    return os.fdopen(read_fd, "rb", buffering=0), os.fdopen(write_fd, "wb", buffering=0)


# ── Enablement ───────────────────────────────────────────────────────────────


def test_disabled_without_the_env_var():
    """Unset is off: a bare `convsim-core` run has a TTY or /dev/null on stdin."""
    assert parent_watch.is_enabled({}) is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " 1 "])
def test_truthy_values_enable_the_watch(value):
    assert parent_watch.is_enabled({parent_watch.ENV_VAR: value}) is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
def test_other_values_leave_it_off(value):
    assert parent_watch.is_enabled({parent_watch.ENV_VAR: value}) is False


def test_watch_is_a_no_op_when_disabled():
    """No thread, and crucially no callback, when the launcher did not opt in."""
    reader, writer = _pipe()
    fired = threading.Event()
    try:
        assert parent_watch.watch_parent_exit(fired.set, stream=reader, env={}) is None
        writer.close()
        assert not fired.wait(0.5), "the watch fired despite being disabled"
    finally:
        reader.close()
        writer.close()


def test_watch_is_a_no_op_without_stdin():
    """A frozen GUI build can have sys.stdin is None — degrade, do not crash."""
    fired = threading.Event()
    real_stdin = sys.stdin
    sys.stdin = None  # type: ignore[assignment]
    try:
        assert parent_watch.watch_parent_exit(fired.set, env=_ENABLED) is None
    finally:
        sys.stdin = real_stdin
    assert not fired.is_set()


# ── The signal itself ────────────────────────────────────────────────────────


def test_shuts_down_when_the_launcher_closes_the_pipe():
    reader, writer = _pipe()
    fired = threading.Event()
    try:
        thread = parent_watch.watch_parent_exit(fired.set, stream=reader, env=_ENABLED)
        assert thread is not None and thread.daemon, (
            "the watch must be a daemon thread: its pending read cannot be cancelled "
            "and must never hold up interpreter shutdown"
        )
        assert not fired.wait(0.25), "fired while the launcher was still alive"
        writer.close()
        assert fired.wait(_WAIT), "EOF on stdin did not request a shutdown"
    finally:
        reader.close()
        writer.close()


def test_the_shutdown_log_line_is_plain_ascii(caplog):
    """The line docs/troubleshooting.md tells players to search for.

    It goes to the launcher's inherited stdout as well as the UTF-8 app.log,
    and on Windows that stream takes the console codepage. A codepage that
    cannot encode the character (cp932, cp437) turns the record into a
    logging-error traceback — losing the one line that says the engine heard
    the shutdown request.
    """
    reader, writer = _pipe()
    fired = threading.Event()
    try:
        with caplog.at_level(logging.INFO, logger=parent_watch.__name__):
            thread = parent_watch.watch_parent_exit(fired.set, stream=reader, env=_ENABLED)
            writer.close()
            assert fired.wait(_WAIT)
            assert thread is not None
            thread.join(_WAIT)
        messages = [record.getMessage() for record in caplog.records]
        assert any("shutting down" in message for message in messages), (
            f"the shutdown was never logged; got {messages!r}"
        )
        for message in messages:
            message.encode("ascii")  # must not raise
    finally:
        reader.close()
        writer.close()


def test_data_on_stdin_is_not_mistaken_for_the_launcher_exiting():
    """Only EOF counts. A byte of input must not take the engine down."""
    reader, writer = _pipe()
    fired = threading.Event()
    try:
        parent_watch.watch_parent_exit(fired.set, stream=reader, env=_ENABLED)
        writer.write(b"x")
        writer.flush()
        assert not fired.wait(0.5), "a stdin byte was treated as the launcher exiting"
        writer.close()
        assert fired.wait(_WAIT), "EOF after the byte did not request a shutdown"
    finally:
        reader.close()
        writer.close()


def test_closed_stream_is_treated_as_the_launcher_being_gone():
    """An unreadable stdin must resolve, not park the watch on a dead pipe."""
    reader, writer = _pipe()
    writer.close()
    reader.close()
    fired = threading.Event()
    parent_watch.watch_parent_exit(fired.set, stream=reader, env=_ENABLED)
    assert fired.wait(_WAIT), "a closed stdin left the watch hanging"


def test_a_failing_callback_does_not_raise_out_of_the_thread():
    """A broken shutdown hook is logged, not left to kill the watch silently."""
    reader, writer = _pipe()
    done = threading.Event()

    def boom():
        done.set()
        raise RuntimeError("shutdown hook exploded")

    try:
        thread = parent_watch.watch_parent_exit(boom, stream=reader, env=_ENABLED)
        writer.close()
        assert done.wait(_WAIT)
        assert thread is not None
        thread.join(_WAIT)
        assert not thread.is_alive()
    finally:
        reader.close()
        writer.close()


# ── End to end: a child process really does exit when its parent does ────────


def _watcher_program(tail: str) -> str:
    """Source for a child that installs the watch, then runs *tail*.

    *tail* can use ``done``, an Event the watch sets when the pipe closes.
    """
    return (
        "import sys, threading;"
        "sys.path.insert(0, %r);"
        "from convsim_core import parent_watch;"
        "done = threading.Event();"
        "t = parent_watch.watch_parent_exit(done.set, env={parent_watch.ENV_VAR: '1'});"
        "assert t is not None;" + tail
    ) % os.path.dirname(os.path.dirname(os.path.abspath(parent_watch.__file__)))


def test_exiting_while_the_launcher_is_still_there_keeps_its_exit_code():
    """The engine can exit for reasons other than its launcher going away.

    uvicorn exits non-zero when startup fails — a port conflict with an engine
    left over from a previous run, which is the very symptom of issue #485.
    That happens with the launcher's pipe still open, so the watch thread is
    parked in its read. Read through a buffered reader and the daemon thread
    holds that object's lock, interpreter shutdown cannot close ``sys.stdin``,
    and CPython aborts the process after a one-second stall:

        Fatal Python error: _enter_buffered_busy: could not acquire lock for
        <_io.BufferedReader name='<stdin>'> at interpreter shutdown

    which replaces the exit code the launcher reads with SIGABRT, and the
    reason the engine could not start with a fatal runtime error at the end of
    app.log — where docs/troubleshooting.md tells players to look.
    """
    # The pause lets the watch thread reach its blocking read before the exit:
    # that is the state the hazard needs, and the state a real engine is always
    # in by the time startup fails, having spent far longer than this booting.
    proc = subprocess.Popen(
        [sys.executable, "-c", _watcher_program("import time; time.sleep(0.5); sys.exit(3)")],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        # wait(), never communicate(): with no input to send, communicate()
        # closes stdin — which is the one thing this test must not do. The pipe
        # stays open, as a live launcher's would.
        proc.wait(timeout=30)
        assert proc.stderr is not None
        stderr = proc.stderr.read().decode("utf-8", "replace")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if proc.stderr is not None:
            proc.stderr.close()
        if proc.stdin is not None:
            proc.stdin.close()

    assert "Fatal Python error" not in stderr, (
        f"the watch thread wedged interpreter shutdown:\n{stderr}"
    )
    assert proc.returncode == 3, (
        f"expected the process's own exit code 3, got {proc.returncode} "
        f"(a negative value is a signal); stderr:\n{stderr}"
    )


def test_child_process_exits_when_its_parent_closes_the_pipe():
    """The whole mechanism, over a real pipe between two real processes.

    This is the shape of what the Tauri shell does: spawn with stdin=PIPE, then
    let the handle close. No signal is sent and no PID is polled — closing the
    write end is the entire shutdown request.
    """
    program = _watcher_program("done.wait(30); sys.exit(0 if done.is_set() else 1)")

    proc = subprocess.Popen(
        [sys.executable, "-c", program],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            proc.wait(timeout=1.0)  # still running: the pipe is open
        assert proc.stdin is not None
        proc.stdin.close()
        assert proc.wait(timeout=30) == 0, "child did not shut down after its stdin closed"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if proc.stderr is not None:
            proc.stderr.close()
