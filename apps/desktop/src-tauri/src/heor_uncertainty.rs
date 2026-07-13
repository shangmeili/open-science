//! App-owned audit and execution boundary for HEOR uncertainty analysis.
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::Path;
use tauri::{path::BaseDirectory, AppHandle, Manager};

pub const UNCERTAINTY_PLAN_PATH: &str = "heor/uncertainty-plan.json";
const ANALYSIS_PLAN_PATH: &str = "heor/analysis-plan.json";
const ARTIFACT_CAP_BYTES: u64 = 5 * 1024 * 1024;
const OUTPUT_CAP_BYTES: usize = 25 * 1024 * 1024;
const MAX_PARAMETERS: usize = 256;
const MAX_SCENARIOS: usize = 64;

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UncertaintyAudit {
    pub complete: bool,
    pub status: &'static str,
    pub uncertainty_id: String,
    pub analysis_id: String,
    pub analysis_plan_sha256: String,
    pub uncertainty_sha256: String,
    pub seed: Option<String>,
    pub parameter_count: usize,
    pub scenario_count: usize,
    pub iterations: Option<u64>,
    pub omitted_parameter_count: usize,
    pub invalid_parameters: Vec<String>,
    pub errors: Vec<String>,
}

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UncertaintyRunResult {
    workflow: crate::heor_engine::HeorWorkflowStatus,
    calculation: serde_json::Value,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn nonempty(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| !value.trim().is_empty())
}

fn string_set(value: Option<&serde_json::Value>) -> Option<HashSet<&str>> {
    let values = value?.as_array()?;
    let mut result = HashSet::new();
    for item in values {
        let text = item.as_str()?;
        if text.trim().is_empty() || !result.insert(text) {
            return None;
        }
    }
    Some(result)
}

fn positive_number(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_f64)
        .is_some_and(|value| value.is_finite() && value > 0.0)
}

fn finite_number(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite())
}

fn parameter_target_allowed(target: &str) -> bool {
    let parts = target.split('/').collect::<Vec<_>>();
    matches!(
        parts.as_slice(),
        ["", "strategies", "comparator" | "intervention", "state_costs" | "state_utilities", index]
            if index.parse::<usize>().is_ok()
    ) || matches!(
        parts.as_slice(),
        ["", "strategies", "comparator" | "intervention", "transition_matrix", row]
            if row.parse::<usize>().is_ok()
    )
}

fn scenario_target_allowed(target: &str) -> bool {
    parameter_target_allowed(target)
        || matches!(
            target,
            "/cycles"
                | "/cycle_length_years"
                | "/discount_rates/costs"
                | "/discount_rates/outcomes"
                | "/half_cycle_correction"
        )
}

fn valid_simplex(value: &serde_json::Value, expected_len: usize) -> bool {
    let Some(values) = value.as_array() else {
        return false;
    };
    if values.len() != expected_len {
        return false;
    }
    let numbers = values
        .iter()
        .filter_map(serde_json::Value::as_f64)
        .collect::<Vec<_>>();
    numbers.len() == values.len()
        && numbers
            .iter()
            .all(|value| value.is_finite() && (0.0..=1.0).contains(value))
        && (numbers.iter().sum::<f64>() - 1.0).abs() <= 1e-9
}

fn replacement_compatible(
    target: &str,
    base: &serde_json::Value,
    replacement: &serde_json::Value,
) -> bool {
    if !scenario_target_allowed(target) {
        return false;
    }
    match base {
        serde_json::Value::Bool(_) => replacement.is_boolean(),
        serde_json::Value::Number(number) if number.is_i64() || number.is_u64() => {
            replacement.as_i64().is_some() || replacement.as_u64().is_some()
        }
        serde_json::Value::Number(_) => finite_number(Some(replacement)).is_some(),
        serde_json::Value::Array(values) => valid_simplex(replacement, values.len()),
        _ => false,
    }
}

fn read_capped(path: &Path, label: &str) -> Result<Vec<u8>, String> {
    let metadata =
        std::fs::metadata(path).map_err(|error| format!("{label} unavailable: {error}"))?;
    if !metadata.is_file() || metadata.len() > ARTIFACT_CAP_BYTES {
        return Err(format!("{label} is not a reviewable artifact"));
    }
    std::fs::read(path).map_err(|error| format!("{label} unavailable: {error}"))
}

