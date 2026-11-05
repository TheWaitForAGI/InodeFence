//! Build-time identity for the Rust `tar` worker (InodeFence, tools/rust-tar).
//!
//! Exposes two compile-time values to `src/main.rs`:
//!   * `INODEFENCE_CARGO_LOCK_PATH` -- the role's committed Cargo.lock, embedded by the worker so
//!     `identify` can report the locked `tar` version and the lock's SHA-256;
//!   * `INODEFENCE_RUSTC_VERSION` -- the version reported by the compiler that built this binary.
//!
//! It refuses to build without the committed lock: the pinned crate graph is part of the target's
//! identity, never resolved ad hoc at image build time.
use std::env;
use std::path::PathBuf;
use std::process::Command;

fn main() {
    let manifest_dir =
        PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("cargo sets CARGO_MANIFEST_DIR"));
    let lock = manifest_dir.join("Cargo.lock");
    if !lock.is_file() {
        panic!(
            "{} is missing: generate it with the pinned toolchain and commit it (tools/rust-tar/README.md)",
            lock.display()
        );
    }
    println!("cargo:rerun-if-changed={}", lock.display());
    println!("cargo:rustc-env=INODEFENCE_CARGO_LOCK_PATH={}", lock.display());

    let rustc = env::var("RUSTC").unwrap_or_else(|_| String::from("rustc"));
    let output = Command::new(&rustc)
        .arg("--version")
        .output()
        .expect("rustc --version runs");
    let text = String::from_utf8(output.stdout).expect("rustc --version output is UTF-8");
    // "rustc 1.99.1 (<commit> <date>)" -> "1.99.1"
    let version = text
        .split_whitespace()
        .nth(1)
        .expect("rustc --version reports a version")
        .to_string();
    println!("cargo:rustc-env=INODEFENCE_RUSTC_VERSION={version}");
}
