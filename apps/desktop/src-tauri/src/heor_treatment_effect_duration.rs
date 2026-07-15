//! Native audit for explicit two-strategy PSM treatment-effect duration scenarios.
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::Path;

pub const TREATMENT_EFFECT_DURATION_PATH: &str = "heor/treatment-effect-duration.json";
const ANALYSIS_PATH: &str = "heor/analysis-plan.json";
const MATERIALIZATION_PATH: &str = "heor/survival-curve-materializations.json";
const TOLERANCE: f64 = 1e-9;

#[derive(Clone, Debug)]
pub struct TreatmentEffectDurationAudit {
    pub complete: bool,
    pub sha256: String,
    pub scenario_count: usize,
    pub base_case_scenario_id: String,
    pub artifact_bindings: Vec<crate::heor_approval::ArtifactBinding>,
    pub errors: Vec<String>,
}

#[derive(Clone, Debug)]
struct Policy {
    mode: String,
    evidence_horizon: f64,
    hazard_ratio: f64,
    waning_end: Option<f64>,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn exact_fields(value: &serde_json::Value, fields: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == fields.len() && fields.iter().all(|field| object.contains_key(*field))
    })
}

fn finite(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite())
}

fn finite_positive(value: Option<&serde_json::Value>) -> Option<f64> {
    finite(value).filter(|value| *value > 0.0)
}

fn nonempty(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| !value.trim().is_empty())
}

fn strings(value: Option<&serde_json::Value>) -> Option<Vec<String>> {
    let values = value?.as_array()?;
    if values.is_empty() {
        return None;
    }
    let mut observed = HashSet::new();
    let mut output = Vec::new();
    for value in values {
        let value = value.as_str()?.trim();
        if value.is_empty() || !observed.insert(value.to_owned()) {
            return None;
        }
        output.push(value.to_owned());
    }
    Some(output)
}

fn valid_sha(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| {
            value.len() == 64
                && value
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        })
}

fn safe_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 80
        && value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'-' | b'_')
        })
}

fn aligned_time(value: f64, cycle: f64, horizon: f64, allow_horizon: bool) -> bool {
    value >= 0.0
        && if allow_horizon {
            value <= horizon + TOLERANCE
        } else {
            value < horizon - TOLERANCE
        }
        && ((value / cycle) - (value / cycle).round()).abs() <= TOLERANCE
}

fn binding_matches(value: Option<&serde_json::Value>, path: &str, digest: &str) -> bool {
    value.is_some_and(|binding| {
        exact_fields(binding, &["path", "content_sha256"])
            && binding.get("path").and_then(serde_json::Value::as_str) == Some(path)
            && binding
                .get("content_sha256")
                .and_then(serde_json::Value::as_str)
                == Some(digest)
    })
}

fn source_curves(
    materializations: &serde_json::Value,
    strategy_order: &[String],
    expected_count: usize,
    errors: &mut Vec<String>,
) -> HashMap<(String, String), Vec<f64>> {
    let mut output = HashMap::new();
    let curves = materializations
        .get("curves")
        .and_then(serde_json::Value::as_array);
    if curves.map_or(0, Vec::len) != strategy_order.len() * 2 {
        errors.push("source materializations must contain every ordered PFS/OS curve".into());
        return output;
    }
    let mut index = 0;
    for strategy_id in strategy_order {
        for endpoint in ["pfs", "os"] {
            let target = format!("partitioned_survival.strategies.{strategy_id}.{endpoint}");
            let curve = &curves.unwrap()[index];
            index += 1;
            if curve.get("target_path").and_then(serde_json::Value::as_str) != Some(target.as_str())
                || curve.get("strategy_id").and_then(serde_json::Value::as_str)
                    != Some(strategy_id.as_str())
                || curve.get("endpoint").and_then(serde_json::Value::as_str) != Some(endpoint)
            {
                errors.push(format!("source materialization does not match {target}"));
                continue;
            }
            let values = curve.get("values").and_then(serde_json::Value::as_array);
            if values.map_or(0, Vec::len) != expected_count {
                errors.push(format!("{target} does not cover the analysis grid"));
                continue;
            }
            let parsed = values
                .unwrap()
                .iter()
                .enumerate()
                .filter_map(|(value_index, row)| {
                    let survival = finite(row.get("survival"));
                    if !survival.is_some_and(|value| value > 0.0 && value <= 1.0) {
                        errors.push(format!(
                            "{target}[{value_index}] must remain strictly positive"
                        ));
                    }
                    survival
                })
                .collect::<Vec<_>>();
            if parsed.len() == expected_count {
                output.insert((strategy_id.clone(), endpoint.to_owned()), parsed);
            }
        }
    }
    output
}

