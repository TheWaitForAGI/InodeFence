# InodeFence Agent Guide

This file defines repository-wide rules for humans and coding agents.

## Project Purpose

InodeFence is a research prototype for TAR extraction security.

The central research question is:

> Can a fuzzer explore archive-extraction boundary violations more effectively by using filesystem security state — especially object identity and external effects — as feedback, without hardcoding a specific CVE proof-of-concept or a fixed attack recipe?

The project does **not** claim that TAR fuzzing, hardlinks, symlinks, entry ordering, filesystem-state fuzzing, or outside-root writes are new by themselves.

## Research Positioning

Treat novelty as a hypothesis to validate, not as an established fact.

Relevant prior work already covers important parts of the problem:

- Jana & Shmatikov: file-processing semantic gaps, including TAR-related attacks.
- ZIPDiff: feedback-guided archive differential fuzzing.
- LinkZard: feedback-driven file-state fuzzing, including link-related state.
- Wormholes: archive extraction attacks involving symlink composition, hardlinks, path resolution, and creation order.

InodeFence currently investigates the gap between these ideas: generic TAR-entry mutation guided by filesystem-security-state feedback.

Do not write claims such as "first", "novel", or "no prior work" unless the supporting literature review is explicitly documented.

## Research Rules

1. Do not hardcode a CVE identifier as an oracle condition.
2. Do not use a known CVE PoC as the default fuzzing seed for rediscovery experiments.
3. Known CVEs may be used as benchmark ground truth and for root-cause analysis.
4. Security decisions should be expressed as general contracts.
5. Separate observed evidence from hypotheses and expected results.
6. Keep raw experiment outputs separate from paper-ready conclusions.
7. Any paper claim about performance must be reproducible from recorded experiment configuration and results.

## Initial Security Contracts

The initial implementation prioritizes:

1. Object Identity Confinement
   - An extracted internal object should not unexpectedly share filesystem identity with a protected external sentinel.

2. External Effect Noninterference
   - Archive extraction should not unexpectedly alter the content or metadata of protected external sentinels.

Additional contracts such as extraction-root integrity and check/use coherence may be added after the minimal pipeline is stable.

## Scope

### In scope

- TAR extraction
- Linux filesystem semantics
- Regular files, directories, hardlinks, and the required subset of symlinks
- Entry path, link target, type, ordering, and dependency mutations
- Filesystem object identity
- External effects
- Feedback-guided corpus evolution
- Known-vulnerability rediscovery
- Cross-implementation evaluation

### Out of scope for the initial implementation

- Every archive format
- Windows NTFS semantics
- General kernel filesystem vulnerabilities
- Full TOCTOU/race-condition analysis
- Complete symbolic execution
- Reimplementation of every Wormholes bypass
- Full archive-parser ambiguity analysis

## Development Environment

The supported development environments are:

- macOS using the repository Dev Container
- Windows through WSL2 using the same Dev Container

The canonical container environment is Ubuntu 24.04 with Python 3.12.

Source code lives under:

`/workspaces/InodeFence`

Filesystem-security experiments must use:

`$INODEFENCE_RUNTIME_ROOT`

which is currently:

`/var/lib/inodefence`

Do not use the source bind mount as the filesystem-semantics experiment area.

Run the environment check with:

```bash
python scripts/check_dev_env.py
```

## Safety Rules

- Never use real sensitive files such as `/etc/passwd`, SSH keys, user documents, or host secrets as attack targets.
- Use disposable sandbox directories and sentinel files.
- Tests and experiments must be reproducible without damaging the host.
- Destructive filesystem operations must be scoped to the runtime sandbox.

## Code Quality

Before opening a PR, run:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

Text files use LF line endings.

Prefer:

- `pathlib.Path`
- Python standard-library filesystem primitives
- explicit data models and typed interfaces
- deterministic seeds/configurations for experiments

Avoid unnecessary shell-specific behavior when Python APIs are sufficient.

## Architecture Boundaries

The intended high-level pipeline is:

```text
Seed Generator
    -> Structure Mutator
    -> TAR Builder
    -> Target Adapter
    -> State Observer
    -> Security Oracle
    -> Feedback / Corpus
    -> next mutation
```

Keep these responsibilities separate. Do not let target-specific CVE logic leak into generic mutation, observation, oracle, or feedback modules.

## Git Workflow

- Do not develop directly on `main`.
- Create a focused branch for each unit of work.
- Open a PR into `main`.
- Keep PRs small enough to review by architecture or research responsibility.
- Do not mix unrelated documentation, refactoring, and feature work in one PR.

## Documentation Discipline

Use:

- `docs/research/` for research notes, design decisions, prior-work analysis, and CVE analysis.
- `experiments/` for experiment configurations and processed results.
- `paper/` for material that is ready to become part of the final paper.

Research notes are not automatically paper claims.
