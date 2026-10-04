# Static artifact and public-API qualification

**SOURCE/METADATA VERIFIED, RUNTIME QUALIFICATION NOT_RUN.** Accessed 2026-10-04.
Only upstream text, Git objects, official registry metadata and checksum records
were inspected. No affected package was installed, built or executed; no archive
or exploit was constructed. Exact machine values are in the
[catalog](../../../experiments/benchmarks/catalog-v1.json), `artifact_metadata`.
These records improve G2 research evidence; they do not pass all of G2 or G3–G8.

## Selected Node artifacts

All six npm versions exist. Each registry `gitHead` equals the peeled upstream
`v<version>` tag commit. Upstream package.json versions/engines agree with npm.
An annotated tag object is distinct from its peeled source commit; freeze the
commit plus package integrity, not the mutable tag name alone.

| Candidate / pair | Registry version records | Peeled source commits, affected → fixed | Declared Node engine |
| --- | --- | --- | --- |
| N01 7.5.2 → 7.5.3 | [7.5.2](https://registry.npmjs.org/tar/7.5.2), [7.5.3](https://registry.npmjs.org/tar/7.5.3) | d9ea73a9b3fc0a2f9734fda65279f48c7cc99f28 → 03138441b238f48070fb22824b2529c445bc70c7 | >=18 |
| N03 7.5.7 → 7.5.8 | [7.5.7](https://registry.npmjs.org/tar/7.5.7), [7.5.8](https://registry.npmjs.org/tar/7.5.8) | 4a37eb9a1cf1137df4eb70c5c7f849f412ff3cdb → 6b8eba0ef367ac937e703238daa6df94ae6f823f | >=18 |
| N04 6.1.1 → 6.1.2 | [6.1.1](https://registry.npmjs.org/tar/6.1.1), [6.1.2](https://registry.npmjs.org/tar/6.1.2) | 1e33534e1e96ca6385b3a4749876aea2cda61cea → 3f7b20097e0daba10441507becbf5b87c6b83b8b | >= 10 |

The registry supplies `dist.integrity` (SHA-512 SRI), `dist.shasum` (SHA-1),
tarball URL, file count and unpacked size for each. Catalog freezes the identity
fields; no tarball-byte verification or registry-signature verification occurred.
SRI identifies npm distribution bytes, not upstream source content or a container.
Release existence here is verified through the upstream release tag and official
package publication; a separate GitHub release page is not required.

Git ancestry checks on the upstream repository show each fixing commit absent
from the selected affected tag and present in the fixed tag:

| Candidate | Production repair in the fixed release |
| --- | --- |
| N01 | [340eb285](https://github.com/isaacs/node-tar/commit/340eb285b6d986e91969a1170d7fe9b0face405e), linkpath sanitation |
| N03 | [d18e4e1f](https://github.com/isaacs/node-tar/commit/d18e4e1f846f4ddddc153b0f536a19c050e7499f) and [2cb1120b](https://github.com/isaacs/node-tar/commit/2cb1120bcefe28d7ecc719b41441ade59c52e384), hardlink resolution checks |
| N04 | [9dbdeb6d](https://github.com/isaacs/node-tar/commit/9dbdeb6df8e9dbd96fa9e84341b9d74734be6c20), directory-cache invalidation |

These checks establish repair inclusion, not that unrelated releases have no
other vulnerabilities. Advisory evidence/range limits remain in the
[candidate ledger](candidate-matrix.md).

## Common Node runtime feasibility

**STATICALLY COMPATIBLE with Node 22.22.0** applies to declared runtime metadata.
All six engine ranges admit it; the production dependency entries in their
upstream package locks also admit it where they declare engines. The 7.x closure
is @isaacs/fs-minipass 4.0.1, chownr 3.0.0, minipass 7.1.2, minizlib 3.1.0,
yallist 5.0.0. The 6.x closure is chownr 2.0.0, fs-minipass 2.1.0, minipass 3.1.3,
minizlib 2.1.1, mkdirp 1.0.4, yallist 4.0.0 (last has no declared engines).
Package metadata supports CommonJS loading: 7.x declares dist/commonjs, while
6.x has index.js/default directory loading. No metadata upper bound excludes 22.
Source does not promise that an old release was tested on a future Node version.

Source links: [v7.5.2 package.json](https://github.com/isaacs/node-tar/blob/v7.5.2/package.json),
[v7.5.3 lock](https://github.com/isaacs/node-tar/blob/v7.5.3/package-lock.json),
[v7.5.7 lock](https://github.com/isaacs/node-tar/blob/v7.5.7/package-lock.json),
[v7.5.8 lock](https://github.com/isaacs/node-tar/blob/v7.5.8/package-lock.json),
[v6.1.1 package.json](https://github.com/isaacs/node-tar/blob/v6.1.1/package.json),
[v6.1.2 lock](https://github.com/isaacs/node-tar/blob/v6.1.2/package-lock.json).

Upstream lock SHA-256 values in the catalog were computed from exact raw file
bytes and checked against the peeled commit's Git blob. These are historical
upstream development locks, not the future benchmark wrapper's npm lock. Later
freeze a wrapper lock containing the selected tar SRI and complete production
closure. Within each pair, prefer identical transitive versions when ranges
permit (the inspected upstream production versions match within all three pairs).
Any required change becomes recorded pair configuration, not hidden build drift.

All pairs still **REQUIRE RUNTIME QUALIFICATION**: benign loading/extraction,
worker options, rejection/error semantics, Linux behavior and strict=true remain
unmeasured. Runtime replacement, if necessary, must be common to the comparison
and frozen before experiments. No static engines check promotes G7.

## Future artifact freeze

| Identity | Already available statically | Required after audit |
| --- | --- | --- |
| npm package/source | Exact version, SRI, shasum, URL, peeled commit and upstream lock hash | Verify fetched bytes; freeze benchmark package-lock and all resolved production artifacts |
| Node/base images | Existing benign [Dockerfile](../../../tools/node-tar/Dockerfile) pins Node 22.22.0 build-base and distroless digests | Reuse/verify platform-specific bases; retain build recipe and platform; no affected image built here |
| Target execution | Immutable local image ID enforced by backend | Record built image ID and distribution/platform digest where available; no bit-identical rebuild claim |
| Worker/dependency identity | Existing bind reports worker/lock SHA-256 | Freeze wrapper source/lock; resolve EC-01 attestation gap; match contents before execution |
| ORAS dependency/source | Module/version and h1 checksums below | Freeze benchmark go.mod/go.sum closure, exact compiler/base/build flags/wrapper/image |

## O01 source and module chain

Upstream [GHSA-fxhp-mv3v-67qp](https://github.com/oras-project/oras-go/security/advisories/GHSA-fxhp-mv3v-67qp)
names affected v2.6.0 and patched v2.6.2. The
[v2 repair c463c654](https://github.com/oras-project/oras-go/commit/c463c654ab3ef34422c1764cd619806cebf20451)
explicitly backports the CWD hardlink correction from main; it is absent from
v2.6.0 and included in v2.6.2. The [fixed release](https://github.com/oras-project/oras-go/releases/tag/v2.6.2)
links that advisory/repair. Source joins a relative target to the link destination's
directory before os.Link. This corrects the validated-versus-used base mismatch.
The selected pair is 2.6.0 → 2.6.2; no claim that every older release was tested.

The [reviewed ecosystem API record](https://api.github.com/advisories/GHSA-fxhp-mv3v-67qp)
(updated 2026-08-04) gives <=2.6.1 and first patched 2.6.2. A cached rendered
advisory view showed no patched version; the current official API resolves that
stale field. Upstream advisory names v2.6.0 specifically, while the v2 repair
message also includes v2.6.1. Record the different range specificity without
claiming independent execution for every earlier version.

| Module version | Official origin | Official checksum record |
| --- | --- | --- |
| v2.6.0 | [proxy metadata](https://proxy.golang.org/oras.land/oras-go/v2/@v/v2.6.0.info): 05a2b09cbf2eab1df691411884dc4df741ec56ab | [sumdb](https://sum.golang.org/lookup/oras.land/oras-go/v2@v2.6.0), module h1:X4ELRsiGkrbeox69+9tzTu492FMUu7zJQW6eJU+I2oc= |
| v2.6.2 | [proxy metadata](https://proxy.golang.org/oras.land/oras-go/v2/@v/v2.6.2.info): 105715ee12eac6895ec736a075285c34d9f2eeb6 | [sumdb](https://sum.golang.org/lookup/oras.land/oras-go/v2@v2.6.2), module h1:N04RXngAp1LJKTG6ifz3xHPipasEkWr+hFmInja5YKo= |

Catalog also stores each go.mod h1 checksum. These identify Go module content,
not final executable/image bytes. Checksum-database records were read; independent
signed-tree proof verification and dependency builds were not performed.
[v2.6.0 go.mod](https://github.com/oras-project/oras-go/blob/v2.6.0/go.mod) requires
Go 1.23.0 with suggested toolchain 1.23.3;
[v2.6.2 go.mod](https://github.com/oras-project/oras-go/blob/v2.6.2/go.mod) requires
Go 1.25.0 and x/sync 0.22.0. Its release notes mention a bump to 0.21.0 instead;
build pins must use the tagged go.mod, with discrepancy recorded. Go 1.23 is
**STATICALLY INCOMPATIBLE** with the fixed source minimum; a common compiler
>=1.25.0 is plausible but **REQUIRES RUNTIME QUALIFICATION** and an exact pin.
[Official Go toolchain rules](https://go.dev/doc/toolchain) treat go directives
as minimums and may automatically fetch toolchains; future offline builds/runs
must freeze the compiler and prevent unrecorded switching.

## O01 supported offline public path

Module `oras.land/oras-go/v2`, package `content/file`, public `file.New(workingDir)`
returns `*file.Store`; `Store.Push(ctx, ocispec.Descriptor, io.Reader)` reaches
push → pushDir → extractTarGzip → extractTarDirectory → ensureLinkPath/os.Link.
Private helpers are evidence, not callable benchmark entrypoints.
Both tags retain that public route. Sources:
[v2.6.0 file.go](https://github.com/oras-project/oras-go/blob/v2.6.0/content/file/file.go),
[v2.6.0 utils.go](https://github.com/oras-project/oras-go/blob/v2.6.0/content/file/utils.go),
[v2.6.2 file.go](https://github.com/oras-project/oras-go/blob/v2.6.2/content/file/file.go),
[v2.6.2 utils.go](https://github.com/oras-project/oras-go/blob/v2.6.2/content/file/utils.go).

Required conceptual inputs: local gzip-compressed TAR reader; descriptor with
actual compressed size/digest, fixed benign `ocispec.AnnotationTitle`, and
`file.AnnotationUnpack="true"`; SkipUnpack=false, ForceCAS=false and default
path-traversal protections. Supplying the uncompressed digest via AnnotationDigest
can verify the logical TAR as well. No registry/client/credentials/network is
needed after dependencies and wrapper are built. Store uses local temp files and
in-memory fallback/storage metadata; temp files can stay in bounded target /tmp.

Title also defines the archive namespace prefix that upstream trims. Raw minimal
seed TARs do not already carry it: the future wrapper must specify a deterministic
prefix/gzip transport or explicitly qualified target-facing case representation.
Store root may be the controlled run root, title `extract`, producing the existing
extract directory while process CWD is controlled outside/. All names/digests and
the mapping must be frozen and shared across the pair. Preserve raw link text,
entry order/duplicates and attack-sensitive spelling; retain original logical
case/TAR and any transformed TAR/gzip hashes separately. No hidden normalization
or silent claim that upstream consumed the original unprefixed bytes.

O01 requires a same-device protected regular file in the controlled process CWD,
with fresh empty extraction and no planted internal symlinks. Current backend
starts in extract/; a future reviewed invocation may set/chdir to outside/ before
calling the public API. That target-specific call belongs in a wrapper/config,
not Campaign/Oracle. Its scope/identity must be recorded before execution.
Offline feasibility is SOURCE-DERIVED; adapter, mapping and runtime are unqualified.

## G01 bounded upstream investigation

The [CNA JSON](https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2026/18xxx/CVE-2026-18508.json)
reports fixed RHEL RPM versions; they remain vendor backports, not GNU release
numbers. The [Red Hat page](https://access.redhat.com/security/cve/CVE-2026-18508)
still exposes deferred-fix wording in some product views, while the newer CNA
record includes fixed package versions. Do not flatten product/date-specific data.
No public backport diff linking those packages to an exact GNU commit was obtained.

Static upstream Git inspected at c17976eba549f44cbc34233cfaac4faddb3918c0.
[Candidate change 1b91f5f6](https://cgit.git.savannah.gnu.org/cgit/tar.git/commit/?id=1b91f5f66f8e6c490eef0fdee50f652cfe155844)
adds a hidden CWD change to the chosen top-level directory and adjusts hardlink
names. The v1.35 source transforms only member names for --one-top-level;
hardlink names are interpreted against working CWD. This explains a narrower
boundary mismatch structurally, without constructing an input. The change's
commit timestamp is 2026-07-29; its author timestamp is older. Its title says
draft and its message records test/behavior concerns. Later top-level/CWD changes
also exist. It is a **candidate repair**, not a verified CVE fixing association.

The [upstream NEWS](https://cgit.git.savannah.gnu.org/cgit/tar.git/plain/NEWS)
still labels current development 1.35.90 (git). No upstream release tag contains
1b91f5f6; latest release tag inspected is v1.35. A parent/commit pair would change
multiple CWD/openat behaviors and is not a clean frozen research pair yet.
Extraction root must represent the designated top-level directory, with controlled
working-directory objects outside it; the current fixed extract/ Region mapping
cannot silently treat a nested top-level boundary as equivalent.

G01 exact CVE fixing commit, upstream affected range, released fixed comparator,
vendor-backport relationship and harness root mapping remain **UNKNOWN**. Preserve
null selected_pair and secondary status. G02 work is deferred: it does not remove
these gates or justify a third target.
