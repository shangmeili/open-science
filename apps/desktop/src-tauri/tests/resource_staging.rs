#[path = "../resource_staging.rs"]
mod resource_staging;

use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

fn temporary_root(label: &str) -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock moved before the Unix epoch")
        .as_nanos();
    std::env::temp_dir().join(format!(
        "ai4heor-resource-staging-{label}-{}-{nonce}",
        std::process::id()
    ))
}

#[test]
fn removes_only_the_generated_admitted_skill_staging_tree() {
    let root = temporary_root("exact-tree");
    let profile = root.join("target/debug");
    let out_dir = profile.join("build/ai4s-workbench-test/out");
    let stale = profile
        .join("skills-admitted-ai4s/integrity-auditor/forensics_tools/__pycache__/probe.pyc");
    let preserved_resource = profile.join("skills-core/keep.txt");
    let preserved_binary = profile.join("ai4s-workbench");
    fs::create_dir_all(&out_dir).unwrap();
    fs::create_dir_all(stale.parent().unwrap()).unwrap();
    fs::create_dir_all(preserved_resource.parent().unwrap()).unwrap();
    fs::write(&stale, b"stale").unwrap();
    fs::write(&preserved_resource, b"keep").unwrap();
    fs::write(&preserved_binary, b"keep").unwrap();

    let removed = resource_staging::clean_staged_admitted_skills(&out_dir).unwrap();

    assert_eq!(removed, profile.join("skills-admitted-ai4s"));
    assert!(!removed.exists());
    assert_eq!(fs::read(&preserved_resource).unwrap(), b"keep");
    assert_eq!(fs::read(&preserved_binary).unwrap(), b"keep");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_an_unexpected_out_dir_without_removing_anything() {
    let root = temporary_root("wrong-shape");
    let out_dir = root.join("not-a-cargo-build-layout/out");
    let marker = root.join("skills-admitted-ai4s/keep.txt");
    fs::create_dir_all(&out_dir).unwrap();
    fs::create_dir_all(marker.parent().unwrap()).unwrap();
    fs::write(&marker, b"keep").unwrap();

    let error = resource_staging::clean_staged_admitted_skills(&out_dir).unwrap_err();

    assert!(error.contains("unexpected Cargo OUT_DIR"));
    assert_eq!(fs::read(&marker).unwrap(), b"keep");
    fs::remove_dir_all(root).unwrap();
}
