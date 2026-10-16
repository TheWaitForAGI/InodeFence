# N04 five-second preflight and bounded pilot decision — prospective proposal

**Date:** 2026-10-16  
**Status:** PROPOSED / AI TECHNICAL REVIEW / RESOURCE AUTHORIZATION NOT RECORDED / PREFLIGHT NOT_RUN / PILOT NOT_RUN  
**Read against:** `main` `21e317281a2d2a7faf6198f66302f3912b429011`. This file is advisory until a separately versioned execution Task Contract is frozen. No historical gate is amended or satisfied by the publication of this document.

## 1. Decision and scientific limits

The AI technical recommendation is to retain the originally specified **5-second per-target timeout** for a *future* pilot, subject to a new exact-identity 5-second admission and benign readiness. The 10-second node-tar N01 source/input/runtime correspondence result is historical evidence only; **it cannot authorize 5-second execution**.

The existing N01 pair contract requires a genuine post-run human correspondence disposition. AI assessment cannot be labelled as human review and cannot mint `N01_RELATIVE_HARDLINK_PAIR_QUALIFIED`. Two prospective pathways are allowed for consideration:

- **Original qualification path:** obtain the specified human disposition, then separately authorize and freeze the N03 historical pilot.
- **New exploratory feasibility path:** if that human gate is impractical, propose a newly versioned, explicitly limited feasibility study that may collect pipeline health, cost, reproducibility and mechanically verified generic C0/C1/C2 observations. It must not claim historical known-class rediscovery, substitute for the frozen N01 qualification token, retroactively alter N03, or pool exploratory runs into formal evaluation. This alternative requires a **separate recorded research-owner and resource authorization** before any target execution, including admission. The original frozen pilot still remains NOT_AUTHORIZED.

This file is not that execution authorization.

## 2. What can be decided now without target execution

| Field | Prospective candidate | State |
| --- | --- | --- |
| Host | trusted macOS/OrbStack -> isolated Linux arm64 container | VERIFY_CURRENT |
| Source | future clean pilot worktree based on reviewed `main` | SHA_NOT_FROZEN |
| Packages | node-tar affected 7.5.2 and fixed 7.5.3, Node 22.22.0 | HISTORICAL_IDS_ONLY |
| Worker | historical exact SHA `feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b` | RECHECK_REQUIRED |
| Sentinel | controlled `outside/sentinel.txt`, mode 0600, frozen benign bytes | RECHECK_REQUIRED |
| Timeout | 5 seconds for **all** new arms at the same configuration | RECOMMENDED_NOT_APPROVED |
| Seeds | existing four canonical `minimal_seed_corpus()` members, original order | PROPOSED_UNCHANGED |
| Policy grammar | `uniform-generic-m1-protected-components-v1` | PROPOSED_UNCHANGED |
| Memory | `linux-proc-self-vmhwm-v1`, dedicated fresh controller OS process per campaign | PROPOSED_UNCHANGED |
| Pilot schedule | existing 20 cells, 5 scheduling seeds, 200 seed-inclusive executions/cell (4,000 total) | PROPOSED_NOT_AUTHORIZED |
| Raw storage | new immutable evidence root, nonoverlapping N02/N03 roots | TO_ALLOCATE |
| Repetition and selection | original predeclared schedule (RNG 4242), retain all returns and invalid slots, no retry | PROPOSED_UNCHANGED |

**Do not** treat historical SHA/image IDs as verification of current image content. The later frozen execution contract must include concrete host, controller, Docker context and volume identity, Linux kernel/filesystem, clean source SHA, target image ID and manifest digest, exact environment isolation/profile, preflight result hashes, approved run budgets, output root, plan digest and independent-reader commands.

## 3. Phase R: zero-target read-only evidence audit

This phase can be prepared without authorization to run historical targets:

1. Verify `origin/main` and inspect the requested clean worktree without modifying any existing local edits. Do not stage, discard or reset the primary checkout's `.devcontainer/devcontainer.json` change. Leave draft PR #92 untouched.
2. Verify the presence and immutable expected SHA of the retained N02 raw evidence before running an independent read. If the host path is unavailable, mark `HOST_RAW_NOT_ACCESSIBLE`, **not** PASS.
3. When the private host archive is available, rerun the existing read-only independent reader (the command below is from the N03 report); capture stdout/stderr/return code, exact tool revision and verified artifact digest. Do not write a new human token.

```bash
PYTHONPATH=src python -m inodefence.evaluation.n01_reader \
  /Users/choijiwng/Projects/InodeFence-n02-evidence-20261015T122200Z \
  --raw-manifest-sha256 \
  2a05b5c92cdc679b73b79630102f2cedc238369c1f8167d8eeee6448e0a3cfac
```

