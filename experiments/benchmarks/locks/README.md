# Historical target locks

These npm lockfile v3 inputs freeze benchmark wrapper dependencies. They are execution
inputs, not upstream development locks and not evidence that a target was qualified.

N01 uses `node-tar-7.5.2.package-lock.json` and
`node-tar-7.5.3.package-lock.json`. Both were resolved from the official npm registry on
2026-10-12 with npm 10.9.4, `--package-lock-only`, `--ignore-scripts`, `--engine-strict`,
`--no-audit` and `--no-fund`. The root dependency is exact. Every package has an official
registry URL and SHA-512 SRI, and both files have the same production closure except for
the selected `tar` release artifact.

The common frozen closure uses `minipass` 7.1.3 rather than the 7.1.2 present in the
historical upstream development locks. This is deliberate pair symmetry, not a claim of
bit-equivalence to an upstream checkout. The immutable lock, target package SRI, worker,
base images and final local image ID must all be retained in runtime qualification.

| Target | Lock SHA-256 |
| --- | --- |
| node-tar 7.5.2 | `d8bb8b8977460d2c0f7c7942d70a2057ee3cc128d80e115d73a2e00b2b84d112` |
| node-tar 7.5.3 | `33067565217418c02e6cd76483587e46c081625b91de7e73d96405bdef4dc8d4` |

These locks are admitted only through `inodefence.evaluation.node_packaging`, which
reconstructs the minimal package manifest, rejects ranges/local dependencies/missing SRI,
and emits source- and file-checksummed build contexts.
