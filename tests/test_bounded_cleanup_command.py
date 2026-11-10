"""The timeout kills only the isolated CLI process group."""

import sys
import time

from scripts.bounded_cleanup_command import run


def test_timeout_kills_cli_ignoring_sigterm() -> None:
    started = time.monotonic()
    result = run(
        [
            sys.executable,
            "-c",
            "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)",
        ],
        0.2,
        1,
    )
    assert result == 124
    assert time.monotonic() - started < 3


def test_success_and_nonzero_are_preserved() -> None:
    assert run([sys.executable, "-c", "pass"], 2) == 0
    assert run([sys.executable, "-c", "raise SystemExit(37)"], 2) == 37
