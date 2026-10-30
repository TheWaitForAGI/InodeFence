"""Linux controller entry; explicit host broker, no socket/CLI inside controller."""

import argparse
import base64
import json
import math
import os
import signal
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from scripts.run_effect_demo import (
    DECOMPRESS_CAMPAIGN_MODE,
    DEFAULT_NATIVE_BUDGET,
    HISTORICAL_DEMO_MODE,
    HISTORICAL_LABEL,
    ORAS_GO_CAMPAIGN_MODE,
    NativeDemoAborted,
    add_demo_arguments,
    check_demo_arguments,
    demo_options,
    historical_demo_report,
    native_demo_report,
)

from inodefence.effect_demo import (
    render_effect_campaign_report,
    render_effect_campaign_summary,
    render_effect_step_line,
    render_effect_step_summary,
)
from inodefence.execution import ContainerExecutionBackend, StdioDockerClient


def demo_steps_path(evidence: Path) -> Path:
    """Sibling JSONL of the final report: `<name>.steps.jsonl` next to `<name>.json`."""
    return evidence.with_suffix(".steps.jsonl")


def _announce(text: str) -> None:
    """Terminal progress for the operator; stdout stays the host protocol channel."""
    print(text, file=sys.stderr, flush=True)


def _announce_demo_start(mode: str, options: dict) -> None:
    shown = " ".join(f"{key}={getattr(value, 'value', value)}" for key, value in options.items())
    _announce(f"{mode}: {shown or 'in-code defaults'}")


def run_native_effect_demo(
    backend: ContainerExecutionBackend, image: str, evidence: Path, args: argparse.Namespace
) -> int:
    """Feedback loop on real node-tar; an infrastructure abort still leaves evidence.

    Each finished step is appended to the sibling steps JSONL and synced before the
    next case runs, so an abort keeps every completed step's loop record. The final
    report keeps its existing shape (its `steps` array equals the JSONL lines).
    """
    steps_path = demo_steps_path(evidence)
    options = demo_options(args)
    budget = int(options.get("budget", DEFAULT_NATIVE_BUDGET))
    _announce_demo_start("effect-demo", options)
    with steps_path.open("x", encoding="ascii") as steps_stream:

        def persist_step(record: dict[str, object]) -> None:
            steps_stream.write(render_effect_step_line(record))
            steps_stream.flush()
            os.fsync(steps_stream.fileno())
            _announce(render_effect_step_summary(record, budget))

        try:
            report = native_demo_report(backend, image, step_sink=persist_step, **options)
            _announce(render_effect_campaign_summary(report))
            returncode = 0
        except NativeDemoAborted as error:
            report = {
                "label": "demo run",
                "producer": "native",
                "aborted": {
                    "step_index": error.step_index,
                    "case_id": error.case_id,
                    "reason": error.reason,
                    "observed": error.observed,
                },
            }
            print(f"effect-demo aborted: {error}", file=sys.stderr)
            returncode = 1
    with evidence.open("x", encoding="ascii") as stream:
        stream.write(render_effect_campaign_report(report))
    print(f"effect demo report: {evidence}", file=sys.stderr)
    print(f"effect demo completed steps: {steps_path}", file=sys.stderr)
    return returncode


def run_native_historical_demo(
    backend: ContainerExecutionBackend, image: str, evidence: Path, args: argparse.Namespace
) -> int:
    """State-aware feedback loop on a frozen historical node-tar; abort still leaves evidence.

    Each finished step is appended to the sibling steps JSONL and synced before the next
    case runs, so an abort mid-campaign keeps every completed step's loop record (including
    any oracle event). Large-budget runs abort more often, so this preserves pre-abort
    discoveries. The final report keeps its shape (its `steps` array equals the JSONL lines).
    """
    steps_path = demo_steps_path(evidence)
    options = demo_options(args)
    budget = int(options.get("budget", DEFAULT_NATIVE_BUDGET))
    _announce_demo_start(f"effect-demo-historical tar-version={args.tar_version}", options)
    with steps_path.open("x", encoding="ascii") as steps_stream:

        def persist_step(record: dict[str, object]) -> None:
            steps_stream.write(render_effect_step_line(record))
            steps_stream.flush()
            os.fsync(steps_stream.fileno())
            _announce(render_effect_step_summary(record, budget))

        try:
            report = historical_demo_report(
                backend, image, args.tar_version, step_sink=persist_step, **options
            )
            _announce(render_effect_campaign_summary(report))
            returncode = 0
        except NativeDemoAborted as error:
            report = {
                "label": HISTORICAL_LABEL,
                "producer": "native",
                "mode": "historical",
                "requested_tar_version": args.tar_version,
                "aborted": {
                    "step_index": error.step_index,
                    "case_id": error.case_id,
                    "reason": error.reason,
                    "observed": error.observed,
                },
            }
            print(f"effect-demo-historical aborted: {error}", file=sys.stderr)
            returncode = 1
    with evidence.open("x", encoding="ascii") as stream:
        stream.write(render_effect_campaign_report(report))
    print(f"effect demo report: {evidence}", file=sys.stderr)
    print(f"effect demo completed steps: {steps_path}", file=sys.stderr)
    return returncode