pub(crate) fn read_workspace_capped(workspace: &Path, relative: &str) -> Result<Vec<u8>, String> {
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let path = root
        .join(relative)
        .canonicalize()
        .map_err(|error| format!("{relative} unavailable: {error}"))?;
    if !path.starts_with(&root) {
        return Err(format!("{relative} must stay inside the current workspace"));
    }
    read_capped(&path, relative)
}

fn empty_audit(plan_raw: &[u8]) -> UncertaintyAudit {
    UncertaintyAudit {
        complete: false,
        status: "incomplete",
        uncertainty_id: String::new(),
        analysis_id: String::new(),
        analysis_plan_sha256: sha256(plan_raw),
        uncertainty_sha256: String::new(),
        seed: None,
        parameter_count: 0,
        scenario_count: 0,
        iterations: None,
        omitted_parameter_count: 0,
        invalid_parameters: Vec::new(),
        errors: Vec::new(),
    }
}

fn validate_distribution(
    parameter_id: &str,
    value: &serde_json::Value,
    base: &serde_json::Value,
    allowed_basis: &HashSet<&str>,
    errors: &mut Vec<String>,
) {
    let Some(distribution) = value.as_object() else {
        errors.push(format!(
            "parameter {parameter_id} probabilistic definition is required"
        ));
        return;
    };
    if !nonempty(distribution.get("rationale")) {
        errors.push(format!(
            "parameter {parameter_id} probabilistic rationale is required"
        ));
    }
    let Some(basis_ids) = string_set(distribution.get("basis_ids")) else {
        errors.push(format!(
            "parameter {parameter_id} basis_ids must be non-empty and unique"
        ));
        return;
    };
    if basis_ids.is_empty() || !basis_ids.is_subset(allowed_basis) {
        errors.push(format!(
            "parameter {parameter_id} basis_ids are not linked by input provenance"
        ));
    }
    let kind = distribution
        .get("type")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let valid = match kind {
        "beta" => {
            !base.is_array()
                && positive_number(distribution.get("alpha"))
                && positive_number(distribution.get("beta"))
        }
        "gamma" => {
            !base.is_array()
                && positive_number(distribution.get("shape"))
                && positive_number(distribution.get("scale"))
        }
        "lognormal" => {
            !base.is_array()
                && finite_number(distribution.get("mu_log")).is_some()
                && positive_number(distribution.get("sigma_log"))
        }
        "uniform" => {
            !base.is_array()
                && finite_number(distribution.get("low"))
                    .zip(finite_number(distribution.get("high")))
                    .is_some_and(|(low, high)| low < high)
        }
        "dirichlet" => {
            let expected = base.as_array().map(Vec::len).unwrap_or_default();
            distribution
                .get("alpha")
                .and_then(serde_json::Value::as_array)
                .is_some_and(|alpha| {
                    expected > 0
                        && alpha.len() == expected
                        && alpha.iter().all(|value| positive_number(Some(value)))
                })
        }
        _ => false,
    };
    if !valid {
        errors.push(format!(
            "parameter {parameter_id} has an invalid or unsupported distribution"
        ));
    }
}

