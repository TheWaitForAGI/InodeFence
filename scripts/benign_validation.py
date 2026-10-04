"""Guards for the approved pre-audit smoke only; never a generic Oracle policy."""

from pathlib import Path, PurePosixPath

from inodefence.model import ArchiveCase, RunResult, canonical_json
from inodefence.model.provenance import ExecutionProvenance


class UnexpectedContractEvidence(RuntimeError):
    """Preserve raw evidence and stop this engineering validation."""


def validate_benign_case(case: ArchiveCase) -> None:
    """Require ordinary relative POSIX path/link spelling before target execution.

    This small input-domain guard does not prove extractor security. The approved
    fixed seeds/budget and enforced container boundary remain necessary.
    """
    for entry in case.entries:
        for text in (entry.path, entry.link_target):
            if text is not None:
                spelling = PurePosixPath(text)
                if not text or spelling.is_absolute() or ".." in spelling.parts or "\\" in text:
                    raise ValueError("benign smoke requires ordinary relative paths and links")


def preserve_unexpected(
    result: RunResult,
    provenance: ExecutionProvenance,
    experiment_json: str,
    destination: Path,
) -> None:
    """Preserve the already-recorded facts; never reconstruct execution conditions."""
    if any(verdict.violated for verdict in result.violations):
        destination.mkdir(mode=0o700, parents=True, exist_ok=False)
        for name, text in (
            ("unexpected-run.json", canonical_json(result)),
            ("provenance.json", canonical_json(provenance)),
            ("experiment.json", experiment_json),
        ):
            (destination / name).write_text(text + "\n", encoding="ascii")
        raise UnexpectedContractEvidence("unexpected benign contract evidence preserved; stopped")
