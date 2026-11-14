PYTHON ?= python
CASE ?= regular-file
BASELINE_CASES := regular-file directory hardlink symlink
DEMO_POLICY ?= effect-feedback-v2-or-violation-v1-adaptive-mutation-v1
DEMO_MUTATION_POLICY ?= uniform-generic-m1-v1
DEMO_SEED ?= 123
DEMO_BUDGET ?= 20
DEMO_OUT ?= $(or $(INODEFENCE_RUNTIME_ROOT),/var/lib/inodefence)/demo/effect-demo-synthetic.json

TAR_VERSION ?= 7.5.2
HISTORICAL_IMAGE ?= inodefence-node-tar-effect:$(TAR_VERSION)

.PHONY: install target-tools lint format-check typecheck test env-check docs-check evidence-chain check fixtures probe isolation-support node-entry-timing-probe node-tar-smoke node-tar-effect-check demo demo-native demo-synthetic demo-native-historical regression target-run replay paper-artifacts

target-tools:
	npm ci --prefix tools/node-tar --ignore-scripts --no-audit --no-fund

install:
	$(PYTHON) -m pip install -e '.[dev]'

lint:
	$(PYTHON) -m ruff check .

format-check:
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m pyright

test:
	$(PYTHON) -m pytest

env-check:
	$(PYTHON) scripts/check_dev_env.py

isolation-support:
	$(PYTHON) scripts/check_linux_isolation_support.py

docs-check:
	$(PYTHON) scripts/check_docs.py

# Verify each validated summary's raw pointer resolves to a committed manifest or
# in-repo file. Reads only committed files (no raw bytes), so it runs on any host.
# Non-strict: fails only on broken in-repo links (REPO-MISSING).
evidence-chain:
	$(PYTHON) -m scripts.check_evidence_chain

check: lint format-check typecheck test env-check docs-check evidence-chain

fixtures:
	$(PYTHON) scripts/generate_tar_fixtures.py

probe:
ifneq ($(words $(CASE)),1)
	$(error CASE must be exactly one baseline case)
else ifeq ($(filter $(BASELINE_CASES),$(CASE)),)
	$(error CASE must be one of: $(BASELINE_CASES))
else
	$(PYTHON) scripts/manual_tar_probe.py tests/fixtures/tar/$(CASE)/fixture.tar
endif

node-entry-timing-probe:
	PYTHONPATH=src $(PYTHON) scripts/probe_node_entry_timing.py

node-tar-smoke:
	bash scripts/local_node_tar_smoke.sh smoke

node-tar-effect-check:
	bash scripts/local_node_tar_smoke.sh effect

# Real node-tar feedback loop; host terminal only (docker). Result label: demo run.
demo:
	DEMO_POLICY=$(DEMO_POLICY) DEMO_MUTATION_POLICY=$(DEMO_MUTATION_POLICY) DEMO_SEED=$(DEMO_SEED) DEMO_BUDGET=$(DEMO_BUDGET) bash scripts/local_node_tar_smoke.sh demo

# Kept so earlier docs/LOG commands still run the same native demo.
demo-native: demo

# Synthetic producer (not node-tar); runs in the Dev Container.
demo-synthetic:
	PYTHONPATH=src $(PYTHON) -m scripts.run_effect_demo --producer synthetic --policy $(DEMO_POLICY) --mutation-policy $(DEMO_MUTATION_POLICY) --seed $(DEMO_SEED) --budget $(DEMO_BUDGET) --out $(DEMO_OUT)

# P2-c: state-aware effect loop on a prebuilt frozen historical node-tar effect image.
# Runtime provides the image (default tag inodefence-node-tar-effect:$(TAR_VERSION)); the
# P2 adaptive arm and escape-hardlink mutation policy are the in-code defaults. Budget stays
# capped at 100 in code. Not run by `make check`. Override the arm/mutation from the command
# line to pick another arm, e.g. the M3 boundary-attempt gradient:
#   make demo-native-historical DEMO_POLICY=effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1 \
#     DEMO_MUTATION_POLICY=uniform-generic-m1-protected-components-escape-hardlink-v1
# A bare `make demo-native-historical` leaves both empty, so the in-code defaults stand.
demo-native-historical: DEMO_POLICY :=
demo-native-historical: DEMO_MUTATION_POLICY :=
demo-native-historical:
	TAR_VERSION=$(TAR_VERSION) HISTORICAL_IMAGE=$(HISTORICAL_IMAGE) DEMO_POLICY=$(DEMO_POLICY) DEMO_MUTATION_POLICY=$(DEMO_MUTATION_POLICY) DEMO_SEED=$(DEMO_SEED) DEMO_BUDGET=$(DEMO_BUDGET) bash scripts/local_node_tar_smoke.sh demo-historical

