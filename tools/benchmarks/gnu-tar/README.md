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

## Contained benign adapter integration

`GnuTarInvocation.bind(backend, immutable_image_id)` returns the existing
`IsolatedTarget` composition. Actual image identity is verified against the
current trusted worker/profile; observed GNU/Python binary digests are retained.
The invocation has no direct subprocess fallback. Both adapter and worker reject
other inputs, and worker infrastructure errors are separate from target statuses.

From the repository root on the host, use Python 3.12+ with `PYTHONPATH=src`:

```bash
python -m scripts.evaluation_gnu_container --context CONTEXT --controller CONTROLLER --volume VOLUME --image IMMUTABLE_IMAGE_ID --evidence NEW_ABSOLUTE_CONTROLLER_PATH
```

The controller must already own the named Linux runtime volume under the existing
container execution contract. The dedicated runner follows the existing trusted
stdio broker design; target streams are captured as data and never broker requests.
Only containers created with its own ownership label are cleaned up.

Four fixed Python-reference originals are verified and replayed against GNU tar
in fresh runtimes. Full replay and pair records, a separate actual tiny-timeout
result and unsupported-ordinary-input Failure Ledger are preserved. Existing
destinations are rejected. `checks.json` appears only after all integration
checks and partial qualification records are published. An interrupted run can
leave a valid complete replay without overall integration completion; never treat
the whole directory as completed merely because some files exist.

The partial qualification links real identity, isolation, primitive extraction,
timeout, snapshot and cleanup observations. Status classification remains NOT_RUN
because REJECTED/FAILED have only unit coverage; overall qualification is NOT_RUN
and benchmark READY remains false. Unexpected contract observations stay in raw
evidence; no clean-security, rediscovery or effectiveness result is assumed.

The runner also exercises existing repeated-run metadata and statistical helpers
with explicit seeds 31/37 and budget four. Each independent campaign consists only
of those four initial fixtures; no mutation executes and seed changes do not alter
this fixed-fixture plumbing input sequence. Validated statistics are engineering
observations, not a research comparison. Clean source provenance is required by
the statistics dataset validator; commit local implementation changes before
running this integration. Prior outputs are retained in their original directories.