fn cycle_ratio(policy: &Policy, interval_start: f64) -> f64 {
    match policy.mode.as_str() {
        "sustained" => policy.hazard_ratio,
        "immediate_stop" => 1.0,
        _ => {
            let end = policy.waning_end.unwrap_or(policy.evidence_horizon);
            if interval_start >= end - TOLERANCE {
                1.0
            } else {
                let fraction =
                    ((end - interval_start) / (end - policy.evidence_horizon)).clamp(0.0, 1.0);
                (policy.hazard_ratio.ln() * fraction).exp()
            }
        }
    }
}

fn derive_curve(
    comparator: &[f64],
    intervention_source: &[f64],
    cycle: f64,
    policy: &Policy,
) -> Option<Vec<f64>> {
    let evidence_index = (policy.evidence_horizon / cycle).round() as usize;
    let mut output = intervention_source.get(..=evidence_index)?.to_vec();
    for index in evidence_index + 1..comparator.len() {
        let ratio = comparator[index] / comparator[index - 1];
        if !ratio.is_finite() || ratio <= 0.0 || ratio > 1.0 + TOLERANCE {
            return None;
        }
        let increment = -ratio.ln();
        let multiplier = cycle_ratio(policy, (index - 1) as f64 * cycle);
        let current = output.last()? * (-multiplier * increment).exp();
        if !current.is_finite()
            || current <= 0.0
            || current > output.last().copied().unwrap_or_default() + TOLERANCE
        {
            return None;
        }
        output.push(current);
    }
    Some(output)
}

fn compare_psm_rows(
    psm: &serde_json::Value,
    strategy_id: &str,
    endpoint: &str,
    expected: &[f64],
    expected_basis: &[String],
    cycle: f64,
    errors: &mut Vec<String>,
) {
    let rows = psm
        .pointer(&format!("/strategies/{strategy_id}/{endpoint}"))
        .and_then(serde_json::Value::as_array);
    if rows.map_or(0, Vec::len) != expected.len() {
        errors.push(format!(
            "PSM {strategy_id}.{endpoint} does not cover the duration base-case grid"
        ));
        return;
    }
    for (index, expected_survival) in expected.iter().enumerate() {
        let row = &rows.unwrap()[index];
        let expected_time = index as f64 * cycle;
        if !finite(row.get("time_years"))
            .is_some_and(|value| (value - expected_time).abs() <= TOLERANCE)
            || !finite(row.get("survival"))
                .is_some_and(|value| (value - expected_survival).abs() <= TOLERANCE)
        {
            errors.push(format!(
                "PSM {strategy_id}.{endpoint}[{index}] does not match the duration base case"
            ));
        }
        if strings(row.get("basis_ids")).as_deref() != Some(expected_basis) {
            errors.push(format!(
                "PSM {strategy_id}.{endpoint}[{index}] basis IDs do not match duration inputs"
            ));
        }
    }
}

