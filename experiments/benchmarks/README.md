# Static benchmark planning metadata

This directory contains **no runnable ExperimentConfig, target adapters, payloads,
archive bytes, exploit command sequences or experimental results**.
[catalog-v1.json](catalog-v1.json) is the machine-readable companion to the
[research plan](../../docs/research/benchmarks/README.md).

Each record has a stable benchmark ID, target/known issue/component, advisory
and version fields, selected exact pair (nullable when unresolved), root cause
and reported effect, entry/path/order/filesystem requirements, expected
observable effect and C0/C1/C2 mapping, required current/planned capabilities,
structural versus complete benchmark reachability, observer needs, selection,
qualification status, uncertainties and typed source references.

`selected_pending_qualification` means chosen for implementation planning, not
ready to execute or validated. `secondary_pending` preserves optional candidates;
`excluded_v1` means intentionally outside this evaluation. Date is the source's
advisory publication date; GNU G02 uses the cited vendor notice (public report
and CNA dates differ and are recorded as uncertainty). Selected versions are
release choices backed by sources, not an assertion of installed artifacts.
`inspected` means source content was read, not reproduced. A release pointer may
exist without establishing a candidate's fixing patch. Source identifiers stay
adjacent to URLs and publisher/type labels.

The [JSON Schema](catalog.schema.json) uses draft 2020-12 object/type/enum,
required/additionalProperties, pattern/minLength and array/items/minItems/
uniqueItems constraints. [validate_catalog.py](validate_catalog.py) implements
only that subset, using the standard library, and adds duplicate benchmark ID,
source URL, local document, capability name and primary-pair/source checks.
Contract mapping keys are exactly C0/C1/C2; unknown contracts are rejected.
There is no production-engine import or API coupling. It is not a complete
third-party JSON Schema implementation or a historical advisory verifier.

From the checkout root:

```bash
python experiments/benchmarks/validate_catalog.py
git diff --check
make docs-check
```

Run this validator alongside canonical `make check` before handoff. It is kept
separate from production validation commands to avoid editing infrastructure hot
files. Schema/catalog changes require re-running both commands. Never deserialize
this catalog as execution settings: actual future configs need audited adapters,
locked artifacts, complete environment, policy binding and approved isolation.

[Result templates](result-templates.md) contain headers only. Raw future datasets
belong in ignored experiments/raw with immutable shared-storage identifiers and
checksums; validated summaries follow [summaries rules](../summaries/README.md).
