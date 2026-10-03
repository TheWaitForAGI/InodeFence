PYTHON ?= python
CASE ?= regular-file
BASELINE_CASES := regular-file directory hardlink symlink

.PHONY: install lint format-check typecheck test env-check docs-check check fixtures probe

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
