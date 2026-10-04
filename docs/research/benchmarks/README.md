# Benchmark and evaluation preparation v1

**PLANNING ONLY — EVALUATION NOT RUN.** This is the parallel research track
requested by the maintainer's Task Contract. No production engine changes, CVE
execution, exploit archives, target installation or generated-input campaigns
belong to this branch. Keep the Draft PR unmerged while infrastructure moves.

Read in this order:

1. [Engine contract audit](engine-contract-audit.md): capabilities and evidence limits.
2. [Candidate matrix](candidate-matrix.md): sources, versions and semantic requirements.
3. [Taxonomy and reachability](taxonomy-and-reachability.md): why a structure can or cannot arise.
4. [Benchmark Set v1](benchmark-set-v1.md): selected pairs and admission gates.
5. [Evaluation protocol](evaluation-protocol-v1.md): success, budgets, repetitions and metrics.
6. [Baselines and ablations](baseline-and-ablation-v1.md): exact comparisons.
7. [Post-audit handoff](post-audit-backlog.md): evidence-driven gaps and ordered tasks.
8. [Catalog](../../../experiments/benchmarks/README.md): static metadata and validation.
9. [Empty result templates](../../../experiments/benchmarks/result-templates.md).

These documents refine evaluation candidates in the [research questions](../design/research-questions.md).
They do not change the [security contracts](../design/security-contracts.md),
[architecture](../design/architecture.md), project Layer or engineering readiness.
Unvalidated predictions are labeled as such; selected cases still require
post-audit Linux qualification. A failed qualification is reported and does not
silently become another benchmark.

The first coherent deliverable is the engine audit. The remaining linked files
are filled in as the same Draft PR progresses. Final state and review evidence
are recorded in the handoff; no implementation may begin until isolation,
repository audit and audit fixes are complete under a new Task Contract.
