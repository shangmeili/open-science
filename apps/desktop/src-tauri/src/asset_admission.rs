//! Fail-closed admission registry for third-party platform assets.
//!
//! The registry is a release inventory, not a candidate backlog. Only a
//! hash-locked `validated-adapter` entry with complete license, boundary, test,
//! security, methods, platform, and kill-switch evidence may be copied into the
//! app-managed runtime. Unfinished and excluded sources are not registry rows.

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use tauri::{path::BaseDirectory, AppHandle, Manager};

pub const ASSET_REGISTRY_RESOURCE: &str = "asset-admission-registry.json";
const REGISTRY_CAP_BYTES: u64 = 2 * 1024 * 1024;
const RELEASE_STATUS: &str = "validated-adapter";

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AssetAdmissionRecord {
    pub asset_id: String,
    pub display_name: String,
    pub kind: String,
    pub status: String,
    pub release_eligible: bool,
    pub repository: String,
    pub revision: String,
    pub license_spdx: String,
    pub license_compatible: bool,
    pub network_egress: String,
    pub execution: String,
    pub blockers: Vec<String>,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AssetAdmissionAudit {
    pub complete: bool,
    pub fail_closed: bool,
    pub schema_version: String,
    pub policy_revision: String,
    pub total_count: usize,
    pub admitted_count: usize,
    pub assets: Vec<AssetAdmissionRecord>,
    pub errors: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct SkillDeployment {
    pub resource_pack: String,
    pub entry: String,
    pub content_sha256: String,
}

fn text(value: Option<&Value>) -> Option<&str> {
    value
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
}

fn strings(value: Option<&Value>) -> Option<Vec<String>> {
    let values = value?.as_array()?;
    let mut output = Vec::with_capacity(values.len());
    for value in values {
        output.push(text(Some(value))?.to_string());
    }
    Some(output)
}

fn safe_id(value: &str) -> bool {
    !value.starts_with('/')
        && !value.ends_with('/')
        && !value.contains("..")
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'/'))
}

