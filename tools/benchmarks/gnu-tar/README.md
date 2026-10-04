# Pinned benign GNU tar tooling

This independent path uses GNU tar 1.34 already present in the exact digest-pinned
Python 3.12.13 bookworm base from the repository's existing benign helper tooling.
No package installer, floating dependency or host-local binary enters the image.
The four fixed benign TAR hashes and original case IDs are generated through the
current pinned builder. Worker, profile and Dockerfile hashes plus actual source
provenance are recorded; incomplete, changed or extra-file contexts fail validation.

Prepare a new context with `python -m inodefence.evaluation.gnu_packaging prepare
CONTEXT --repository REPOSITORY`, then validate it with the `validate` operation.
Use Docker's explicit context and `build --iidfile NEW_IIDFILE CONTEXT`; consume
only the inspected immutable image ID. Build-time identification checks exact
Python/GNU versions and records hashes of the actual image binaries, worker and
profile. A registry manifest digest and resulting platform-specific image ID are
different identities. Preserve the generated packaging manifest and build logs.

The worker additionally checks identity immediately before extraction and accepts
only fixed regular/directory/internal-hardlink/internal-symlink TARs into a fresh
empty root. Other inputs fail closed before GNU tar executes. This is benign
target infrastructure, not arbitrary-case fuzzing or vulnerability reproduction.
Adapter integration, qualification, benchmark READY status and actual evaluation
results are separate stages. Existing node-tar 7.5.22 tooling is unchanged.
