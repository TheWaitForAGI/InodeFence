//! Target-specific Rust `tar` crate (tar-rs) extraction worker for InodeFence (Tier-B, D039).
//!
//! It drives the crate's standard `Archive::unpack` path with the crate's DEFAULT settings -- no
//! `set_overwrite`, `set_preserve_permissions`, `set_unpack_xattrs`, `set_mask` or any other
//! hardening call -- so the post-extraction filesystem state is the library's own behaviour.
//! InodeFence's generic model/oracle are NOT reimplemented here: this worker only invokes the
//! third-party extractor and reports raw bytes/outcome. The Observer and Oracle judge the resulting
//! filesystem state unchanged. It speaks the same worker protocol as the oras-go worker
//! (`tools/oras-go/worker/main.go`), so the existing adapters and frame pipeline can drive it.
//!
//! Subcommands:
//!
//!   identify                  print JSON {tar_crate_version, rustc_version, cargo_lock_sha256,
//!                             worker_sha256}
//!   extract <archive> <dest>  unpack <archive> into <dest> with `Archive::unpack`
//!   frame <archive> <dest>    unpack, then emit one inodefence-boundary-attempt-v1 stdout frame
//!                             (a post-state SET of per-operation boundary attempts)
//!   probe                     self-contained fixture probe (see `run_probe`)
//!
//! Exit codes for `extract`/`frame`: 0 success, 2 extraction refused/failed (REJECTED),
//! 3 harness/IO failure. The security verdict is never decided here.
//!
//! Only the Rust standard library and the pinned `tar` crate are used (SHA-256, base64 and JSON
//! output are small local helpers), so the locked crate graph stays the `tar` crate's own.

use std::collections::BTreeMap;
use std::env;
use std::ffi::{OsStr, OsString};
use std::fmt::Display;
use std::fs;
use std::io::{self, Cursor};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};
use std::process;

/// The role's committed Cargo.lock (the exact crate graph this binary was built from).
const CARGO_LOCK: &str = include_str!(env!("INODEFENCE_CARGO_LOCK_PATH"));
/// The compiler version observed by build.rs for this build.
const RUSTC_VERSION: &str = env!("INODEFENCE_RUSTC_VERSION");
/// The dependency whose locked version the identity probe reports.
const TAR_CRATE: &str = "tar";
const FRAME_FORMAT: &str = "inodefence-boundary-attempt-v1";

fn main() {
    let args: Vec<OsString> = env::args_os().collect();
    let command = args.get(1).and_then(|value| value.to_str()).unwrap_or("");
    match command {
        "identify" => identify(),
        "extract" => {
            if args.len() != 4 {
                die(3, "usage: rust-tar-worker extract <archive> <dest>");
            }
            run_extract(Path::new(&args[2]), Path::new(&args[3]));
        }
        "frame" => {
            if args.len() != 4 {
                die(3, "usage: rust-tar-worker frame <archive> <dest>");
            }
            run_frame(Path::new(&args[2]), Path::new(&args[3]));
        }
        "probe" => run_probe(),
        "" => die(
            3,
            "usage: rust-tar-worker identify|extract <archive> <dest>|frame <archive> <dest>|probe",
        ),
        other => die(3, &format!("unknown subcommand: {other}")),
    }
}

/// Unpack an in-memory tar into `dest` through the crate's standard `Archive::unpack`, with the
/// crate's default settings: the point is to observe the library's own behaviour.
fn do_extract(raw_tar: &[u8], dest: &Path) -> io::Result<()> {
    let mut archive = tar::Archive::new(Cursor::new(raw_tar));
    archive.unpack(dest)
}

/// Isolated CWD: the extractor runs from the disposable sandbox root (the parent of the extraction
/// root), exactly like the oras-go/decompress workers, so any CWD-relative resolution stays inside
/// the disposable sandbox. The backend supplies the OS isolation; this only sets the directory.
fn enter_sandbox_root(dest: &Path) -> (PathBuf, PathBuf) {
    let extract_abs = lexical_clean(dest);
    let root = match extract_abs.parent() {
        Some(parent) => parent.to_path_buf(),
        None => die(3, "extraction root has no parent sandbox directory"),
    };
    if let Err(error) = env::set_current_dir(&root) {
        die(3, &format!("chdir sandbox root: {error}"));
    }
    (root, extract_abs)
}

fn read_archive(archive: &Path) -> Vec<u8> {
    match fs::read(archive) {
        Ok(bytes) => bytes,
        Err(error) => die(3, &format!("read archive: {error}")),
    }
}

