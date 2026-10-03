# System Architecture

## Design Goal

Build the smallest end-to-end loop that can later grow into a feedback-guided fuzzer.

Do not begin with the full mutation space or complex runtime tracing.

## High-Level Pipeline

```text
Seed Generator
    ↓
Structure Mutator
    ↓
TAR Builder
    ↓
Target Adapter
    ↓
State Observer
    ↓
Security Oracle
    ↓
Feedback / Corpus
    └──────────────→ next mutation
```

## Layer 1 — Seed Generator

Purpose:

- create small, valid TAR test cases,
- keep seeds understandable,
- provide stable initial input for experiments.

Initial seed support should be minimal.

## Layer 2 — Structure Mutator

Purpose:

- mutate entry type,
- mutate path,
- mutate link target,
- reorder entries,
- add/remove/duplicate entries,
- vary target-existence dependencies.

Important:

Mutation operators are generic. They must not simply encode a CVE PoC or a numbered Wormholes bypass.

## Layer 3 — TAR Builder

Purpose:

- serialize an internal archive representation into a concrete TAR input,
- keep archive construction separate from mutation policy.

## Layer 4 — Target Adapter

Purpose:

- execute a specific extractor with a common interface,
- isolate target-specific invocation details.

Initial target order:

1. node-tar
2. oras-go
3. GNU tar if time permits

Target-specific logic belongs here, not in generic oracle or mutation code.

## Layer 5 — State Observer

Purpose:

- snapshot relevant filesystem state before and after extraction.

Initial observations:

- relative path
- object type
- `st_dev`
- `st_ino`
- `st_nlink`
- mode
- size
- symlink target
- content hash for selected objects
- protected sentinel state

The initial version uses pre/post snapshots rather than full operation tracing.

## Layer 6 — Security Oracle

Purpose:

- evaluate generic security contracts.

Initial implementation order:

1. Object Identity Confinement
2. External Effect Noninterference
3. Extraction Root Integrity
4. Check/Use Coherence if instrumentation is later added

## Layer 7 — Feedback and Corpus

Purpose:

- convert observed state into a stable signature,
- decide whether a test case is interesting,
- retain security-relevant novel states,
- schedule retained seeds for further mutation.

This layer is the core research mechanism.

## Planned Common Data Flow

```text
ArchiveCase
    ↓
build / run
    ↓
ExecutionResult
    ↓
observe
    ↓
StateSnapshot
    ↓
signature
    ↓
StateSignature
    ↓
oracle
    ↓
ViolationResult
    ↓
feedback
    ↓
Interesting / Boring
```

The exact Python data models should be introduced in the next implementation layer, after these responsibilities are agreed upon.

## Implementation Order

### Milestone 1 — Minimal observation path

```text
Known small TAR
    → one target
    → sandbox
    → pre/post snapshot
    → identity/effect oracle
```

### Milestone 2 — Generic TAR generation

Create equivalent TAR cases from internal data models.

### Milestone 3 — Mutation

Add generic structural mutations.

### Milestone 4 — Feedback loop

Retain and reschedule interesting security states.

### Milestone 5 — Evaluation

Run baselines, ablations, known-vulnerability rediscovery, and current-version campaigns.
