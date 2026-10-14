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
source files, not benchmark locks. The separately prepared
[N01 wrapper locks](locks/README.md) are exact future build inputs, not container images,
runnable ExperimentConfig values or target qualification. npm SRI/go.sum h1 are not
container digests.

The catalog's `engine_revision` is the capability baseline main SHA
**`8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`** reviewed for the
[G0 contract](../../docs/research/design/research-contract-v1.md), not a moving
checkout revision. `evidence_accessed: 2026-10-04` preserves the original upstream
source-access date; this documentation reconciliation does not assert new
upstream inspection or target execution. The old [engine audit](../../docs/research/benchmarks/engine-contract-audit.md)
is historical; [STATUS](../../docs/STATUS.md) records current code/test evidence.

M1, B0/B1/B3, A1/A2/A3, minimization, replay and policy-result analysis are
implemented. M1's finite components still cannot spell the default
`outside/sentinel.txt`. Structural composition does not establish selected-case
reachability or bounded rediscovery. Existing catalog
`component_recombination_planned` is a legacy missing-address-vocabulary label,
not a claim that the whole M1 mutator is absent. Generation, observation and
execution fields must be rechecked after relevant source changes.

**N01 node-tar 7.5.2 / 7.5.3 is the first intended historical qualification
pair.** The validated benign Node pin is 7.5.22, not either member of N01.
No historical vulnerability has been rediscovered and no vulnerability is claimed.
`candidate_id` (N/O/G), `benchmark_id`, R and S IDs are stable joins, not CVE oracle
rules. Representation, seed proximity, structural reachability, full setup
reachability and isolated qualification are independent.

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
fixture/configured-smoke CI and verified artifact/invocation admission at the baseline
do not qualify historical benchmark versions or change
these fields. The planning-only validator rejects executed
qualification/READY/evaluation assertions; executed qualification belongs to the separate evaluation qualification/matrix API
and requires retained gate evidence, not a metadata status edit.

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
