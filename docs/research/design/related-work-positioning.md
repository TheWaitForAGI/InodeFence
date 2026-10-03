# Related-Work Positioning

This document records the current working position of InodeFence relative to the closest prior work.

It exists to prevent the project from accidentally presenting already-established ideas as new contributions.

## Jana & Shmatikov — 2012

**Abusing File Processing in Malware Detectors for Fun and Profit**

Relevant points:

- studied semantic gaps between file-processing implementations,
- included TAR-related attacks,
- used black-box differential techniques for some formats,
- showed that malformed archive/file metadata can create security-relevant interpretation differences.

What this removes from our novelty space:

- TAR malformed inputs are not new,
- TAR semantic-gap attacks are not new,
- header/metadata mutation is not new.

Current distinction to investigate:

- archive extraction guided by filesystem object identity and external-effect feedback is not established by this work.

## ZIPDiff — 2025

**My ZIP isn't your ZIP: Identifying and Exploiting Semantic Gaps Between ZIP Parsers**

Relevant points:

- archive-aware mutation,
- byte-level mutation,
- feedback-guided corpus evolution,
- extraction-output comparison,
- large-scale differential testing across ZIP parsers.

What this removes from our novelty space:

- archive-aware fuzzing is not new,
- feedback-guided archive fuzzing is not new,
- interesting-seed retention is not new,
- path/order mutation by itself is not enough for novelty.

Important limitation for InodeFence:

Later work reports that ZIPDiff did not discover tested symlink vulnerabilities that required more complex link composition and creation-order behavior.

## LinkZard — 2025

**Pig in a Poke: Automatically Detecting and Exploiting Link Following Vulnerabilities in Windows File Operations**

Relevant points:

- feedback-driven file-state fuzzing,
- state-query-driven mutation,
- file-operation sequence analysis,
- link-related state including hardlink information and link count.

What this removes from our novelty space:

- filesystem-state fuzzing in general is not new,
- observing hardlink state is not new,
- observing link count is not new,
- analyzing ordered file operations is not new.

Current distinction to investigate:

- LinkZard is not an archive-entry mutation framework and does not use a TAR archive as the evolving input corpus.

## Wormholes — 2026

**Wormholes in the File System: Understanding the Misunderstanding of Symlinks**

This is currently the closest prior work.

Relevant points:

- archive extraction is a core scenario,
- symlink composition,
- entry creation order,
- dangling symlinks,
- symlink updates,
- extraction-root manipulation,
- hardlink creation through symlink-related paths,
- arbitrary file write/read consequences.

What this removes from our novelty space:

- symlink attacks are not new,
- hardlink attacks are not new,
- symlink + hardlink combinations are not new,
- entry-order attacks are not new,
- state changes across archive entries are not new,
- outside-root effects are not new.

## Current InodeFence Research Gap Hypothesis

The current question is not:

> Can TAR hardlinks, symlinks, or entry ordering cause extraction vulnerabilities?

Prior work already answers that.

The question is:

> Can generic archive-entry mutation be guided by filesystem object identity and external-effect state so that a fuzzer evolves its corpus toward security-relevant states without being given a fixed attack recipe?

Conceptually:

```text
Fixed strategy
    known semantic analysis
        -> predefined bypass/write recipe
        -> target

InodeFence hypothesis
    generic seed
        -> generic mutation
        -> extractor
        -> filesystem security state
        -> retain novel state
        -> mutate again
```

## Claims We Must Not Make Yet

Do not currently claim:

- "InodeFence is the first state-guided archive fuzzer."
- "No prior work uses inode information."
- "No prior work fuzzes archive links."
- "No prior work considers entry ordering."
- "The proposed method is better than fixed strategies."
- "The proposed method generalizes across extractors."

These are either contradicted by prior work or require experiments / broader literature review.

## What the Evaluation Must Establish

The project becomes defensible if experiments show that the proposed state representation and feedback loop provide measurable value.

Examples:

- faster rediscovery under equal budget,
- higher rediscovery rate,
- exploration of more security-relevant states,
- useful generalization across target implementations,
- discovery of states not reached by weaker baselines.

Until those measurements exist, these remain hypotheses.
