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
//	frame <archive> <dest>    unpack, then emit one inodefence-boundary-attempt-v1 stdout
//	                          frame (a post-state SET of per-operation boundary attempts) for
//	                          M4 self-discovery feedback
//	probe                     self-contained capability probe (see runProbe)
//
// Exit codes for `extract`/`frame`: 0 success, 2 extraction refused/failed (REJECTED),
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
	"sort"
	"strings"
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
		die(3, "usage: oras-worker identify|extract <archive> <dest>|frame <archive> <dest>|probe")
	}
	switch os.Args[1] {
	case "identify":
		identify()
	case "extract":
		if len(os.Args) != 4 {
			die(3, "usage: oras-worker extract <archive> <dest>")
		}
		runExtract(os.Args[2], os.Args[3])
	case "frame":
		if len(os.Args) != 4 {
			die(3, "usage: oras-worker frame <archive> <dest>")
		}
		runFrame(os.Args[2], os.Args[3])
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

// orasGoVersion reports the pinned oras-go module version observed in this build's
// embedded dependency graph (empty only if the build info is unavailable). It is an
// evidence label, never a verdict condition (D005/D006).
func orasGoVersion() string {
	if info, ok := debug.ReadBuildInfo(); ok {
		for _, dep := range info.Deps {
			if dep.Path == orasGoModule {
				return dep.Version
			}
		}
	}
	return ""
}

func identify() {
	meta := map[string]string{"oras_go_version": orasGoVersion(), "go_version": "", "worker_sha256": ""}
	if info, ok := debug.ReadBuildInfo(); ok {
		meta["go_version"] = info.GoVersion
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

// runFrame is the M4 self-discovery observation for oras-go. It runs the SAME real
// extraction as `extract` (isolated CWD at the sandbox root, same doExtract path), then
// derives one inodefence-boundary-attempt-v1 frame from the OBSERVED post-extraction
// filesystem state and prints it as the last stdout line.
//
// Why post-state, not call interposition: oras-go is a compiled third-party extractor
// whose os.Link / os.Symlink calls cannot be wrapped from this worker without forking
// oras-go (decompress could wrap its JS callback fs, per that target's feasibility probe;
// oras-go cannot). So the feasible channel here is the post-state SET: each created object
// inside the extraction root becomes one attempt, with region-based target resolution. This
// is NARROWER than decompress's fs-wrap set -- a refused/errored link leaves no object, so
// a cleanly refused attempt is NOT observed here (it still shows up in the independent
// Observer/Oracle before/after verdict, which this frame never replaces).
//
// Region-based, no sentinel/CVE hardcoding (D005): an attempt reports only the created and
// resolved REGIONS (extraction/harness/external) and whether the created inode aliases any
// object outside the extraction root -- never a sentinel name or release string. The frame
// is emitted whether extraction succeeded or failed (exit 2 on failure), mirroring the
// decompress frame worker; a hardlink that escaped to an external inode yields the same
// OBSERVED_EXTERNAL_RESOLVE key the decompress frame does.
func runFrame(archive, dest string) {
	root := filepath.Dir(filepath.Clean(dest))
	extractAbs := filepath.Clean(dest)
	if err := os.Chdir(root); err != nil {
		die(3, "chdir sandbox root: %v", err)
	}
	rawTar, err := os.ReadFile(archive)
	if err != nil {
		die(3, "read archive: %v", err)
	}
	threw := false
	if err := doExtract(dest, rawTar); err != nil {
		threw = true
		fmt.Fprintf(os.Stderr, "%v\n", err)
	}

	// Inodes of every object OUTSIDE the extraction root, so aliasing is judged by region
	// (any non-extraction object), never by a sentinel name (D005).
	external := collectExternalInodes(root, extractAbs)
	attempts := []map[string]any{}
	walkExtractionAttempts(root, extractAbs, extractAbs, external, &attempts)
	// Deterministic order so two frames over the same post-state are byte-identical; the
	// consumer treats `attempts` as an unordered set regardless.
	sort.Slice(attempts, func(i, j int) bool {
		return attempts[i]["created_path"].(string) < attempts[j]["created_path"].(string)
	})

	report := map[string]any{
		"format":                   "inodefence-boundary-attempt-v1",
		"schema_version":           1,
		"extractor":                orasGoModule + "@" + orasGoVersion(),
		"extraction_root_absolute": extractAbs,
		"attempts":                 attempts,
	}
	out, _ := json.Marshal(report)
	fmt.Println(string(out))
	if threw {
		os.Exit(2)
	}
}

// frameRegion classifies an absolute path exactly as the Python path_region does over the
// sandbox-relative path: under the extraction root => extraction; the run root or the
// reserved archive/ subtree => harness; anything else => external.
func frameRegion(root, extractAbs, abs string) string {
	r := filepath.Clean(abs)
	if r == extractAbs || strings.HasPrefix(r, extractAbs+string(os.PathSeparator)) {
		return "extraction"
	}
	rel, err := filepath.Rel(root, r)
	if err == nil && (rel == "." || rel == "archive" || strings.HasPrefix(rel, "archive"+string(os.PathSeparator))) {
		return "harness"
	}
	return "external"
}

func sandboxRel(root, abs string) string {
	if rel, err := filepath.Rel(root, filepath.Clean(abs)); err == nil {
		return rel
	}
	return filepath.Clean(abs)
}

// collectExternalInodes maps dev:ino -> sandbox-relative path for every object strictly
// outside the extraction root (the sentinel, the archive, the run root). The extraction
// subtree is skipped, so an external inode observed on a created extraction object means the
// extractor aliased an object outside its root.
func collectExternalInodes(root, extractAbs string) map[string]string {
	out := map[string]string{}
	var rec func(dir string)
	rec = func(dir string) {
		ents, err := os.ReadDir(dir)
		if err != nil {
			return
		}
		for _, e := range ents {
			full := filepath.Join(dir, e.Name())
			if filepath.Clean(full) == extractAbs {
				continue
			}
			var st syscall.Stat_t
			if err := syscall.Lstat(full, &st); err == nil {
				key := fmt.Sprintf("%d:%d", uint64(st.Dev), uint64(st.Ino))
				if _, ok := out[key]; !ok {
					out[key] = sandboxRel(root, full)
				}
			}
			if e.IsDir() {
				rec(full)
			}
		}
	}
	rec(root)
	return out
}

// walkExtractionAttempts projects every created object under the extraction root to one v1
// attempt. A symlink reports its readlink target region; a regular file whose inode matches
// an external object is an escaping hardlink (operation=hardlink, target_region=that
// object's region); any other regular file is a plain write. Directories carry no attempt.
func walkExtractionAttempts(
	root, extractAbs, dir string, external map[string]string, attempts *[]map[string]any,
) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, e := range ents {
		full := filepath.Join(dir, e.Name())
		var st syscall.Stat_t
		if err := syscall.Lstat(full, &st); err != nil {
			continue
		}
		mode := st.Mode & syscall.S_IFMT
		if mode == syscall.S_IFDIR {
			walkExtractionAttempts(root, extractAbs, full, external, attempts)
			continue
		}
		key := fmt.Sprintf("%d:%d", uint64(st.Dev), uint64(st.Ino))
		att := map[string]any{
			"created_path":             sandboxRel(root, full),
			"created_region":           "extraction",
			"target_raw":               nil,
			"target_resolved_absolute": nil,
			"target_region":            "n/a",
			"aliases_external_object":  false,
			"outcome":                  "created",
		}
		switch mode {
		case syscall.S_IFLNK:
			raw, _ := os.Readlink(full)
			var targetAbs string
			if filepath.IsAbs(raw) {
				targetAbs = filepath.Clean(raw)
			} else {
				targetAbs = filepath.Clean(filepath.Join(filepath.Dir(full), raw))
			}
			att["operation"] = "symlink"
			att["target_raw"] = raw
			att["target_resolved_absolute"] = sandboxRel(root, targetAbs)
			att["target_region"] = frameRegion(root, extractAbs, targetAbs)
			if _, ok := external[key]; ok {
				att["aliases_external_object"] = true
			}
		default:
			if extPath, ok := external[key]; ok {
				att["operation"] = "hardlink"
				att["aliases_external_object"] = true
				att["target_resolved_absolute"] = extPath
				att["target_region"] = frameRegion(root, extractAbs, filepath.Join(root, extPath))
			} else {
				att["operation"] = "regular"
			}
		}
		*attempts = append(*attempts, att)
	}
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