def run_native_decompress_campaign(
    backend: ContainerExecutionBackend, image: str, evidence: Path, args: argparse.Namespace
) -> int:
    """M4 self-discovery: the effect campaign loop over REAL decompress; report as-is.

    Binds the pinned decompress image through the production backend and drives
    ``run_decompress_effect_campaign`` (generic mutator → real decompress → generic C0/C1/C2 oracle
    → set-based boundary-attempt / violation feedback). A C0/C1/C2 verdict on any step is the hit
    (self-discovered by mutation, not a planted PoC — the seeds are the benign generic baselines);
    a run with none is an honest right-censored negative, not a failure. The generic oracle is
    unchanged. The whole report (incl. ``discovered_violation`` and per-step oracle/feedback) is
    written to evidence; on an infrastructure abort a stub is written so the run is still recorded.
    """
    from inodefence.decompress_effect_campaign import (
        DecompressEffectCampaignConfig,
        decompress_effect_campaign_report,
        run_decompress_effect_campaign,
    )
    from inodefence.effect_pipeline_decompress import run_decompress_frame_case
    from inodefence.generator.minimal import minimal_seed_corpus
    from inodefence.model import ArchiveCase
    from inodefence.mutator import MutationPolicy
    from inodefence.targets.decompress_effect import DecompressFrameTarget

    seed = args.seed if args.seed is not None else 123
    budget = args.budget if args.budget is not None else DEFAULT_NATIVE_BUDGET
    policy = (
        MutationPolicy(args.mutation_policy)
        if args.mutation_policy is not None
        else MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK
    )
    target = DecompressFrameTarget.bind(backend, image)
    producer = f"native-decompress[{target.provenance.target_version}]"
    config = DecompressEffectCampaignConfig(
        random_seed=seed, execution_budget=budget, mutation_policy=policy
    )
    _announce(
        f"{DECOMPRESS_CAMPAIGN_MODE}: seed={seed} budget={budget} "
        f"policy={policy.value} extractor={target.provenance.target_version}"
    )

    def produce(case: ArchiveCase):
        return run_decompress_frame_case(case, target)

    try:
        result = run_decompress_effect_campaign(minimal_seed_corpus(), produce, config)
        report = decompress_effect_campaign_report(result, producer=producer, label="demo run")
        stats = result.final_stats
        _announce(
            f"decompress self-discovery: discovered_violation={result.discovered_violation} "
            f"unique_attempt_keys={stats.unique_attempt_keys} "
            f"unique_violation_fingerprints={stats.unique_violation_fingerprints} "
            f"retained={stats.retained_cases}/{stats.observations}"
        )
        returncode = 0
    except Exception as error:  # infrastructure/backend failure: record the abort, do not invent
        report = {
            "decompress_campaign_schema": 1,
            "producer": producer,
            "label": "demo run",
            "aborted": {"reason": str(error)},
        }
        _announce(f"{DECOMPRESS_CAMPAIGN_MODE} aborted: {error}")
        returncode = 1
    with evidence.open("x", encoding="ascii") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n")
    _announce(f"decompress campaign report: {evidence}")
    return returncode