fn audit_values(
    plan: &serde_json::Value,
    plan_raw: &[u8],
    uncertainty: &serde_json::Value,
    uncertainty_raw: &[u8],
) -> UncertaintyAudit {
    let mut audit = empty_audit(plan_raw);
    audit.uncertainty_sha256 = sha256(uncertainty_raw);
    audit.uncertainty_id = uncertainty
        .get("uncertainty_id")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
        .to_string();
    audit.analysis_id = uncertainty
        .get("analysis_id")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
        .to_string();
    audit.seed = uncertainty
        .get("seed")
        .and_then(serde_json::Value::as_u64)
        .map(|seed| seed.to_string());

    if uncertainty
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
    {
        audit
            .errors
            .push("uncertainty schema_version must be 0.1.0".into());
    }
    for field in ["uncertainty_id", "analysis_id"] {
        if !nonempty(uncertainty.get(field)) {
            audit
                .errors
                .push(format!("uncertainty {field} is required"));
        }
    }
    if uncertainty.get("analysis_id") != plan.get("analysis_id") {
        audit
            .errors
            .push("uncertainty analysis_id does not match the plan".into());
    }
    if uncertainty
        .get("status")
        .and_then(serde_json::Value::as_str)
        != Some("ready_for_human_review")
    {
        audit
            .errors
            .push("uncertainty plan must be ready_for_human_review".into());
    }
    if plan
        .pointer("/uncertainty_analysis/path")
        .and_then(serde_json::Value::as_str)
        != Some(UNCERTAINTY_PLAN_PATH)
    {
        audit
            .errors
            .push(format!("analysis plan must link {UNCERTAINTY_PLAN_PATH}"));
    }
    if uncertainty
        .pointer("/base_analysis/path")
        .and_then(serde_json::Value::as_str)
        != Some(ANALYSIS_PLAN_PATH)
        || uncertainty
            .pointer("/base_analysis/content_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(audit.analysis_plan_sha256.as_str())
    {
        audit.errors.push(
            "uncertainty base_analysis does not match the current analysis-plan bytes".into(),
        );
    }
    if audit.seed.is_none() {
        audit
            .errors
            .push("uncertainty seed must be an unsigned 64-bit integer".into());
    }
    if !plan
        .get("willingness_to_pay")
        .and_then(serde_json::Value::as_f64)
        .is_some_and(|value| value.is_finite() && value > 0.0)
    {
        audit.errors.push(
            "a positive willingness_to_pay is required for cost-effectiveness probability".into(),
        );
    }

    let mappings = plan
        .get("input_provenance")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|mapping| Some((mapping.get("path")?.as_str()?, mapping)))
        .collect::<HashMap<_, _>>();
    let dsa_paths =
        string_set(plan.pointer("/methodology/uncertainty_analysis/deterministic/input_paths"));
    let psa_paths =
        string_set(plan.pointer("/methodology/uncertainty_analysis/probabilistic/input_paths"));
    let parameters = uncertainty
        .get("parameters")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    audit.parameter_count = parameters.len();
    if parameters.is_empty() || parameters.len() > MAX_PARAMETERS {
        audit.errors.push(format!(
            "uncertainty parameters must contain from 1 to {MAX_PARAMETERS} entries"
        ));
    }
    let mut parameter_ids = HashSet::new();
    let mut targets = HashSet::new();
    for (index, parameter) in parameters.iter().enumerate() {
        let id = parameter
            .get("id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        if id.trim().is_empty() || !parameter_ids.insert(id) {
            audit
                .invalid_parameters
                .push(format!("parameters[{index}].id"));
        }
        if !nonempty(parameter.get("label")) {
            audit
                .invalid_parameters
                .push(format!("parameters[{index}].label"));
        }
        let target = parameter
            .get("target")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let Some(base) = plan.pointer(target) else {
            audit.invalid_parameters.push(id.into());
            audit
                .errors
                .push(format!("parameter {id} target does not exist"));
            continue;
        };
        if !parameter_target_allowed(target) || !targets.insert(target) {
            audit.invalid_parameters.push(id.into());
            audit.errors.push(format!(
                "parameter {id} target is not unique and allowlisted"
            ));
        }
        let provenance_path = parameter
            .get("provenance_path")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let Some(mapping) = mappings.get(provenance_path).copied() else {
            audit.invalid_parameters.push(id.into());
            audit
                .errors
                .push(format!("parameter {id} has no input-provenance mapping"));
            continue;
        };
        if mapping
            .get("uncertainty_status")
            .and_then(serde_json::Value::as_str)
            != Some("distribution_available")
            || !dsa_paths
                .as_ref()
                .is_some_and(|paths| paths.contains(provenance_path))
            || !psa_paths
                .as_ref()
                .is_some_and(|paths| paths.contains(provenance_path))
        {
            audit.invalid_parameters.push(id.into());
            audit.errors.push(format!(
                "parameter {id} must use a distribution_available path listed for DSA and PSA"
            ));
        }
        let deterministic = parameter
            .get("deterministic")
            .and_then(serde_json::Value::as_object);
        if !nonempty(deterministic.and_then(|value| value.get("rationale"))) {
            audit.errors.push(format!(
                "parameter {id} deterministic rationale is required"
            ));
        }
        let low = deterministic.and_then(|value| value.get("low"));
        let high = deterministic.and_then(|value| value.get("high"));
        let bounds_valid = match (base, low, high) {
            (serde_json::Value::Array(values), Some(low), Some(high)) => {
                valid_simplex(low, values.len()) && valid_simplex(high, values.len())
            }
            (_, Some(low), Some(high)) => finite_number(Some(base))
                .zip(finite_number(Some(low)))
                .zip(finite_number(Some(high)))
                .is_some_and(|((base, low), high)| low < high && low <= base && base <= high),
            _ => false,
        };
        if !bounds_valid {
            audit
                .errors
                .push(format!("parameter {id} deterministic bounds are invalid"));
        }
        let mut allowed_basis = string_set(mapping.get("source_ids")).unwrap_or_default();
        allowed_basis.extend(string_set(mapping.get("assumption_ids")).unwrap_or_default());
        validate_distribution(
            id,
            parameter
                .get("probabilistic")
                .unwrap_or(&serde_json::Value::Null),
            base,
            &allowed_basis,
            &mut audit.errors,
        );
    }
    audit.invalid_parameters.sort();
    audit.invalid_parameters.dedup();

    let probabilistic = uncertainty
        .get("probabilistic_analysis")
        .and_then(serde_json::Value::as_object);
    audit.iterations = probabilistic
        .and_then(|value| value.get("iterations"))
        .and_then(serde_json::Value::as_u64);
    if !audit
        .iterations
        .is_some_and(|iterations| (1_000..=10_000).contains(&iterations))
        || plan
            .pointer("/methodology/uncertainty_analysis/probabilistic/iterations")
            .and_then(serde_json::Value::as_u64)
            != audit.iterations
    {
        audit
            .errors
            .push("PSA iterations must be 1000-10000 and match the analysis plan".into());
    }
    let checkpoints = probabilistic
        .and_then(|value| value.get("convergence"))
        .and_then(serde_json::Value::as_object)
        .and_then(|value| value.get("checkpoints"))
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(serde_json::Value::as_u64)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let mut sorted = checkpoints.clone();
    sorted.sort_unstable();
    sorted.dedup();
    if checkpoints.len() < 2
        || sorted != checkpoints
        || checkpoints.last().copied() != audit.iterations
        || checkpoints.first().is_some_and(|value| *value < 100)
    {
        audit.errors.push(
            "convergence checkpoints must be unique, increasing, and end at iterations".into(),
        );
    }
    for field in ["max_probability_mcse", "max_probability_drift"] {
        let valid = probabilistic
            .and_then(|value| value.get("convergence"))
            .and_then(serde_json::Value::as_object)
            .and_then(|value| value.get(field))
            .and_then(serde_json::Value::as_f64)
            .is_some_and(|value| value.is_finite() && value > 0.0 && value <= 0.1);
        if !valid {
            audit.errors.push(format!(
                "convergence {field} must be greater than 0 and no more than 0.1"
            ));
        }
    }
    let correlation = probabilistic
        .and_then(|value| value.get("correlation_handling"))
        .and_then(serde_json::Value::as_object);
    if !nonempty(correlation.and_then(|value| value.get("independence_rationale"))) {
        audit
            .errors
            .push("correlation independence_rationale is required".into());
    }
    if correlation
        .and_then(|value| value.get("known_omitted_correlations"))
        .and_then(serde_json::Value::as_array)
        != Some(&Vec::new())
    {
        audit
            .errors
            .push("known omitted correlations must be resolved before review".into());
    }
    let omitted = probabilistic
        .and_then(|value| value.get("omitted_parameters"))
        .and_then(serde_json::Value::as_array);
    audit.omitted_parameter_count = omitted.map(Vec::len).unwrap_or_default();
    if omitted.is_none_or(|items| {
        items
            .iter()
            .any(|item| !nonempty(item.get("provenance_path")) || !nonempty(item.get("rationale")))
    }) {
        audit
            .errors
            .push("omitted_parameters must contain provenance_path and rationale".into());
    }

    let scenarios = uncertainty
        .get("structural_scenarios")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    audit.scenario_count = scenarios.len();
    if scenarios.is_empty() || scenarios.len() > MAX_SCENARIOS {
        audit.errors.push(format!(
            "structural_scenarios must contain from 1 to {MAX_SCENARIOS} entries"
        ));
    }
    let mut scenario_ids = HashSet::new();
    for (index, scenario) in scenarios.iter().enumerate() {
        let id = scenario
            .get("id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        if id.trim().is_empty() || !scenario_ids.insert(id) {
            audit
                .errors
                .push(format!("structural_scenarios[{index}].id must be unique"));
        }
        if !nonempty(scenario.get("label")) || !nonempty(scenario.get("rationale")) {
            audit.errors.push(format!(
                "structural scenario {id} needs label and rationale"
            ));
        }
        let replacements = scenario
            .get("replacements")
            .and_then(serde_json::Value::as_array)
            .map(Vec::as_slice)
            .unwrap_or(&[]);
        if replacements.is_empty() {
            audit
                .errors
                .push(format!("structural scenario {id} needs replacements"));
        }
        let mut replacement_targets = HashSet::new();
        for replacement in replacements {
            let target = replacement
                .get("target")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            let compatible = plan.pointer(target).is_some_and(|base| {
                replacement
                    .get("value")
                    .is_some_and(|value| replacement_compatible(target, base, value))
            });
            if !compatible || !replacement_targets.insert(target) {
                audit.errors.push(format!(
                    "structural scenario {id} has an invalid or duplicate replacement"
                ));
            }
        }
    }
    let planned_scenarios =
        string_set(plan.pointer("/methodology/uncertainty_analysis/structural_scenarios"));
    if planned_scenarios.as_ref() != Some(&scenario_ids) {
        audit
            .errors
            .push("analysis-plan structural scenarios do not match the uncertainty plan".into());
    }
    audit.complete = audit.errors.is_empty() && audit.invalid_parameters.is_empty();
    if audit.complete {
        audit.status = "complete";
    }
    audit
}

