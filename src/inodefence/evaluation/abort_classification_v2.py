"""v2 abort classification: the builder's USTAR refusals as their own category.

``abort_classification.InvalidReason`` is not extended: ``scripts/analyze_exp0.py`` (a
file the preregistration points at, byte-identical on ``main``) keeps a fallback list
that must name every ``InvalidReason`` value and derives its abort vocabulary from the
enum, so a new member would change that file's output. v2 classifies through this
module instead; the registered path keeps classifying these aborts as ``other``.

The two phrases are the TAR builder's own messages (``builder.build_tar``), not target
output and not tied to any CVE, path or target.
"""

from __future__ import annotations

from inodefence.evaluation.abort_classification import classify_abort_reason

BUILD_INVALID = "build_invalid"

_BUILD_INVALID_SIGNATURES: tuple[str, ...] = (
    "cannot be represented in USTAR",
    "USTAR name/prefix split would change the raw path",
)


def is_build_invalid_reason(reason: str) -> bool:
    if not isinstance(reason, str):
        raise TypeError("abort reason must be a string")
    return any(phrase in reason for phrase in _BUILD_INVALID_SIGNATURES)


def classify_abort_reason_v2(reason: str) -> str:
    """``build_invalid`` for a builder refusal, else ``classify_abort_reason``'s value."""
    if is_build_invalid_reason(reason):
        return BUILD_INVALID
    return classify_abort_reason(reason).value