def run_native_oras_go_campaign(
    backend: ContainerExecutionBackend, image: str, evidence: Path, args: argparse.Namespace
) -> int:
    """M4 self-discovery: the effect campaign loop over REAL oras-go (3rd extractor); report as-is.

    Binds the pinned oras-go image through the production backend and drives
    ``run_oras_go_effect_campaign`` (generic mutator → real oras-go frame worker → generic C0/C1/C2
    oracle → set-based boundary-attempt / violation feedback). A C0/C1/C2 verdict on any step is the
    hit (self-discovered by mutation, not a planted PoC — the seeds are the benign generic
    baselines); a run with none is an honest right-censored negative, not a failure. The generic
    oracle is unchanged. The whole report (incl. ``discovered_violation`` and per-step
    oracle/feedback) is written to evidence; on an infrastructure abort a stub is written so the run
    is still recorded.
    """
    from inodefence.effect_pipeline_oras_go import run_oras_go_frame_case
    from inodefence.generator.minimal import minimal_seed_corpus
    from inodefence.model import ArchiveCase
    from inodefence.mutator import MutationPolicy
    from inodefence.oras_go_effect_campaign import (
        OrasGoEffectCampaignConfig,
        oras_go_effect_campaign_report,
        run_oras_go_effect_campaign,
    )
    from inodefence.targets.oras_go_effect import OrasGoFrameTarget

    seed = args.seed if args.seed is not None else 123
    budget = args.budget if args.budget is not None else DEFAULT_NATIVE_BUDGET
    policy = (
        MutationPolicy(args.mutation_policy)
        if args.mutation_policy is not None
        else MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK
    )
    target = OrasGoFrameTarget.bind(backend, image)
    producer = f"native-oras-go[{target.provenance.target_version}]"
    config = OrasGoEffectCampaignConfig(
        random_seed=seed, execution_budget=budget, mutation_policy=policy
    )
    _announce(
        f"{ORAS_GO_CAMPAIGN_MODE}: seed={seed} budget={budget} "
        f"policy={policy.value} extractor={target.provenance.target_version}"
    )

    def produce(case: ArchiveCase):
        return run_oras_go_frame_case(case, target)

    try:
        result = run_oras_go_effect_campaign(minimal_seed_corpus(), produce, config)
        report = oras_go_effect_campaign_report(result, producer=producer, label="demo run")
        stats = result.final_stats
        _announce(
            f"oras-go self-discovery: discovered_violation={result.discovered_violation} "
            f"unique_attempt_keys={stats.unique_attempt_keys} "
            f"unique_violation_fingerprints={stats.unique_violation_fingerprints} "
            f"retained={stats.retained_cases}/{stats.observations}"
        )
        returncode = 0
    except Exception as error:  # infrastructure/backend failure: record the abort, do not invent
        report = {
            "oras_go_campaign_schema": 1,
            "producer": producer,
            "label": "demo run",
            "aborted": {"reason": str(error)},
        }
        _announce(f"{ORAS_GO_CAMPAIGN_MODE} aborted: {error}")
        returncode = 1
    with evidence.open("x", encoding="ascii") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n")
    _announce(f"oras-go campaign report: {evidence}")
    return returncode