pub fn audit_uncertainty_plan_for_plan(
    workspace: &Path,
    plan_raw: &[u8],
) -> Result<UncertaintyAudit, String> {
    let plan: serde_json::Value = serde_json::from_slice(plan_raw)
        .map_err(|error| format!("uncertainty plan audit failed: {error}"))?;
    let uncertainty_raw = match read_workspace_capped(workspace, UNCERTAINTY_PLAN_PATH) {
        Ok(raw) => raw,
        Err(error) => {
            let mut audit = empty_audit(plan_raw);
            audit.errors.push(error);
            return Ok(audit);
        }
    };
    let uncertainty: serde_json::Value = serde_json::from_slice(&uncertainty_raw)
        .map_err(|error| format!("uncertainty plan is invalid: {error}"))?;
    Ok(audit_values(
        &plan,
        plan_raw,
        &uncertainty,
        &uncertainty_raw,
    ))
}

pub fn require_uncertainty_plan_approvable(
    workspace: &Path,
    plan_raw: &[u8],
) -> Result<UncertaintyAudit, String> {
    let audit = audit_uncertainty_plan_for_plan(workspace, plan_raw)?;
    if !audit.complete {
        return Err(format!(
            "uncertainty audit is incomplete: {} parameters, {} scenarios, {} invalid parameters, {} errors",
            audit.parameter_count,
            audit.scenario_count,
            audit.invalid_parameters.len(),
            audit.errors.len()
        ));
    }
    Ok(audit)
}

