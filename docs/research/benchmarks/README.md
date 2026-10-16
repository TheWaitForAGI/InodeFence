# Benchmark and evaluation preparation v1

**SOURCE-DERIVED PLAN — HISTORICAL / FORMAL EVALUATION NOT_RUN.**
Capability baseline is main **`8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`**.
[G0 Research Contract](../design/research-contract-v1.md) fixes definitions,
evidence levels and claim scope. Implemented search/evaluation APIs and benign
Node checks are engineering evidence; no historical vulnerability has been
rediscovered and no vulnerability is currently claimed.

**N01 node-tar 7.5.2 / 7.5.3 is the first historical qualification pair.**
Its exact artifacts were admitted and its automated 8-run readiness plus 10-run
same-input replay completed; final human correspondence remains pending. Other original selected
candidates are conditional later scope, not permission to add adapters or run
unqualified targets. Static catalog execution remains NOT_RUN for all 15 cases.
The exact same-input [N01 pair qualification contract](n01-pair-qualification-contract-v1.md)
governs that retained evidence; the [N02 report](../diagnostics/n02-autonomous-integration-and-qualification.md)
and [N03 machine audit](../diagnostics/n03-n01-machine-correspondence-audit.md) do not
replace its pending human disposition or count its positive control as rediscovery.

Read current definitions in this order:

1. [Research questions](../design/research-questions.md) and [STATUS](../../STATUS.md).
2. [Candidate matrix](candidate-matrix.md) and [static artifact sources](artifact-qualification-v1.md).
3. [Taxonomy/reachability](taxonomy-and-reachability.md): structural support versus actual protected setup.
4. [Benchmark Set](benchmark-set-v1.md): selected pairs and admission gates.
5. [Executable baselines/ablations](baseline-and-ablation-v1.md): B0/B1/B3 and A1/A2/A3 only.
6. [Evaluation protocol](evaluation-protocol-v1.md): success, provisional budgets, censoring and metrics.
7. [N03 pilot proposal](n03-b0-b1-b3-pilot-task-proposal.md): exact candidate cells and unresolved execution gates.
8. [Static catalog](../../../experiments/benchmarks/README.md) and [empty result templates](../../../experiments/benchmarks/result-templates.md).

The [engine audit](engine-contract-audit.md) and [post-audit handoff](post-audit-backlog.md)
are explicitly historical `d1982e4` records. Their counts, absent-policy/reader
findings, task IDs and draft-PR instructions do not define present implementation
status. They remain evidence of what was reviewed then, without rewriting raw
validation history. Current interfaces and limitations are recorded in STATUS,
[search policy contract](../design/search-policy-core-v1.md) and
[evaluation API guide](../../../src/inodefence/evaluation/README.md).

Selection is prioritization, not readiness. Independently verify exact source
pins, runtime/options/setup, generation reachability, isolation/full path and
persistent effect/fixed comparator before admission. Qualification report and
matrix primitives exist but do not prove assessor assertions or classify known
vulnerabilities. A failed gate stays failed and reduces the formal dataset with
an explicit pre-freeze amendment, rather than a silent substitute benchmark.

No PoC seeds, oracle CVE/version conditions, new contracts, operators or adapters
are introduced here. Provisional schedules/subsets are not a main-experiment
freeze. Preserve negative/invalid data and honor the research-stage order.
