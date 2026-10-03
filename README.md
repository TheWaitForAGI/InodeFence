# InodeFence

InodeFence is a research prototype for **filesystem-security-state-guided fuzzing of TAR extraction**.

The project investigates whether archive fuzzing can be guided by security-relevant filesystem state — especially object identity and external effects — instead of relying only on fixed attack recipes, output paths, crashes, or code coverage.

## Research Question

> Can generic TAR-entry mutation combined with filesystem-security-state feedback discover archive-extraction boundary violations efficiently without hardcoding a specific CVE PoC or fixed attack sequence?

This is a research hypothesis, not a claim that the approach is already proven or novel.

## Current Status

**Layer 0 — Reproducible development environment: complete**

Verified on:

- macOS / ARM64 through the repository Dev Container
- Windows / WSL2 / x86_64 through the same Dev Container

Container baseline:

- Ubuntu 24.04
- Python 3.12
- pytest
- Ruff
- dedicated Linux runtime volume for filesystem-semantics experiments

The project is now entering **Layer 1 — research context and architecture definition**.

No production fuzzer exists yet.

## Core Pipeline

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

## Initial Research Focus

The first implementation focuses on:

- TAR
- Linux filesystem semantics
- regular files, directories, hardlinks, and a required subset of symlinks
- filesystem object identity
- protected external sentinels
- pre/post state observation
- security-state-guided corpus selection

Initial target order:

1. node-tar
2. oras-go
3. GNU tar if time permits

## What InodeFence Does Not Claim

The project does not claim that the following are new on their own:

- TAR fuzzing
- hardlink or symlink attacks
- entry-order attacks
- filesystem-state fuzzing
- outside-root writes
- feedback-guided fuzzing

The research contribution must be supported by comparison with prior work and experiments.

See:

- `docs/research/design/project-scope.md`
- `docs/research/design/research-questions.md`
- `docs/research/design/security-contracts.md`
- `docs/research/design/threat-model.md`
- `docs/research/design/architecture.md`
- `AGENTS.md`

## Development Environment

Open the repository in its Dev Container.

Then verify the environment:

```bash
python scripts/check_dev_env.py
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

Filesystem-security experiments must run under:

```text
/var/lib/inodefence
```

Do not use real sensitive host files as experimental targets.

## Repository Layout

```text
src/inodefence/
├── generator/
├── mutator/
├── targets/
├── observer/
├── oracle/
└── feedback/

docs/research/   research and design notes
experiments/     experiment configuration and results
paper/           paper-ready material
findings/        intentionally saved findings
scripts/         development and experiment helpers
tests/           automated tests
```

## Workflow

- Do not develop directly on `main`.
- Use focused branches.
- Open a PR into `main`.
- Keep generic research logic separate from target-specific CVE details.

See `AGENTS.md` for the repository-wide rules.
