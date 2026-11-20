"""Record-only summary of the two additive detectors for one run (D-258, series
``additive-detectors-v1 (record-only)``).

The oracle's C0/C1/C2 verdict comes from :func:`inodefence.oracle.evaluate_contracts` alone. This
module never calls it and never changes its result, the violation fingerprints or any feedback
input: it reads the run's AFTER snapshot and calls the two additive detectors, which are defined
not to touch that tuple either (:func:`inodefence.oracle.generalized_identity_confinement`,
:func:`inodefence.oracle.symlink_referent_confinement`).

What a value means:

* ``generalized_identity``: extraction objects sharing (st_dev, st_ino) with a non-extraction
  object. Physical, but only over the objects the AFTER snapshot holds; ``0`` means none among
  those, not none anywhere.
* ``symlink_referent``: extraction symlinks whose raw target, resolved LEXICALLY against the
  link's own directory, leaves the extraction root. ``0`` is a lexical proxy: a chain that only
  leaves the root by following a symlink created earlier on disk reads as inside the root.
* A count above zero is a candidate-screening signal, not a violation and not a confirmed issue.

No path is written to the record. ``evidence_sha256`` is a digest over the evidence with
sandbox-relative paths (as the snapshot records them), keys sorted, and a fixed field set per
detector; device and inode numbers are left out because they differ between runs.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from inodefence.model import StateSnapshot
from inodefence.oracle import generalized_identity_confinement, symlink_referent_confinement

SCHEMA = "additive-detectors-v1"
#: The series name for tables and the run ledger. Kept apart from C0/C1/C2; never pooled.
SERIES = "additive-detectors-v1 (record-only)"
#: How each detector decides, for tables and the ledger.
BASIS = {"generalized_identity": "physical", "symlink_referent": "lexical"}
#: The fixed field set each evidence item contributes to ``evidence_sha256``.
IDENTITY_FIELDS = ("internal_path", "external_path")
REFERENT_FIELDS = ("internal_path", "referent_target", "referent_region")
DETECTORS = tuple(BASIS)
#: The region-list field each detector's block carries.
REGIONS_KEY = {"generalized_identity": "external_regions", "symlink_referent": "referent_regions"}


def evidence_digest(after: StateSnapshot) -> str:
    """sha256 of the canonical JSON of both detectors' evidence (paths sandbox-relative)."""
    identity = [
        {field: str(getattr(item, field)) for field in IDENTITY_FIELDS}
        for item in generalized_identity_confinement(after)
    ]
    referent = [
        {field: str(getattr(item, field)) for field in REFERENT_FIELDS}
        for item in symlink_referent_confinement(after)
    ]
    document = {"generalized_identity": identity, "symlink_referent": referent}
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(encoded.encode("utf-8")).hexdigest()


def additive_detector_fields(after: StateSnapshot) -> dict[str, Any]:
    """The ``additive_detectors`` record of one run: counts, regions, basis and a digest."""
    identity = generalized_identity_confinement(after)
    referent = symlink_referent_confinement(after)
    return {
        "schema": SCHEMA,
        "generalized_identity": {
            "count": len(identity),
            "external_regions": sorted({item.external_region.value for item in identity}),
            "basis": BASIS["generalized_identity"],
        },
        "symlink_referent": {
            "count": len(referent),
            "referent_regions": sorted({item.referent_region.value for item in referent}),
            "basis": BASIS["symlink_referent"],
        },
        "evidence_sha256": evidence_digest(after),
    }


def check_fields(value: Any) -> dict[str, Any]:
    """Validate a recorded ``additive_detectors`` value; return it unchanged or raise ValueError."""
    if not isinstance(value, dict) or set(value) != {"schema", *DETECTORS, "evidence_sha256"}:
        raise ValueError("additive_detectors must hold schema, both detectors and evidence_sha256")
    if value["schema"] != SCHEMA:
        raise ValueError(f"additive_detectors schema must be {SCHEMA}")
    regions_key = REGIONS_KEY
    for name in DETECTORS:
        block = value[name]
        if not isinstance(block, dict) or set(block) != {"count", regions_key[name], "basis"}:
            raise ValueError(f"additive_detectors.{name} has the wrong fields")
        if type(block["count"]) is not int or block["count"] < 0:
            raise ValueError(f"additive_detectors.{name}.count must be a nonnegative integer")
        regions = block[regions_key[name]]
        if not isinstance(regions, list) or not all(isinstance(r, str) for r in regions):
            raise ValueError(f"additive_detectors.{name}.{regions_key[name]} must be strings")
        if block["basis"] != BASIS[name]:
            raise ValueError(f"additive_detectors.{name}.basis must be {BASIS[name]}")
    digest = value["evidence_sha256"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("additive_detectors.evidence_sha256 must be a sha256 hex digest")
    return value
