"""v2 holdout reservation ranges (data only; read by ``inodefence.sealed_lineage``).

These versions are reserved as v2 holdout candidates: the product CLI refuses to explore,
replay or prepare them, and allows ``verify`` only as a ledgered fixed-input qualification run.

Source of truth is RESERVED.md on the team Drive. Change this file only together with a new
RESERVED version: update ``RESERVED_SOURCE`` (document and its sha256) and ``RESERVED`` in the
same commit, after the release rule of RESERVED (ledger note first, reason in #510, W4 check).
Never edit a host file instead.

Rows are ``(id, target, min, below)``; the range is ``[min, below)`` in SemVer order.
"""

RESERVED_SOURCE: tuple[str, str] = (
    "Drive Research/01-분석·설계(#507 #508 #509 #510)/"
    "20261118-HOST1-510-v2-holdout-예약/RESERVED.md v1.2",
    "90017217352b54d9f35454375377c260f0a9e8f83a59d79de1841c46e0a56835",
)

RESERVED: tuple[tuple[str, str, str, str], ...] = (
    ("v2-R-A", "node-tar", "7.0.0", "7.4.4"),  # 7.0.0 ~ 7.4.3 (7.0.1-7.3.0 included)
    ("v2-R-B", "node-tar", "6.0.0", "6.2.2"),  # 6.0.0 ~ 6.2.1
    ("v2-R-C", "node-tar", "4.4.0", "5.1.0"),  # 4.4.0 ~ 5.0.x
)
