"""`inodefence dashboard` stops on Ctrl-C (SIGINT) with exit 0 even while a browser holds the live
event stream (SSE) open. A real server process; no extractor runs and nothing is written.
"""

from __future__ import annotations

import http.client
import signal
import socket
import subprocess
import sys
import threading
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

DEADLINE_SECONDS = 10.0  # the server's graceful shutdown is 3 s; generous for a slow CI host


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_listening(port: int, server: subprocess.Popen[str]) -> None:
    for _ in range(120):
        if server.poll() is not None:
            raise AssertionError(f"dashboard exited early: {server.returncode}")
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return
        except OSError:
            time.sleep(0.25)
    raise AssertionError("dashboard did not start listening")


def _hold_event_stream(port: int, opened: threading.Event) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        conn.request("GET", "/api/events", headers={"Accept": "text/event-stream"})
        response = conn.getresponse()
        assert response.status == 200
        opened.set()
        while response.read(1):
            pass
    except Exception:  # noqa: BLE001 - the server going away ends the stream
        opened.set()


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT to a child process is POSIX here")
def test_sigint_stops_the_dashboard_with_an_open_event_stream(tmp_path) -> None:
    port = _free_port()
    server = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; from inodefence.cli import main; sys.exit(main(sys.argv[1:]))",
            "dashboard",
            str(tmp_path),
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_listening(port, server)
        opened = threading.Event()
        threading.Thread(target=_hold_event_stream, args=(port, opened), daemon=True).start()
        assert opened.wait(10), "the event stream did not open"
        time.sleep(0.5)
        started = time.monotonic()
        server.send_signal(signal.SIGINT)
        code = server.wait(timeout=DEADLINE_SECONDS)
        assert code == 0, server.stderr.read() if server.stderr else ""
        assert time.monotonic() - started < DEADLINE_SECONDS
    finally:
        if server.poll() is None:
            server.kill()
            server.wait()
