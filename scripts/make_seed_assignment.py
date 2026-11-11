"""Write the seed assignment file of a two-host run from a registration's seeds.

The registered rules (``seed_assignment_rule``; ``inodefence.evaluation.seed_assignment``), all
over every registered seed and the participating hosts (``--participants``, default both):

* ``alternate-v1`` (train, fixed at freeze): registered order, alternating over the participants.
  No measured input. Its sha256 goes into the registration.
* ``replicate-v1`` (host qualification only): every participant gets every seed; compared across
  hosts, never pooled. Its sha256 goes into the registration.
* ``rh-proportional-v1`` (holdout, made at GO): HOST1 the first ``round_half_down(N·r1/(r1+r2))``
  seeds, HOST2 the rest, from ``rates_exec_per_hour`` in the GO decision file (the per-host ``r_h``
  text ``gen_exp3_tables --go-rates-out`` writes). With one participant it gets all seeds. Only
  infrastructure values go in. With ``--participants``, ``--rate-source HOST=<label>`` is required
  for every participant (no default: where an ``r_h`` comes from is a registered rule).
  ``--record-in-go-decision`` then adds the participants, the rate sources and the file's sha256
  to the GO decision file.

    python -m scripts.make_seed_assignment --preregistration exp3-v1.md --rule alternate-v1 --out A
    python -m scripts.make_seed_assignment --preregistration exp2-v1.md \\
        --rule rh-proportional-v1 --go-decision exp3-train-go-decision.json \\
        --rate-source HOST1=train-r_h --rate-source HOST2=train-r_h --record-in-go-decision --out B

The bytes are canonical, so the launcher and the merge tool regenerate them and accept only the
same file. The sha256 is printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from inodefence.evaluation.rds_preregistration import (
    PreregistrationFormatError,
    load_preregistration,
)
from inodefence.evaluation.seed_assignment import (
    HOST_IDS,
    RULE_ALTERNATE,
    RULE_REPLICATE,
    RULE_RH_PROPORTIONAL,
    RULES,
    SeedAssignmentError,
    assignment_bytes,
    parse_seed_assignment,
    rule_problems,
    split_alternate,
    split_by_rate,
    split_replicate,
)


def _pairs(items: Sequence[str], flag: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        host, sep, value = item.partition("=")
        if not sep or host not in HOST_IDS or not value or host in result:
            raise SeedAssignmentError(f"{flag} expects HOST=<value> once per host, got {item!r}")
        result[host] = value
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--rule", choices=RULES, required=True)
    parser.add_argument(
        "--participants",
        default=None,
        help="comma-separated participating hosts (default: both; written only when given)",
    )
    parser.add_argument("--go-decision", type=Path, help="rh-proportional-v1: GO decision file")
    parser.add_argument(
        "--rate-source",
        action="append",
        default=[],
        metavar="HOST=LABEL",
        help="rh-proportional-v1: where each participant's r_h comes from (required, no default)",
    )
    parser.add_argument(
        "--record-in-go-decision",
        action="store_true",
        help="rh-proportional-v1: add participants, rate sources and the sha256 to the GO file",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    holdout = args.rule == RULE_RH_PROPORTIONAL
    if holdout != (args.go_decision is not None):
        parser.error(f"--go-decision goes with --rule {RULE_RH_PROPORTIONAL}, and only with it")
    if (args.record_in_go_decision or args.rate_source) and not holdout:
        parser.error("--rate-source and --record-in-go-decision go with --go-decision")
    participants = None if args.participants is None else args.participants.split(",")
    try:
        prereg = load_preregistration(args.preregistration)
        seeds = prereg.seeds
        if prereg.seed_assignment_rule not in (None, args.rule):
            raise SeedAssignmentError(
                f"the registration names {prereg.seed_assignment_rule}, not {args.rule}"
            )
        go_decision = None
        if args.rule == RULE_ALTERNATE:
            document = split_alternate(seeds, participants)
        elif args.rule == RULE_REPLICATE:
            document = split_replicate(seeds, participants)
        else:
            go_decision = json.loads(args.go_decision.read_text(encoding="utf-8"))
            members = list(HOST_IDS) if participants is None else participants
            sources = _pairs(args.rate_source, "--rate-source")
            # With --participants the rate source is a registered rule question (a host that did
            # not run train has no train r_h): no default, every participant names its source.
            if (participants is not None or sources) and set(sources) != set(members):
                raise SeedAssignmentError(
                    f"--rate-source is required for exactly the participants {members}"
                )
            recorded = go_decision.get("participants")
            if recorded is not None and recorded != participants:
                raise SeedAssignmentError(
                    f"the GO decision file names participants {recorded}, not {participants}"
                )
            rates = go_decision["rates_exec_per_hour"]
            document = split_by_rate(
                seeds, len(seeds), {host: rates[host] for host in members}, participants
            )
            if participants is not None:
                go_decision["participants"] = participants
            if sources:
                go_decision["rate_sources"] = sources
        data = assignment_bytes(document)
        parse_seed_assignment(data, seeds)  # The written file must load as the launcher loads it.
        if go_decision is not None:
            problems = rule_problems(
                data,
                rule=args.rule,
                registered_seeds=seeds,
                registered_sha256=None,
                go_decision={k: v for k, v in go_decision.items() if k != "seed_assignment_sha256"},
            )
            if problems:
                raise SeedAssignmentError("; ".join(problems))
    except (
        PreregistrationFormatError,
        SeedAssignmentError,
        OSError,
        KeyError,
        TypeError,
        AttributeError,
        json.JSONDecodeError,
    ) as error:
        print(f"no assignment written: {error}", file=sys.stderr)
        return 2
    digest = hashlib.sha256(data).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(data)
    if args.record_in_go_decision:
        assert go_decision is not None
        recorded_sha = go_decision.get("seed_assignment_sha256")
        if recorded_sha not in (None, digest):
            print(f"GO decision already names assignment {recorded_sha}", file=sys.stderr)
            return 2
        go_decision["seed_assignment_sha256"] = digest
        args.go_decision.write_text(
            json.dumps(go_decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(f"{digest}  {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