fn run_extract(archive: &Path, dest: &Path) {
    let (_root, extract_abs) = enter_sandbox_root(dest);
    let raw_tar = read_archive(archive);
    if let Err(error) = do_extract(&raw_tar, &extract_abs) {
        // Extraction refused or failed: recorded as REJECTED. The Observer/Oracle judge the
        // actual (possibly partial) post-state regardless.
        eprintln!("{error}");
        process::exit(2);
    }
}

/// The version of `name` recorded in the embedded Cargo.lock (the resolved, locked graph). It is an
/// evidence label, never a verdict condition (D005/D006). Empty lock entry => None.
fn locked_version(name: &str) -> Option<String> {
    let wanted = format!("name = \"{name}\"");
    let mut lines = CARGO_LOCK.lines();
    while let Some(line) = lines.next() {
        if line.trim() == wanted {
            let next = lines.next()?.trim();
            let version = next.strip_prefix("version = \"")?.strip_suffix('"')?;
            return Some(version.to_string());
        }
    }
    None
}

fn identify() {
    let worker_sha256 = env::current_exe()
        .and_then(fs::read)
        .map(|bytes| hex(&sha256(&bytes)))
        .unwrap_or_default();
    let fields = [
        ("cargo_lock_sha256", hex(&sha256(CARGO_LOCK.as_bytes()))),
        ("rustc_version", RUSTC_VERSION.to_string()),
        ("tar_crate_version", locked_version(TAR_CRATE).unwrap_or_default()),
        ("worker_sha256", worker_sha256),
    ];
    let body: Vec<String> = fields
        .iter()
        .map(|(key, value)| format!("{}:{}", json_string(key), json_string(value)))
        .collect();
    println!("{{{}}}", body.join(","));
}

// --- frame: the post-state boundary-attempt SET (same channel as the oras-go worker) ---------

/// One created object under the extraction root, projected to a v1 boundary attempt.
struct Attempt {
    created_path: String,
    operation: &'static str,
    target_raw: Option<String>,
    target_resolved_absolute: Option<String>,
    target_region: &'static str,
    aliases_external_object: bool,
}

impl Attempt {
    fn to_json(&self) -> String {
        format!(
            "{{\"aliases_external_object\":{},\"created_path\":{},\"created_region\":\"extraction\",\
             \"operation\":{},\"outcome\":\"created\",\"target_raw\":{},\"target_region\":{},\
             \"target_resolved_absolute\":{}}}",
            self.aliases_external_object,
            json_string(&self.created_path),
            json_string(self.operation),
            json_optional(self.target_raw.as_deref()),
            json_string(self.target_region),
            json_optional(self.target_resolved_absolute.as_deref()),
        )
    }
}

/// The M4-style self-discovery observation for the Rust `tar` crate. It runs the SAME real
/// extraction as `extract` (isolated CWD at the sandbox root, same `do_extract` path), then derives
/// one inodefence-boundary-attempt-v1 frame from the OBSERVED post-extraction filesystem state and
/// prints it as the last stdout line.
///
/// Why post-state, not call interposition: the crate is compiled into this binary and its
/// `std::fs` link/symlink calls cannot be wrapped without forking the crate, so -- exactly as for
/// oras-go -- the feasible channel is the post-state SET: each created object inside the extraction
/// root becomes one attempt, with region-based target resolution. A cleanly refused/errored link
/// leaves no object and is therefore NOT observed here (it still shows up in the independent
/// Observer/Oracle before/after verdict, which this frame never replaces).
///
/// Region-based, no sentinel/advisory hardcoding (D005): an attempt reports only the created and
/// resolved REGIONS (extraction/harness/external) and whether the created inode aliases any object
/// outside the extraction root -- never a sentinel name or release string. The frame is emitted
/// whether extraction succeeded or failed (exit 2 on failure), mirroring the oras-go worker.
fn run_frame(archive: &Path, dest: &Path) {
    let (root, extract_abs) = enter_sandbox_root(dest);
    let raw_tar = read_archive(archive);
    let mut threw = false;
    if let Err(error) = do_extract(&raw_tar, &extract_abs) {
        threw = true;
        eprintln!("{error}");
    }

    // Inodes of every object OUTSIDE the extraction root, so aliasing is judged by region (any
    // non-extraction object), never by a sentinel name (D005).
    let external = collect_external_inodes(&root, &extract_abs);
    let mut attempts = Vec::new();
    walk_extraction_attempts(&root, &extract_abs, &extract_abs, &external, &mut attempts);
    // Deterministic order so two frames over the same post-state are byte-identical; the consumer
    // treats `attempts` as an unordered set regardless.
    attempts.sort_by(|left, right| left.created_path.cmp(&right.created_path));
    let body: Vec<String> = attempts.iter().map(Attempt::to_json).collect();
    let extractor = format!("{}@{}", TAR_CRATE, locked_version(TAR_CRATE).unwrap_or_default());
    println!(
        "{{\"attempts\":[{}],\"extraction_root_absolute\":{},\"extractor\":{},\"format\":{},\
         \"schema_version\":1}}",
        body.join(","),
        json_string(&extract_abs.to_string_lossy()),
        json_string(&extractor),
        json_string(FRAME_FORMAT),
    );
    if threw {
        process::exit(2);
    }
}

