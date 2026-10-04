# Benchmark and evaluation preparation v1

**PLANNING ONLY — EVALUATION NOT RUN.** This retains the original research track
and applies the maintainer's Phase-4B documentation refresh Task Contract. No production engine changes, CVE
execution, exploit archives, target installation or generated-input campaigns
belong to this branch. Keep the existing Draft PR unmerged while global closeout
and the remaining candidate-specific prerequisites are reviewed.

The audited integrated main is `d1982e4cf3174e28d4eeb73af7b32829f6751b30`;
the [engine audit](engine-contract-audit.md) and [final audit #47](https://github.com/TheWaitForAGI/InodeFence/pull/47)
record functional closure, residual EN-005/current-package disposition and the
NO-GO for unconditional global closeout on that main. This Draft proposes current
planning/navigation corrections without asserting main or evaluation readiness.
Pre-audit freeze, Phases 1–2 and Phase-3 #45/#46 fixes are completed. Tagged v3,
artifact/invocation verification and export regressions are already implemented.
Implemented repository behavior, upstream source facts, source-derived reachability
predictions and future experiment results have separate evidence labels. No benchmark
qualification, pilot, rediscovery, replay, baseline, ablation or evaluation has run.
Inherited engineering fixture/helper tests are not benchmark results.

Read in this order:

1. [Engine contract audit](engine-contract-audit.md): capabilities and evidence limits.
2. [Candidate matrix](candidate-matrix.md): sources, versions and semantic requirements;
   [static artifact qualification](artifact-qualification-v1.md) gives pin/runtime/public-API evidence.
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

Admission follows the [Set v1 gates](benchmark-set-v1.md): verify sources and
exact release pairs, describe semantics and generic reachability, finish approved
isolated binding, independently qualify the effect and fixed comparator, then
attach complete evidence before READY. Selection is prioritization only.
The [catalog state definitions](../../../experiments/benchmarks/README.md) keep
qualification independent of execution; missing capability remains
IMPLEMENTATION_BLOCKED and all current execution states remain NOT_RUN.

The complete planning package is kept in one Draft PR. Final state and review
evidence are recorded in the handoff; P01–P11 implementation awaits accepted global
Phase-4 closeout and a new Task Contract. All benchmark execution remains NOT_RUN.
