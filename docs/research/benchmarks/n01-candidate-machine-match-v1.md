# N01 policy-candidate machine match v1

Status: **IMPLEMENTED / TESTED WITH CONTROLLED ADAPTERS / HISTORICAL USE NOT_RUN /
HUMAN DISPOSITION REQUIRED**.

This versioned derivative implements the mechanical part of the existing N01 rediscovery
rule for a completed generic policy-candidate 3+3 replay. It neither authorizes a campaign nor
turns machine contrast into confirmed rediscovery, historical qualification or a vulnerability
claim.

## Input and trust boundary

`assess_n01_candidate_replay` reopens both inputs rather than trusting a copied summary:

1. a completed checksummed `PolicyEvaluationConfig` evidence bundle; and
2. its bound `policy-candidate-pair-replay-v1` directory.

The caller may supply the trusted replay completion SHA-256. The candidate nomination must
reconstruct exactly from the source bundle. Corrupt raw/derived state, TAR, oracle, feedback,
schedule, pair, provenance or checksum evidence is rejected by the underlying readers.

Machine assessment additionally requires:

- the exact four `minimal_seed_corpus()` IDs, full feedback projection and
  `uniform-generic-m1-protected-components-v1` mutation policy;
- an available clean Git revision on Linux;
- source campaign provenance byte-equal to the affected replay provenance;
- the default `outside/sentinel.txt` bytes and mode;
- node-tar `7.5.2` affected and `7.5.3` fixed target identities, Node `22.22.0`, exact
  wrapper-lock and worker digests, container-required safety and the frozen default isolation
  policy; and
- unchanged `archive/input.tar` in every retained replay.

The generic replay reader already requires equal adapter, timeout, safety, source,
environment, sentinel and isolation/runtime/resource context across arms while allowing the
declared target image/version/artifact differences. This matcher does not choose between the
still-unresolved 5-second and 10-second pilot timeout proposals. That setting must be frozen
and qualified before execution; the matcher cannot authorize it after results exist.

## Pre-replay nomination rule

The candidate case ID must not be one of the four seed IDs. Only source occurrences marked
`MUTATION` are eligible. An eligible occurrence must retain an unchanged input archive and a
recomputed persistent C1 `IdentityEvidence` relation between an extraction path and the
controlled sentinel.

If multiple eligible internal paths share the sentinel, v1 selects the lexicographically first
`(internal_path, sentinel_path)` pair. This deterministic source-evidence rule is applied
before consulting replay outcomes; it prevents post-replay choice of the most favorable
relation. Every source step containing that selected relation remains in the assessment.

No CVE identifier, package version or expected process status enters the generic oracle,
feedback, mutator or scheduler. Version/artifact checks exist only in this benchmark-specific
offline reader.

## Mechanical 3+3 rule

For the selected relation, count all six scheduled results:

- affected match: the recomputed C1 evidence and AFTER lstat observations contain that exact
  persistent internal/sentinel identity relation;
- fixed match: the same definition, with no special treatment of rejection or success; and
- machine contrast pass: affected **3/3** and fixed **0/3** in a complete valid replay.

C2, C0 and process status are retained per run but are not the selected N01 relation. C2
nlink/ctime may corroborate a match; C2 alone never creates one. Success, rejection, failure
or timeout alone never creates one. An unrelated C0/C1/C2 observation is not silently erased
or converted into the N01 class. Human review must interpret additional effects and archive
semantics.

Statuses are deliberately separate:

- `machine_contrast_pass_pending_human`: the narrow automated 3/3 versus 0/3 relation passed;
- `ambiguous`: an eligible source relation failed affected 3/3 or appeared on fixed;
- `not_nominated`: no eligible mutation-origin source relation exists; and
- `not_evaluable`: completion, binding, clean-source or archive-integrity prerequisites fail.

Incomplete or infrastructure-invalid evidence is never a no-hit. Seed-phase evidence is not
credited. The output always fixes `human_disposition=pending_human_root_cause_review`,
`confirmed_rediscovery=false` and `qualification_token=null`. No automated path can issue
`N01_RELATIVE_HARDLINK_PAIR_QUALIFIED`.

## Reproduction

```bash
PYTHONPATH=src python -m inodefence.evaluation.n01_candidate_match \
  <candidate-replay-root> <source-policy-evidence> \
  --completion-sha256 <trusted-replay-completion-sha256>
```

Exit zero means the inputs were independently readable and an assessment was produced; the
assessment status may still be ambiguous, not nominated or not evaluable. Reader corruption
returns nonzero. Unit tests use explicit controlled adapters and are engineering evidence
only. No historical target or pilot has been executed by this implementation.
