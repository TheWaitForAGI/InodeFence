// Target-specific oras-go extraction worker for InodeFence generality (M4.1).
//
// It drives oras-go's content/file Store, which unpacks a directory artifact
// (a gzipped tar carrying the io.deis.oras.content.unpack annotation) to disk.
// InodeFence's generic model/oracle are NOT imported here: this worker only
// invokes the third-party extractor and reports raw bytes/outcome. The Observer
// and Oracle judge the resulting filesystem state unchanged.
//
// Subcommands:
//
//	identify                  print JSON {oras_go_version, go_version, worker_sha256}
//	extract <archive> <dest>  unpack <archive> into the oras-go file.Store at <dest>
//	probe                     self-contained capability probe (see runProbe)
//
// Exit codes for `extract`: 0 success, 2 extraction refused/failed (REJECTED),
// 3 harness/IO failure. The security verdict is never decided here.
package main

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256" // registers SHA-256 for go-digest AND provides Sum256 for the self hash
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime/debug"
	"syscall"

	digest "github.com/opencontainers/go-digest"
	ocispec "github.com/opencontainers/image-spec/specs-go/v1"
	"oras.land/oras-go/v2/content/file"
)

// oras-go unpacks a directory artifact under the descriptor's title; the tar
// members are therefore prefixed with this name (e.g. "d/evil"). It is an
// extractor-geometry constant, not a security decision.
const artifactDir = "d"

// orasGoModule is the dependency whose version the identity probe reports.
const orasGoModule = "oras.land/oras-go/v2"

func main() {
	if len(os.Args) < 2 {
		die(3, "usage: oras-worker identify|extract <archive> <dest>|probe")
	}
	switch os.Args[1] {
	case "identify":
		identify()
	case "extract":
		if len(os.Args) != 4 {
			die(3, "usage: oras-worker extract <archive> <dest>")
		}
		runExtract(os.Args[2], os.Args[3])
	case "probe":
		runProbe()
	default:
		die(3, "unknown subcommand: %s", os.Args[1])
	}
}

// doExtract unpacks a tar (gzipped in-memory) into an oras-go file.Store rooted
// at dest, via the same Push+unpack path a real `oras pull` uses.
func doExtract(dest string, rawTar []byte) error {
	var buf bytes.Buffer
	zw := gzip.NewWriter(&buf)
	if _, err := zw.Write(rawTar); err != nil {
		return err
	}
	if err := zw.Close(); err != nil {
		return err
	}
	blob := buf.Bytes()

	desc := ocispec.Descriptor{
		MediaType: "application/vnd.oci.image.layer.v1.tar+gzip",
		Digest:    digest.FromBytes(blob),
		Size:      int64(len(blob)),
		Annotations: map[string]string{
			ocispec.AnnotationTitle: artifactDir,
			file.AnnotationUnpack:   "true",
		},
	}
	store, err := file.New(dest)
	if err != nil {
		return err
	}
	defer store.Close()
	return store.Push(context.Background(), desc, bytes.NewReader(blob))
}

func runExtract(archive, dest string) {
	// Isolated CWD: the extractor runs from the disposable sandbox root (the
	// parent of the extraction root), mirroring a caller that runs `oras pull`
	// from its working directory and extracts into a subdirectory. The backend
	// supplies the OS isolation; this only sets the working directory.
	if err := os.Chdir(filepath.Dir(dest)); err != nil {
		die(3, "chdir sandbox root: %v", err)
	}
	rawTar, err := os.ReadFile(archive)
	if err != nil {
		die(3, "read archive: %v", err)
	}
	if err := doExtract(dest, rawTar); err != nil {
		// Extraction refused or failed (a fixed oras-go release contains the
		// hardlink target inside the extraction root, so os.Link has no target).
		// Recorded as REJECTED; the Observer/Oracle judge the actual post-state.
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(2)
	}
}

