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
    "20261118-HOST1-510-v2-holdout-예약/RESERVED.md v2.0 (해제)",
    "f5bb23c95269f9be992df155ae413c0305d336da08ab05815b810287e898409c",
)

#: Empty since RESERVED v2.0 (2026-11-18, W4): the v2 confirmatory line ended by its stopping rule
#: (v2.1 power NO-GO), so R-A [7.0.0, 7.4.4), R-B [6.0.0, 6.2.2) and R-C [4.4.0, 5.1.0) of
#: RESERVED v1.2 (sha256 90017217…) were released. Sealed-run locks still apply.
RESERVED: tuple[tuple[str, str, str, str], ...] = ()