type InodeKey = (u64, u64);

/// Directory entries sorted by path, so every walk (and the first-seen path per inode) is
/// deterministic. An unreadable directory contributes nothing.
fn sorted_entries(dir: &Path) -> Vec<PathBuf> {
    let mut entries: Vec<PathBuf> = match fs::read_dir(dir) {
        Ok(iter) => iter.filter_map(|entry| entry.ok().map(|entry| entry.path())).collect(),
        Err(_) => Vec::new(),
    };
    entries.sort();
    entries
}

fn is_lstat_dir(path: &Path) -> bool {
    fs::symlink_metadata(path)
        .map(|meta| meta.file_type().is_dir())
        .unwrap_or(false)
}

/// Map (dev, ino) -> sandbox-relative path for every object strictly outside the extraction root
/// (the sentinel, the archive, the run root). The extraction subtree is skipped, so an external
/// inode observed on a created extraction object means the extractor aliased an outside object.
fn collect_external_inodes(root: &Path, extract_abs: &Path) -> BTreeMap<InodeKey, String> {
    let mut out = BTreeMap::new();
    collect_external_into(root, root, extract_abs, &mut out);
    out
}

fn collect_external_into(
    root: &Path,
    dir: &Path,
    extract_abs: &Path,
    out: &mut BTreeMap<InodeKey, String>,
) {
    for full in sorted_entries(dir) {
        if lexical_clean(&full).as_path() == extract_abs {
            continue;
        }
        if let Ok(meta) = fs::symlink_metadata(&full) {
            out.entry((meta.dev(), meta.ino()))
                .or_insert_with(|| sandbox_rel(root, &full));
            if meta.file_type().is_dir() {
                collect_external_into(root, &full, extract_abs, out);
            }
        }
    }
}

/// Project every created object under the extraction root to one v1 attempt. A symlink reports
/// its readlink target region; a non-directory whose inode matches an external object is an
/// escaping hardlink (operation=hardlink, target_region=that object's region); any other
/// non-directory is a plain regular write. Directories carry no attempt.
fn walk_extraction_attempts(
    root: &Path,
    extract_abs: &Path,
    dir: &Path,
    external: &BTreeMap<InodeKey, String>,
    attempts: &mut Vec<Attempt>,
) {
    for full in sorted_entries(dir) {
        let meta = match fs::symlink_metadata(&full) {
            Ok(meta) => meta,
            Err(_) => continue,
        };
        let file_type = meta.file_type();
        if file_type.is_dir() {
            walk_extraction_attempts(root, extract_abs, &full, external, attempts);
            continue;
        }
        let key = (meta.dev(), meta.ino());
        let mut attempt = Attempt {
            created_path: sandbox_rel(root, &full),
            operation: "regular",
            target_raw: None,
            target_resolved_absolute: None,
            target_region: "n/a",
            aliases_external_object: false,
        };
        if file_type.is_symlink() {
            let raw = fs::read_link(&full).unwrap_or_default();
            let target_abs = if raw.is_absolute() {
                lexical_clean(&raw)
            } else {
                lexical_clean(&full.parent().unwrap_or(root).join(&raw))
            };
            attempt.operation = "symlink";
            attempt.target_raw = Some(raw.to_string_lossy().into_owned());
            attempt.target_resolved_absolute = Some(sandbox_rel(root, &target_abs));
            attempt.target_region = frame_region(root, extract_abs, &target_abs);
            attempt.aliases_external_object = external.contains_key(&key);
        } else if let Some(external_path) = external.get(&key) {
            attempt.operation = "hardlink";
            attempt.aliases_external_object = true;
            attempt.target_resolved_absolute = Some(external_path.clone());
            attempt.target_region = frame_region(root, extract_abs, &root.join(external_path));
        }
        attempts.push(attempt);
    }
}

