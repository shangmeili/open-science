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
const MAX_CORRELATION_GROUPS: usize = 64;
const MAX_CORRELATION_GROUP_SIZE: usize = 32;
const MAX_SCENARIOS: usize = 64;
const MAX_DECISION_THRESHOLDS: usize = 101;

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
    pub correlation_group_count: usize,
    pub scenario_count: usize,
    pub iterations: Option<u64>,
    pub primary_threshold: Option<f64>,
    pub threshold_count: usize,
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

fn safe_strategy_id(value: &str) -> bool {
    let mut bytes = value.bytes();
    bytes.next().is_some_and(|byte| byte.is_ascii_lowercase())
        && value.len() <= 64
        && bytes.all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'_' | b'-')
        })
}

fn strategy_ids(plan: &serde_json::Value) -> HashSet<&str> {
    if matches!(
        plan.get("schema_version")
            .and_then(serde_json::Value::as_str),
        Some("0.8.0" | "0.9.0")
    ) {
        return plan
            .get("strategy_order")
            .and_then(serde_json::Value::as_array)
            .and_then(|items| {
                items
                    .iter()
                    .map(serde_json::Value::as_str)
                    .collect::<Option<HashSet<_>>>()
            })
            .unwrap_or_default();
    }
    HashSet::from(["comparator", "intervention"])
}

fn parameter_target_allowed(target: &str, strategy_ids: &HashSet<&str>) -> bool {
    let parts = target.split('/').collect::<Vec<_>>();
    matches!(
        parts.as_slice(),
        ["", "strategies", strategy_id, "state_costs" | "state_utilities", index]
            if safe_strategy_id(strategy_id)
                && strategy_ids.contains(strategy_id)
                && index.parse::<usize>().is_ok()
    ) || matches!(
        parts.as_slice(),
        ["", "strategies", strategy_id, "transition_matrix", row]
            if safe_strategy_id(strategy_id)
                && strategy_ids.contains(strategy_id)
                && row.parse::<usize>().is_ok()
    ) || matches!(
        parts.as_slice(),
        ["", "strategies", strategy_id, "transition_schedule", phase, "matrix", row]
            if safe_strategy_id(strategy_id)
                && strategy_ids.contains(strategy_id)
                && phase.parse::<usize>().is_ok()
                && row.parse::<usize>().is_ok()
    )
}

fn rate_target_indices(target: &str) -> Option<(usize, usize, usize, usize)> {
    let parts = target.split('/').collect::<Vec<_>>();
    match parts.as_slice() {
        ["", "input_provenance", mapping, "derivation", "transformation", "phases", phase, "rows", row, "events", event, "rate_per_year"] => {
            Some((
                mapping.parse().ok()?,
                phase.parse().ok()?,
                row.parse().ok()?,
                event.parse().ok()?,
            ))
        }
        _ => None,
    }
}

fn survival_target_indices(target: &str) -> Option<(usize, &str)> {
    let parts = target.split('/').collect::<Vec<_>>();
    match parts.as_slice() {
        ["", "input_provenance", mapping, "derivation", "transformation", "parameters", parameter @ ("rate_per_year" | "shape" | "scale_years"), "value"] => {
            Some((mapping.parse().ok()?, parameter))
        }
        _ => None,
    }
}

fn probability_target_indices(target: &str) -> Option<(usize, usize, usize)> {
    let parts = target.split('/').collect::<Vec<_>>();
    match parts.as_slice() {
        ["", "input_provenance", mapping, "derivation", "transformation", "phases", phase, "rows", row, "event", "source_probability"] => {
            Some((
                mapping.parse().ok()?,
                phase.parse().ok()?,
                row.parse().ok()?,
            ))
        }
        _ => None,
    }
}

fn background_excess_target_index(target: &str) -> Option<usize> {
    let parts = target.split('/').collect::<Vec<_>>();
    match parts.as_slice() {
        ["", "input_provenance", mapping, "derivation", "transformation", "excess_mortality_rate_per_year", "value"] => {
            mapping.parse().ok()
        }
        _ => None,
    }
}

