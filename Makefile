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

.PHONY: install target-tools lint format-check typecheck test env-check docs-check check fixtures probe isolation-support node-entry-timing-probe node-tar-smoke node-tar-effect-check demo demo-native demo-synthetic demo-native-historical

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

check: lint format-check typecheck test env-check docs-check

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