/// Classify an absolute path exactly as the oras-go worker (and the Python `path_region` over the
/// sandbox-relative path) does: under the extraction root => extraction; the run root or the
/// reserved archive/ subtree => harness; anything else => external.
fn frame_region(root: &Path, extract_abs: &Path, abs: &Path) -> &'static str {
    let resolved = lexical_clean(abs);
    if resolved.starts_with(extract_abs) {
        return "extraction";
    }
    if let Ok(rel) = resolved.strip_prefix(root) {
        if rel.as_os_str().is_empty() || rel.starts_with("archive") {
            return "harness";
        }
    }
    "external"
}

/// Lexical path normalization (Go's `filepath.Clean`): drop `.` and empty components and fold
/// `..` against the preceding component, without touching the filesystem.
fn lexical_clean(path: &Path) -> PathBuf {
    let absolute = path.has_root();
    let mut parts: Vec<OsString> = Vec::new();
    for component in path.components() {
        match component {
            Component::Prefix(_) | Component::RootDir | Component::CurDir => {}
            Component::ParentDir => {
                let foldable = parts
                    .last()
                    .map_or(false, |last| last.as_os_str() != OsStr::new(".."));
                if foldable {
                    parts.pop();
                } else if !absolute {
                    parts.push(OsString::from(".."));
                }
            }
            Component::Normal(name) => parts.push(name.to_os_string()),
        }
    }
    let mut out = if absolute {
        PathBuf::from("/")
    } else {
        PathBuf::new()
    };
    for part in parts {
        out.push(part);
    }
    if out.as_os_str().is_empty() {
        out.push(".");
    }
    out
}

/// Sandbox-relative spelling of `abs` (Go's `filepath.Rel(root, abs)` for absolute paths): a
/// path outside the root is spelled with leading `..` components.
fn sandbox_rel(root: &Path, abs: &Path) -> String {
    let target = lexical_clean(abs);
    let base: Vec<Component> = root.components().collect();
    let parts: Vec<Component> = target.components().collect();
    let common = base
        .iter()
        .zip(parts.iter())
        .take_while(|(left, right)| left == right)
        .count();
    let mut rel = PathBuf::new();
    for _ in common..base.len() {
        rel.push("..");
    }
    for part in &parts[common..] {
        rel.push(part.as_os_str());
    }
    if rel.as_os_str().is_empty() {
        String::from(".")
    } else {
        rel.to_string_lossy().into_owned()
    }
}

// --- probe: self-contained fixture probe (same geometry as the node-tar regression program) ---