fn safe_segment(value: &str) -> bool {
    !value.is_empty()
        && value != "."
        && value != ".."
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn hex(value: &str, len: usize) -> bool {
    value.len() == len
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn exact_platforms(value: Option<&Value>) -> bool {
    let Some(platforms) = strings(value) else {
        return false;
    };
    let platforms: HashSet<_> = platforms.into_iter().collect();
    platforms.len() == 3
        && ["macos", "windows", "linux"]
            .iter()
            .all(|platform| platforms.contains(*platform))
}

fn empty(error: impl Into<String>) -> AssetAdmissionAudit {
    AssetAdmissionAudit {
        complete: false,
        fail_closed: true,
        schema_version: String::new(),
        policy_revision: String::new(),
        total_count: 0,
        admitted_count: 0,
        assets: Vec::new(),
        errors: vec![error.into()],
    }
}

pub(crate) fn validate_registry(raw: &[u8]) -> (AssetAdmissionAudit, Vec<SkillDeployment>) {
    let registry: Value = match serde_json::from_slice::<Value>(raw) {
        Ok(value) if value.is_object() => value,
        Ok(_) => return (empty("asset registry must be a JSON object"), Vec::new()),
        Err(error) => {
            return (
                empty(format!("asset registry is invalid JSON: {error}")),
                Vec::new(),
            )
        }
    };
    let mut audit = empty("");
    audit.errors.clear();
    audit.schema_version = text(registry.get("schema_version"))
        .unwrap_or_default()
        .to_string();
    audit.policy_revision = text(registry.get("policy_revision"))
        .unwrap_or_default()
        .to_string();
    if audit.schema_version != "1.1.0" {
        audit.errors.push("schema_version must be 1.1.0".into());
    }
    if audit.policy_revision.len() != 10
        || audit.policy_revision.as_bytes().get(4) != Some(&b'-')
        || audit.policy_revision.as_bytes().get(7) != Some(&b'-')
    {
        audit
            .errors
            .push("policy_revision must be YYYY-MM-DD".into());
    }
    if registry.get("release_statuses") != Some(&serde_json::json!([RELEASE_STATUS])) {
        audit
            .errors
            .push("release_statuses must contain only validated-adapter".into());
    }
    if text(registry.get("purpose")) != Some("release-eligible-external-adapters-only") {
        audit
            .errors
            .push("purpose must be release-eligible-external-adapters-only".into());
    }

    let Some(assets) = registry.get("assets").and_then(Value::as_array) else {
        audit.errors.push("assets must be an array".into());
        return (audit, Vec::new());
    };
    audit.total_count = assets.len();
    let mut ids = HashSet::new();
    let mut deployment_keys = HashSet::new();
    let mut deployments = Vec::new();

    for (index, asset) in assets.iter().enumerate() {
        let prefix = format!("assets[{index}]");
        let Some(asset) = asset.as_object() else {
            audit.errors.push(format!("{prefix} must be an object"));
            continue;
        };
        let asset_id = text(asset.get("asset_id"));
        let display_name = text(asset.get("display_name"));
        let kind = text(asset.get("kind"));
        let status = text(asset.get("status"));
        let release_eligible = asset.get("release_eligible").and_then(Value::as_bool);
        if asset_id.is_none_or(|value| !safe_id(value)) {
            audit.errors.push(format!("{prefix}.asset_id is unsafe"));
        } else if !ids.insert(asset_id.unwrap()) {
            audit
                .errors
                .push(format!("{prefix}.asset_id is duplicated"));
        }
        if display_name.is_none() {
            audit
                .errors
                .push(format!("{prefix}.display_name is required"));
        }
        if !matches!(kind, Some("skill" | "mcp" | "package")) {
            audit.errors.push(format!("{prefix}.kind is invalid"));
        }
        if status != Some(RELEASE_STATUS) {
            audit.errors.push(format!(
                "{prefix}.status must be validated-adapter; unresolved or excluded sources do not belong in the release registry"
            ));
        }
        if release_eligible != Some(status == Some(RELEASE_STATUS)) {
            audit.errors.push(format!(
                "{prefix}.release_eligible must exactly match validated-adapter status"
            ));
        }

        let source = asset.get("source").and_then(Value::as_object);
        let repository = source.and_then(|value| text(value.get("repository")));
        let revision = source.and_then(|value| text(value.get("revision")));
        let license_spdx = source.and_then(|value| text(value.get("license_spdx")));
        let license_evidence = source.and_then(|value| text(value.get("license_evidence_url")));
        let license_compatible = source
            .and_then(|value| value.get("license_compatible"))
            .and_then(Value::as_bool);
        if repository.is_none_or(|value| !value.starts_with("https://")) {
            audit
                .errors
                .push(format!("{prefix}.source.repository must use HTTPS"));
        }
        if revision.is_none_or(|value| !hex(value, 40)) {
            audit.errors.push(format!(
                "{prefix}.source.revision must be a lowercase 40-character commit"
            ));
        }
        if license_spdx.is_none() {
            audit
                .errors
                .push(format!("{prefix}.source.license_spdx is required"));
        }
        if license_evidence.is_none_or(|value| !value.starts_with("https://")) {
            audit.errors.push(format!(
                "{prefix}.source.license_evidence_url must use HTTPS"
            ));
        }
        if license_compatible.is_none() {
            audit.errors.push(format!(
                "{prefix}.source.license_compatible must be boolean"
            ));
        }

        let boundary = asset.get("capability_boundary").and_then(Value::as_object);
        for field in ["workspace_access", "network_egress", "execution"] {
            if boundary.and_then(|value| text(value.get(field))).is_none() {
                audit
                    .errors
                    .push(format!("{prefix}.capability_boundary.{field} is required"));
            }
        }
        if boundary.and_then(|value| text(value.get("authority")))
            != Some("no-approval-or-decision-authority")
        {
            audit.errors.push(format!(
                "{prefix}.capability_boundary.authority cannot delegate approval or decision authority"
            ));
        }

        let industrial = asset.get("industrialization").and_then(Value::as_object);
        let adaptation_mode = industrial.and_then(|value| text(value.get("adaptation_mode")));
        let delta_record = industrial.and_then(|value| text(value.get("delta_record")));
        let contract_tests = industrial.and_then(|value| strings(value.get("contract_tests")));
        let adversarial_tests =
            industrial.and_then(|value| strings(value.get("adversarial_tests")));
        let security_review = industrial.and_then(|value| text(value.get("security_review")));
        let methods_review = industrial.and_then(|value| text(value.get("methods_review")));
        let kill_switch = industrial
            .and_then(|value| value.get("kill_switch"))
            .and_then(Value::as_bool);
        if adaptation_mode.is_none() || delta_record.is_none() {
            audit.errors.push(format!(
                "{prefix}.industrialization adaptation_mode and delta_record are required"
            ));
        }
        if contract_tests.is_none()
            || adversarial_tests.is_none()
            || industrial
                .and_then(|value| strings(value.get("platforms")))
                .is_none()
            || industrial
                .and_then(|value| strings(value.get("upstream_evidence")))
                .is_none()
        {
            audit.errors.push(format!(
                "{prefix}.industrialization evidence arrays must contain only non-empty strings"
            ));
        }
        if security_review.is_none() || methods_review.is_none() || kill_switch.is_none() {
            audit.errors.push(format!(
                "{prefix}.industrialization review and kill-switch fields are required"
            ));
        }
        let blockers = strings(asset.get("blockers"));
        if blockers.is_none() {
            audit
                .errors
                .push(format!("{prefix}.blockers must be a string array"));
        }

        match status {
            Some(RELEASE_STATUS) => {
                audit.admitted_count += 1;
                if license_compatible != Some(true)
                    || !matches!(
                        adaptation_mode,
                        Some("first-party-derivative" | "isolated-adapter")
                    )
                    || contract_tests.as_ref().is_none_or(Vec::is_empty)
                    || adversarial_tests.as_ref().is_none_or(Vec::is_empty)
                    || !exact_platforms(industrial.and_then(|value| value.get("platforms")))
                    || security_review != Some("passed")
                    || methods_review != Some("passed")
                    || kill_switch != Some(true)
                    || blockers.as_ref().is_none_or(|values| !values.is_empty())
                {
                    audit.errors.push(format!(
                        "{prefix} is not industrially complete enough for validated-adapter"
                    ));
                }
                let distribution = asset.get("distribution").and_then(Value::as_object);
                let resource_pack = distribution
                    .and_then(|value| text(value.get("resource_pack")))
                    .unwrap_or_default();
                let entry = distribution
                    .and_then(|value| text(value.get("entry")))
                    .unwrap_or_default();
                let content_sha256 = distribution
                    .and_then(|value| text(value.get("content_sha256")))
                    .unwrap_or_default();
                if kind != Some("skill")
                    || !safe_segment(resource_pack)
                    || !resource_pack.starts_with("skills-admitted-")
                    || !safe_segment(entry)
                    || !hex(content_sha256, 64)
                {
                    audit.errors.push(format!(
                        "{prefix}.distribution must name a hash-locked admitted skill resource"
                    ));
                } else if !deployment_keys.insert((resource_pack, entry)) {
                    audit.errors.push(format!(
                        "{prefix}.distribution duplicates an admitted resource"
                    ));
                } else {
                    deployments.push(SkillDeployment {
                        resource_pack: resource_pack.to_string(),
                        entry: entry.to_string(),
                        content_sha256: content_sha256.to_string(),
                    });
                }
            }
            _ => {}
        }

        audit.assets.push(AssetAdmissionRecord {
            asset_id: asset_id.unwrap_or_default().to_string(),
            display_name: display_name.unwrap_or_default().to_string(),
            kind: kind.unwrap_or_default().to_string(),
            status: status.unwrap_or_default().to_string(),
            release_eligible: release_eligible.unwrap_or(false),
            repository: repository.unwrap_or_default().to_string(),
            revision: revision.unwrap_or_default().to_string(),
            license_spdx: license_spdx.unwrap_or_default().to_string(),
            license_compatible: license_compatible.unwrap_or(false),
            network_egress: boundary
                .and_then(|value| text(value.get("network_egress")))
                .unwrap_or_default()
                .to_string(),
            execution: boundary
                .and_then(|value| text(value.get("execution")))
                .unwrap_or_default()
                .to_string(),
            blockers: blockers.unwrap_or_default(),
        });
    }
    audit.complete = audit.errors.is_empty();
    audit.fail_closed = !audit.complete;
    if !audit.complete {
        deployments.clear();
    }
    (audit, deployments)
}

pub(crate) fn read_registry_resource(app: &AppHandle) -> Result<Vec<u8>, String> {
    let path = app
        .path()
        .resolve(ASSET_REGISTRY_RESOURCE, BaseDirectory::Resource)
        .map_err(|error| format!("asset registry resource is unavailable: {error}"))?;
    let metadata = std::fs::metadata(&path)
        .map_err(|error| format!("asset registry resource is unavailable: {error}"))?;
    if !metadata.is_file() || metadata.len() > REGISTRY_CAP_BYTES {
        return Err("asset registry resource is not a bounded regular file".into());
    }
    std::fs::read(path).map_err(|error| format!("asset registry resource cannot be read: {error}"))
}

#[tauri::command]
pub fn audit_asset_admission(app: AppHandle) -> Result<AssetAdmissionAudit, String> {
    let raw = match read_registry_resource(&app) {
        Ok(raw) => raw,
        Err(error) => return Ok(empty(error)),
    };
    let (mut audit, deployments) = validate_registry(&raw);
    if !audit.complete {
        return Ok(audit);
    }
    let declared_admitted = audit.admitted_count;
    audit.admitted_count = 0;
    for deployment in deployments {
        let resource = app
            .path()
            .resolve(&deployment.resource_pack, BaseDirectory::Resource)
            .map_err(|error| error.to_string());
        match resource.and_then(|path| verify_skill_deployment(&path, &deployment)) {
            Ok(()) => audit.admitted_count += 1,
            Err(error) => audit.errors.push(format!(
                "admitted asset {}/{} failed packaged-byte verification: {error}",
                deployment.resource_pack, deployment.entry
            )),
        }
    }
    if audit.admitted_count != declared_admitted {
        audit.complete = false;
        audit.fail_closed = true;
    }
    Ok(audit)
}

fn collect_files(root: &Path, directory: &Path, files: &mut Vec<PathBuf>) -> Result<(), String> {
    for entry in std::fs::read_dir(directory)
        .map_err(|error| format!("cannot inspect admitted asset: {error}"))?
    {
        let entry = entry.map_err(|error| format!("cannot inspect admitted asset: {error}"))?;
        let metadata = std::fs::symlink_metadata(entry.path())
            .map_err(|error| format!("cannot inspect admitted asset: {error}"))?;
        if metadata.file_type().is_symlink() {
            return Err("admitted asset trees cannot contain symlinks".into());
        }
        if metadata.is_dir() {
            collect_files(root, &entry.path(), files)?;
        } else if metadata.is_file() {
            files.push(
                entry
                    .path()
                    .strip_prefix(root)
                    .map_err(|_| "admitted asset escaped its root")?
                    .to_path_buf(),
            );
        } else {
            return Err("admitted asset trees may contain only regular files".into());
        }
    }
    Ok(())
}

pub(crate) fn tree_sha256(root: &Path) -> Result<String, String> {
    if !root.is_dir() || !root.join("SKILL.md").is_file() {
        return Err("admitted skill must be a directory containing SKILL.md".into());
    }
    let mut files = Vec::new();
    collect_files(root, root, &mut files)?;
    files.sort_by(|left, right| {
        left.to_string_lossy()
            .replace('\\', "/")
            .cmp(&right.to_string_lossy().replace('\\', "/"))
    });
    let mut digest = Sha256::new();
    for relative in files {
        let portable = relative.to_string_lossy().replace('\\', "/");
        let bytes = std::fs::read(root.join(&relative))
            .map_err(|error| format!("cannot hash admitted asset: {error}"))?;
        digest.update((portable.len() as u64).to_be_bytes());
        digest.update(portable.as_bytes());
        digest.update((bytes.len() as u64).to_be_bytes());
        digest.update(bytes);
    }
    Ok(format!("{:x}", digest.finalize()))
}

pub(crate) fn verify_skill_deployment(
    resource_root: &Path,
    deployment: &SkillDeployment,
) -> Result<(), String> {
    if !resource_root.is_dir() {
        return Err("admitted resource pack is missing".into());
    }
    let actual = tree_sha256(&resource_root.join(&deployment.entry))?;
    if actual != deployment.content_sha256 {
        return Err(format!(
            "content hash mismatch: expected {}, got {actual}",
            deployment.content_sha256
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{tree_sha256, validate_registry};
    use serde_json::Value;
    use std::fs;

    const REGISTRY: &[u8] =
        include_bytes!("../../../../runtime/assets/asset-admission-registry.json");

    fn unfinished_asset(status: &str) -> Value {
        serde_json::json!({
            "asset_id": "example/tool",
            "display_name": "Example Tool",
            "kind": "skill",
            "status": status,
            "release_eligible": status == "validated-adapter",
            "source": {
                "repository": "https://example.test/tool",
                "revision": "0123456789abcdef0123456789abcdef01234567",
                "license_spdx": "MIT",
                "license_evidence_url": "https://example.test/tool/LICENSE",
                "license_compatible": true
            },
            "capability_boundary": {
                "workspace_access": "current-workspace-required",
                "network_egress": "none-by-default",
                "execution": "human-approved",
                "authority": "no-approval-or-decision-authority"
            },
            "industrialization": {
                "adaptation_mode": "rewrite-required",
                "delta_record": "docs/audit.md",
                "contract_tests": [],
                "adversarial_tests": [],
                "platforms": [],
                "security_review": "pending",
                "methods_review": "pending",
                "kill_switch": false,
                "upstream_evidence": ["Pinned source"]
            },
            "distribution": null,
            "blockers": ["Not production ready"]
        })
    }

    #[test]
    fn production_registry_is_valid_and_contains_no_external_candidate_rows() {
        let (audit, deployments) = validate_registry(REGISTRY);
        assert!(audit.complete, "{:?}", audit.errors);
        assert!(!audit.fail_closed);
        assert_eq!(audit.total_count, 0);
        assert_eq!(audit.admitted_count, 0);
        assert!(deployments.is_empty());
    }

    #[test]
    fn unresolved_or_excluded_source_cannot_enter_release_registry() {
        let mut value: Value = serde_json::from_slice(REGISTRY).unwrap();
        value["assets"] = serde_json::json!([unfinished_asset("quarantined")]);
        let (audit, deployments) = validate_registry(&serde_json::to_vec(&value).unwrap());
        assert!(!audit.complete);
        assert!(deployments.is_empty());
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("do not belong in the release registry")));
    }

    #[test]
    fn status_edit_cannot_promote_an_unfinished_asset() {
        let mut value: Value = serde_json::from_slice(REGISTRY).unwrap();
        value["assets"] = serde_json::json!([unfinished_asset("validated-adapter")]);
        let (audit, deployments) = validate_registry(&serde_json::to_vec(&value).unwrap());
        assert!(!audit.complete);
        assert!(deployments.is_empty());
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("industrially complete")));
    }

    #[test]
    fn duplicate_ids_fail_closed() {
        let mut value: Value = serde_json::from_slice(REGISTRY).unwrap();
        let asset = unfinished_asset("validated-adapter");
        value["assets"] = serde_json::json!([asset.clone(), asset]);
        let (audit, deployments) = validate_registry(&serde_json::to_vec(&value).unwrap());
        assert!(!audit.complete);
        assert!(deployments.is_empty());
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("duplicated")));
    }

    #[test]
    fn tree_hash_is_content_and_path_bound() {
        let root = std::env::temp_dir().join(format!("asset-tree-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("references")).unwrap();
        fs::write(root.join("SKILL.md"), b"one").unwrap();
        fs::write(root.join("references/a.md"), b"two").unwrap();
        let first = tree_sha256(&root).unwrap();
        assert_eq!(first, tree_sha256(&root).unwrap());
        fs::write(root.join("references/a.md"), b"changed").unwrap();
        assert_ne!(first, tree_sha256(&root).unwrap());
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn tree_hash_rejects_symlinks() {
        use std::os::unix::fs::symlink;
        let root = std::env::temp_dir().join(format!("asset-link-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("SKILL.md"), b"one").unwrap();
        symlink(root.join("SKILL.md"), root.join("alias.md")).unwrap();
        assert!(tree_sha256(&root).unwrap_err().contains("symlinks"));
        fs::remove_dir_all(root).unwrap();
    }
}
