"""Measure this host's realtime clock offset to an NTP server (SNTP), for the cross-host record.

D047 (W4, 2026-11-11): each host, inside WSL, asks the same NTP server five times with a plain
UDP socket; the sample with the shortest round trip gives the offset. The two hosts' files are
combined later (``combine``: the difference and its uncertainty). Measured at the start and end
of the qualification run, at freeze and at GO. A record only, never a verdict input. The only
network use is the NTP query.

    python -m scripts.measure_clock_offset --server pool.ntp.org --host-id HOST1 --out H1.json
    python -m scripts.run_exp0 ... --clock-reference H1.json

``offset_s`` is server time minus this host's clock (positive: this clock is behind). For two
hosts, ``diff_s = offset_HOST2 - offset_HOST1`` equals ``clock_HOST1 - clock_HOST2``, and the
uncertainty is the sum of the chosen samples' half round trips.
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

METHOD = "sntp-v1"
SCHEMA = "inodefence-clock-offset-v1"
SAMPLES = 5
NTP_PORT = 123
NTP_EPOCH_OFFSET = 2208988800  # 1900-01-01 to 1970-01-01, seconds
TIMEOUT_SECONDS = 5.0


def _from_ntp(data: bytes, at: int) -> float:
    seconds, fraction = struct.unpack("!II", data[at : at + 8])
    return seconds - NTP_EPOCH_OFFSET + fraction / 2**32


def query(server: str, clock: Callable[[], float] = time.time) -> dict[str, float]:
    """One SNTP exchange: offset and round trip (RFC 4330 formulas)."""
    packet = b"\x23" + 47 * b"\0"  # LI 0, version 4, mode 3 (client)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(TIMEOUT_SECONDS)
        t1 = clock()
        sock.sendto(packet, (server, NTP_PORT))
        data, _ = sock.recvfrom(1024)
        t4 = clock()
    if len(data) < 48:
        raise ValueError(f"short NTP reply ({len(data)} bytes)")
    t2, t3 = _from_ntp(data, 32), _from_ntp(data, 40)
    return {"offset_s": ((t2 - t1) + (t3 - t4)) / 2, "rtt_s": (t4 - t1) - (t3 - t2)}


def measure(
    server: str,
    host_id: str,
    *,
    samples: int = SAMPLES,
    ask: Callable[[str], Mapping[str, float]] = query,
    pause: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    taken: list[dict[str, Any]] = []
    for index in range(samples):
        try:
            taken.append({"index": index, **ask(server)})
        except (OSError, ValueError) as error:
            taken.append({"index": index, "error": f"{type(error).__name__}: {error}"})
        if index + 1 < samples:
            pause(0.2)
    good = [sample for sample in taken if "offset_s" in sample]
    if not good:
        raise RuntimeError(f"no NTP reply from {server} in {samples} tries")
    chosen = min(good, key=lambda sample: sample["rtt_s"])
    return {
        "schema": SCHEMA,
        "method": METHOD,
        "server": server,
        "host_id": host_id,
        "measured_at": datetime.now(UTC).isoformat(),
        "samples": taken,
        "chosen": chosen,
        "offset_s": chosen["offset_s"],
        "uncertainty_s": chosen["rtt_s"] / 2,
    }


def combine(first: Mapping[str, Any], second: Mapping[str, Any]) -> dict[str, Any]:
    """Two hosts' measurements: ``diff_s = offset_HOST2 - offset_HOST1`` and its uncertainty."""
    by_host = {str(m["host_id"]): m for m in (first, second)}
    if set(by_host) != {"HOST1", "HOST2"}:
        raise ValueError(f"need one HOST1 and one HOST2 measurement, got {sorted(by_host)}")
    if by_host["HOST1"]["server"] != by_host["HOST2"]["server"]:
        raise ValueError("the two hosts asked different NTP servers")
    h1, h2 = by_host["HOST1"], by_host["HOST2"]
    return {
        "method": METHOD,
        "server": h1["server"],
        "samples": {"HOST1": len(h1["samples"]), "HOST2": len(h2["samples"])},
        "chosen": {"HOST1": h1["chosen"], "HOST2": h2["chosen"]},
        "diff_s": float(h2["offset_s"]) - float(h1["offset_s"]),
        "uncertainty_s": float(h1["uncertainty_s"]) + float(h2["uncertainty_s"]),
        "measured_at": {"HOST1": h1["measured_at"], "HOST2": h2["measured_at"]},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--server", required=True, help="the NTP server both hosts ask")
    parser.add_argument("--host-id", choices=("HOST1", "HOST2"), required=True)
    parser.add_argument("--samples", type=int, default=SAMPLES)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        document = measure(args.server, args.host_id, samples=args.samples)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: document[k] for k in ("offset_s", "uncertainty_s", "measured_at")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