/// The self-contained fixture probe. It builds a disposable layout entirely inside this
/// (ephemeral) container -- an extraction root `/work/extract`, an external reference file
/// `/work/ext/reference.bin` beside it (bytes from REF_B64), the archive bytes from TAR_B64 --
/// extracts with CWD at `/work`, and reports raw observations only: the reference's lstat before
/// and after, every extracted object sharing the reference's (dev, ino), and the sandbox-relative
/// objects that appeared, disappeared or changed identity/type OUTSIDE the extraction root. The
/// output keys match the node-tar regression program (`experiments/repro/
/// cross_release_identity.py`) so the same Python C1/C2 derivation applies; the host is never the
/// extraction target and no verdict is decided here.
fn run_probe() {
    let root = Path::new("/work");
    let extract = root.join("extract");
    let ext = root.join("ext");
    let archive_dir = root.join("archive");
    for dir in [&extract, &ext, &archive_dir] {
        must(fs::create_dir_all(dir));
    }
    let reference = ext.join("reference.bin");
    must(fs::write(&reference, must(decode_env("REF_B64"))));
    must(fs::set_permissions(&reference, fs::Permissions::from_mode(0o600)));
    let raw_tar = must(decode_env("TAR_B64"));
    must(fs::write(archive_dir.join("input.tar"), &raw_tar));
    must(env::set_current_dir(root));

    let reference_before = fs::symlink_metadata(&reference).ok();
    let outside_before = outside_objects(root, &extract);
    let declined = match do_extract(&raw_tar, &extract) {
        Ok(()) => None,
        Err(error) => Some(error.to_string().chars().take(200).collect::<String>()),
    };
    let reference_after = fs::symlink_metadata(&reference).ok();
    let outside_after = outside_objects(root, &extract);

    let mut tree = Vec::new();
    walk_tree(&extract, "", &mut tree);
    let mut shared = Vec::new();
    let mut tree_json = Vec::new();
    for (rel, full) in &tree {
        tree_json.push(format!("{}:{}", json_string(rel), stat_json(full)));
        if let (Some(after), Ok(meta)) = (&reference_after, fs::symlink_metadata(full)) {
            if meta.dev() == after.dev() && meta.ino() == after.ino() {
                shared.push(json_string(&format!("extract/{rel}")));
            }
        }
    }
    let created: Vec<String> = outside_after
        .keys()
        .filter(|path| !outside_before.contains_key(*path))
        .map(|path| json_string(path))
        .collect();
    let removed: Vec<String> = outside_before
        .keys()
        .filter(|path| !outside_after.contains_key(*path))
        .map(|path| json_string(path))
        .collect();
    let changed: Vec<String> = outside_before
        .iter()
        .filter(|(path, identity)| {
            outside_after
                .get(*path)
                .map_or(false, |after| after != *identity)
        })
        .map(|(path, _)| json_string(path))
        .collect();
    let declined_json = match &declined {
        Some(message) => format!("{{\"message\":{}}}", json_string(message)),
        None => String::from("null"),
    };
    println!(
        "{{\"declined\":{},\"extract_tree\":{{{}}},\"nlink_after\":{},\"nlink_before\":{},\
         \"outside_changed\":[{}],\"outside_created\":[{}],\"outside_removed\":[{}],\
         \"reference_after\":{},\"reference_before\":{},\"shared_identity\":[{}]}}",
        declined_json,
        tree_json.join(","),
        nlink_json(reference_after.as_ref()),
        nlink_json(reference_before.as_ref()),
        changed.join(","),
        created.join(","),
        removed.join(","),
        metadata_json(reference_after.as_ref(), &reference),
        metadata_json(reference_before.as_ref(), &reference),
        shared.join(","),
    );
}

/// (dev, ino, type) per sandbox-relative object outside the extraction root.
fn outside_objects(
    root: &Path,
    extract_abs: &Path,
) -> BTreeMap<String, (u64, u64, &'static str)> {
    let mut out = BTreeMap::new();
    collect_outside(root, root, extract_abs, &mut out);
    out
}

fn collect_outside(
    root: &Path,
    dir: &Path,
    extract_abs: &Path,
    out: &mut BTreeMap<String, (u64, u64, &'static str)>,
) {
    for full in sorted_entries(dir) {
        if full.as_path() == extract_abs {
            continue;
        }
        if let Ok(meta) = fs::symlink_metadata(&full) {
            out.insert(
                sandbox_rel(root, &full),
                (meta.dev(), meta.ino(), kind_of(&meta)),
            );
            if meta.file_type().is_dir() {
                collect_outside(root, &full, extract_abs, out);
            }
        }
    }
}

fn walk_tree(dir: &Path, base: &str, out: &mut Vec<(String, PathBuf)>) {
    for full in sorted_entries(dir) {
        let name = full
            .file_name()
            .map(|name| name.to_string_lossy().into_owned())
            .unwrap_or_default();
        let rel = if base.is_empty() {
            name
        } else {
            format!("{base}/{name}")
        };
        out.push((rel.clone(), full.clone()));
        if is_lstat_dir(&full) {
            walk_tree(&full, &rel, out);
        }
    }
}

fn kind_of(meta: &fs::Metadata) -> &'static str {
    let file_type = meta.file_type();
    if file_type.is_symlink() {
        "sym"
    } else if file_type.is_dir() {
        "dir"
    } else if file_type.is_file() {
        "reg"
    } else {
        "other"
    }
}

/// lstat JSON with the node-tar regression program's keys; dev/ino are strings (no precision
/// loss), a missing object reports {"error": <kind>}.
fn stat_json(path: &Path) -> String {
    metadata_json(fs::symlink_metadata(path).ok().as_ref(), path)
}

fn metadata_json(meta: Option<&fs::Metadata>, path: &Path) -> String {
    match meta {
        Some(meta) => {
            let target = if meta.file_type().is_symlink() {
                fs::read_link(path)
                    .map(|raw| json_string(&raw.to_string_lossy()))
                    .unwrap_or_else(|_| String::from("null"))
            } else {
                String::from("null")
            };
            format!(
                "{{\"dev\":\"{}\",\"ino\":\"{}\",\"nlink\":{},\"size\":{},\"target\":{},\"type\":\"{}\"}}",
                meta.dev(),
                meta.ino(),
                meta.nlink(),
                meta.size(),
                target,
                kind_of(meta),
            )
        }
        None => String::from("{\"error\":\"NotFound\"}"),
    }
}

