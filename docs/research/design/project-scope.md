# Project Scope

## One-Sentence Definition

InodeFence is a state-guided TAR extraction fuzzer that repeatedly mutates archive entries, executes real extractors, observes filesystem object identity and external effects, and uses new security-relevant states to guide future mutations.

## Problem

Traditional archive-extraction checks often focus on path confinement:

> Does the archive path escape the extraction root?

InodeFence asks a broader question:

> After or during extraction, did the resulting filesystem object relationships violate the intended security boundary?

A path can appear internal while referring to, or affecting, an external filesystem object.

## Core Idea

Treat a TAR archive as a sequence of filesystem-transforming operations:

```text
Entry 1 -> State S1
Entry 2 -> State S2
Entry 3 -> State S3
```

Instead of using only crashes, code coverage, or output paths as feedback, InodeFence investigates security-relevant state such as:

- object type
- `st_dev` and `st_ino`
- link count
- hardlink relationships
- symlink target
- internal-to-external identity relationships
- external content/metadata effects

## What Is Not Claimed as Novel

The project must not present the following ideas alone as contributions:

- fuzzing TAR archives
- using hardlinks
- using symlinks
- changing archive entry order
- observing filesystem state
- detecting outside-root writes
- feedback-guided fuzzing in general

Prior work already covers these ideas in different forms.

## Current Research Gap Hypothesis

The current hypothesis is that archive extraction can benefit from a feedback loop that:

1. performs generic archive-entry mutation,
2. executes a real extractor,
3. observes filesystem security state,
4. retains inputs that create previously unseen security-relevant states,
5. mutates those inputs again.

The research contribution depends on whether this approach improves exploration compared with appropriate baselines.

## Initial Scope

- Format: TAR
- Platform semantics: Linux
- Primary objects: regular files, directories, hardlinks, required symlink subset
- Initial targets: node-tar and oras-go
- Optional cross-implementation target: GNU tar
- Initial observation: pre/post filesystem snapshots
- Primary security dimensions: object identity and external effects

## Explicit Non-Goals

The first version does not attempt to solve:

- every archive format
- every filesystem
- Windows-specific NTFS semantics
- general race-condition discovery
- kernel filesystem vulnerability discovery
- complete symlink semantics
- full parser differential testing
- symbolic execution

## Success Does Not Require a Zero-Day

A successful capstone can be supported by:

- reliable rediscovery of known vulnerable behavior,
- measurable improvement over baselines,
- cross-implementation applicability,
- reproducible experimental evidence.

A new vulnerability is an additional outcome, not a mandatory success criterion.
