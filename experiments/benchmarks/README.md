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
qualification status, uncertainties and typed source references. Optional
`artifact_metadata` stores official package/module identities and source commits
for the selected primary pair; `static_runtime` labels metadata compatibility
separately from runtime qualification (NOT_RUN). Upstream lock hashes identify
source files, not benchmark locks. npm SRI/go.sum h1 are not container digests.

The catalog's `engine_revision` is the source-reviewed main SHA, not necessarily
the engine checked out on the research branch. The
[engine audit](../../docs/research/benchmarks/engine-contract-audit.md) records the
current integrated main `d1982e4`, the completed Phase-4B review and the explicitly
superseded historical #39 record. The final audit still recommends NO-GO for
unconditional global closeout pending documentation disposition; this Draft
proposes those current-state corrections. Generation,
observation and execution fields must be rechecked after relevant source changes.
`candidate_id` (N/O/G series), descriptive `benchmark_id`, R root-cause ID and S
semantic IDs are stable joins, not display names or CVE-based oracle rules.
`representation`, `seed_start`, `structure_reachability`, `current_reachability`
and `isolated_execution` answer different questions. Seed proximity cannot
establish complete benchmark reachability.

## Independent state fields

`selection` and its legacy `status` record scope/prioritization only.
`qualification` records evidence gates, independent of `execution`:

| Qualification | Meaning |
| --- | --- |
| PROPOSED | Candidate nominated; source gates incomplete |
| SOURCE_VERIFIED | Trustworthy metadata inspected; version/platform fields may remain UNKNOWN |
| SEMANTICS_VERIFIED | Selected effect independently qualified with retained evidence; source prose alone does not suffice |
| IMPLEMENTATION_BLOCKED | Concrete engine/config/setup prerequisites absent; source evidence retained |
| ISOLATION_QUALIFIED | Candidate image/invocation/full path has approved boundary evidence; helper success alone does not suffice |
| READY | Every Set v1 gate passed for exact version/setup/policy with linked evidence |

These are gate summaries, not a monotonic score; source/engine changes can
invalidate qualification. Admission also requires the per-gate records in the
[qualification template](result-templates.md); one state cannot replace them.

| Execution | Meaning |
| --- | --- |
| NOT_RUN | No benchmark qualification/evaluation execution |
| QUALIFICATION_ONLY | Authorized qualification performed; no formal evaluation |
| EVALUATION_RUN | Formal executions exist; evidence validation remains separate |

Current primaries are IMPLEMENTATION_BLOCKED; excluded candidates remain
SOURCE_VERIFIED with excluded_v1 scope. G01 remains SOURCE_VERIFIED with unresolved
pin/root gates. All 15 execution states are NOT_RUN, all candidate isolated
campaign bindings NOT_IMPLEMENTED, and none is READY. `isolated_execution` refers
to an exact candidate's frozen image/config/provenance and approved campaign
path. The implemented benign Node/backend composition and passing helper/image/
fixture/configured-smoke CI and verified artifact/invocation admission at d1982e4
do not qualify historical benchmark versions or change
these fields. The planning-only validator rejects executed
qualification/READY/evaluation assertions; future ingestion needs a reviewed
schema/state transition and retained gate evidence.

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

[Result templates](result-templates.md) contain empty tables and placeholder records only. Raw future datasets
belong in ignored experiments/raw with immutable shared-storage identifiers and
checksums; validated summaries follow [summaries rules](../summaries/README.md).