fn nlink_json(meta: Option<&fs::Metadata>) -> String {
    match meta {
        Some(meta) => meta.nlink().to_string(),
        None => String::from("null"),
    }
}

// --- small std-only helpers (no extra crates in the locked graph) ---------------------------

fn decode_env(name: &str) -> Result<Vec<u8>, String> {
    let text = env::var(name).map_err(|error| format!("{name}: {error}"))?;
    base64_decode(&text)
}

/// Standard (RFC 4648) base64 decoding; padding ends the input, ASCII whitespace is skipped.
fn base64_decode(text: &str) -> Result<Vec<u8>, String> {
    let mut out = Vec::with_capacity(text.len() / 4 * 3);
    let mut buffer: u32 = 0;
    let mut bits: u32 = 0;
    for byte in text.bytes() {
        let value = match byte {
            b'A'..=b'Z' => byte - b'A',
            b'a'..=b'z' => byte - b'a' + 26,
            b'0'..=b'9' => byte - b'0' + 52,
            b'+' => 62,
            b'/' => 63,
            b'=' => break,
            b'\n' | b'\r' | b'\t' | b' ' => continue,
            _ => return Err(format!("invalid base64 byte {byte}")),
        };
        buffer = (buffer << 6) | u32::from(value);
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((buffer >> bits) as u8);
            buffer &= (1u32 << bits) - 1;
        }
    }
    Ok(out)
}

fn json_string(value: &str) -> String {
    let mut out = String::with_capacity(value.len() + 2);
    out.push('"');
    for ch in value.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

fn json_optional(value: Option<&str>) -> String {
    match value {
        Some(text) => json_string(text),
        None => String::from("null"),
    }
}

fn hex(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push_str(&format!("{byte:02x}"));
    }
    out
}

const SHA256_K: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

/// FIPS 180-4 SHA-256 (used for the self/lock digests in `identify`).
fn sha256(data: &[u8]) -> [u8; 32] {
    let mut state: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
        0x5be0cd19,
    ];
    let bit_length = (data.len() as u64).wrapping_mul(8);
    let mut message = data.to_vec();
    message.push(0x80);
    while message.len() % 64 != 56 {
        message.push(0);
    }
    message.extend_from_slice(&bit_length.to_be_bytes());
    for block in message.chunks_exact(64) {
        let mut w = [0u32; 64];
        for (index, word) in block.chunks_exact(4).enumerate() {
            w[index] = u32::from_be_bytes([word[0], word[1], word[2], word[3]]);
        }
        for index in 16..64 {
            let s0 = w[index - 15].rotate_right(7)
                ^ w[index - 15].rotate_right(18)
                ^ (w[index - 15] >> 3);
            let s1 = w[index - 2].rotate_right(17)
                ^ w[index - 2].rotate_right(19)
                ^ (w[index - 2] >> 10);
            w[index] = w[index - 16]
                .wrapping_add(s0)
                .wrapping_add(w[index - 7])
                .wrapping_add(s1);
        }
        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut h] = state;
        for index in 0..64 {
            let big_s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let choose = (e & f) ^ (!e & g);
            let temp1 = h
                .wrapping_add(big_s1)
                .wrapping_add(choose)
                .wrapping_add(SHA256_K[index])
                .wrapping_add(w[index]);
            let big_s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let majority = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = big_s0.wrapping_add(majority);
            h = g;
            g = f;
            f = e;
            e = d.wrapping_add(temp1);
            d = c;
            c = b;
            b = a;
            a = temp1.wrapping_add(temp2);
        }
        for (slot, value) in state.iter_mut().zip([a, b, c, d, e, f, g, h]) {
            *slot = slot.wrapping_add(value);
        }
    }
    let mut digest = [0u8; 32];
    for (index, word) in state.iter().enumerate() {
        digest[index * 4..index * 4 + 4].copy_from_slice(&word.to_be_bytes());
    }
    digest
}

fn must<T, E: Display>(result: Result<T, E>) -> T {
    match result {
        Ok(value) => value,
        Err(error) => die(3, &error.to_string()),
    }
}

fn die(code: i32, message: &str) -> ! {
    eprintln!("{message}");
    process::exit(code)
}