#[tauri::command(async)]
pub fn audit_heor_uncertainty(app: AppHandle) -> Result<UncertaintyAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    let plan_raw = read_workspace_capped(&workspace, ANALYSIS_PLAN_PATH)?;
    audit_uncertainty_plan_for_plan(&workspace, &plan_raw)
}

fn capped_stderr(bytes: &[u8]) -> String {
    String::from_utf8_lossy(&bytes[..bytes.len().min(4_000)])
        .trim()
        .to_string()
}

#[tauri::command(async)]
pub fn run_heor_uncertainty(
    app: AppHandle,
    approval_state: tauri::State<crate::heor_approval::HeorApprovalState>,
    project_id: String,
) -> Result<UncertaintyRunResult, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("HEOR projectId does not match the current project".into());
    }
    let plan_path = workspace.join(ANALYSIS_PLAN_PATH);
    let plan_raw = read_workspace_capped(&workspace, ANALYSIS_PLAN_PATH)?;
    let evidence_audit = crate::heor_evidence::audit_plan_bytes(&plan_raw)?;
    let uncertainty_audit = require_uncertainty_plan_approvable(&workspace, &plan_raw)?;
    let uncertainty_path = workspace.join(UNCERTAINTY_PLAN_PATH);

    let package_src = app
        .path()
        .resolve("heor-core/src", BaseDirectory::Resource)
        .map_err(|error| format!("bundled HEOR engine unavailable: {error}"))?;
    if !package_src.join("heor_core").is_dir() {
        return Err("bundled HEOR engine source is missing".into());
    }
    let (python, _) = crate::kernel::python_bin(&app)?;
    let output = crate::runtime::quiet_command(python)
        .args(["-m", "heor_core"])
        .arg(&plan_path)
        .arg("--uncertainty-plan")
        .arg(&uncertainty_path)
        .current_dir(&workspace)
        .env("PYTHONPATH", &package_src)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONNOUSERSITE", "1")
        .output()
        .map_err(|error| format!("HEOR uncertainty engine failed to start: {error}"))?;
    if !output.status.success() {
        let message = capped_stderr(&output.stderr);
        return Err(if message.is_empty() {
            format!("HEOR uncertainty engine exited with {}", output.status)
        } else {
            message
        });
    }
    if output.stdout.len() > OUTPUT_CAP_BYTES {
        return Err(format!(
            "HEOR uncertainty output exceeds the {} MB limit",
            OUTPUT_CAP_BYTES / 1024 / 1024
        ));
    }
    let calculation: serde_json::Value = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("HEOR uncertainty engine returned invalid JSON: {error}"))?;
    if calculation
        .get("base_analysis_sha256")
        .and_then(serde_json::Value::as_str)
        != Some(uncertainty_audit.analysis_plan_sha256.as_str())
        || calculation
            .get("uncertainty_plan_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(uncertainty_audit.uncertainty_sha256.as_str())
    {
        return Err("HEOR uncertainty engine hashes do not match desktop-audited inputs".into());
    }
    crate::heor_reporting::write_result(
        &workspace,
        crate::heor_reporting::UNCERTAINTY_RESULT_PATH,
        &output.stdout,
    )?;

    let plan: serde_json::Value = serde_json::from_slice(&plan_raw)
        .map_err(|error| format!("analysis plan is invalid: {error}"))?;
    let reference_case_id = plan
        .pointer("/reference_case/id")
        .and_then(serde_json::Value::as_str)
        .ok_or("analysis plan omitted reference-case id")?;
    let claimed_reference_case_status = plan
        .pointer("/reference_case/status")
        .and_then(serde_json::Value::as_str)
        .ok_or("analysis plan omitted reference-case status")?;
    let reference_case_status = crate::heor_engine::registered_reference_case_status(
        &app,
        reference_case_id,
        claimed_reference_case_status,
    )?;
    let reference_case_audit =
        crate::heor_reference_case::audit_reference_case_for_plan(&app, &workspace, &plan_raw)?;
    let budget_impact_audit =
        crate::heor_budget_impact::audit_budget_impact_for_plan(&workspace, &plan_raw)?;
    let validation_audit =
        crate::heor_validation::audit_model_validation_for_plan(&workspace, &plan_raw)?;
    let reporting_audit = crate::heor_reporting::audit_report_package(&workspace)?;

    // Read the approval state last: a revocation or artifact change made while
    // the deterministic child runs must affect the returned classification.
    let approval_log = {
        let _guard = approval_state
            .0
            .lock()
            .map_err(|_| "HEOR approval lock poisoned")?;
        crate::heor_approval::verified_log(&app, &project_id)?
    };
    let conceptual_model_matches_artifact =
        crate::heor_engine::conceptual_model_matches_approval(&workspace, &approval_log);
    let workflow = crate::heor_engine::workflow_status(
        approval_log,
        uncertainty_audit.analysis_plan_sha256.clone(),
        conceptual_model_matches_artifact,
        &reference_case_status,
        crate::heor_engine::HeorWorkflowAudits {
            evidence: evidence_audit,
            reference_case: reference_case_audit,
            uncertainty: uncertainty_audit,
            budget_impact: budget_impact_audit,
            validation: validation_audit,
            reporting: reporting_audit,
        },
    );
    Ok(UncertaintyRunResult {
        workflow,
        calculation,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn plan() -> serde_json::Value {
        serde_json::json!({
            "analysis_id": "analysis-1",
            "willingness_to_pay": 100000,
            "cycles": 3,
            "cycle_length_years": 1.0,
            "discount_rates": {"costs": 0.05, "outcomes": 0.05},
            "half_cycle_correction": true,
            "uncertainty_analysis": {"path": UNCERTAINTY_PLAN_PATH},
            "strategies": {
                "comparator": {
                    "state_costs": [1000, 2000], "state_utilities": [0.8, 0.0],
                    "transition_matrix": [[0.9, 0.1], [0.0, 1.0]]
                },
                "intervention": {
                    "state_costs": [4000, 2000], "state_utilities": [0.8, 0.0],
                    "transition_matrix": [[0.95, 0.05], [0.0, 1.0]]
                }
            },
            "input_provenance": [{
                "path": "strategies.intervention.state_costs",
                "source_ids": ["source-1"], "assumption_ids": [],
                "uncertainty_status": "distribution_available"
            }],
            "methodology": {"uncertainty_analysis": {
                "deterministic": {"planned": true, "input_paths": ["strategies.intervention.state_costs"]},
                "probabilistic": {"planned": true, "input_paths": ["strategies.intervention.state_costs"], "iterations": 1000},
                "structural_scenarios": ["long-horizon"]
            }}
        })
    }

    fn uncertainty(plan_raw: &[u8]) -> serde_json::Value {
        serde_json::json!({
            "schema_version": "0.1.0",
            "uncertainty_id": "uncertainty-1",
            "analysis_id": "analysis-1",
            "status": "ready_for_human_review",
            "base_analysis": {"path": ANALYSIS_PLAN_PATH, "content_sha256": sha256(plan_raw)},
            "seed": 42,
            "parameters": [{
                "id": "cost", "label": "Cost",
                "target": "/strategies/intervention/state_costs/0",
                "provenance_path": "strategies.intervention.state_costs",
                "deterministic": {"low": 3000, "high": 5000, "rationale": "Evidence interval"},
                "probabilistic": {
                    "type": "gamma", "shape": 100, "scale": 40,
                    "basis_ids": ["source-1"], "rationale": "Positive cost"
                }
            }],
            "probabilistic_analysis": {
                "iterations": 1000,
                "convergence": {"checkpoints": [500, 1000], "max_probability_mcse": 0.02, "max_probability_drift": 0.02},
                "correlation_handling": {"independence_rationale": "One sampled scalar", "known_omitted_correlations": []},
                "omitted_parameters": []
            },
            "structural_scenarios": [{
                "id": "long-horizon", "label": "Long horizon", "rationale": "Structural test",
                "replacements": [{"target": "/cycles", "value": 5}]
            }]
        })
    }

    #[test]
    fn complete_uncertainty_plan_is_machine_reviewable() {
        let plan = plan();
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let uncertainty = uncertainty(&plan_raw);
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(audit.complete, "{:?}", audit.errors);
        assert_eq!(audit.parameter_count, 1);
        assert_eq!(audit.scenario_count, 1);
    }

    #[test]
    fn changed_hash_and_unlinked_basis_fail_closed() {
        let plan = plan();
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let mut uncertainty = uncertainty(&plan_raw);
        uncertainty["base_analysis"]["content_sha256"] = serde_json::json!("0".repeat(64));
        uncertainty["parameters"][0]["probabilistic"]["basis_ids"] =
            serde_json::json!(["missing-source"]);
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("base_analysis")));
        assert!(audit.errors.iter().any(|error| error.contains("basis_ids")));
    }

    #[test]
    fn authority_and_unknown_targets_are_outside_the_allowlist() {
        assert!(!parameter_target_allowed("/reference_case/status"));
        assert!(!scenario_target_allowed("/analysis_id"));
        assert!(parameter_target_allowed(
            "/strategies/intervention/transition_matrix/0"
        ));
    }

    #[cfg(unix)]
    #[test]
    fn workspace_artifacts_cannot_escape_through_a_symlink() {
        use std::os::unix::fs::symlink;

        let root =
            std::env::temp_dir().join(format!("heor-uncertainty-symlink-{}", std::process::id()));
        let outside =
            std::env::temp_dir().join(format!("heor-uncertainty-outside-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_file(&outside);
        std::fs::create_dir_all(root.join("heor")).unwrap();
        std::fs::write(&outside, b"{}").unwrap();
        symlink(&outside, root.join(UNCERTAINTY_PLAN_PATH)).unwrap();

        assert!(read_workspace_capped(&root, UNCERTAINTY_PLAN_PATH)
            .unwrap_err()
            .contains("inside the current workspace"));
        let _ = std::fs::remove_dir_all(root);
        let _ = std::fs::remove_file(outside);
    }
}
