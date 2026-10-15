# N01 historical wrapper locks

Status: **EXACT LOCK INPUTS PREPARED / PORTABLE VALIDATION PASS**.
Candidate image build, runtime compatibility, benign qualification, affected/fixed replay,
rediscovery and effectiveness are all **NOT_RUN**.

## Task Contract

Current Layer: Layer 6 historical-target preparation. The objective is to freeze the exact npm
wrapper inputs for the intended N01 node-tar `7.5.2 / 7.5.3` pair while changing only the
selected `tar` distribution between pair members.

Allowed files are these locks, this provenance record and portable packaging tests. Target
execution, Docker workflow/runner changes, mutation/oracle/feedback changes and any claim that
an image or historical effect was qualified are prohibited. The existing
`inodefence.evaluation.node_packaging` validator and common Node/worker/base-image pins are
reused unchanged.

## Frozen identities

| Pair member | Wrapper lock SHA-256 | npm tar integrity | Independently retained tarball SHA-256 |
| --- | --- | --- | --- |
| 7.5.2 | `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243` | `sha512-7NyxrTE4Anh8km8iEy7o0QYPs+0JKBTj5ZaqHg6B39erLg0qYXN3BijtShwbsNSvQ+LN75+KV+C4QR/f6Gwnpg==` | `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a` |
| 7.5.3 | `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24` | `sha512-ENg5JUHUm2rDD7IvKNFGzyElLXNjachNLp6RaGf4+JOgxXHkqA+gq81ZAMCUmtMtqBsoU62lcp6S27g1LCYGGQ==` | `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66` |

The two locks share this exact non-target production closure:

- `@isaacs/fs-minipass 4.0.1`
- `chownr 3.0.0`
- `minipass 7.1.2`
- `minizlib 3.1.0`
- `yallist 5.0.0`

Every installed artifact has an official `https://registry.npmjs.org/` URL and canonical
SHA-512 SRI. The `7.1.2` minipass pin matches both historical upstream release locks and the
independently verified common closure. It intentionally supersedes the unmerged
`experiment/n01-node-historical-qualification` branch's later-resolved `7.1.3` wrapper locks;
that branch is not used as runtime evidence or silently merged.

The official registry tarball bytes and all five common dependency artifacts were previously
downloaded and matched to their SRI in the retained static investigation at PR #92 head
`f8be20a37ea5ffdd64c2b56fbc7bfd14218ab595`. This task reviewed that machine evidence and the
two upstream production closures; it did not redownload, install or load the historical
target. Registry signature verification remains NOT_RUN.

## Portable validation and next gate

`tests/evaluation/test_node_historical_locks.py` checks lock byte hashes, selected tar
version/URL/SRI, exact common closure equality and no-overwrite build-context preparation.
`prepare_node_release` copies the exact lock bytes and current source worker into a checksummed
context with the existing Node 22.22.0/build/runtime pins. This is static build-input
validation, not an image build or extractor execution.

The next execution task must use a trusted host broker to build both contexts, retain actual
immutable image IDs/architecture/digests, validate worker/lock/package identity and run benign
readiness before any separately authorized same-input historical qualification. Direct npm
install or Node subprocess execution in the Dev Container is forbidden.
