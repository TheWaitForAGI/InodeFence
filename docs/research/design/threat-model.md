# Threat Model

## Attacker Capability

The attacker can provide a malicious TAR archive to a victim or service that extracts it.

The attacker may control archive-entry properties including:

- entry type
- path
- link target
- entry order
- duplicate entries
- whether referenced targets exist at the time an entry is processed

Initial entry types include:

- regular file
- directory
- hardlink
- required subset of symbolic links

## Victim Behavior

A target extractor processes the attacker-controlled TAR into a designated extraction directory.

The security expectation is that archive processing does not unexpectedly affect protected filesystem objects outside that extraction boundary.

## Initial Boundary

Each test run uses a disposable sandbox with:

```text
run-UUID/
├── outside/
│   └── protected sentinels
└── extract/
    └── extraction destination
```

The `outside` directory represents protected external state.

## Attacker Does Not Initially Control

The first version does not assume an attacker can:

- modify the filesystem concurrently while extraction is running,
- race validation and use with external processes,
- exploit kernel/filesystem implementation bugs,
- gain arbitrary host access outside the sandbox.

Runtime manipulation such as the OpLock-style model studied in other work is out of scope for the initial implementation.

## Candidate Security Failures

A run may be security-relevant when:

- an internal path unexpectedly shares identity with an external sentinel,
- an external sentinel's content or metadata changes,
- a protected external object is created, replaced, removed, or linked unexpectedly,
- the extraction root itself is redirected in a way that changes the intended confinement boundary.

## Safety Requirements

- Never use real sensitive files as sentinels.
- Never point experiments at a developer's home directory.
- Use only the dedicated runtime root.
- Clean up disposable run directories.
- Persist only intentionally saved findings and experiment data.