# Maintainer regression: do known C1/C2 boundary fixtures still breach at a node-tar version?
# Runs the M2.1 hand hardlink fixtures + the #205 FN symlink-write placements through the repro
# disposable-container path against inodefence-node-tar-effect:$(TAR_VERSION); one-line PASS/FAIL
# + JSON. Host terminal only (docker). `--dry-run` via REGRESSION_ARGS runs no container.
#   make regression TAR_VERSION=7.5.2
#   make regression TAR_VERSION=7.5.2 REGRESSION_ARGS=--dry-run
regression:
	PYTHONPATH=src:. $(PYTHON) scripts/regression_check.py --tar-version $(TAR_VERSION) $(REGRESSION_ARGS)

# One command per target (common result format inodefence-target-result-v1, label demo run):
# isolated run -> C0/C1/C2 judgment -> DIR/<cell>/{result.json,inputs/*.tar,raw/}.
# Targets: node-tar, python-tarfile (both fixture-regression: the make regression fixtures;
# C0 not observed = null). Host terminal only (docker). TARGET_VERSIONS is the target's version
# axis (node-tar package; python-tarfile exact runtime X.Y.Z); TARGET_FILTERS is the
# extraction-filter axis (python-tarfile: fully_trusted / data). Vary one axis per run.
# TARGET_ARGS=--dry-run runs no container and writes nothing. Existing results are not overwritten.
#   make target-run TARGET=node-tar TARGET_VERSIONS="7.5.2 7.5.3"
#   make target-run TARGET=python-tarfile TARGET_VERSIONS=3.12.16 TARGET_FILTERS="fully_trusted data"
#   make target-run TARGET=python-tarfile TARGET_VERSIONS="3.12.3 3.12.16" TARGET_FILTERS=data
#   make target-run TARGET=oras-go TARGET_VERSIONS="2.6.1 2.6.2"
#   make target-run TARGET=decompress TARGET_VERSIONS="decompress@4.2.1 @xhmikosr/decompress@11.1.4"
TARGET ?= node-tar
TARGET_VERSIONS ?= $(TAR_VERSION)
TARGET_FILTERS ?=
TARGET_OUT ?= $(HOME)/inodefence-evidence/target-run
target-run:
	PYTHONPATH=src:. $(PYTHON) scripts/run_target.py --target $(TARGET) $(foreach v,$(TARGET_VERSIONS),--version $(v)) $(foreach f,$(TARGET_FILTERS),--extraction-filter $(f)) $(if $(filter --dry-run,$(TARGET_ARGS)),,--out $(TARGET_OUT)) $(TARGET_ARGS)

# Offline replay planner: read a demo report (REPORT=<path>) and reproduce its run
# command, binding the recorded image recipe to the committed one and checking the
# recorded case_id sequence. Runs no docker; native re-execution is the Runtime lane.
replay:
ifndef REPORT
	$(error REPORT=<demo-report.json> is required)
endif
	PYTHONPATH=src $(PYTHON) -m scripts.replay_report --report $(REPORT)

# Regenerate/verify the paper's tables and figures from one entry point (audit (8)).
# Default (ARGS empty) verifies committed artifacts read-only + runs the evidence-chain
# check; ARGS=--list lists inputs; ARGS=--regenerate stages the tables to a temp dir outside
# the repo (removed on success unless --keep-stage); ARGS="--regenerate --apply" writes in
# place (figures via an ephemeral matplotlib env). Not part of `make check`.
paper-artifacts:
	$(PYTHON) -m scripts.regenerate_paper_artifacts $(ARGS)