4. Verify proposed target packages, production lockfiles, worker and image evidence against the new clean source; record any change as a proposed revision rather than silently carrying N02 admission forward.
5. Review the exact 5-second comparison protocol, per-step timing, required terminal memory record and independent ledger join. Keep N01 known-class assessment distinct from generic oracle output.

**Phase R output:** read-only audit report with PASS/FAIL/NOT_VERIFIABLE by check and original digests; no new target launch and no new pilot PASS token.

## 4. Phase A: resource-approved 5-second admission (NOT AUTHORIZED HERE)

After the team has separately authorized the bounded **preflight** and the trusted host isolation has been reverified, run only:

1. Transport/broker identity and containment checks. Refuse dirty source, unexpected Docker context/controller/volume, mutable tag, source bind mount, or a worker/image/package mismatch; never silently fall back to direct Node subprocess.
2. Revalidate both exact package images against their immutable identities and current controller/runtime.
3. Run only the unchanged oracle controls and four benign seeds per target at the selected **5-second** limit, recording all steps, statuses, and cleanup; do not run the known positive-control TAR as a seed or exploratory search step.
4. Validate the target-side timeout includes lifecycle accounting as required; record full-step time separately. Verify resource limits, non-root/no-network/read-only filesystem and fresh runtime subpath for each run.
5. Write a checksummed immutable admission manifest and independently verify it with a fresh reader. Preserve failure and partial attempts without selective retry.

**STOP immediately** on mismatch, unsafe containment, failed readiness, absent digest/evidence or inadequate resource isolation. Mark the proposed pilot BLOCKED. Do not silently upgrade to 10 seconds: a 10-second choice requires a *pre-outcome*, versioned amendment and equivalent fresh admission.

The concrete invocation for historical 5-second admission must be sourced from an audited, callable host broker. This proposal deliberately does not fabricate one.

## 5. Phase P: separate approval for the proposed B0/B1/B3 feasibility pilot

Only after Phase A passes and a future **specific execution authorization** records an immutable pilot plan can the following be considered:

- Exact 20-cell schedule, seeds 9001–9005, 200 seed-inclusive executions per cell; affected B0/B1/B3 and fixed B3 only, with no feedback across cells.
- Each campaign uses a new controller process and fresh per-case isolated target; never retry a claimed repetition, drop a failed/invalid/STARTED slot, or stop on first observation.
- Per-step monotonic time runs through cleanup, feedback and synchronous journal write. Report final bulk publication and post-campaign candidate adjudication time separately.
- Retain raw mutation-origin provenance and nominate from all completed steps, not just retained-corpus parents. Candidate 3+3 replays are a separate bounded validation budget, never an initial seed or free execution.
- The `VmHWM` record is controller process-lifetime peak RSS and **not** a campaign memory delta or full target-container memory bound. Missing required record and repeated controller process identity fail closed.
- The pilot tests feasibility, artifact integrity, rate and costs. It is not a formally powered feedback superiority estimate; no-hit is INCONCLUSIVE. Historically confirmed known-class rediscovery remains blocked by the original human-disposition contract unless a new prospective claim framework has explicitly been established.

## 6. Before/after decision table

| Finding | Permitted next status | Action |
| --- | --- | --- |
| Read-only N01 digest/reader agrees | MACHINE_EVIDENCE_VERIFIED; HUMAN_PENDING | Continue planning only |
| Retained N02 archive inaccessible | NOT_VERIFIABLE | Preserve blocker; do not claim fresh independent verification |
| 5-second exact-identity preflight succeeds after authorization | PREFLIGHT_PASS_ONLY | Freeze a separate pilot contract; obtain new run authorization |
| 5-second readiness fails | PREFLIGHT_FAIL / PILOT_BLOCKED | Retain negative record; consider predeclared 10-second amendment |
| 20-cell feasibility pilot completes after independent authorization | PILOT_COMPLETED / ANALYSIS_PENDING | Check denominators, journals, timing, memory, controls; no automatic effectiveness claim |
| Provenance or isolation invalid | INVALID / STOP | Preserve artifact and prevent experiment continuation |
| Any attempt to mint the original human N01 token via AI | PROTOCOL_VIOLATION | Reject; no relabeling |

## 7. Student-readable authorizations (not given by creating this document)

A project owner may later approve (a) **only** the fixed-bounded preflight, and separately (b) the 20-cell feasibility pilot, with actual maximum resource budget, host and output volume listed. Approval of a workflow **delegation** is not approval of the target execution or of a scientific verdict. The original human-qualification requirement, and the distinct v3 observation gate, are not implicitly waived.

**Current bottom line:** read-only audit can be prepared; 5-second admission and all fuzzing are still **NOT_RUN / NOT_AUTHORIZED**. Central hypothesis remains **NOT_EVALUATED**.
