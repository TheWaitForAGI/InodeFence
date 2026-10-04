# Policy dataset compatibility v1

`validate_policy_dataset((PolicyDatasetMember(directory, binding_digest), ...))`
freshly verifies every complete evaluation-bound policy bundle before comparison.
An optional externally trusted binding digest anchors each member. Unsupported
legacy/raw-only formats, missing/corrupt bindings, unknown/dirty source or unknown
harness runtime are incompatible. Invalid members retain their position with null
digest slots and explicit diagnostics; they are not silently excluded.

Source revision, builder/schemas, protocol, seed profile/order, budget, timeout,
sentinel bytes/modes/profile and isolation policy must agree. Differences are
`incompatible` and prevent pooling. Search/mutation/projection IDs, target/image/
artifact identity, harness/container runtime, environment profile and random seed
differences are `requires_stratification` with explicit original member-index
groups. Only `compatible` permits pooling. Seed variation is ignored only when
`allow_seed_variation=True` is explicitly selected for independent repetitions.
Policy differences are never erased, even when seed variation is allowed.

Full canonical RunResult digests detect duplicated raw executions within/across
members. Relabeling config/policies/source/profiles and recomputing checksums
cannot make copies into independent observations. This checks recorded evidence,
not authenticity or unrecorded correlated effects. Independent executions may
still be semantically identical; their raw lifecycle/timing/object evidence is
preserved and distinct. No mutation proposal or RNG execution is reconstructed.

CLI: `python -m inodefence.evaluation.policy_dataset DIRECTORY...` with optional
`--allow-seed-variation`. Output is machine-readable schema-v1 JSON, exit zero
only on compatibility. There is no automatic execution, grouping/pooling of
incompatible strata, statistical result, rediscovery or paper-readiness claim.
Qualification remains a separate prerequisite for formal benchmark use. Profile
names are explicit declarations; binary identity absent from original reference
provenance is not invented. Tests label synthetic metadata/policy assemblies
explicitly and execute only four benign initial cases, with no mutations.
