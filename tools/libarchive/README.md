# libarchive entry-boundary qualification dependency

This tool is a benign research probe for the public libarchive read/write-disk API.
It is not an InodeFence target adapter or a qualified benchmark target.

`entry-boundary-probe.c` follows the upstream `archive_read_next_header` →
`archive_write_header` → data copy → `archive_write_finish_entry` loop. In traced
mode it writes the archive ordinal and path only after `finish_entry` returns, then
marks the calls immediately before and after `archive_write_close`. `quiet` mode
runs the same extraction loop without markers for final-state baseline comparison.

The qualification image adds pinned Ubuntu arm64 packages libarchive-dev and
libarchive13t64 3.7.2-2ubuntu0.9 to the current Dev Container image. Resolve and
record both the base and resulting image IDs; the local base tag is a build input,
not a portable registry identity.

```bash
docker build -f tools/libarchive/Dockerfile.qualification \
  -t inodefence-libarchive-qualification:3.7.2-2ubuntu0.9 .
```

The target run must still use a read-only root filesystem, no network, uid/gid 1000,
capabilities 0, no-new-privileges, resource bounds and the disposable runtime volume.
The probe accepts only a controlled archive path and an existing extraction root.
It does not contain a CVE payload or access host documents.