fn scenario_target_allowed(target: &str, strategy_ids: &HashSet<&str>) -> bool {
    let parts = target.split('/').collect::<Vec<_>>();
    parameter_target_allowed(target, strategy_ids)
        || matches!(
            parts.as_slice(),
            ["", "strategies", strategy_id, "transition_schedule", phase, "start_cycle"]
                if safe_strategy_id(strategy_id)
                    && strategy_ids.contains(strategy_id)
                    && phase.parse::<usize>().is_ok()
        )
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
    strategy_ids: &HashSet<&str>,
    background_mortality_schema: bool,
) -> bool {
    let background_safe = parameter_target_allowed(target, strategy_ids)
        && matches!(
            target.split('/').collect::<Vec<_>>().as_slice(),
            ["", "strategies", _, "state_costs" | "state_utilities", _]
        )
        || matches!(
            target,
            "/discount_rates/costs" | "/discount_rates/outcomes" | "/half_cycle_correction"
        );
    if (background_mortality_schema && !background_safe)
        || (!background_mortality_schema && !scenario_target_allowed(target, strategy_ids))
    {
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
        correlation_group_count: 0,
        scenario_count: 0,
        iterations: None,
        primary_threshold: None,
        threshold_count: 0,
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
    exact_basis: Option<&str>,
    bounded_probability: bool,
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
    let basis_valid = exact_basis.map_or_else(
        || !basis_ids.is_empty() && basis_ids.is_subset(allowed_basis),
        |expected| basis_ids.len() == 1 && basis_ids.contains(expected),
    );
    if !basis_valid {
        errors.push(format!(
            "parameter {parameter_id} basis_ids are not linked by input provenance"
        ));
    }
    let kind = distribution
        .get("type")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let positive_distribution = exact_basis.is_some() && !bounded_probability;
    let valid = match kind {
        "beta" => {
            !positive_distribution
                && !base.is_array()
                && positive_number(distribution.get("alpha"))
                && positive_number(distribution.get("beta"))
        }
        "gamma" => {
            !bounded_probability
                && !base.is_array()
                && positive_number(distribution.get("shape"))
                && positive_number(distribution.get("scale"))
        }
        "lognormal" => {
            !bounded_probability
                && !base.is_array()
                && finite_number(distribution.get("mu_log")).is_some()
                && positive_number(distribution.get("sigma_log"))
        }
        "uniform" => {
            !base.is_array()
                && finite_number(distribution.get("low"))
                    .zip(finite_number(distribution.get("high")))
                    .is_some_and(|(low, high)| {
                        low < high
                            && (!positive_distribution || low > 0.0)
                            && (!bounded_probability || (low > 0.0 && high < 1.0))
                    })
        }
        "dirichlet" => {
            let expected = base.as_array().map(Vec::len).unwrap_or_default();
            !positive_distribution
                && !bounded_probability
                && distribution
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

fn correlation_matrix_error(value: &serde_json::Value, size: usize) -> Option<&'static str> {
    let Some(matrix) = value.as_array() else {
        return Some("must be a finite square matrix matching parameter_ids");
    };
    if matrix.len() != size
        || matrix.iter().any(|row| {
            row.as_array().is_none_or(|values| {
                values.len() != size
                    || values
                        .iter()
                        .any(|item| finite_number(Some(item)).is_none())
            })
        })
    {
        return Some("must be a finite square matrix matching parameter_ids");
    }
    let number =
        |row: usize, column: usize| matrix[row].as_array().unwrap()[column].as_f64().unwrap();
    for row in 0..size {
        if (number(row, row) - 1.0).abs() > 1e-12 {
            return Some("diagonal must equal 1");
        }
        for column in 0..row {
            if !(-1.0..1.0).contains(&number(row, column)) {
                return Some("off-diagonal correlations must be strictly between -1 and 1");
            }
            if (number(row, column) - number(column, row)).abs() > 1e-12 {
                return Some("must be symmetric");
            }
        }
    }
    let mut lower = vec![vec![0.0; size]; size];
    for row in 0..size {
        for column in 0..=row {
            let remainder = number(row, column)
                - (0..column)
                    .map(|item| lower[row][item] * lower[column][item])
                    .sum::<f64>();
            if row == column {
                if remainder <= 1e-12 {
                    return Some("must be strictly positive definite");
                }
                lower[row][column] = remainder.sqrt();
            } else {
                lower[row][column] = remainder / lower[column][column];
            }
        }
    }
    None
}

fn validate_correlation_groups(
    schema_version: Option<&str>,
    correlation: Option<&serde_json::Map<String, serde_json::Value>>,
    parameters: &[serde_json::Value],
    errors: &mut Vec<String>,
) -> usize {
    if !matches!(
        schema_version,
        Some("0.4.0" | "0.5.0" | "0.6.0" | "0.7.0" | "0.8.0")
    ) {
        if correlation.is_some_and(|value| value.contains_key("groups")) {
            errors.push(
                "correlation groups require uncertainty schema_version 0.4.0 through 0.8.0".into(),
            );
        }
        return 0;
    }
    let groups = correlation
        .and_then(|value| value.get("groups"))
        .and_then(serde_json::Value::as_array);
    let Some(groups) = groups else {
        errors.push(
            "correlation groups must be an array for schema_version 0.4.0 through 0.8.0".into(),
        );
        return 0;
    };
    if groups.len() > MAX_CORRELATION_GROUPS {
        errors.push(format!(
            "correlation groups must contain no more than {MAX_CORRELATION_GROUPS} entries"
        ));
    }
    let by_id = parameters
        .iter()
        .filter_map(|parameter| Some((parameter.get("id")?.as_str()?, parameter)))
        .collect::<HashMap<_, _>>();
    let mut group_ids = HashSet::new();
    let mut grouped_parameters = HashSet::new();
    for (index, group) in groups.iter().enumerate() {
        let label = format!("correlation groups[{index}]");
        let Some(group) = group.as_object() else {
            errors.push(format!("{label} must be an object"));
            continue;
        };
        let unknown = group
            .keys()
            .filter(|key| {
                !matches!(
                    key.as_str(),
                    "id" | "parameter_ids"
                        | "scale"
                        | "method"
                        | "correlation_matrix"
                        | "basis_ids"
                        | "rationale"
                )
            })
            .cloned()
            .collect::<Vec<_>>();
        if !unknown.is_empty() {
            errors.push(format!(
                "{label} contains unsupported fields: {}",
                unknown.join(", ")
            ));
        }
        let identifier = group
            .get("id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        if identifier.trim().is_empty() || !group_ids.insert(identifier) {
            errors.push(format!("{label} id must be non-empty and unique"));
        }
        let Some(parameter_ids) = string_set(group.get("parameter_ids")) else {
            errors.push(format!(
                "{label} parameter_ids must contain 2-{MAX_CORRELATION_GROUP_SIZE} unique ids"
            ));
            continue;
        };
        if !(2..=MAX_CORRELATION_GROUP_SIZE).contains(&parameter_ids.len()) {
            errors.push(format!(
                "{label} parameter_ids must contain 2-{MAX_CORRELATION_GROUP_SIZE} unique ids"
            ));
        }
        if parameter_ids.iter().any(|item| !by_id.contains_key(item)) {
            errors.push(format!("{label} references an unknown parameter id"));
        }
        if parameter_ids
            .iter()
            .any(|item| !grouped_parameters.insert(*item))
        {
            errors.push("an uncertainty parameter may belong to only one correlation group".into());
        }
        if parameter_ids.iter().any(|item| {
            by_id
                .get(item)
                .and_then(|parameter| parameter.pointer("/probabilistic/type"))
                .and_then(serde_json::Value::as_str)
                != Some("lognormal")
        }) {
            errors.push(format!(
                "{label} supports only scalar lognormal parameter members"
            ));
        }
        if group.get("scale").and_then(serde_json::Value::as_str) != Some("log_standard_normal")
            || group.get("method").and_then(serde_json::Value::as_str) != Some("cholesky")
        {
            errors.push(format!(
                "{label} requires log_standard_normal scale and cholesky method"
            ));
        }
        if let Some(message) = group
            .get("correlation_matrix")
            .and_then(|value| correlation_matrix_error(value, parameter_ids.len()))
            .or_else(|| {
                group
                    .get("correlation_matrix")
                    .is_none()
                    .then_some("must be a finite square matrix matching parameter_ids")
            })
        {
            errors.push(format!("{label} correlation_matrix {message}"));
        }
        let Some(basis_ids) = string_set(group.get("basis_ids")) else {
            errors.push(format!("{label} basis_ids must be non-empty and unique"));
            continue;
        };
        if basis_ids.is_empty() {
            errors.push(format!("{label} basis_ids must be non-empty and unique"));
        } else {
            let linked_by_every_member = parameter_ids.iter().all(|item| {
                let member_basis = by_id
                    .get(item)
                    .and_then(|parameter| parameter.pointer("/probabilistic/basis_ids"))
                    .and_then(serde_json::Value::as_array)
                    .into_iter()
                    .flatten()
                    .filter_map(serde_json::Value::as_str)
                    .collect::<HashSet<_>>();
                basis_ids.is_subset(&member_basis)
            });
            if !linked_by_every_member {
                errors.push(format!(
                    "{label} basis_ids must be linked by every member parameter distribution"
                ));
            }
        }
        if !nonempty(group.get("rationale")) {
            errors.push(format!("{label} rationale is required"));
        }
    }
    groups.len()
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

    let schema_version = uncertainty
        .get("schema_version")
        .and_then(serde_json::Value::as_str);
    if !matches!(
        schema_version,
        Some("0.1.0" | "0.2.0" | "0.3.0" | "0.4.0" | "0.5.0" | "0.6.0" | "0.7.0" | "0.8.0")
    ) {
        audit
            .errors
            .push("uncertainty schema_version must be 0.1.0 through 0.8.0".into());
    }
    let analysis_schema = plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str);
    if (analysis_schema == Some("0.8.0")) != (schema_version == Some("0.7.0"))
        || (analysis_schema == Some("0.9.0")) != (schema_version == Some("0.8.0"))
    {
        audit.errors.push(
            "analysis schema_version 0.8.0/0.9.0 must pair with uncertainty schema_version 0.7.0/0.8.0 respectively".into(),
        );
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
    audit.primary_threshold = plan
        .get("willingness_to_pay")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0);
    if audit.primary_threshold.is_none() {
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
    let allowed_strategy_ids = strategy_ids(plan);
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
        let rate_indices = rate_target_indices(target);
        let survival_indices = survival_target_indices(target);
        let probability_indices = probability_target_indices(target);
        let background_index = background_excess_target_index(target);
        let Some(base) = plan.pointer(target) else {
            audit.invalid_parameters.push(id.into());
            audit
                .errors
                .push(format!("parameter {id} target does not exist"));
            continue;
        };
        let target_allowed = if schema_version == Some("0.8.0") {
            background_index.is_some()
        } else {
            parameter_target_allowed(target, &allowed_strategy_ids)
                || (matches!(
                    schema_version,
                    Some("0.3.0" | "0.4.0" | "0.5.0" | "0.6.0" | "0.7.0")
                ) && rate_indices.is_some())
                || (matches!(schema_version, Some("0.5.0" | "0.6.0" | "0.7.0"))
                    && survival_indices.is_some())
                || (matches!(schema_version, Some("0.6.0" | "0.7.0"))
                    && probability_indices.is_some())
        };
        if !target_allowed || !targets.insert(target) {
            audit.invalid_parameters.push(id.into());
            audit.errors.push(format!(
                "parameter {id} target is not unique and allowlisted"
            ));
        }
        let provenance_path = parameter
            .get("provenance_path")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let Some(mut mapping) = mappings.get(provenance_path).copied() else {
            audit.invalid_parameters.push(id.into());
            audit
                .errors
                .push(format!("parameter {id} has no input-provenance mapping"));
            continue;
        };
        let mut rate_basis = None;
        if let Some((mapping_index, phase, row, event)) = rate_indices {
            let indexed_mapping = plan.pointer(&format!("/input_provenance/{mapping_index}"));
            if !matches!(
                schema_version,
                Some("0.3.0" | "0.4.0" | "0.5.0" | "0.6.0" | "0.7.0" | "0.8.0")
            ) || !matches!(
                plan.get("schema_version")
                    .and_then(serde_json::Value::as_str),
                Some("0.5.0" | "0.8.0" | "0.9.0")
            ) || indexed_mapping
                .and_then(|value| value.get("path"))
                .and_then(serde_json::Value::as_str)
                != Some(provenance_path)
                || indexed_mapping
                    .and_then(|value| value.pointer("/derivation/method"))
                    .and_then(serde_json::Value::as_str)
                    != Some("deterministic_transformation")
                || indexed_mapping
                    .and_then(|value| value.pointer("/derivation/transformation/operation"))
                    .and_then(serde_json::Value::as_str)
                    != Some("constant_competing_rates")
            {
                audit.invalid_parameters.push(id.into());
                audit.errors.push(format!(
                    "parameter {id} must bind an admitted constant competing-rate transformation"
                ));
            } else if let Some(indexed_mapping) = indexed_mapping {
                mapping = indexed_mapping;
            }
            let event_value = mapping.pointer(&format!(
                "/derivation/transformation/phases/{phase}/rows/{row}/events/{event}"
            ));
            rate_basis = event_value.and_then(|value| {
                value
                    .get("source_extraction_id")
                    .and_then(serde_json::Value::as_str)
                    .or_else(|| {
                        value
                            .get("assumption_id")
                            .and_then(serde_json::Value::as_str)
                    })
            });
            if rate_basis.is_none() {
                audit.invalid_parameters.push(id.into());
                audit.errors.push(format!(
                    "parameter {id} event rate has no exact extraction or assumption basis"
                ));
            }
        } else if let Some((mapping_index, parameter_name)) = survival_indices {
            let indexed_mapping = plan.pointer(&format!("/input_provenance/{mapping_index}"));
            let transformation =
                indexed_mapping.and_then(|value| value.pointer("/derivation/transformation"));
            let expected_parameter = match transformation
                .and_then(|value| value.get("distribution"))
                .and_then(serde_json::Value::as_str)
            {
                Some("exponential") => parameter_name == "rate_per_year",
                Some("weibull") => matches!(parameter_name, "shape" | "scale_years"),
                _ => false,
            };
            if !matches!(schema_version, Some("0.5.0" | "0.6.0" | "0.7.0" | "0.8.0"))
                || !matches!(
                    plan.get("schema_version")
                        .and_then(serde_json::Value::as_str),
                    Some("0.6.0" | "0.8.0" | "0.9.0")
                )
                || indexed_mapping
                    .and_then(|value| value.get("path"))
                    .and_then(serde_json::Value::as_str)
                    != Some(provenance_path)
                || indexed_mapping
                    .and_then(|value| value.pointer("/derivation/method"))
                    .and_then(serde_json::Value::as_str)
                    != Some("deterministic_transformation")
                || transformation
                    .and_then(|value| value.get("operation"))
                    .and_then(serde_json::Value::as_str)
                    != Some("parametric_survival_to_transition_schedule")
                || !expected_parameter
            {
                audit.invalid_parameters.push(id.into());
                audit.errors.push(format!(
                    "parameter {id} must bind an admitted parametric survival transformation"
                ));
            } else if let Some(indexed_mapping) = indexed_mapping {
                mapping = indexed_mapping;
            }
            let parameter_value = mapping.pointer(&format!(
                "/derivation/transformation/parameters/{parameter_name}"
            ));
            rate_basis = parameter_value.and_then(|value| {
                value
                    .get("source_extraction_id")
                    .and_then(serde_json::Value::as_str)
                    .or_else(|| {
                        value
                            .get("assumption_id")
                            .and_then(serde_json::Value::as_str)
                    })
            });
            if rate_basis.is_none() {
                audit.invalid_parameters.push(id.into());
                audit.errors.push(format!(
                    "parameter {id} survival parameter has no exact extraction or assumption basis"
                ));
            }
        } else if let Some((mapping_index, phase, row)) = probability_indices {
            let indexed_mapping = plan.pointer(&format!("/input_provenance/{mapping_index}"));
            if !matches!(schema_version, Some("0.6.0" | "0.7.0" | "0.8.0"))
                || !matches!(
                    plan.get("schema_version")
                        .and_then(serde_json::Value::as_str),
                    Some("0.7.0" | "0.8.0" | "0.9.0")
                )
                || indexed_mapping
                    .and_then(|value| value.get("path"))
                    .and_then(serde_json::Value::as_str)
                    != Some(provenance_path)
                || indexed_mapping
                    .and_then(|value| value.pointer("/derivation/method"))
                    .and_then(serde_json::Value::as_str)
                    != Some("deterministic_transformation")
                || indexed_mapping
                    .and_then(|value| value.pointer("/derivation/transformation/operation"))
                    .and_then(serde_json::Value::as_str)
                    != Some("single_event_probability_time_conversion")
            {
                audit.invalid_parameters.push(id.into());
                audit.errors.push(format!(
                    "parameter {id} must bind an admitted probability-time transformation"
                ));
            } else if let Some(indexed_mapping) = indexed_mapping {
                mapping = indexed_mapping;
            }
            let event_value = mapping.pointer(&format!(
                "/derivation/transformation/phases/{phase}/rows/{row}/event"
            ));
            rate_basis = event_value.and_then(|value| {
                value
                    .get("source_extraction_id")
                    .and_then(serde_json::Value::as_str)
                    .or_else(|| {
                        value
                            .get("assumption_id")
                            .and_then(serde_json::Value::as_str)
                    })
            });
            if rate_basis.is_none() {
                audit.invalid_parameters.push(id.into());
                audit.errors.push(format!(
                    "parameter {id} source probability has no exact extraction or assumption basis"
                ));
            }
        } else if let Some(mapping_index) = background_index {
            let indexed_mapping = plan.pointer(&format!("/input_provenance/{mapping_index}"));
            if schema_version != Some("0.8.0")
                || analysis_schema != Some("0.9.0")
                || indexed_mapping
                    .and_then(|value| value.get("path"))
                    .and_then(serde_json::Value::as_str)
                    != Some(provenance_path)
                || indexed_mapping
                    .and_then(|value| value.pointer("/derivation/method"))
                    .and_then(serde_json::Value::as_str)
                    != Some("deterministic_transformation")
                || indexed_mapping
                    .and_then(|value| value.pointer("/derivation/transformation/operation"))
                    .and_then(serde_json::Value::as_str)
                    != Some("background_plus_excess_mortality_to_transition_schedule")
            {
                audit.invalid_parameters.push(id.into());
                audit.errors.push(format!(
                    "parameter {id} must bind an admitted background-plus-excess mortality transformation"
                ));
            } else if let Some(indexed_mapping) = indexed_mapping {
                mapping = indexed_mapping;
            }
            let excess =
                mapping.pointer("/derivation/transformation/excess_mortality_rate_per_year");
            rate_basis = excess.and_then(|value| {
                value
                    .get("source_extraction_id")
                    .and_then(serde_json::Value::as_str)
                    .or_else(|| {
                        value
                            .get("assumption_id")
                            .and_then(serde_json::Value::as_str)
                    })
            });
            if rate_basis.is_none() {
                audit.invalid_parameters.push(id.into());
                audit.errors.push(format!(
                    "parameter {id} excess mortality has no exact extraction or assumption basis"
                ));
            }
        } else if mapping
            .pointer("/derivation/method")
            .and_then(serde_json::Value::as_str)
            == Some("deterministic_transformation")
        {
            audit.invalid_parameters.push(id.into());
            audit.errors.push(format!(
                "parameter {id} must vary an admitted transformation parameter, not a derived transition row"
            ));
        }
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
                .is_some_and(|((base, low), high)| {
                    low < high
                        && low <= base
                        && base <= high
                        && (rate_indices.is_none()
                            && survival_indices.is_none()
                            && background_index.is_none()
                            || low > 0.0)
                        && (probability_indices.is_none() || (low > 0.0 && high < 1.0))
                }),
            _ => false,
        };
        if !bounds_valid {
            audit
                .errors
                .push(format!("parameter {id} deterministic bounds are invalid"));
        }
        let mut allowed_basis = string_set(mapping.get("source_ids")).unwrap_or_default();
        allowed_basis.extend(string_set(mapping.get("extraction_ids")).unwrap_or_default());
        allowed_basis.extend(string_set(mapping.get("assumption_ids")).unwrap_or_default());
        validate_distribution(
            id,
            parameter
                .get("probabilistic")
                .unwrap_or(&serde_json::Value::Null),
            base,
            &allowed_basis,
            rate_basis,
            probability_indices.is_some(),
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
    let has_threshold_config = probabilistic
        .and_then(|value| value.get("decision_thresholds"))
        .is_some();
    let threshold_config = probabilistic
        .and_then(|value| value.get("decision_thresholds"))
        .and_then(serde_json::Value::as_object);
    if matches!(
        schema_version,
        Some("0.2.0" | "0.3.0" | "0.4.0" | "0.5.0" | "0.6.0" | "0.7.0" | "0.8.0")
    ) {
        let thresholds = threshold_config
            .and_then(|value| value.get("values"))
            .and_then(serde_json::Value::as_array);
        audit.threshold_count = thresholds.map_or(0, Vec::len);
        let values = thresholds
            .into_iter()
            .flatten()
            .filter_map(serde_json::Value::as_f64)
            .collect::<Vec<_>>();
        let increasing = values
            .windows(2)
            .all(|pair| pair[0].is_finite() && pair[1].is_finite() && pair[0] < pair[1]);
        let valid = audit.threshold_count == values.len()
            && (2..=MAX_DECISION_THRESHOLDS).contains(&values.len())
            && increasing
            && values.first().is_some_and(|value| *value >= 0.0)
            && audit
                .primary_threshold
                .is_some_and(|primary| values.iter().any(|value| (value - primary).abs() <= 1e-9));
        if !valid {
            audit.errors.push(
                "decision thresholds must be 2-101 unique, non-negative, strictly increasing values and include the primary threshold".into(),
            );
        }
        if !nonempty(threshold_config.and_then(|value| value.get("rationale"))) {
            audit
                .errors
                .push("decision thresholds rationale is required".into());
        }
    } else if has_threshold_config {
        audit.errors.push(
            "decision thresholds require uncertainty schema_version 0.2.0 through 0.8.0".into(),
        );
    } else if schema_version == Some("0.1.0") {
        audit.threshold_count = usize::from(audit.primary_threshold.is_some());
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
    audit.correlation_group_count =
        validate_correlation_groups(schema_version, correlation, parameters, &mut audit.errors);
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
                replacement.get("value").is_some_and(|value| {
                    replacement_compatible(
                        target,
                        base,
                        value,
                        &allowed_strategy_ids,
                        schema_version == Some("0.8.0"),
                    )
                })
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
    let evidence_selection = crate::heor_evidence::audit_evidence_selection_for_plan(
        &app,
        &workspace,
        &project_id,
        &plan_raw,
    );

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
            evidence_selection,
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
            "schema_version": "0.2.0",
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
                "decision_thresholds": {
                    "values": [0, 50000, 100000, 150000, 200000],
                    "rationale": "Threshold range for CEAC, CEAF, and per-person EVPI"
                },
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
        assert_eq!(audit.threshold_count, 5);
        assert_eq!(audit.primary_threshold, Some(100000.0));
    }

    #[test]
    fn multi_strategy_uncertainty_uses_dynamic_strategy_paths() {
        let mut plan = plan();
        plan["schema_version"] = serde_json::json!("0.8.0");
        plan["baseline_strategy_id"] = serde_json::json!("standard_care");
        plan["strategy_order"] = serde_json::json!(["standard_care", "treatment_a", "treatment_b"]);
        let comparator = plan["strategies"]
            .as_object_mut()
            .unwrap()
            .remove("comparator")
            .unwrap();
        let intervention = plan["strategies"]
            .as_object_mut()
            .unwrap()
            .remove("intervention")
            .unwrap();
        plan["strategies"]["standard_care"] = comparator;
        plan["strategies"]["treatment_a"] = intervention.clone();
        plan["strategies"]["treatment_b"] = intervention;
        plan["input_provenance"][0]["path"] =
            serde_json::json!("strategies.treatment_a.state_costs");
        plan["methodology"]["uncertainty_analysis"]["deterministic"]["input_paths"] =
            serde_json::json!(["strategies.treatment_a.state_costs"]);
        plan["methodology"]["uncertainty_analysis"]["probabilistic"]["input_paths"] =
            serde_json::json!(["strategies.treatment_a.state_costs"]);
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let mut uncertainty = uncertainty(&plan_raw);
        uncertainty["schema_version"] = serde_json::json!("0.7.0");
        uncertainty["parameters"][0]["target"] =
            serde_json::json!("/strategies/treatment_a/state_costs/0");
        uncertainty["parameters"][0]["provenance_path"] =
            serde_json::json!("strategies.treatment_a.state_costs");
        uncertainty["probabilistic_analysis"]["correlation_handling"]["groups"] =
            serde_json::json!([]);
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();

        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);

        assert!(audit.complete, "{:?}", audit.errors);
        assert_eq!(audit.parameter_count, 1);
    }

    #[test]
    fn schema_08_varies_only_the_exact_positive_excess_mortality_value() {
        let mut plan = plan();
        plan["schema_version"] = serde_json::json!("0.9.0");
        plan["baseline_strategy_id"] = serde_json::json!("comparator");
        plan["strategy_order"] = serde_json::json!(["comparator", "intervention"]);
        plan["input_provenance"][0] = serde_json::json!({
            "path": "strategies.comparator.transition_schedule",
            "source_ids": [],
            "extraction_ids": [],
            "assumption_ids": ["excess"],
            "uncertainty_status": "distribution_available",
            "derivation": {
                "method": "deterministic_transformation",
                "transformation": {
                    "operation": "background_plus_excess_mortality_to_transition_schedule",
                    "excess_mortality_rate_per_year": {"value": 0.05, "assumption_id": "excess"},
                    "life_table": {"cycle_probabilities": [
                        {"annual_probability": {"value": 0.1, "assumption_id": "q"}}
                    ]},
                    "review_bases": {
                        "population_exchangeability": {"assumption_id": "exchangeability"},
                        "no_double_counting": {"assumption_id": "no-double-counting"}
                    }
                }
            }
        });
        plan["methodology"]["uncertainty_analysis"]["deterministic"]["input_paths"] =
            serde_json::json!(["strategies.comparator.transition_schedule"]);
        plan["methodology"]["uncertainty_analysis"]["probabilistic"]["input_paths"] =
            serde_json::json!(["strategies.comparator.transition_schedule"]);
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let mut uncertainty = uncertainty(&plan_raw);
        uncertainty["schema_version"] = serde_json::json!("0.8.0");
        uncertainty["parameters"][0] = serde_json::json!({
            "id": "excess-mortality",
            "label": "Excess mortality rate",
            "target": "/input_provenance/0/derivation/transformation/excess_mortality_rate_per_year/value",
            "provenance_path": "strategies.comparator.transition_schedule",
            "deterministic": {"low": 0.02, "high": 0.08, "rationale": "Evidence interval"},
            "probabilistic": {
                "type": "gamma", "shape": 5, "scale": 0.01,
                "basis_ids": ["excess"], "rationale": "Positive excess hazard"
            }
        });
        uncertainty["probabilistic_analysis"]["correlation_handling"]["groups"] =
            serde_json::json!([]);
        uncertainty["structural_scenarios"][0]["replacements"] = serde_json::json!([{
            "target": "/discount_rates/costs",
            "value": 0.02
        }]);
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(audit.complete, "{:?}", audit.errors);

        uncertainty["parameters"][0]["target"] = serde_json::json!(
            "/input_provenance/0/derivation/transformation/life_table/cycle_probabilities/0/annual_probability/value"
        );
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("target is not unique and allowlisted")));

        uncertainty["parameters"][0]["target"] = serde_json::json!(
            "/input_provenance/0/derivation/transformation/excess_mortality_rate_per_year/value"
        );
        uncertainty["structural_scenarios"][0]["replacements"] = serde_json::json!([{
            "target": "/cycle_length_years",
            "value": 0.5
        }]);
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("invalid or duplicate replacement")));

        uncertainty["parameters"][0]["target"] =
            serde_json::json!("/strategies/comparator/state_costs");
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("target is not unique and allowlisted")));
    }

    #[test]
    fn legacy_uncertainty_rejects_targets_for_ignored_extra_strategies() {
        let mut plan = plan();
        let shadow = plan["strategies"]["intervention"].clone();
        plan["strategies"]["shadow"] = shadow;
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let mut uncertainty = uncertainty(&plan_raw);
        uncertainty["parameters"][0]["target"] =
            serde_json::json!("/strategies/shadow/state_costs/0");
        uncertainty["structural_scenarios"][0]["replacements"] = serde_json::json!([{
            "target": "/strategies/shadow/state_utilities/0",
            "value": 0.7
        }]);
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();

        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);

        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("target is not unique and allowlisted")));
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("invalid or duplicate replacement")));
    }

    #[test]
    fn decision_thresholds_fail_closed_on_duplicates_or_missing_primary() {
        let plan = plan();
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        for values in [
            serde_json::json!([0, 100000, 100000]),
            serde_json::json!([0, 50000, 150000]),
        ] {
            let mut uncertainty = uncertainty(&plan_raw);
            uncertainty["probabilistic_analysis"]["decision_thresholds"]["values"] = values;
            let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
            let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
            assert!(!audit.complete);
            assert!(audit.errors.iter().any(|error| error.contains("threshold")));
        }
    }

    #[test]
    fn legacy_schema_rejects_a_silently_ignored_threshold_grid() {
        let plan = plan();
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let mut uncertainty = uncertainty(&plan_raw);
        uncertainty["schema_version"] = serde_json::json!("0.1.0");
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("schema_version 0.2.0")));
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
    fn event_rate_parameter_requires_exact_basis_and_positive_distribution() {
        let mut plan = plan();
        plan["schema_version"] = serde_json::json!("0.5.0");
        plan["input_provenance"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "path": "strategies.intervention.transition_matrix",
                "source_ids": [],
                "extraction_ids": [],
                "assumption_ids": ["intervention-mortality-rate"],
                "uncertainty_status": "distribution_available",
                "derivation": {
                    "method": "deterministic_transformation",
                    "model_value": [[0.95, 0.05], [0.0, 1.0]],
                    "transformation": {
                        "operation": "constant_competing_rates",
                        "cycle_length_years": 1.0,
                        "phases": [{
                            "start_cycle": 1,
                            "rows": [{
                                "self_index": 0,
                                "events": [{
                                    "target_index": 1,
                                    "rate_per_year": 0.05129329438755058,
                                    "assumption_id": "intervention-mortality-rate"
                                }]
                            }, {"self_index": 1, "events": []}]
                        }]
                    }
                }
            }));
        for kind in ["deterministic", "probabilistic"] {
            plan["methodology"]["uncertainty_analysis"][kind]["input_paths"] =
                serde_json::json!(["strategies.intervention.transition_matrix"]);
        }
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let mut uncertainty = uncertainty(&plan_raw);
        uncertainty["schema_version"] = serde_json::json!("0.3.0");
        uncertainty["parameters"] = serde_json::json!([{
            "id": "intervention-mortality-rate",
            "label": "Intervention mortality event rate",
            "target": "/input_provenance/1/derivation/transformation/phases/0/rows/0/events/0/rate_per_year",
            "provenance_path": "strategies.intervention.transition_matrix",
            "deterministic": {"low": 0.02, "high": 0.1, "rationale": "Evidence range"},
            "probabilistic": {
                "type": "gamma", "shape": 4, "scale": 0.012823323596887645,
                "basis_ids": ["intervention-mortality-rate"], "rationale": "Positive rate"
            }
        }]);
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(audit.complete, "{:?}", audit.errors);

        uncertainty["parameters"][0]["probabilistic"]["basis_ids"] =
            serde_json::json!(["unlinked"]);
        uncertainty["parameters"][0]["probabilistic"]["type"] = serde_json::json!("beta");
        uncertainty["parameters"][0]["probabilistic"]["alpha"] = serde_json::json!(2);
        uncertainty["parameters"][0]["probabilistic"]["beta"] = serde_json::json!(8);
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(!audit.complete);
        assert!(audit.errors.iter().any(|error| error.contains("basis_ids")));
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("invalid or unsupported distribution")));
    }

    #[test]
    fn survival_parameter_requires_current_schema_exact_basis_and_positive_distribution() {
        let mut plan = plan();
        plan["schema_version"] = serde_json::json!("0.6.0");
        plan["strategies"]["intervention"]
            .as_object_mut()
            .unwrap()
            .remove("transition_matrix");
        plan["strategies"]["intervention"]["transition_schedule"] = serde_json::json!([
            {"start_cycle": 1, "matrix": [[0.95, 0.05], [0.0, 1.0]]},
            {"start_cycle": 2, "matrix": [[0.90, 0.10], [0.0, 1.0]]},
            {"start_cycle": 3, "matrix": [[0.85, 0.15], [0.0, 1.0]]}
        ]);
        let transition_schedule = plan["strategies"]["intervention"]["transition_schedule"].clone();
        plan["input_provenance"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "path": "strategies.intervention.transition_schedule",
                "source_ids": [],
                "extraction_ids": [],
                "assumption_ids": ["intervention-weibull-shape", "intervention-weibull-scale"],
                "uncertainty_status": "distribution_available",
                "derivation": {
                    "method": "deterministic_transformation",
                    "model_value": transition_schedule,
                    "transformation": {
                        "operation": "parametric_survival_to_transition_schedule",
                        "cycle_length_years": 1.0,
                        "distribution": "weibull",
                        "parameters": {
                            "shape": {"value": 2.0, "assumption_id": "intervention-weibull-shape"},
                            "scale_years": {"value": 4.0, "assumption_id": "intervention-weibull-scale"}
                        }
                    }
                }
            }));
        for kind in ["deterministic", "probabilistic"] {
            plan["methodology"]["uncertainty_analysis"][kind]["input_paths"] =
                serde_json::json!(["strategies.intervention.transition_schedule"]);
        }
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let mut uncertainty = uncertainty(&plan_raw);
        uncertainty["schema_version"] = serde_json::json!("0.5.0");
        uncertainty["parameters"] = serde_json::json!([{
            "id": "intervention-weibull-shape",
            "label": "Intervention Weibull shape",
            "target": "/input_provenance/1/derivation/transformation/parameters/shape/value",
            "provenance_path": "strategies.intervention.transition_schedule",
            "deterministic": {"low": 1.5, "high": 2.5, "rationale": "Evidence range"},
            "probabilistic": {
                "type": "lognormal", "mu_log": std::f64::consts::LN_2, "sigma_log": 0.1,
                "basis_ids": ["intervention-weibull-shape"], "rationale": "Positive shape"
            }
        }]);
        uncertainty["probabilistic_analysis"]["correlation_handling"]["groups"] =
            serde_json::json!([]);
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(audit.complete, "{:?}", audit.errors);

        uncertainty["schema_version"] = serde_json::json!("0.4.0");
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(!audit.complete);
        assert!(audit.errors.iter().any(|error| error.contains("target")));
    }

    #[test]
    fn probability_time_parameter_requires_bounded_distribution_and_exact_basis() {
        let mut plan = plan();
        plan["schema_version"] = serde_json::json!("0.7.0");
        plan["strategies"]["intervention"]["transition_matrix"] =
            serde_json::json!([[0.8, 0.2], [0.0, 1.0]]);
        plan["input_provenance"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "path": "strategies.intervention.transition_matrix",
                "source_ids": [],
                "extraction_ids": [],
                "assumption_ids": ["two-year-event-probability"],
                "uncertainty_status": "distribution_available",
                "derivation": {
                    "method": "deterministic_transformation",
                    "model_value": [[0.8, 0.2], [0.0, 1.0]],
                    "transformation": {
                        "operation": "single_event_probability_time_conversion",
                        "cycle_length_years": 1.0,
                        "phases": [{
                            "start_cycle": 1,
                            "rows": [
                                {"self_index": 0, "event": {
                                    "target_index": 1,
                                    "source_probability": 0.36,
                                    "source_interval_years": 2.0,
                                    "assumption_id": "two-year-event-probability"
                                }},
                                {"self_index": 1, "event": null}
                            ]
                        }]
                    }
                }
            }));
        for kind in ["deterministic", "probabilistic"] {
            plan["methodology"]["uncertainty_analysis"][kind]["input_paths"] =
                serde_json::json!(["strategies.intervention.transition_matrix"]);
        }
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let mut uncertainty = uncertainty(&plan_raw);
        uncertainty["schema_version"] = serde_json::json!("0.6.0");
        uncertainty["parameters"] = serde_json::json!([{
            "id": "two-year-event-probability",
            "label": "Two-year event probability",
            "target": "/input_provenance/1/derivation/transformation/phases/0/rows/0/event/source_probability",
            "provenance_path": "strategies.intervention.transition_matrix",
            "deterministic": {"low": 0.25, "high": 0.49, "rationale": "Evidence range"},
            "probabilistic": {
                "type": "beta", "alpha": 36, "beta": 64,
                "basis_ids": ["two-year-event-probability"], "rationale": "Bounded source probability"
            }
        }]);
        uncertainty["probabilistic_analysis"]["correlation_handling"]["groups"] =
            serde_json::json!([]);
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(audit.complete, "{:?}", audit.errors);

        uncertainty["parameters"][0]["probabilistic"] = serde_json::json!({
            "type": "gamma", "shape": 4, "scale": 0.09,
            "basis_ids": ["unlinked"], "rationale": "Invalid unbounded probability"
        });
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(!audit.complete);
        assert!(audit.errors.iter().any(|error| error.contains("basis_ids")));
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("invalid or unsupported distribution")));
    }

    #[test]
    fn lognormal_correlation_group_is_evidence_bound_and_positive_definite() {
        assert!(
            correlation_matrix_error(&serde_json::json!([[1.0, 1.0], [1.0, 1.0]]), 2)
                .is_some_and(|error| error.contains("strictly between"))
        );
        assert!(correlation_matrix_error(
            &serde_json::json!([[1.0, 0.9, 0.9], [0.9, 1.0, -0.9], [0.9, -0.9, 1.0]]),
            3,
        )
        .is_some_and(|error| error.contains("strictly positive definite")));

        let plan = plan();
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let mut uncertainty = uncertainty(&plan_raw);
        uncertainty["schema_version"] = serde_json::json!("0.4.0");
        uncertainty["parameters"] = serde_json::json!([{
            "id": "stable-cost",
            "label": "Stable-state cost",
            "target": "/strategies/intervention/state_costs/0",
            "provenance_path": "strategies.intervention.state_costs",
            "deterministic": {"low": 3000, "high": 5000, "rationale": "Evidence interval"},
            "probabilistic": {
                "type": "lognormal", "mu_log": 8.294049640102028, "sigma_log": 0.2,
                "basis_ids": ["source-1"], "rationale": "Joint log-scale estimate"
            }
        }, {
            "id": "progressed-cost",
            "label": "Progressed-state cost",
            "target": "/strategies/intervention/state_costs/1",
            "provenance_path": "strategies.intervention.state_costs",
            "deterministic": {"low": 1000, "high": 3000, "rationale": "Evidence interval"},
            "probabilistic": {
                "type": "lognormal", "mu_log": 7.600902459542082, "sigma_log": 0.3,
                "basis_ids": ["source-1"], "rationale": "Joint log-scale estimate"
            }
        }]);
        uncertainty["probabilistic_analysis"]["correlation_handling"]["groups"] = serde_json::json!([{
            "id": "joint-costs",
            "parameter_ids": ["stable-cost", "progressed-cost"],
            "scale": "log_standard_normal",
            "method": "cholesky",
            "correlation_matrix": [[1.0, 0.6], [0.6, 1.0]],
            "basis_ids": ["source-1"],
            "rationale": "The source reports a joint log-scale covariance estimate."
        }]);
        let uncertainty_raw = serde_json::to_vec(&uncertainty).unwrap();
        let audit = audit_values(&plan, &plan_raw, &uncertainty, &uncertainty_raw);
        assert!(audit.complete, "{:?}", audit.errors);
        assert_eq!(audit.correlation_group_count, 1);

        let mut asymmetric = uncertainty.clone();
        asymmetric["probabilistic_analysis"]["correlation_handling"]["groups"][0]
            ["correlation_matrix"] = serde_json::json!([[1.0, 0.6], [0.5, 1.0]]);
        let raw = serde_json::to_vec(&asymmetric).unwrap();
        let audit = audit_values(&plan, &plan_raw, &asymmetric, &raw);
        assert!(audit.errors.iter().any(|error| error.contains("symmetric")));

        let mut unlinked = uncertainty.clone();
        unlinked["probabilistic_analysis"]["correlation_handling"]["groups"][0]["basis_ids"] =
            serde_json::json!(["unlinked"]);
        let raw = serde_json::to_vec(&unlinked).unwrap();
        let audit = audit_values(&plan, &plan_raw, &unlinked, &raw);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("member parameter")));

        let mut legacy = uncertainty;
        legacy["schema_version"] = serde_json::json!("0.3.0");
        let raw = serde_json::to_vec(&legacy).unwrap();
        let audit = audit_values(&plan, &plan_raw, &legacy, &raw);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("require uncertainty schema_version 0.4.0")));
    }

    #[test]
    fn authority_and_unknown_targets_are_outside_the_allowlist() {
        let legacy = HashSet::from(["comparator", "intervention"]);
        assert!(!parameter_target_allowed("/reference_case/status", &legacy));
        assert!(!scenario_target_allowed("/analysis_id", &legacy));
        assert!(parameter_target_allowed(
            "/strategies/intervention/transition_matrix/0",
            &legacy,
        ));
        assert!(parameter_target_allowed(
            "/strategies/intervention/transition_schedule/1/matrix/0",
            &legacy,
        ));
        assert!(scenario_target_allowed(
            "/strategies/intervention/transition_schedule/1/start_cycle",
            &legacy,
        ));
        assert!(!parameter_target_allowed(
            "/strategies/intervention/transition_schedule/1/start_cycle",
            &legacy,
        ));
        assert!(!parameter_target_allowed(
            "/strategies/treatment_a/state_costs/0",
            &legacy,
        ));

        let multi = HashSet::from(["standard_care", "treatment_a"]);
        assert!(parameter_target_allowed(
            "/strategies/treatment_a/state_costs/0",
            &multi,
        ));
        assert!(!parameter_target_allowed(
            "/strategies/alternative/state_costs/0",
            &multi,
        ));
        assert!(!scenario_target_allowed(
            "/strategies/alternative/transition_schedule/0/start_cycle",
            &multi,
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