class IntegrationFixtures:
    def __init__(
        self, backend: ContainerExecutionBackend, image: str, evidence: Path | None
    ) -> None:
        self.backend = backend
        self.image = image
        self.evidence = evidence

    @pytest.fixture
    def container_backend(self):
        return self.backend

    @pytest.fixture
    def container_image(self):
        return self.image

    @pytest.fixture
    def campaign_evidence(self):
        assert self.evidence is not None
        return self.evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", required=True)
    parser.add_argument("--volume", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--image", required=True, action="append")
    parser.add_argument("--evidence", type=Path)
    add_demo_arguments(parser)
    parser.add_argument(
        "mode",
        choices=(
            "validate",
            "validate-node-image",
            "validate-node-target",
            "validate-node-effect-producer",
            "qualify-node-effect-v2",
            "benign-node-smoke",
            "qualify-node-n01",
            "preflight-node-n04-5s",
            "effect-demo",
            HISTORICAL_DEMO_MODE,
            DECOMPRESS_CAMPAIGN_MODE,
            ORAS_GO_CAMPAIGN_MODE,
        ),
    )
    args = parser.parse_args()
    evidence_modes = {
        "benign-node-smoke",
        "qualify-node-effect-v2",
        "qualify-node-n01",
        "preflight-node-n04-5s",
        "effect-demo",
        HISTORICAL_DEMO_MODE,
        DECOMPRESS_CAMPAIGN_MODE,
        ORAS_GO_CAMPAIGN_MODE,
    }
    if (args.mode in evidence_modes) != (args.evidence is not None):
        parser.error("evidence mode requires --evidence; validation modes do not export")
    check_demo_arguments(parser, args)
    pair_mode = args.mode in {"qualify-node-n01", "preflight-node-n04-5s"}
    expected_images = 2 if pair_mode else 1
    if len(args.image) != expected_images:
        parser.error(f"{args.mode} requires exactly {expected_images} immutable image ID(s)")
    if args.evidence is not None and (
        not args.evidence.is_absolute() or args.evidence.exists() or args.evidence.is_symlink()
    ):
        raise ValueError("evidence requires a new absolute controller destination")
    if args.mode == "preflight-node-n04-5s":
        from inodefence.evaluation.n04_preflight import ATTEMPT_CONSUMED

        if ATTEMPT_CONSUMED:
            raise RuntimeError(
                "N04 five-second preflight v1 attempt is consumed; a new Task Contract is required"
            )
    pair_initial_value = None
    if pair_mode:
        line = sys.stdin.readline(16 * 1024 * 1024)
        pair_initial_value = json.loads(line)
    client = StdioDockerClient(sys.stdin, sys.stdout)
    with redirect_stdout(sys.stderr):
        if args.mode == "preflight-node-n04-5s":
            from inodefence.evaluation.encoding import decode
            from inodefence.evaluation.n04_preflight import (
                EVIDENCE_ROOT,
                EXPECTED_BUILD_FILES,
                N04BrokerAttestation,
                N04BuildContext,
                N04BuildFile,
                N04PackageTarball,
                N04PreflightRole,
                bind_targets,
                run_n04_preflight,
            )

            value = pair_initial_value
            if not isinstance(value, dict) or set(value) != {
                "n04_build_contexts",
                "n04_package_tarballs",
                "controller_deadline_seconds",
                "broker_attestation",
            }:
                raise ValueError("missing N04 preflight initialization")
            raw_contexts = value["n04_build_contexts"]
            if not isinstance(raw_contexts, list) or len(raw_contexts) != 2:
                raise ValueError("N04 preflight requires two build contexts")
            contexts = []
            for role, raw in zip(N04PreflightRole, raw_contexts, strict=True):
                if not isinstance(raw, dict) or set(raw) != set(EXPECTED_BUILD_FILES):
                    raise ValueError("N04 build-context initialization has unexpected files")
                contexts.append(
                    N04BuildContext(
                        role,
                        tuple(
                            N04BuildFile(name, base64.b64decode(raw[name], validate=True))
                            for name in EXPECTED_BUILD_FILES
                        ),
                    )
                )
            raw_broker = value["broker_attestation"]
            raw_packages = value["n04_package_tarballs"]
            if not isinstance(raw_packages, list) or len(raw_packages) != 2:
                raise ValueError("N04 preflight requires two package tarballs")
            packages = (
                N04PackageTarball(
                    N04PreflightRole.AFFECTED,
                    base64.b64decode(raw_packages[0], validate=True),
                ),
                N04PackageTarball(
                    N04PreflightRole.FIXED,
                    base64.b64decode(raw_packages[1], validate=True),
                ),
            )
            controller_deadline_seconds = value["controller_deadline_seconds"]
            if (
                not isinstance(controller_deadline_seconds, (int, float))
                or isinstance(controller_deadline_seconds, bool)
                or not math.isfinite(controller_deadline_seconds)
                or not 1 <= controller_deadline_seconds < 30 * 60
            ):
                raise ValueError("invalid N04 cooperative controller deadline")
            assert args.evidence is not None
            if args.evidence != EVIDENCE_ROOT:
                raise ValueError("N04 preflight requires its one frozen evidence destination")

            def broker():
                return decode(N04BrokerAttestation, raw_broker)

            def targets():
                backend = ContainerExecutionBackend(
                    client, args.controller, args.volume, args.owner
                )
                return bind_targets(backend, tuple(args.image))

            def deadline_expired(_signum, _frame):
                raise TimeoutError("N04 controller cooperative deadline expired")

            previous_handler = signal.signal(signal.SIGALRM, deadline_expired)
            signal.setitimer(signal.ITIMER_REAL, controller_deadline_seconds)
            try:
                outcome = run_n04_preflight(
                    args.evidence,
                    targets,
                    tuple(contexts),
                    packages,
                    broker,
                    repository=Path.cwd(),
                )
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous_handler)
            verified = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "inodefence.evaluation.n04_preflight_reader",
                    str(args.evidence),
                    "--raw-manifest-sha256",
                    outcome.manifest_sha256,
                ),
                check=False,
                text=True,
                capture_output=True,
                timeout=120,
            )
            print(verified.stdout, end="")
            print(verified.stderr, end="", file=sys.stderr)
            terminal = json.loads(verified.stdout)
            if not isinstance(terminal, dict):
                raise ValueError("N04 reader did not emit a terminal object")
            terminal.update(
                raw_manifest_sha256=outcome.manifest_sha256,
                reader_returncode=verified.returncode,
            )
            client.writer.write(json.dumps({"terminal": terminal}, sort_keys=True) + "\n")
            client.writer.flush()
            return verified.returncode
        if args.mode == "qualify-node-n01":
            from inodefence.evaluation.n01 import (
                EXPECTED_BUILD_FILES,
                N01BuildContext,
                N01BuildFile,
                N01Role,
                run_n01_qualification,
            )
            from inodefence.targets.node_tar import NodeTarTarget

            value = pair_initial_value
            if not isinstance(value, dict) or set(value) != {"n01_build_contexts"}:
                raise ValueError("missing N01 build-context initialization")
            raw_contexts = value["n01_build_contexts"]
            if not isinstance(raw_contexts, list) or len(raw_contexts) != 2:
                raise ValueError("N01 requires two build contexts")
            contexts = []
            for role, raw in zip(N01Role, raw_contexts, strict=True):
                if not isinstance(raw, dict) or set(raw) != set(EXPECTED_BUILD_FILES):
                    raise ValueError("N01 build-context initialization has unexpected files")
                files = tuple(
                    N01BuildFile(name, base64.b64decode(raw[name], validate=True))
                    for name in EXPECTED_BUILD_FILES
                )
                contexts.append(N01BuildContext(role, files))

            def targets():
                backend = ContainerExecutionBackend(
                    client, args.controller, args.volume, args.owner
                )
                return (
                    NodeTarTarget.bind(backend, args.image[0], timeout_seconds=10),
                    NodeTarTarget.bind(backend, args.image[1], timeout_seconds=10),
                )

            assert args.evidence is not None
            outcome = run_n01_qualification(
                args.evidence,
                targets,
                tuple(contexts),
                repository=Path.cwd(),
            )
            verified = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "inodefence.evaluation.n01_reader",
                    str(args.evidence),
                    "--raw-manifest-sha256",
                    outcome.manifest_sha256,
                ),
                check=False,
                text=True,
                capture_output=True,
                timeout=120,
            )
            print(verified.stdout, end="")
            print(verified.stderr, end="", file=sys.stderr)
            return verified.returncode
        backend = ContainerExecutionBackend(client, args.controller, args.volume, args.owner)
        if args.mode == "effect-demo":
            assert args.evidence is not None
            return run_native_effect_demo(backend, args.image[0], args.evidence, args)
        if args.mode == HISTORICAL_DEMO_MODE:
            assert args.evidence is not None
            return run_native_historical_demo(backend, args.image[0], args.evidence, args)
        if args.mode == DECOMPRESS_CAMPAIGN_MODE:
            assert args.evidence is not None
            return run_native_decompress_campaign(backend, args.image[0], args.evidence, args)
        if args.mode == ORAS_GO_CAMPAIGN_MODE:
            assert args.evidence is not None
            return run_native_oras_go_campaign(backend, args.image[0], args.evidence, args)
        suite = {
            "validate": "check_boundary.py",
            "validate-node-image": "check_node_image.py",
            "validate-node-target": "check_node_target.py",
            "validate-node-effect-producer": "check_node_effect_producer.py",
            "qualify-node-effect-v2": "check_node_effect_qualification.py",
            "benign-node-smoke": "check_node_campaign.py",
        }[args.mode]
        return pytest.main(
            [f"tests/container_integration/{suite}", "-q", "-s", "-p", "no:cacheprovider"],
            plugins=[IntegrationFixtures(backend, args.image[0], args.evidence)],
        )


if __name__ == "__main__":
    raise SystemExit(main())
