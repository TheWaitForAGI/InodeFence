"""v2 G1 gate over a launcher output folder; writes ``<output>/summaries-v2/g1-v2.json``.

Reads the launcher's ``summaries/index.json`` and each cell's own report/steps files; never
writes into ``summaries/`` (the registered tool chain's output stays byte-identical). See
``inodefence.evaluation.g1_v2`` for the checks. Exit status: 0 pass, 1 fail, 2 pass with groups
to review (unverifiable checks, or seed corpus cells incomplete).

    PYTHONPATH=src python -m scripts.check_g1_v2 --output <launcher output folder>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from inodefence.evaluation.g1_v2 import check_output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    document = check_output(args.output)
    target = args.output / "summaries-v2" / "g1-v2.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="ascii"
    )
    status = "pass" if document["pass"] else "FAIL"
    review = " (review required)" if document["review_required"] else ""
    print(f"g1-v2: {status}{review} -> {target}")
    if not document["pass"]:
        return 1
    return 2 if document["review_required"] else 0


if __name__ == "__main__":
    sys.exit(main())