func identify() {
	meta := map[string]string{"oras_go_version": "", "go_version": "", "worker_sha256": ""}
	if info, ok := debug.ReadBuildInfo(); ok {
		meta["go_version"] = info.GoVersion
		for _, dep := range info.Deps {
			if dep.Path == orasGoModule {
				meta["oras_go_version"] = dep.Version
			}
		}
	}
	if self, err := os.Executable(); err == nil {
		if data, err := os.ReadFile(self); err == nil {
			sum := sha256.Sum256(data)
			meta["worker_sha256"] = hex.EncodeToString(sum[:])
		}
	}
	out, _ := json.Marshal(meta)
	os.Stdout.Write(out)
}

// statInfo is a JSON-friendly lstat snapshot; dev/ino are strings to avoid any
// precision loss, matching the node hand probe's schema.
type statInfo struct {
	Dev   string `json:"dev"`
	Ino   string `json:"ino"`
	Nlink uint64 `json:"nlink"`
	Type  string `json:"type"`
	Size  int64  `json:"size"`
}

func lstat(path string) *statInfo {
	var st syscall.Stat_t
	if err := syscall.Lstat(path, &st); err != nil {
		return nil
	}
	kind := "other"
	switch st.Mode & syscall.S_IFMT {
	case syscall.S_IFREG:
		kind = "reg"
	case syscall.S_IFDIR:
		kind = "dir"
	case syscall.S_IFLNK:
		kind = "sym"
	}
	return &statInfo{
		Dev:   fmt.Sprintf("%d", uint64(st.Dev)),
		Ino:   fmt.Sprintf("%d", uint64(st.Ino)),
		Nlink: uint64(st.Nlink),
		Type:  kind,
		Size:  st.Size,
	}
}

func walk(dir, base string) map[string]*statInfo {
	out := map[string]*statInfo{}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return out
	}
	for _, entry := range entries {
		full := filepath.Join(dir, entry.Name())
		rel := entry.Name()
		if base != "" {
			rel = base + "/" + entry.Name()
		}
		info := lstat(full)
		out[rel] = info
		if info != nil && info.Type == "dir" {
			for key, value := range walk(full, rel) {
				out[key] = value
			}
		}
	}
	return out
}

// runProbe is the self-contained capability probe. It builds a disposable
// sandbox entirely inside this (ephemeral) container -- an extraction root, an
// external "outside/sentinel.txt" beside it, and the attacker-controlled tar
// from TAR_B64 -- extracts with CWD at the sandbox root, then reports whether
// any extracted object shares the sentinel's (dev, ino) identity. This is the
// same C1 relation the oracle evaluates; the host is never the target.
func runProbe() {
	root := "/work"
	extract := filepath.Join(root, "extract")
	outside := filepath.Join(root, "outside")
	must(os.MkdirAll(extract, 0o755))
	must(os.MkdirAll(outside, 0o755))

	content, err := base64.StdEncoding.DecodeString(os.Getenv("SENTINEL_B64"))
	must(err)
	sentinel := filepath.Join(outside, "sentinel.txt")
	must(os.WriteFile(sentinel, content, 0o600))

	rawTar, err := base64.StdEncoding.DecodeString(os.Getenv("TAR_B64"))
	must(err)

	must(os.Chdir(root))
	before := lstat(sentinel)

	var declined map[string]string
	if err := doExtract(extract, rawTar); err != nil {
		message := err.Error()
		if len(message) > 200 {
			message = message[:200]
		}
		declined = map[string]string{"message": message}
	}

	after := lstat(sentinel)
	tree := walk(extract, "")
	shared := []string{}
	if after != nil {
		for rel, obj := range tree {
			if obj != nil && obj.Dev == after.Dev && obj.Ino == after.Ino {
				shared = append(shared, "extract/"+rel)
			}
		}
	}
	var nlinkBefore, nlinkAfter any
	if before != nil {
		nlinkBefore = before.Nlink
	}
	if after != nil {
		nlinkAfter = after.Nlink
	}
	report := map[string]any{
		"declined":         declined,
		"reference_before": before,
		"reference_after":  after,
		"nlink_before":     nlinkBefore,
		"nlink_after":      nlinkAfter,
		"shared_identity":  shared,
		"extract_tree":     tree,
	}
	out, _ := json.Marshal(report)
	fmt.Println(string(out))
}

func must(err error) {
	if err != nil {
		die(3, "%v", err)
	}
}

func die(code int, format string, args ...any) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(code)
}
