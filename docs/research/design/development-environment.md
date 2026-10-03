# Development Environment

## Goal

A developer should be able to work on InodeFence from either:

- macOS,
- Windows through WSL2,

while running the project inside the same repository Dev Container.

The host environment is not treated as the canonical filesystem-semantics environment.

## Canonical Container

Current baseline:

- Ubuntu 24.04
- Python 3.12
- pytest
- Ruff
- tar / gzip / xz
- jq
- strace

The virtual environment is:

```text
/opt/venv
```

The repository is mounted at:

```text
/workspaces/InodeFence
```

## Runtime Filesystem

Filesystem-security experiments use:

```text
/var/lib/inodefence
```

This path is backed by a Docker volume rather than the source-code bind mount.

Reason:

InodeFence studies hardlink, symlink, inode, and filesystem side effects. Host-shared source mounts may have different semantics across macOS and WSL hosts.

## Verified Hosts

### macOS

Verified with:

- ARM64 host
- OrbStack Docker engine
- Ubuntu 24.04 Dev Container
- Python 3.12.3
- Linux volume with working hardlinks and symlinks

### Windows / WSL2

Verified with:

- x86_64 WSL2 host
- Ubuntu 24.04 Dev Container
- Python 3.12.3
- Linux ext4-backed runtime volume
- working hardlinks and symlinks

The CPU architecture and backing filesystem may differ during development.

Do not mix results from different development hosts into one formal evaluation dataset.

## Environment Check

Inside the Dev Container:

```bash
python scripts/check_dev_env.py
```

The check validates:

- Python 3.12
- runtime root availability
- hardlink identity
- symlink behavior
- shared-object write effect

Then run:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

## Line Endings

Repository text files use LF.

This is enforced by:

- `.gitattributes`
- `.editorconfig`
- Ruff formatting configuration

Inspect when needed:

```bash
git ls-files --eol
```

Meaningful text files should normally report:

```text
i/lf w/lf
```

## WSL Repository Location

Keep the repository in the WSL Linux filesystem, for example:

```text
~/Projects/InodeFence
```

Do not use `/mnt/c/...` as the normal project location for filesystem-sensitive development.

## Formal Evaluation

The final paper must select and record one canonical evaluation environment.

At minimum record:

- OS version
- CPU architecture
- filesystem
- container/runtime setup
- Python version
- target versions
- experiment configuration

Development portability and formal experimental reproducibility are separate requirements.