pub fn audit_treatment_effect_duration(
    workspace: &Path,
    plan: &serde_json::Value,
    plan_raw: &[u8],
    psm: &serde_json::Value,
    materialization_sha: &str,
) -> TreatmentEffectDurationAudit {
    let mut audit = TreatmentEffectDurationAudit {
        complete: false,
        sha256: String::new(),
        scenario_count: 0,
        base_case_scenario_id: String::new(),
        artifact_bindings: Vec::new(),
        errors: Vec::new(),
    };
    if psm
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.4.0")
    {
        audit.complete = true;
        return audit;
    }
    let link = psm
        .get("treatment_effect_duration")
        .unwrap_or(&serde_json::Value::Null);
    if !exact_fields(link, &["path", "content_sha256"])
        || link.get("path").and_then(serde_json::Value::as_str)
            != Some(TREATMENT_EFFECT_DURATION_PATH)
        || !valid_sha(link.get("content_sha256"))
    {
        audit.errors.push(format!(
            "treatment_effect_duration must bind {TREATMENT_EFFECT_DURATION_PATH}"
        ));
        return audit;
    }
    let raw = match crate::heor_uncertainty::read_workspace_capped(
        workspace,
        TREATMENT_EFFECT_DURATION_PATH,
    ) {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    audit.sha256 = sha256(&raw);
    if link
        .get("content_sha256")
        .and_then(serde_json::Value::as_str)
        != Some(audit.sha256.as_str())
    {
        audit
            .errors
            .push("treatment-effect duration hash does not match current bytes".into());
        return audit;
    }
    let duration: serde_json::Value = match serde_json::from_slice(&raw) {
        Ok(value) => value,
        Err(error) => {
            audit.errors.push(format!(
                "treatment-effect duration is invalid JSON: {error}"
            ));
            return audit;
        }
    };
    audit
        .artifact_bindings
        .push(crate::heor_approval::ArtifactBinding {
            path: TREATMENT_EFFECT_DURATION_PATH.into(),
            sha256: audit.sha256.clone(),
        });
    if !exact_fields(
        &duration,
        &[
            "schema_version",
            "duration_id",
            "analysis_id",
            "psm_id",
            "status",
            "base_analysis",
            "source_curve_materializations",
            "comparison",
            "base_case_scenario_id",
            "scenarios",
            "limitations",
        ],
    ) {
        audit
            .errors
            .push("treatment-effect duration fields are not the exact contract".into());
    }
    if duration
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
    {
        audit
            .errors
            .push("treatment-effect duration schema_version must be 0.1.0".into());
    }
    if duration.get("status").and_then(serde_json::Value::as_str) != Some("ready_for_human_review")
    {
        audit
            .errors
            .push("treatment-effect duration must be ready_for_human_review".into());
    }
    if !nonempty(duration.get("duration_id"))
        || duration.get("analysis_id") != plan.get("analysis_id")
        || duration.get("psm_id") != psm.get("psm_id")
    {
        audit
            .errors
            .push("treatment-effect duration identity is invalid".into());
    }
    if !binding_matches(
        duration.get("base_analysis"),
        ANALYSIS_PATH,
        &sha256(plan_raw),
    ) || !binding_matches(
        duration.get("source_curve_materializations"),
        MATERIALIZATION_PATH,
        materialization_sha,
    ) {
        audit
            .errors
            .push("treatment-effect duration source bindings are stale".into());
    }

    let strategy_order = plan
        .get("strategy_order")
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(serde_json::Value::as_str)
                .map(str::to_owned)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    if strategy_order.len() != 2 || strategy_order[0] == strategy_order[1] {
        audit
            .errors
            .push("treatment-effect duration requires exactly two strategies".into());
        return audit;
    }
    let comparison = duration
        .get("comparison")
        .unwrap_or(&serde_json::Value::Null);
    if !exact_fields(
        comparison,
        &[
            "comparator_strategy_id",
            "intervention_strategy_id",
            "endpoint_order",
        ],
    ) || comparison
        .get("comparator_strategy_id")
        .and_then(serde_json::Value::as_str)
        != plan
            .get("baseline_strategy_id")
            .and_then(serde_json::Value::as_str)
        || comparison
            .get("comparator_strategy_id")
            .and_then(serde_json::Value::as_str)
            != Some(strategy_order[0].as_str())
        || comparison
            .get("intervention_strategy_id")
            .and_then(serde_json::Value::as_str)
            != Some(strategy_order[1].as_str())
        || comparison
            .get("endpoint_order")
            .and_then(serde_json::Value::as_array)
            .map(|values| {
                values
                    .iter()
                    .filter_map(serde_json::Value::as_str)
                    .collect::<Vec<_>>()
            })
            != Some(vec!["pfs", "os"])
    {
        audit
            .errors
            .push("treatment-effect duration comparison is invalid".into());
    }
    let cycles = plan
        .get("cycles")
        .and_then(serde_json::Value::as_u64)
        .filter(|value| (1..=10_000).contains(value));
    let cycle = finite_positive(plan.get("cycle_length_years"));
    let (Some(cycles), Some(cycle)) = (cycles, cycle) else {
        audit.errors.push("analysis cycle grid is invalid".into());
        return audit;
    };
    let expected_count = cycles as usize + 1;
    let horizon = cycles as f64 * cycle;
    let materialization_raw =
        match crate::heor_uncertainty::read_workspace_capped(workspace, MATERIALIZATION_PATH) {
            Ok(raw) => raw,
            Err(error) => {
                audit.errors.push(error);
                return audit;
            }
        };
    if sha256(&materialization_raw) != materialization_sha {
        audit
            .errors
            .push("current materialization bytes do not match native audit".into());
        return audit;
    }
    let materializations: serde_json::Value = match serde_json::from_slice(&materialization_raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("source materializations are invalid JSON: {error}"));
            return audit;
        }
    };
    let source = source_curves(
        &materializations,
        &strategy_order,
        expected_count,
        &mut audit.errors,
    );
    let scenarios = duration
        .get("scenarios")
        .and_then(serde_json::Value::as_array);
    audit.scenario_count = scenarios.map_or(0, Vec::len);
    if !(3..=5).contains(&audit.scenario_count) {
        audit
            .errors
            .push("treatment-effect duration requires 3-5 scenarios".into());
        return audit;
    }
    audit.base_case_scenario_id = duration
        .get("base_case_scenario_id")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
        .to_owned();
    let mut ids = HashSet::new();
    let mut coverage: HashMap<&str, HashSet<String>> =
        [("pfs", HashSet::new()), ("os", HashSet::new())]
            .into_iter()
            .collect();
    let mut shared: HashMap<&str, (f64, f64, Vec<String>)> = HashMap::new();
    let materialization_basis = format!("source-materialization-sha256:{materialization_sha}");
    let duration_basis = format!("treatment-effect-duration-sha256:{}", audit.sha256);
    let mut base_seen = false;
    for (scenario_index, scenario) in scenarios.into_iter().flatten().enumerate() {
        if !exact_fields(
            scenario,
            &["scenario_id", "label", "rationale", "basis_ids", "policies"],
        ) {
            audit
                .errors
                .push(format!("scenario {scenario_index} fields are invalid"));
            continue;
        }
        let scenario_id = scenario
            .get("scenario_id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        if !safe_id(scenario_id) || !ids.insert(scenario_id.to_owned()) {
            audit.errors.push(format!(
                "scenario {scenario_index} id is invalid or duplicated"
            ));
        }
        if !nonempty(scenario.get("label"))
            || !nonempty(scenario.get("rationale"))
            || strings(scenario.get("basis_ids")).is_none()
        {
            audit.errors.push(format!(
                "scenario {scenario_id} rationale or basis is incomplete"
            ));
        }
        let policies = scenario
            .get("policies")
            .and_then(serde_json::Value::as_array);
        if policies.map_or(0, Vec::len) != 2 {
            audit
                .errors
                .push(format!("scenario {scenario_id} must contain PFS then OS"));
            continue;
        }
        let mut parsed: HashMap<&str, Policy> = HashMap::new();
        for (policy_index, endpoint) in ["pfs", "os"].into_iter().enumerate() {
            let policy = &policies.unwrap()[policy_index];
            if !exact_fields(
                policy,
                &[
                    "endpoint",
                    "mode",
                    "evidence_horizon_years",
                    "hazard_ratio",
                    "waning_end_years",
                    "rationale",
                    "basis_ids",
                ],
            ) || policy.get("endpoint").and_then(serde_json::Value::as_str) != Some(endpoint)
            {
                audit.errors.push(format!(
                    "scenario {scenario_id} {endpoint} policy is invalid"
                ));
                continue;
            }
            let mode = policy
                .get("mode")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            if !matches!(mode, "sustained" | "immediate_stop" | "log_linear_waning") {
                audit.errors.push(format!(
                    "scenario {scenario_id} {endpoint} mode is unsupported"
                ));
                continue;
            }
            coverage.get_mut(endpoint).unwrap().insert(mode.to_owned());
            let evidence = finite(policy.get("evidence_horizon_years"));
            let hazard = policy.get("hazard_ratio");
            let hazard_ratio = hazard.and_then(|value| finite_positive(value.get("value")));
            let hazard_basis = hazard.and_then(|value| strings(value.get("basis_ids")));
            let (Some(evidence), Some(hazard_ratio), Some(hazard_basis)) =
                (evidence, hazard_ratio, hazard_basis)
            else {
                audit.errors.push(format!(
                    "scenario {scenario_id} {endpoint} evidence horizon or HR is invalid"
                ));
                continue;
            };
            if !aligned_time(evidence, cycle, horizon, false)
                || (hazard_ratio - 1.0).abs() <= TOLERANCE
                || !nonempty(policy.get("rationale"))
                || strings(policy.get("basis_ids")).is_none()
            {
                audit.errors.push(format!(
                    "scenario {scenario_id} {endpoint} duration basis is invalid"
                ));
            }
            let waning_end = finite(policy.get("waning_end_years"));
            if mode == "log_linear_waning" {
                if !waning_end.is_some_and(|value| {
                    aligned_time(value, cycle, horizon, true) && value > evidence + TOLERANCE
                }) {
                    audit.errors.push(format!(
                        "scenario {scenario_id} {endpoint} waning end is invalid"
                    ));
                }
            } else if !policy
                .get("waning_end_years")
                .is_some_and(serde_json::Value::is_null)
            {
                audit.errors.push(format!(
                    "scenario {scenario_id} {endpoint} waning end must be null"
                ));
            }
            if let Some((prior_horizon, prior_hr, prior_basis)) = shared.get(endpoint) {
                if (prior_horizon - evidence).abs() > TOLERANCE
                    || (prior_hr - hazard_ratio).abs() > TOLERANCE
                    || prior_basis != &hazard_basis
                {
                    audit.errors.push(format!(
                        "all {endpoint} scenarios must share evidence horizon, HR, and basis"
                    ));
                }
            } else {
                shared.insert(endpoint, (evidence, hazard_ratio, hazard_basis.clone()));
            }
            parsed.insert(
                endpoint,
                Policy {
                    mode: mode.to_owned(),
                    evidence_horizon: evidence,
                    hazard_ratio,
                    waning_end,
                },
            );
        }
        if parsed.len() != 2 {
            continue;
        }
        let expected_basis = vec![
            materialization_basis.clone(),
            duration_basis.clone(),
            format!("duration-scenario:{scenario_id}"),
        ];
        let mut derived: HashMap<(String, String), Vec<f64>> = HashMap::new();
        for endpoint in ["pfs", "os"] {
            let comparator_key = (strategy_order[0].clone(), endpoint.to_owned());
            let intervention_key = (strategy_order[1].clone(), endpoint.to_owned());
            let Some(comparator_values) = source.get(&comparator_key) else {
                continue;
            };
            let Some(intervention_values) = source.get(&intervention_key) else {
                continue;
            };
            let Some(values) = derive_curve(
                comparator_values,
                intervention_values,
                cycle,
                &parsed[endpoint],
            ) else {
                audit.errors.push(format!(
                    "scenario {scenario_id} {endpoint} curve derivation failed"
                ));
                continue;
            };
            derived.insert(comparator_key, comparator_values.clone());
            derived.insert(intervention_key, values);
        }
        for strategy_id in &strategy_order {
            let pfs = derived.get(&(strategy_id.clone(), "pfs".into()));
            let overall = derived.get(&(strategy_id.clone(), "os".into()));
            if let (Some(pfs), Some(overall)) = (pfs, overall) {
                if pfs
                    .iter()
                    .zip(overall)
                    .any(|(pfs, overall)| pfs > &(overall + TOLERANCE))
                {
                    audit.errors.push(format!(
                        "scenario {scenario_id} has PFS above OS for {strategy_id}"
                    ));
                }
            }
        }
        if scenario_id == audit.base_case_scenario_id {
            base_seen = true;
            for strategy_id in &strategy_order {
                for endpoint in ["pfs", "os"] {
                    if let Some(values) = derived.get(&(strategy_id.clone(), endpoint.to_owned())) {
                        compare_psm_rows(
                            psm,
                            strategy_id,
                            endpoint,
                            values,
                            &expected_basis,
                            cycle,
                            &mut audit.errors,
                        );
                    }
                }
            }
        }
    }
    for endpoint in ["pfs", "os"] {
        if coverage.get(endpoint).map(HashSet::len) != Some(3) {
            audit.errors.push(format!(
                "{endpoint} scenarios must cover sustained, immediate_stop, and log_linear_waning"
            ));
        }
    }
    if !base_seen {
        audit
            .errors
            .push("base_case_scenario_id must identify one scenario".into());
    }
    if strings(duration.get("limitations")).is_none() {
        audit
            .errors
            .push("treatment-effect duration limitations are required".into());
    }
    let authority = String::from_utf8_lossy(&raw).to_ascii_lowercase();
    if [
        "\"approved\":",
        "\"approval_timestamp\":",
        "\"independently_validated\":",
    ]
    .iter()
    .any(|field| authority.contains(field))
    {
        audit
            .errors
            .push("treatment-effect duration contains a forbidden authority field".into());
    }
    audit.complete = audit.errors.is_empty();
    audit
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(time: f64, survival: f64, basis: &[String]) -> serde_json::Value {
        serde_json::json!({
            "time_years": time,
            "survival": survival,
            "basis_ids": basis,
        })
    }

    #[test]
    fn cycle_ratio_distinguishes_all_duration_modes() {
        let policy = |mode: &str, end| Policy {
            mode: mode.into(),
            evidence_horizon: 1.0,
            hazard_ratio: 0.5,
            waning_end: end,
        };
        assert!((cycle_ratio(&policy("sustained", None), 2.0) - 0.5).abs() < TOLERANCE);
        assert!((cycle_ratio(&policy("immediate_stop", None), 2.0) - 1.0).abs() < TOLERANCE);
        assert!(
            (cycle_ratio(&policy("log_linear_waning", Some(3.0)), 2.0) - 0.5_f64.sqrt()).abs()
                < TOLERANCE
        );
        assert!(
            (cycle_ratio(&policy("log_linear_waning", Some(3.0)), 3.0) - 1.0).abs() < TOLERANCE
        );
    }

    #[test]
    fn derived_curve_uses_comparator_hazard_increments_after_horizon() {
        let policy = Policy {
            mode: "immediate_stop".into(),
            evidence_horizon: 1.0,
            hazard_ratio: 0.5,
            waning_end: None,
        };
        let comparator = vec![1.0, (-0.4_f64).exp(), (-0.8_f64).exp()];
        let source = vec![1.0, (-0.2_f64).exp(), (-0.4_f64).exp()];
        let derived = derive_curve(&comparator, &source, 1.0, &policy).unwrap();
        assert!((derived[1] - (-0.2_f64).exp()).abs() < TOLERANCE);
        assert!((derived[2] - (-0.6_f64).exp()).abs() < TOLERANCE);
    }

    #[test]
    fn complete_native_fixture_and_stale_hash_fail_closed() {
        let root = std::env::temp_dir().join(format!(
            "ai4heor-duration-{}-{}",
            std::process::id(),
            std::thread::current().name().unwrap_or("test")
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor")).unwrap();
        let plan = serde_json::json!({
            "schema_version": "0.12.0",
            "analysis_id": "analysis",
            "cycles": 2,
            "cycle_length_years": 1.0,
            "strategy_order": ["comparator", "intervention"],
            "baseline_strategy_id": "comparator"
        });
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let curves = [
            ("comparator", "pfs", 0.5),
            ("comparator", "os", 0.2),
            ("intervention", "pfs", 0.25),
            ("intervention", "os", 0.1),
        ]
        .into_iter()
        .map(|(strategy, endpoint, rate)| {
            serde_json::json!({
                "target_path": format!("partitioned_survival.strategies.{strategy}.{endpoint}"),
                "strategy_id": strategy,
                "endpoint": endpoint,
                "values": (0..=2).map(|index| serde_json::json!({
                    "time_years": index as f64,
                    "survival": (-(rate * index as f64)).exp(),
                })).collect::<Vec<_>>()
            })
        })
        .collect::<Vec<_>>();
        let materializations = serde_json::json!({"curves": curves});
        let materialization_raw = serde_json::to_vec(&materializations).unwrap();
        let materialization_sha = sha256(&materialization_raw);
        std::fs::write(root.join(MATERIALIZATION_PATH), &materialization_raw).unwrap();
        let policy = |endpoint: &str, mode: &str, end: Option<f64>, suffix: &str| {
            serde_json::json!({
                "endpoint": endpoint,
                "mode": mode,
                "evidence_horizon_years": 0.0,
                "hazard_ratio": {"value": 0.5, "basis_ids": [format!("effect-{endpoint}")]},
                "waning_end_years": end,
                "rationale": "Reviewable duration policy.",
                "basis_ids": [format!("duration-{endpoint}-{suffix}")]
            })
        };
        let scenarios = [
            ("waning", "log_linear_waning", Some(2.0)),
            ("sustained", "sustained", None),
            ("stop", "immediate_stop", None),
        ]
        .into_iter()
        .map(|(id, mode, end)| {
            serde_json::json!({
                "scenario_id": id,
                "label": id,
                "rationale": "Reviewable scenario.",
                "basis_ids": [format!("scenario-{id}")],
                "policies": [policy("pfs", mode, end, id), policy("os", mode, end, id)]
            })
        })
        .collect::<Vec<_>>();
        let duration = serde_json::json!({
            "schema_version": "0.1.0",
            "duration_id": "duration",
            "analysis_id": "analysis",
            "psm_id": "psm",
            "status": "ready_for_human_review",
            "base_analysis": {"path": ANALYSIS_PATH, "content_sha256": sha256(&plan_raw)},
            "source_curve_materializations": {"path": MATERIALIZATION_PATH, "content_sha256": materialization_sha},
            "comparison": {
                "comparator_strategy_id": "comparator",
                "intervention_strategy_id": "intervention",
                "endpoint_order": ["pfs", "os"]
            },
            "base_case_scenario_id": "waning",
            "scenarios": scenarios,
            "limitations": ["Clinical validity is not established."]
        });
        let duration_raw = serde_json::to_vec(&duration).unwrap();
        let duration_sha = sha256(&duration_raw);
        std::fs::write(root.join(TREATMENT_EFFECT_DURATION_PATH), &duration_raw).unwrap();
        let basis = vec![
            format!("source-materialization-sha256:{materialization_sha}"),
            format!("treatment-effect-duration-sha256:{duration_sha}"),
            "duration-scenario:waning".into(),
        ];
        let sqrt_half = 0.5_f64.sqrt();
        let psm = serde_json::json!({
            "schema_version": "0.4.0",
            "psm_id": "psm",
            "analysis_id": "analysis",
            "treatment_effect_duration": {"path": TREATMENT_EFFECT_DURATION_PATH, "content_sha256": duration_sha},
            "strategies": {
                "comparator": {
                    "pfs": [row(0.0, 1.0, &basis), row(1.0, (-0.5_f64).exp(), &basis), row(2.0, (-1.0_f64).exp(), &basis)],
                    "os": [row(0.0, 1.0, &basis), row(1.0, (-0.2_f64).exp(), &basis), row(2.0, (-0.4_f64).exp(), &basis)]
                },
                "intervention": {
                    "pfs": [row(0.0, 1.0, &basis), row(1.0, (-0.25_f64).exp(), &basis), row(2.0, (-0.25_f64 - sqrt_half * 0.5).exp(), &basis)],
                    "os": [row(0.0, 1.0, &basis), row(1.0, (-0.1_f64).exp(), &basis), row(2.0, (-0.1_f64 - sqrt_half * 0.2).exp(), &basis)]
                }
            }
        });
        let audit =
            audit_treatment_effect_duration(&root, &plan, &plan_raw, &psm, &materialization_sha);
        assert!(audit.complete, "{:?}", audit.errors);
        assert_eq!(audit.scenario_count, 3);
        std::fs::write(
            root.join(TREATMENT_EFFECT_DURATION_PATH),
            b"{\"changed\":true}",
        )
        .unwrap();
        let stale =
            audit_treatment_effect_duration(&root, &plan, &plan_raw, &psm, &materialization_sha);
        assert!(!stale.complete);
        assert!(stale.errors.iter().any(|error| error.contains("hash")));
        let _ = std::fs::remove_dir_all(root);
    }
}
