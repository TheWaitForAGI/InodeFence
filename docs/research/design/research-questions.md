# Research Questions and Hypotheses

## RQ1 — Known Vulnerability Rediscovery

Can InodeFence rediscover known TAR extraction link/path security violations without seeding the fuzzer with the corresponding CVE PoC?

Candidate benchmarks include:

- node-tar CVE-2026-23745
- node-tar CVE-2026-24842
- node-tar CVE-2026-26960
- oras-go CVE-2026-50163
- GNU tar CVE-2026-18508 (optional)

The exact benchmark set must be version-pinned before evaluation.

## RQ2 — Feedback Effectiveness

Does filesystem-security-state feedback improve discovery efficiency compared with:

- random mutation,
- path-only feedback,
- fixed attack strategies?

Primary measurements:

- detection rate
- time to first violation
- executions to first violation
- number of unique security states

## RQ3 — Feedback Ablation

Which components of the state representation contribute to exploration?

Candidate configurations:

- F0: path only
- F1: path + object type
- F2: path + object identity / link relation
- F3: identity + external effect
- Full state

The exact signature must be frozen before the final experiment.

## RQ4 — Cross-Implementation Generality

Can the same security-state representation and generic oracle logic be applied across multiple TAR extractors?

Initial target order:

1. node-tar
2. oras-go
3. GNU tar if schedule permits

## RQ5 — Unknown-State Discovery

Can the same framework discover previously unseen security-contract violations in patched or current target versions?

This RQ is exploratory. A zero-day is not required for project success.

## H1 — State-Guided Search

Under the same execution or time budget, a corpus-guided fuzzer using object-identity and external-effect feedback will discover archive-extraction boundary violations more effectively than a fixed attack-recipe strategy or weaker feedback baselines.

This is a hypothesis to test, not an assumed result.

## H2 — Generic Security Contracts

A general security contract that does not encode a CVE-specific string or code path can identify related security failures across multiple TAR extractors.

This is also an experimental hypothesis.

## Evaluation Discipline

Experiments should use:

- identical initial corpus where applicable,
- identical mutation operators across feedback baselines where possible,
- pinned target versions,
- fixed time or execution budgets,
- repeated runs,
- reproducible random seeds or recorded RNG seeds.

At minimum report:

- median,
- spread such as IQR,
- success rate,
- exact target/environment configuration.

Do not state an expected ordering of methods as an observed result until the experiments support it.
