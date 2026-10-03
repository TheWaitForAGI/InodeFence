# Security Contracts

Security contracts are generic rules that describe what a safe extraction should preserve.

They are intentionally independent of individual CVE identifiers.

## Contract A — Object Identity Confinement

### Rule

An object created inside the extraction area must not unexpectedly share filesystem identity with a protected external sentinel.

### Initial Observable

On the same filesystem, compare:

```text
(st_dev, st_ino)
```

A candidate violation exists when an internal object and a protected external sentinel unexpectedly share the same object identity.

### Why It Matters

Different paths can refer to the same underlying object. A path-only observer may therefore miss a security-relevant relationship.

### Initial Priority

High. This is part of the minimal implementation.

---

## Contract B — External Effect Noninterference

### Rule

Processing an untrusted archive must not unexpectedly change protected external sentinel objects.

### Candidate Observables

- existence
- content hash
- file size
- mode
- selected timestamps
- later: ownership where the experiment environment supports it safely

### Example

If modifying or creating an extraction result causes a protected external sentinel's content to change, the extraction has produced an external side effect.

### Initial Priority

High. This is part of the minimal implementation.

---

## Contract C — Extraction Root Integrity

### Rule

The physical meaning of the extraction root must not be redirected or replaced in a way that causes later extraction operations to escape the intended boundary.

### Notes

This contract is relevant to destination-manipulation patterns, but it should not block the minimal A/B implementation.

### Initial Priority

Medium.

---

## Contract D — Check/Use Coherence

### Rule

When a target validates one path or object and later performs a filesystem operation, the validated target and the used target should remain semantically consistent.

### Notes

This contract may require target-specific instrumentation or operation tracing. It is useful for root-cause analysis of validation/use mismatches, but it is not required for the first end-to-end fuzzer.

### Initial Priority

Later.

---

## Oracle Design Principles

The oracle must:

- express a general security property,
- avoid checks such as `if target_version == vulnerable_version`,
- avoid matching a known PoC byte sequence,
- produce enough evidence to reproduce a finding,
- distinguish a suspicious state from a confirmed security violation when necessary.

## Sentinel Policy

Never target real host-sensitive files.

Each run should create controlled sentinels inside the dedicated runtime sandbox, for example:

```text
run-UUID/
├── outside/
│   ├── sentinel-a
│   └── sentinel-b
└── extract/
```

The observer records sentinel state before and after extraction.
