//! Native audit for backend-neutral joint PFS/OS survival-draw artifacts.

use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::io::Read;
use std::path::{Component, Path, PathBuf};

pub const MANIFEST_PATH: &str = "heor/joint-survival-uncertainty.json";
pub const DRAWS_PATH: &str = "heor/joint-survival-draws.jsonl";
const DRAW_FORMAT: &str = "ai4heor-joint-survival-draws-jsonl@0.1.0";
const MAX_DRAW_BYTES: u64 = 128 * 1024 * 1024;
const MAX_LINE_BYTES: usize = 2 * 1024 * 1024;
const MAX_CELLS: u64 = 5_000_000;
const TOLERANCE: f64 = 1e-9;

#[derive(Clone, Debug, Default)]
pub struct JointSurvivalAudit {
    pub complete: bool,
    pub manifest_sha256: String,
    pub draws_sha256: String,
    pub draw_count: Option<u64>,
    pub errors: Vec<String>,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn text(value: Option<&serde_json::Value>) -> Option<&str> {
    value
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.trim().is_empty())
}

fn object_has_exact_keys(value: &serde_json::Value, expected: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == expected.len() && expected.iter().all(|key| object.contains_key(*key))
    })
}

fn safe_relative_path(value: &str) -> bool {
    value.starts_with("heor/")
        && Path::new(value)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn resolve_workspace_file(workspace: &Path, relative: &str) -> Result<PathBuf, String> {
    if !safe_relative_path(relative) {
        return Err(format!("{relative} must be a safe path under heor/"));
    }
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let path = root
        .join(relative)
        .canonicalize()
        .map_err(|error| format!("{relative} unavailable: {error}"))?;
    if !path.starts_with(&root) || !path.is_file() {
        return Err(format!(
            "{relative} must be a file inside the current workspace"
        ));
    }
    Ok(path)
}

fn read_workspace_file(workspace: &Path, relative: &str, cap: u64) -> Result<Vec<u8>, String> {
    let path = resolve_workspace_file(workspace, relative)?;
    let metadata =
        std::fs::metadata(&path).map_err(|error| format!("{relative} unavailable: {error}"))?;
    if metadata.len() > cap {
        return Err(format!("{relative} exceeds the bounded audit size"));
    }
    std::fs::read(path).map_err(|error| format!("{relative} unavailable: {error}"))
}

fn hash_workspace_file(workspace: &Path, relative: &str) -> Result<String, String> {
    let path = resolve_workspace_file(workspace, relative)?;
    let mut file =
        std::fs::File::open(path).map_err(|error| format!("{relative} unavailable: {error}"))?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|error| format!("{relative} unavailable: {error}"))?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn validate_binding(
    value: Option<&serde_json::Value>,
    path: &str,
    expected_sha256: &str,
    label: &str,
    errors: &mut Vec<String>,
) {
    let valid = value.is_some_and(|binding| {
        object_has_exact_keys(binding, &["path", "content_sha256"])
            && text(binding.get("path")) == Some(path)
            && text(binding.get("content_sha256")) == Some(expected_sha256)
    });
    if !valid {
        errors.push(format!("{label} does not bind the current artifact bytes"));
    }
}

fn finite_curve(value: &serde_json::Value, grid_count: usize) -> Option<Vec<f64>> {
    let values = value.as_array()?;
    if values.len() != grid_count {
        return None;
    }
    values
        .iter()
        .map(|item| item.as_f64().filter(|number| number.is_finite()))
        .collect()
}

fn validate_draws(
    raw: &[u8],
    draw_count: usize,
    curve_count: usize,
    grid_count: usize,
    strategy_count: usize,
    errors: &mut Vec<String>,
) {
    let Ok(text) = std::str::from_utf8(raw) else {
        errors.push("joint survival draws must be UTF-8 JSONL".into());
        return;
    };
    let lines = text.lines().collect::<Vec<_>>();
    if lines.len() != draw_count || lines.iter().any(|line| line.trim().is_empty()) {
        errors.push("joint survival draws must contain exactly draw_count non-empty rows".into());
        return;
    }
    for (offset, line) in lines.iter().enumerate() {
        let row_index = offset + 1;
        if line.len() > MAX_LINE_BYTES {
            errors.push(format!("joint survival draw row {row_index} exceeds 2 MB"));
            continue;
        }
        let Ok(row) = serde_json::from_str::<serde_json::Value>(line) else {
            errors.push(format!(
                "joint survival draw row {row_index} is invalid JSON"
            ));
            continue;
        };
        if !object_has_exact_keys(&row, &["draw_index", "curves"])
            || row.get("draw_index").and_then(serde_json::Value::as_u64) != Some(row_index as u64)
        {
            errors.push(format!(
                "joint survival draw row {row_index} fields or index are invalid"
            ));
            continue;
        }
        let Some(curves) = row.get("curves").and_then(serde_json::Value::as_array) else {
            errors.push(format!(
                "joint survival draw row {row_index} omitted curves"
            ));
            continue;
        };
        if curves.len() != curve_count {
            errors.push(format!(
                "joint survival draw row {row_index} does not cover curve_order"
            ));
            continue;
        }
        let mut checked = Vec::with_capacity(curve_count);
        for (curve_index, curve) in curves.iter().enumerate() {
            let Some(values) = finite_curve(curve, grid_count) else {
                errors.push(format!(
                    "joint survival draw row {row_index} curve {curve_index} is incomplete or non-finite"
                ));
                continue;
            };
            if (values[0] - 1.0).abs() > TOLERANCE
                || values.iter().any(|value| !(0.0..=1.0).contains(value))
                || values.windows(2).any(|pair| pair[1] > pair[0] + TOLERANCE)
            {
                errors.push(format!(
                    "joint survival draw row {row_index} curve {curve_index} is incoherent"
                ));
            }
            checked.push(values);
        }
        if checked.len() == curve_count {
            for strategy_index in 0..strategy_count {
                if checked[strategy_index * 2]
                    .iter()
                    .zip(&checked[strategy_index * 2 + 1])
                    .any(|(pfs, overall)| pfs > &(overall + TOLERANCE))
                {
                    errors.push(format!(
                        "joint survival draw row {row_index} has PFS above OS"
                    ));
                }
            }
        }
        if errors.len() >= 100 {
            errors.push("joint survival draw validation stopped after 100 errors".into());
            break;
        }
    }
}

pub fn audit_joint_survival_for_plan(
    workspace: &Path,
    plan_raw: &[u8],
    uncertainty: &serde_json::Value,
    expected_iterations: Option<u64>,
) -> JointSurvivalAudit {
    let mut audit = JointSurvivalAudit::default();
    let plan: serde_json::Value = match serde_json::from_slice(plan_raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("analysis plan is invalid: {error}"));
            return audit;
        }
    };
    let manifest_raw = match read_workspace_file(workspace, MANIFEST_PATH, 5 * 1024 * 1024) {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let draws_raw = match read_workspace_file(workspace, DRAWS_PATH, MAX_DRAW_BYTES) {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    audit.manifest_sha256 = sha256(&manifest_raw);
    audit.draws_sha256 = sha256(&draws_raw);
    let manifest: serde_json::Value = match serde_json::from_slice(&manifest_raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("joint survival manifest is invalid: {error}"));
            return audit;
        }
    };
    let legacy_fields = [
        "schema_version",
        "survival_uncertainty_id",
        "analysis_id",
        "psm_id",
        "status",
        "base_analysis",
        "partitioned_survival_plan",
        "curve_materializations",
        "draw_file",
        "curve_order",
        "time_grid_years",
        "generation",
        "limitations",
    ];
    let duration_fields = [
        "schema_version",
        "survival_uncertainty_id",
        "analysis_id",
        "psm_id",
        "status",
        "base_analysis",
        "partitioned_survival_plan",
        "curve_materializations",
        "treatment_effect_duration",
        "draw_file",
        "curve_order",
        "time_grid_years",
        "generation",
        "limitations",
    ];
    if !object_has_exact_keys(&manifest, &legacy_fields)
        && !object_has_exact_keys(&manifest, &duration_fields)
    {
        audit
            .errors
            .push("joint survival manifest fields do not match a supported schema".into());
    }
    if text(manifest.get("status")) != Some("ready_for_human_review")
        || text(manifest.get("survival_uncertainty_id")).is_none()
    {
        audit
            .errors
            .push("joint survival manifest identity or status is invalid".into());
    }

    let psm_raw = match crate::heor_uncertainty::read_workspace_capped(
        workspace,
        crate::heor_partitioned_survival::PARTITIONED_SURVIVAL_PLAN_PATH,
    ) {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let materializations_raw = match crate::heor_uncertainty::read_workspace_capped(
        workspace,
        crate::heor_survival_materialization::SURVIVAL_MATERIALIZATION_PATH,
    ) {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let psm: serde_json::Value = match serde_json::from_slice(&psm_raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("partitioned-survival plan is invalid: {error}"));
            return audit;
        }
    };
    let psm_schema = psm
        .get("schema_version")
        .and_then(serde_json::Value::as_str);
    let duration_required = matches!(psm_schema, Some("0.4.0" | "0.7.0"));
    let manifest_schema = text(manifest.get("schema_version"));
    let schema_supported = match psm_schema {
        Some("0.7.0") => matches!(manifest_schema, Some("0.4.0" | "0.3.0")),
        Some("0.4.0") => manifest_schema == Some("0.2.0"),
        _ => manifest_schema == Some("0.1.0"),
    };
    if !schema_supported
        || (duration_required && !object_has_exact_keys(&manifest, &duration_fields))
        || (!duration_required && !object_has_exact_keys(&manifest, &legacy_fields))
    {
        let expected = if psm_schema == Some("0.7.0") {
            "0.4.0 or prior current schema 0.3.0"
        } else if psm_schema == Some("0.4.0") {
            "0.2.0"
        } else {
            "0.1.0"
        };
        audit.errors.push(format!(
            "joint survival manifest must use schema {expected} for the current PSM"
        ));
    }
    if manifest.get("analysis_id") != plan.get("analysis_id")
        || manifest.get("psm_id") != psm.get("psm_id")
    {
        audit
            .errors
            .push("joint survival manifest IDs do not match current inputs".into());
    }
    validate_binding(
        manifest.get("base_analysis"),
        "heor/analysis-plan.json",
        &sha256(plan_raw),
        "base_analysis",
        &mut audit.errors,
    );
    validate_binding(
        manifest.get("partitioned_survival_plan"),
        crate::heor_partitioned_survival::PARTITIONED_SURVIVAL_PLAN_PATH,
        &sha256(&psm_raw),
        "partitioned_survival_plan",
        &mut audit.errors,
    );
    validate_binding(
        manifest.get("curve_materializations"),
        crate::heor_survival_materialization::SURVIVAL_MATERIALIZATION_PATH,
        &sha256(&materializations_raw),
        "curve_materializations",
        &mut audit.errors,
    );
    if duration_required {
        match crate::heor_uncertainty::read_workspace_capped(
            workspace,
            crate::heor_treatment_effect_duration::TREATMENT_EFFECT_DURATION_PATH,
        ) {
            Ok(duration_raw) => validate_binding(
                manifest.get("treatment_effect_duration"),
                crate::heor_treatment_effect_duration::TREATMENT_EFFECT_DURATION_PATH,
                &sha256(&duration_raw),
                "treatment_effect_duration",
                &mut audit.errors,
            ),
            Err(error) => audit.errors.push(error),
        }
    }
    if uncertainty
        .get("joint_survival_inputs")
        .is_none_or(|value| !object_has_exact_keys(value, &["manifest", "draws"]))
    {
        audit
            .errors
            .push("joint_survival_inputs must contain only manifest and draws".into());
    }
    validate_binding(
        uncertainty.pointer("/joint_survival_inputs/manifest"),
        MANIFEST_PATH,
        &audit.manifest_sha256,
        "joint_survival_inputs.manifest",
        &mut audit.errors,
    );
    validate_binding(
        uncertainty.pointer("/joint_survival_inputs/draws"),
        DRAWS_PATH,
        &audit.draws_sha256,
        "joint_survival_inputs.draws",
        &mut audit.errors,
    );

    let strategy_order = plan
        .get("strategy_order")
        .and_then(serde_json::Value::as_array)
        .and_then(|values| {
            values
                .iter()
                .map(serde_json::Value::as_str)
                .collect::<Option<Vec<_>>>()
        })
        .unwrap_or_default();
    let expected_curve_order = strategy_order
        .iter()
        .flat_map(|strategy_id| {
            ["pfs", "os"]
                .map(|endpoint| format!("partitioned_survival.strategies.{strategy_id}.{endpoint}"))
        })
        .collect::<Vec<_>>();
    let curve_order = manifest
        .get("curve_order")
        .and_then(serde_json::Value::as_array)
        .and_then(|values| {
            values
                .iter()
                .map(|value| value.as_str().map(str::to_string))
                .collect::<Option<Vec<_>>>()
        })
        .unwrap_or_default();
    if strategy_order.is_empty() || curve_order != expected_curve_order {
        audit
            .errors
            .push("curve_order must list every strategy PFS then OS".into());
    }

    let cycles = plan.get("cycles").and_then(serde_json::Value::as_u64);
    let cycle_length = plan
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0);
    let grid = manifest
        .get("time_grid_years")
        .and_then(serde_json::Value::as_array);
    let grid_valid = cycles.zip(cycle_length).is_some_and(|(cycles, length)| {
        grid.is_some_and(|values| {
            values.len() == cycles as usize + 1
                && values.iter().enumerate().all(|(index, value)| {
                    value.as_f64().is_some_and(|value| {
                        value.is_finite() && (value - index as f64 * length).abs() <= TOLERANCE
                    })
                })
        })
    });
    if !grid_valid {
        audit
            .errors
            .push("joint survival time grid does not match the analysis grid".into());
    }

    let generation = manifest.get("generation");
    let current_generation = manifest_schema == Some("0.4.0");
    let generation_fields = if current_generation {
        vec![
            "method",
            "sampling_unit",
            "independent_endpoint_sampling",
            "strategy_resampling_design",
            "between_strategy_assumption",
            "dependence_scope",
            "source_artifact_bindings",
            "rationale",
        ]
    } else {
        vec![
            "method",
            "sampling_unit",
            "independent_endpoint_sampling",
            "dependence_scope",
            "source_artifact_bindings",
            "rationale",
        ]
    };
    if generation.is_none_or(|value| !object_has_exact_keys(value, &generation_fields)) {
        audit
            .errors
            .push("joint survival generation fields are invalid".into());
    }
    if !matches!(
        generation.and_then(|value| text(value.get("method"))),
        Some("joint_posterior" | "paired_patient_bootstrap")
    ) || generation.and_then(|value| text(value.get("sampling_unit")))
        != Some("joint_draw_across_all_curves")
        || generation
            .and_then(|value| value.get("independent_endpoint_sampling"))
            .and_then(serde_json::Value::as_bool)
            != Some(false)
        || generation
            .and_then(|value| text(value.get("rationale")))
            .is_none()
    {
        audit
            .errors
            .push("joint survival generation method or sampling unit is invalid".into());
    }
    let dependence = generation
        .and_then(|value| value.get("dependence_scope"))
        .and_then(serde_json::Value::as_array)
        .and_then(|values| {
            values
                .iter()
                .map(serde_json::Value::as_str)
                .collect::<Option<Vec<_>>>()
        });
    if current_generation {
        let method = generation.and_then(|value| text(value.get("method")));
        let design = generation.and_then(|value| text(value.get("strategy_resampling_design")));
        let between_strategy =
            generation.and_then(|value| text(value.get("between_strategy_assumption")));
        let valid = match method {
            Some("paired_patient_bootstrap") => {
                design == Some("stratified_independent_parallel_arms")
                    && between_strategy
                        == Some("conditional_independence_given_parallel_arm_design")
                    && dependence == Some(vec!["within_strategy_pfs_os"])
            }
            Some("joint_posterior") => {
                design == Some("joint_model")
                    && between_strategy == Some("represented_by_source_joint_distribution")
                    && dependence == Some(vec!["within_strategy_pfs_os", "between_strategy_curves"])
            }
            _ => false,
        };
        if !valid {
            audit.errors.push(
                "current joint survival generation design, between-strategy assumption, or dependence scope is invalid"
                    .into(),
            );
        }
    } else if dependence != Some(vec!["within_strategy_pfs_os", "between_strategy_curves"]) {
        audit
            .errors
            .push("legacy joint survival dependence scope is incomplete".into());
    }
    let source_bindings = generation
        .and_then(|value| value.get("source_artifact_bindings"))
        .and_then(serde_json::Value::as_array);
    let mut source_paths = HashSet::new();
    if source_bindings.is_none_or(Vec::is_empty) {
        audit
            .errors
            .push("joint survival source artifact bindings are required".into());
    }
    for (index, binding) in source_bindings.into_iter().flatten().enumerate() {
        let path = text(binding.get("path"));
        let digest = text(binding.get("content_sha256"));
        if !object_has_exact_keys(binding, &["path", "content_sha256", "role"])
            || path.is_none_or(|path| !safe_relative_path(path) || !source_paths.insert(path))
            || digest.is_none_or(|value| {
                value.len() != 64
                    || !value
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            })
            || text(binding.get("role")).is_none()
        {
            audit
                .errors
                .push(format!("source artifact binding {index} is invalid"));
            continue;
        }
        match hash_workspace_file(workspace, path.unwrap()) {
            Ok(actual) if Some(actual.as_str()) == digest => {}
            Ok(_) => audit
                .errors
                .push(format!("source artifact binding {index} hash is stale")),
            Err(error) => audit.errors.push(error),
        }
    }

    let draw_file = manifest.get("draw_file");
    let draw_count = draw_file
        .and_then(|value| value.get("draw_count"))
        .and_then(serde_json::Value::as_u64);
    audit.draw_count = draw_count;
    if draw_file.is_none_or(|value| {
        !object_has_exact_keys(value, &["path", "content_sha256", "format", "draw_count"])
    }) || draw_file.and_then(|value| text(value.get("path"))) != Some(DRAWS_PATH)
        || draw_file.and_then(|value| text(value.get("format"))) != Some(DRAW_FORMAT)
        || draw_file.and_then(|value| text(value.get("content_sha256")))
            != Some(audit.draws_sha256.as_str())
        || draw_count.is_none_or(|count| !(1_000..=10_000).contains(&count))
        || draw_count != expected_iterations
    {
        audit
            .errors
            .push("joint survival draw-file binding or draw_count is invalid".into());
    }
    let grid_count = grid.map(Vec::len).unwrap_or_default();
    if draw_count.is_some_and(|count| {
        count
            .saturating_mul(curve_order.len() as u64)
            .saturating_mul(grid_count as u64)
            > MAX_CELLS
    }) {
        audit
            .errors
            .push(format!("joint survival draws exceed {MAX_CELLS} values"));
    } else if let Some(count) = draw_count {
        validate_draws(
            &draws_raw,
            count as usize,
            curve_order.len(),
            grid_count,
            strategy_order.len(),
            &mut audit.errors,
        );
    }

    let limitations = manifest
        .get("limitations")
        .and_then(serde_json::Value::as_array);
    if limitations.is_none_or(|values| {
        values.is_empty()
            || values.iter().any(|value| text(Some(value)).is_none())
            || values
                .iter()
                .filter_map(serde_json::Value::as_str)
                .collect::<HashSet<_>>()
                .len()
                != values.len()
    }) {
        audit
            .errors
            .push("joint survival limitations must be non-empty unique strings".into());
    }
    let lowered = String::from_utf8_lossy(&manifest_raw).to_ascii_lowercase();
    if [
        "\"approved\":",
        "\"approval_timestamp\":",
        "\"independently_validated\":",
    ]
    .iter()
    .any(|field| lowered.contains(field))
    {
        audit
            .errors
            .push("joint survival manifest contains a forbidden authority field".into());
    }
    audit.complete = audit.errors.is_empty();
    audit
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_root(label: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "ai4heor-joint-survival-{label}-{}",
            std::process::id()
        ))
    }

    #[test]
    fn draw_rows_fail_closed_on_endpoint_crossing() {
        let raw = br#"{"draw_index":1,"curves":[[1.0,0.9],[1.0,0.8]]}"#;
        let mut errors = Vec::new();
        validate_draws(raw, 1, 2, 2, 1, &mut errors);
        assert!(errors.iter().any(|error| error.contains("PFS above OS")));
    }

    #[test]
    fn safe_paths_reject_parent_segments() {
        assert!(safe_relative_path("heor/fits/joint.json"));
        assert!(!safe_relative_path("heor/../outside.json"));
        assert!(!safe_relative_path("/heor/fits/joint.json"));
    }

    #[test]
    fn full_native_audit_binds_joint_rows_and_source_bytes() {
        let root = temp_root("complete");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor/fits")).unwrap();
        let plan = serde_json::json!({
            "schema_version": "0.12.0",
            "analysis_id": "analysis-1",
            "cycles": 1,
            "cycle_length_years": 1.0,
            "strategy_order": ["comparator", "intervention"]
        });
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let psm_raw = serde_json::to_vec(&serde_json::json!({
            "schema_version": "0.3.0",
            "analysis_id": "analysis-1",
            "psm_id": "psm-1"
        }))
        .unwrap();
        let materializations_raw = serde_json::to_vec(&serde_json::json!({
            "schema_version": "0.1.0",
            "analysis_id": "analysis-1"
        }))
        .unwrap();
        let source_raw = b"joint posterior";
        let draws_raw = (1..=1000)
            .map(|index| {
                format!(
                    "{{\"draw_index\":{index},\"curves\":[[1.0,0.6],[1.0,0.8],[1.0,0.7],[1.0,0.9]]}}\n"
                )
            })
            .collect::<String>()
            .into_bytes();
        let manifest = serde_json::json!({
            "schema_version": "0.1.0",
            "survival_uncertainty_id": "joint-1",
            "analysis_id": "analysis-1",
            "psm_id": "psm-1",
            "status": "ready_for_human_review",
            "base_analysis": {"path": "heor/analysis-plan.json", "content_sha256": sha256(&plan_raw)},
            "partitioned_survival_plan": {"path": "heor/partitioned-survival-plan.json", "content_sha256": sha256(&psm_raw)},
            "curve_materializations": {"path": "heor/survival-curve-materializations.json", "content_sha256": sha256(&materializations_raw)},
            "draw_file": {
                "path": DRAWS_PATH,
                "content_sha256": sha256(&draws_raw),
                "format": DRAW_FORMAT,
                "draw_count": 1000
            },
            "curve_order": [
                "partitioned_survival.strategies.comparator.pfs",
                "partitioned_survival.strategies.comparator.os",
                "partitioned_survival.strategies.intervention.pfs",
                "partitioned_survival.strategies.intervention.os"
            ],
            "time_grid_years": [0.0, 1.0],
            "generation": {
                "method": "joint_posterior",
                "sampling_unit": "joint_draw_across_all_curves",
                "independent_endpoint_sampling": false,
                "dependence_scope": ["within_strategy_pfs_os", "between_strategy_curves"],
                "source_artifact_bindings": [{
                    "path": "heor/fits/joint.json",
                    "content_sha256": sha256(source_raw),
                    "role": "Joint posterior"
                }],
                "rationale": "One posterior row covers every curve."
            },
            "limitations": ["Structural uncertainty remains."]
        });
        let manifest_raw = serde_json::to_vec(&manifest).unwrap();
        let uncertainty = serde_json::json!({
            "joint_survival_inputs": {
                "manifest": {"path": MANIFEST_PATH, "content_sha256": sha256(&manifest_raw)},
                "draws": {"path": DRAWS_PATH, "content_sha256": sha256(&draws_raw)}
            }
        });
        for (relative, raw) in [
            ("heor/partitioned-survival-plan.json", psm_raw.as_slice()),
            (
                "heor/survival-curve-materializations.json",
                materializations_raw.as_slice(),
            ),
            (MANIFEST_PATH, manifest_raw.as_slice()),
            (DRAWS_PATH, draws_raw.as_slice()),
            ("heor/fits/joint.json", source_raw.as_slice()),
        ] {
            std::fs::write(root.join(relative), raw).unwrap();
        }

        let audit = audit_joint_survival_for_plan(&root, &plan_raw, &uncertainty, Some(1000));
        assert!(audit.complete, "{:?}", audit.errors);
        assert_eq!(audit.draw_count, Some(1000));

        let current_psm_raw = serde_json::to_vec(&serde_json::json!({
            "schema_version": "0.7.0",
            "analysis_id": "analysis-1",
            "psm_id": "psm-1"
        }))
        .unwrap();
        let duration_raw = br#"{"schema_version":"0.1.0"}"#;
        let mut current_manifest = manifest.clone();
        current_manifest["schema_version"] = serde_json::json!("0.3.0");
        current_manifest["partitioned_survival_plan"]["content_sha256"] =
            serde_json::json!(sha256(&current_psm_raw));
        current_manifest["treatment_effect_duration"] = serde_json::json!({
            "path": "heor/treatment-effect-duration.json",
            "content_sha256": sha256(duration_raw)
        });
        let current_manifest_raw = serde_json::to_vec(&current_manifest).unwrap();
        let current_uncertainty = serde_json::json!({
            "joint_survival_inputs": {
                "manifest": {"path": MANIFEST_PATH, "content_sha256": sha256(&current_manifest_raw)},
                "draws": {"path": DRAWS_PATH, "content_sha256": sha256(&draws_raw)}
            }
        });
        std::fs::write(
            root.join("heor/partitioned-survival-plan.json"),
            &current_psm_raw,
        )
        .unwrap();
        std::fs::write(
            root.join("heor/treatment-effect-duration.json"),
            duration_raw,
        )
        .unwrap();
        std::fs::write(root.join(MANIFEST_PATH), &current_manifest_raw).unwrap();
        let current =
            audit_joint_survival_for_plan(&root, &plan_raw, &current_uncertainty, Some(1000));
        assert!(current.complete, "{:?}", current.errors);

        let mut paired_manifest = current_manifest.clone();
        paired_manifest["schema_version"] = serde_json::json!("0.4.0");
        paired_manifest["generation"] = serde_json::json!({
            "method": "paired_patient_bootstrap",
            "sampling_unit": "joint_draw_across_all_curves",
            "independent_endpoint_sampling": false,
            "strategy_resampling_design": "stratified_independent_parallel_arms",
            "between_strategy_assumption": "conditional_independence_given_parallel_arm_design",
            "dependence_scope": ["within_strategy_pfs_os"],
            "source_artifact_bindings": [{
                "path": "heor/fits/joint.json",
                "content_sha256": sha256(source_raw),
                "role": "Audited paired patient bootstrap result"
            }],
            "rationale": "Whole-subject rows preserve paired PFS and OS observations within each independently randomized arm."
        });
        let paired_manifest_raw = serde_json::to_vec(&paired_manifest).unwrap();
        let paired_uncertainty = serde_json::json!({
            "joint_survival_inputs": {
                "manifest": {"path": MANIFEST_PATH, "content_sha256": sha256(&paired_manifest_raw)},
                "draws": {"path": DRAWS_PATH, "content_sha256": sha256(&draws_raw)}
            }
        });
        std::fs::write(root.join(MANIFEST_PATH), &paired_manifest_raw).unwrap();
        let paired =
            audit_joint_survival_for_plan(&root, &plan_raw, &paired_uncertainty, Some(1000));
        assert!(paired.complete, "{:?}", paired.errors);

        paired_manifest["generation"]["dependence_scope"] =
            serde_json::json!(["within_strategy_pfs_os", "between_strategy_curves"]);
        let false_claim_raw = serde_json::to_vec(&paired_manifest).unwrap();
        let false_claim_uncertainty = serde_json::json!({
            "joint_survival_inputs": {
                "manifest": {"path": MANIFEST_PATH, "content_sha256": sha256(&false_claim_raw)},
                "draws": {"path": DRAWS_PATH, "content_sha256": sha256(&draws_raw)}
            }
        });
        std::fs::write(root.join(MANIFEST_PATH), &false_claim_raw).unwrap();
        let false_claim =
            audit_joint_survival_for_plan(&root, &plan_raw, &false_claim_uncertainty, Some(1000));
        assert!(!false_claim.complete);
        assert!(false_claim
            .errors
            .iter()
            .any(|error| error.contains("between-strategy assumption")));

        std::fs::write(root.join(MANIFEST_PATH), &current_manifest_raw).unwrap();
        std::fs::write(root.join("heor/fits/joint.json"), b"changed").unwrap();
        let stale =
            audit_joint_survival_for_plan(&root, &plan_raw, &current_uncertainty, Some(1000));
        assert!(!stale.complete);
        assert!(stale
            .errors
            .iter()
            .any(|error| error.contains("hash is stale")));
        let _ = std::fs::remove_dir_all(root);
    }
}
