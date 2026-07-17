//! Native full replay and app-owned Human review for bounded semi-Markov microsimulation.

use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const REQUEST_PATH: &str = "heor/semi-markov-microsimulation-request.json";
const REQUEST_SCHEMA: &str = "0.1.0";
const RESULT_SCHEMA: &str = "0.1.0";
const REVIEW_SCHEMA: &str = "0.1.0";
const REVIEW_EVENT_SCHEMA: u32 = 1;
const REVIEW_ASSURANCE: &str = "app_owned_local_human_assertion";
const EVALUATOR: &str = "ai4heor-semi-markov-microsimulation@0.1.0";
const MAX_JSON_BYTES: u64 = 16 * 1024 * 1024;
const MAX_TRACE_BYTES: u64 = 64 * 1024 * 1024;
const MAX_SIMULATION_STEPS: usize = 5_000_000;
const MASK64: u64 = u64::MAX;
const TOLERANCE: f64 = 1e-8;
const EVALUATOR_BYTES: &[u8] = include_bytes!(
    "../../../../runtime/skills/core/heor-semi-markov-microsimulation/scripts/microsimulation_contract.py"
);
const REVIEW_CHECKS: [&str; 8] = [
    "decision_problem_and_individual_model_justification",
    "states_horizon_timing_and_absorbing_death",
    "input_provenance_and_population_alignment",
    "time_in_state_rules_and_state_rewards",
    "history_trackers_and_transition_event_costs",
    "prng_seeds_common_random_numbers_and_traces",
    "monte_carlo_error_replicates_and_performance",
    "structural_parameter_uncertainty_and_downstream_limits",
];

#[derive(Default)]
pub struct MicrosimulationReviewState(pub Mutex<()>);

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MicrosimulationComparisonAudit {
    pub baseline_strategy_id: String,
    pub strategy_id: String,
    pub incremental_cost: f64,
    pub incremental_qaly: f64,
    pub incremental_net_monetary_benefit: f64,
    pub standard_error_incremental_net_monetary_benefit: f64,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MicrosimulationAudit {
    pub complete: bool,
    pub reviewable: bool,
    pub status: String,
    pub simulation_id: String,
    pub request_path: String,
    pub request_sha256: Option<String>,
    pub result_path: String,
    pub result_sha256: Option<String>,
    pub state_count: usize,
    pub strategy_count: usize,
    pub tracker_count: usize,
    pub patients_per_replicate: usize,
    pub replicates: usize,
    pub cycles: usize,
    pub simulation_steps: usize,
    pub trace_rows: usize,
    pub comparisons: Vec<MicrosimulationComparisonAudit>,
    pub native_scope: String,
    pub limitations: Vec<String>,
    pub errors: Vec<String>,
}

impl Default for MicrosimulationAudit {
    fn default() -> Self {
        Self {
            complete: false,
            reviewable: false,
            status: "unavailable".into(),
            simulation_id: String::new(),
            request_path: REQUEST_PATH.into(),
            request_sha256: None,
            result_path: String::new(),
            result_sha256: None,
            state_count: 0,
            strategy_count: 0,
            tracker_count: 0,
            patients_per_replicate: 0,
            replicates: 0,
            cycles: 0,
            simulation_steps: 0,
            trace_rows: 0,
            comparisons: Vec::new(),
            native_scope: "complete_patient_cycle_summary_and_sampled_trace_replay".into(),
            limitations: Vec::new(),
            errors: Vec::new(),
        }
    }
}

#[derive(Clone)]
struct Tracker {
    id: String,
    from_states: HashSet<usize>,
    to_state: usize,
    cap: usize,
}

#[derive(Clone)]
struct Condition {
    time: (usize, usize),
    trackers: HashMap<usize, (usize, usize)>,
}

#[derive(Clone)]
struct Rule {
    id: String,
    condition: Option<Condition>,
    probabilities: Vec<f64>,
    annual_cost: f64,
    utility: f64,
}

#[derive(Clone)]
struct Strategy {
    id: String,
    label: String,
    rules: Vec<Vec<Rule>>,
    transition_costs: HashMap<(usize, usize), f64>,
}

#[derive(Default)]
struct RequestFacts {
    simulation_id: String,
    evidence_path: String,
    evidence_sha256: String,
    output_directory: String,
    states: Vec<String>,
    absorbing: Vec<bool>,
    death: usize,
    initial: Vec<f64>,
    cycle_length: f64,
    cycles: usize,
    trackers: Vec<Tracker>,
    strategies: Vec<Strategy>,
    currency: String,
    price_year: u64,
    discount_costs: f64,
    discount_outcomes: f64,
    willingness_to_pay: f64,
    patients: usize,
    replicates: usize,
    seed: u64,
    trace_replicate: usize,
    trace_patients: Vec<usize>,
    limitations: Vec<String>,
}

fn exact(value: &serde_json::Value, fields: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == fields.len() && fields.iter().all(|field| object.contains_key(*field))
    })
}

fn text(value: Option<&serde_json::Value>) -> Option<&str> {
    value
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.is_empty() && *value == value.trim())
}

fn finite(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite())
}

fn string_array(value: Option<&serde_json::Value>) -> Option<Vec<String>> {
    value
        .and_then(serde_json::Value::as_array)
        .and_then(|values| {
            values
                .iter()
                .map(|value| text(Some(value)).map(str::to_string))
                .collect::<Option<Vec<_>>>()
        })
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn safe_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .next()
            .is_some_and(|byte| byte.is_ascii_lowercase())
        && value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'-' | b'_')
        })
}

fn read_capped(path: &Path, cap: u64, label: &str) -> Result<Vec<u8>, String> {
    let metadata =
        std::fs::metadata(path).map_err(|error| format!("{label} unavailable: {error}"))?;
    if metadata.len() > cap {
        return Err(format!("{label} exceeds the size cap"));
    }
    let mut raw = Vec::with_capacity(metadata.len() as usize);
    std::fs::File::open(path)
        .map_err(|error| format!("{label} unavailable: {error}"))?
        .read_to_end(&mut raw)
        .map_err(|error| format!("{label} unreadable: {error}"))?;
    Ok(raw)
}

fn resolve_file(workspace: &Path, relative: &str, label: &str) -> Result<PathBuf, String> {
    let relative_path = Path::new(relative);
    if relative_path.is_absolute()
        || relative_path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(format!("{label} path is unsafe"));
    }
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let candidate = root.join(relative_path);
    if std::fs::symlink_metadata(&candidate).is_ok_and(|metadata| metadata.file_type().is_symlink())
    {
        return Err(format!("{label} must not be a symlink"));
    }
    let resolved = candidate
        .canonicalize()
        .map_err(|error| format!("{label} unavailable: {error}"))?;
    if !resolved.starts_with(&root) || !resolved.is_file() {
        return Err(format!("{label} escapes the workspace or is not a file"));
    }
    Ok(resolved)
}

fn bound_bytes(
    workspace: &Path,
    binding: &serde_json::Value,
    expected_path: Option<&str>,
    label: &str,
    errors: &mut Vec<String>,
) -> Option<(String, Vec<u8>)> {
    if binding
        .as_object()
        .is_none_or(|object| !object.contains_key("path") || !object.contains_key("sha256"))
    {
        errors.push(format!("{label} binding fields are invalid"));
        return None;
    }
    let Some(path) = text(binding.get("path")) else {
        errors.push(format!("{label} path is invalid"));
        return None;
    };
    let Some(expected_hash) = text(binding.get("sha256")) else {
        errors.push(format!("{label} sha256 is invalid"));
        return None;
    };
    if !is_sha256(expected_hash) || expected_path.is_some_and(|expected| expected != path) {
        errors.push(format!("{label} path or sha256 is invalid"));
        return None;
    }
    let resolved = match resolve_file(workspace, path, label) {
        Ok(value) => value,
        Err(error) => {
            errors.push(error);
            return None;
        }
    };
    let raw = match read_capped(&resolved, MAX_TRACE_BYTES, label) {
        Ok(value) => value,
        Err(error) => {
            errors.push(error);
            return None;
        }
    };
    if sha256(&raw) != expected_hash {
        errors.push(format!("{label} sha256 does not match current bytes"));
        return None;
    }
    Some((path.into(), raw))
}

fn evidence_ids(
    value: Option<&serde_json::Value>,
    available: &HashSet<String>,
    label: &str,
    errors: &mut Vec<String>,
) {
    let Some(values) = string_array(value) else {
        errors.push(format!("{label} evidence_record_ids are invalid"));
        return;
    };
    let unique: HashSet<_> = values.iter().collect();
    if values.is_empty() || unique.len() != values.len() || values.iter().any(|id| !safe_id(id)) {
        errors.push(format!("{label} evidence_record_ids are invalid"));
    } else if values.iter().any(|id| !available.contains(id)) {
        errors.push(format!("{label} evidence_record_ids are not all bound"));
    }
}

fn parse_interval(
    value: &serde_json::Value,
    cap: usize,
    label: &str,
    errors: &mut Vec<String>,
) -> Option<(usize, usize)> {
    if !exact(value, &["minimum", "maximum"]) {
        errors.push(format!("{label} interval fields are invalid"));
        return None;
    }
    let Some(minimum) = value.get("minimum").and_then(serde_json::Value::as_u64) else {
        errors.push(format!("{label} minimum is invalid"));
        return None;
    };
    let minimum = minimum as usize;
    let maximum = match value.get("maximum") {
        Some(serde_json::Value::Null) => cap,
        Some(value) => {
            let Some(value) = value.as_u64() else {
                errors.push(format!("{label} maximum is invalid"));
                return None;
            };
            value as usize
        }
        None => {
            errors.push(format!("{label} maximum is missing"));
            return None;
        }
    };
    if minimum > maximum || maximum > cap {
        errors.push(format!("{label} interval is outside its cap"));
        return None;
    }
    Some((minimum, maximum))
}

fn overlap(left: &Condition, right: &Condition, cycles: usize, tracker_caps: &[usize]) -> bool {
    if left.time.0.max(right.time.0) > left.time.1.min(right.time.1) {
        return false;
    }
    (0..tracker_caps.len()).all(|index| {
        let left_interval = left
            .trackers
            .get(&index)
            .copied()
            .unwrap_or((0, tracker_caps[index]));
        let right_interval = right
            .trackers
            .get(&index)
            .copied()
            .unwrap_or((0, tracker_caps[index]));
        left_interval.0.max(right_interval.0) <= left_interval.1.min(right_interval.1)
    }) && left.time.1 <= cycles
        && right.time.1 <= cycles
}

fn validate_request(
    workspace: &Path,
    request: &serde_json::Value,
    errors: &mut Vec<String>,
) -> RequestFacts {
    let mut facts = RequestFacts::default();
    let top_fields = [
        "schema_version",
        "simulation_id",
        "status",
        "question",
        "evidence_synthesis",
        "model",
        "strategies",
        "economics",
        "simulation",
        "output",
        "human_authorization",
        "limitations",
        "human_gate",
    ];
    if !exact(request, &top_fields)
        || text(request.get("schema_version")) != Some(REQUEST_SCHEMA)
        || text(request.get("status")) != Some("ready_for_execution")
    {
        errors.push("microsimulation request top-level contract is invalid".into());
    }
    facts.simulation_id = text(request.get("simulation_id"))
        .unwrap_or_default()
        .into();
    if !safe_id(&facts.simulation_id) {
        errors.push("microsimulation simulation_id is invalid".into());
    }
    let question = &request["question"];
    let question_fields = [
        "population",
        "purpose",
        "time_origin",
        "perspective",
        "intended_use",
        "individual_model_justification",
    ];
    if !exact(question, &question_fields)
        || question_fields
            .iter()
            .any(|field| text(question.get(*field)).is_none())
    {
        errors.push("microsimulation question fields are invalid".into());
    }

    let evidence = &request["evidence_synthesis"];
    let mut available_evidence = HashSet::new();
    if !exact(evidence, &["path", "sha256", "included_record_ids"]) {
        errors.push("microsimulation evidence binding fields are invalid".into());
    } else {
        facts.evidence_path = text(evidence.get("path")).unwrap_or_default().into();
        facts.evidence_sha256 = text(evidence.get("sha256")).unwrap_or_default().into();
        let included = string_array(evidence.get("included_record_ids")).unwrap_or_default();
        if included.is_empty()
            || included.iter().any(|id| !safe_id(id))
            || included.iter().collect::<HashSet<_>>().len() != included.len()
        {
            errors.push("microsimulation included evidence ids are invalid".into());
        }
        available_evidence.extend(included.iter().cloned());
        match resolve_file(workspace, &facts.evidence_path, "microsimulation evidence")
            .and_then(|path| read_capped(&path, MAX_JSON_BYTES, "microsimulation evidence"))
        {
            Ok(raw) => {
                if !is_sha256(&facts.evidence_sha256) || sha256(&raw) != facts.evidence_sha256 {
                    errors.push(
                        "microsimulation evidence sha256 does not match current bytes".into(),
                    );
                }
                match serde_json::from_slice::<serde_json::Value>(&raw) {
                    Ok(value) => {
                        let records: HashSet<String> = value
                            .get("records")
                            .and_then(serde_json::Value::as_array)
                            .into_iter()
                            .flatten()
                            .filter_map(|record| {
                                record.as_str().or_else(|| {
                                    record.get("id").and_then(serde_json::Value::as_str)
                                })
                            })
                            .map(str::to_string)
                            .collect();
                        if !available_evidence.is_subset(&records) {
                            errors.push(
                                "microsimulation evidence does not contain every included record"
                                    .into(),
                            );
                        }
                    }
                    Err(error) => {
                        errors.push(format!("microsimulation evidence is invalid JSON: {error}"))
                    }
                }
            }
            Err(error) => errors.push(error),
        }
    }

    let model = &request["model"];
    let model_fields = [
        "type",
        "states",
        "initial_distribution",
        "cycle_length_years",
        "cycles",
        "transition_timing",
        "reward_timing",
        "interactions",
        "event_trackers",
    ];
    if !exact(model, &model_fields)
        || text(model.get("type")) != Some("discrete_time_individual_state_transition")
        || text(model.get("transition_timing")) != Some("one_transition_at_cycle_end")
        || text(model.get("reward_timing"))
            != Some("trapezoidal_state_rewards_transition_costs_at_cycle_end")
        || text(model.get("interactions")) != Some("none_closed_independent_cohort")
    {
        errors.push("microsimulation model family or timing contract is invalid".into());
    }
    let states = model
        .get("states")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut state_index = HashMap::new();
    let mut death_indices = Vec::new();
    for (index, state) in states.iter().enumerate() {
        if !exact(state, &["id", "label", "absorbing", "death"]) {
            errors.push(format!("microsimulation state {index} fields are invalid"));
            continue;
        }
        let id = text(state.get("id")).unwrap_or_default();
        let label = text(state.get("label"));
        let absorbing = state.get("absorbing").and_then(serde_json::Value::as_bool);
        let death = state.get("death").and_then(serde_json::Value::as_bool);
        if !safe_id(id)
            || label.is_none()
            || absorbing.is_none()
            || death.is_none()
            || state_index.contains_key(id)
        {
            errors.push(format!("microsimulation state {index} values are invalid"));
            continue;
        }
        let compact_index = facts.states.len();
        state_index.insert(id.to_string(), compact_index);
        facts.states.push(id.into());
        facts.absorbing.push(absorbing.unwrap_or(false));
        if death == Some(true) {
            death_indices.push(compact_index);
            if absorbing != Some(true) {
                errors.push("microsimulation death state must be absorbing".into());
            }
        }
    }
    if !(2..=8).contains(&facts.states.len()) || death_indices.len() != 1 {
        errors.push(
            "microsimulation requires 2-8 states and exactly one absorbing death state".into(),
        );
    } else {
        facts.death = death_indices[0];
    }
    facts.initial = model
        .get("initial_distribution")
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(|value| finite(Some(value)))
                .collect()
        })
        .unwrap_or_default();
    if facts.initial.len() != facts.states.len()
        || facts
            .initial
            .iter()
            .any(|value| !(0.0..=1.0).contains(value))
        || (facts.initial.iter().sum::<f64>() - 1.0).abs() > 1e-10
        || facts.initial.get(facts.death).copied().unwrap_or(1.0) != 0.0
    {
        errors.push("microsimulation initial distribution is invalid".into());
    }
    facts.cycle_length = finite(model.get("cycle_length_years")).unwrap_or_default();
    facts.cycles = model
        .get("cycles")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or_default() as usize;
    if !(0.0 < facts.cycle_length && facts.cycle_length <= 5.0)
        || !(1..=600).contains(&facts.cycles)
    {
        errors.push("microsimulation cycle length or horizon is invalid".into());
    }

    let tracker_values = model
        .get("event_trackers")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut tracker_index = HashMap::new();
    for (index, tracker) in tracker_values.iter().enumerate() {
        let fields = [
            "id",
            "label",
            "from_states",
            "to_state",
            "maximum_count",
            "rationale",
            "evidence_record_ids",
        ];
        if !exact(tracker, &fields) {
            errors.push(format!(
                "microsimulation tracker {index} fields are invalid"
            ));
            continue;
        }
        let id = text(tracker.get("id")).unwrap_or_default();
        let from_state_ids = string_array(tracker.get("from_states")).unwrap_or_default();
        let from_states: HashSet<usize> = from_state_ids
            .iter()
            .filter_map(|state| state_index.get(state).copied())
            .collect();
        let to_state =
            text(tracker.get("to_state")).and_then(|state| state_index.get(state).copied());
        let cap = tracker
            .get("maximum_count")
            .and_then(serde_json::Value::as_u64)
            .unwrap_or_default() as usize;
        let valid = safe_id(id)
            && text(tracker.get("label")).is_some()
            && text(tracker.get("rationale")).is_some()
            && !tracker_index.contains_key(id)
            && !from_states.is_empty()
            && from_states.len() == from_state_ids.len()
            && to_state.is_some()
            && !to_state.is_some_and(|state| from_states.contains(&state))
            && (1..=facts.cycles.max(1)).contains(&cap);
        if !valid {
            errors.push(format!(
                "microsimulation tracker {index} values are invalid"
            ));
        }
        evidence_ids(
            tracker.get("evidence_record_ids"),
            &available_evidence,
            "microsimulation tracker",
            errors,
        );
        if !valid {
            continue;
        }
        tracker_index.insert(id.to_string(), facts.trackers.len());
        facts.trackers.push(Tracker {
            id: id.into(),
            from_states,
            to_state: to_state.unwrap_or_default(),
            cap,
        });
    }
    if !(1..=3).contains(&facts.trackers.len()) {
        errors.push("microsimulation requires 1-3 event trackers".into());
    }
    let tracker_caps: Vec<usize> = facts.trackers.iter().map(|tracker| tracker.cap).collect();

    let strategy_values = request
        .get("strategies")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut strategy_ids = HashSet::new();
    for (strategy_number, strategy) in strategy_values.iter().enumerate() {
        let fields = [
            "id",
            "label",
            "rationale",
            "evidence_record_ids",
            "state_rules",
            "transition_costs",
        ];
        if !exact(strategy, &fields) {
            errors.push(format!(
                "microsimulation strategy {strategy_number} fields are invalid"
            ));
            continue;
        }
        let id = text(strategy.get("id")).unwrap_or_default();
        let label = text(strategy.get("label")).unwrap_or_default();
        if !safe_id(id)
            || label.is_empty()
            || text(strategy.get("rationale")).is_none()
            || !strategy_ids.insert(id.to_string())
        {
            errors.push(format!(
                "microsimulation strategy {strategy_number} values are invalid"
            ));
        }
        evidence_ids(
            strategy.get("evidence_record_ids"),
            &available_evidence,
            "microsimulation strategy",
            errors,
        );
        let mut rules_by_state = vec![Vec::<Rule>::new(); facts.states.len()];
        let mut seen_states = HashSet::new();
        let mut rule_ids = HashSet::new();
        for state_entry in strategy
            .get("state_rules")
            .and_then(serde_json::Value::as_array)
            .into_iter()
            .flatten()
        {
            if !exact(state_entry, &["state_id", "rules"]) {
                errors.push(format!(
                    "microsimulation strategy {id} state-rule fields are invalid"
                ));
                continue;
            }
            let Some(state) =
                text(state_entry.get("state_id")).and_then(|state| state_index.get(state).copied())
            else {
                errors.push(format!(
                    "microsimulation strategy {id} state-rule id is invalid"
                ));
                continue;
            };
            if !seen_states.insert(state) {
                errors.push(format!(
                    "microsimulation strategy {id} duplicates a state-rule entry"
                ));
            }
            let rule_values = state_entry
                .get("rules")
                .and_then(serde_json::Value::as_array)
                .cloned()
                .unwrap_or_default();
            let mut conditional = Vec::<(String, Condition)>::new();
            let mut fallback_count = 0;
            for (rule_number, rule) in rule_values.iter().enumerate() {
                let fields = [
                    "id",
                    "condition",
                    "probabilities",
                    "annual_cost",
                    "utility",
                    "rationale",
                    "evidence_record_ids",
                ];
                if !exact(rule, &fields) {
                    errors.push(format!(
                        "microsimulation strategy {id} rule fields are invalid"
                    ));
                    continue;
                }
                let rule_id = text(rule.get("id")).unwrap_or_default();
                if !safe_id(rule_id)
                    || !rule_ids.insert(rule_id.to_string())
                    || text(rule.get("rationale")).is_none()
                {
                    errors.push(format!(
                        "microsimulation strategy {id} rule id or rationale is invalid"
                    ));
                }
                evidence_ids(
                    rule.get("evidence_record_ids"),
                    &available_evidence,
                    "microsimulation rule",
                    errors,
                );
                let condition_value = &rule["condition"];
                let condition = if exact(condition_value, &["kind"])
                    && text(condition_value.get("kind")) == Some("otherwise")
                {
                    fallback_count += 1;
                    if rule_number + 1 != rule_values.len() {
                        errors.push(format!(
                            "microsimulation strategy {id} otherwise rule must be last"
                        ));
                    }
                    None
                } else if exact(
                    condition_value,
                    &["kind", "time_in_state_cycles", "tracker_counts"],
                ) && text(condition_value.get("kind")) == Some("when")
                {
                    let time = parse_interval(
                        &condition_value["time_in_state_cycles"],
                        facts.cycles,
                        "microsimulation time-in-state",
                        errors,
                    )
                    .unwrap_or((0, facts.cycles));
                    let mut tracker_ranges = HashMap::new();
                    for tracker_range in condition_value
                        .get("tracker_counts")
                        .and_then(serde_json::Value::as_array)
                        .into_iter()
                        .flatten()
                    {
                        if !exact(tracker_range, &["tracker_id", "minimum", "maximum"]) {
                            errors.push(
                                "microsimulation tracker condition fields are invalid".into(),
                            );
                            continue;
                        }
                        let Some(tracker) = text(tracker_range.get("tracker_id"))
                            .and_then(|id| tracker_index.get(id).copied())
                        else {
                            errors.push("microsimulation tracker condition id is invalid".into());
                            continue;
                        };
                        let interval_value = serde_json::json!({
                            "minimum": tracker_range.get("minimum"),
                            "maximum": tracker_range.get("maximum"),
                        });
                        let interval = parse_interval(
                            &interval_value,
                            tracker_caps[tracker],
                            "microsimulation tracker condition",
                            errors,
                        )
                        .unwrap_or((0, tracker_caps[tracker]));
                        if tracker_ranges.insert(tracker, interval).is_some() {
                            errors
                                .push("microsimulation tracker condition id is duplicated".into());
                        }
                    }
                    let value = Condition {
                        time,
                        trackers: tracker_ranges,
                    };
                    conditional.push((rule_id.into(), value.clone()));
                    Some(value)
                } else {
                    errors.push(format!(
                        "microsimulation strategy {id} rule condition is invalid"
                    ));
                    None
                };
                let probabilities: Vec<f64> = rule
                    .get("probabilities")
                    .and_then(serde_json::Value::as_array)
                    .map(|values| {
                        values
                            .iter()
                            .filter_map(|value| finite(Some(value)))
                            .collect()
                    })
                    .unwrap_or_default();
                let annual_cost = finite(rule.get("annual_cost")).unwrap_or(-1.0);
                let utility = finite(rule.get("utility")).unwrap_or(2.0);
                if probabilities.len() != facts.states.len()
                    || probabilities
                        .iter()
                        .any(|value| !(0.0..=1.0).contains(value))
                    || (probabilities.iter().sum::<f64>() - 1.0).abs() > 1e-10
                    || annual_cost < 0.0
                    || !(-1.0..=1.0).contains(&utility)
                {
                    errors.push(format!(
                        "microsimulation strategy {id} rule probabilities or rewards are invalid"
                    ));
                }
                if facts.absorbing.get(state).copied().unwrap_or(false)
                    && probabilities.iter().enumerate().any(|(index, value)| {
                        (*value - if index == state { 1.0 } else { 0.0 }).abs() > 1e-12
                    })
                {
                    errors.push(format!(
                        "microsimulation strategy {id} absorbing row is invalid"
                    ));
                }
                if state == facts.death && (annual_cost != 0.0 || utility != 0.0) {
                    errors.push(format!(
                        "microsimulation strategy {id} death rewards must be zero"
                    ));
                }
                rules_by_state[state].push(Rule {
                    id: rule_id.into(),
                    condition,
                    probabilities,
                    annual_cost,
                    utility,
                });
            }
            if fallback_count != 1 {
                errors.push(format!(
                    "microsimulation strategy {id} requires one final otherwise rule per state"
                ));
            }
            for left in 0..conditional.len() {
                for right in left + 1..conditional.len() {
                    if overlap(
                        &conditional[left].1,
                        &conditional[right].1,
                        facts.cycles,
                        &tracker_caps,
                    ) {
                        errors.push(format!(
                            "microsimulation strategy {id} rules {} and {} overlap",
                            conditional[left].0, conditional[right].0
                        ));
                    }
                }
            }
        }
        if seen_states.len() != facts.states.len() || rules_by_state.iter().any(Vec::is_empty) {
            errors.push(format!(
                "microsimulation strategy {id} must cover every state exactly once"
            ));
        }
        let mut transition_costs = HashMap::new();
        let mut transition_cost_ids = HashSet::new();
        for entry in strategy
            .get("transition_costs")
            .and_then(serde_json::Value::as_array)
            .into_iter()
            .flatten()
        {
            let fields = [
                "id",
                "from_state",
                "to_state",
                "cost",
                "rationale",
                "evidence_record_ids",
            ];
            if !exact(entry, &fields) {
                errors.push(format!(
                    "microsimulation strategy {id} transition-cost fields are invalid"
                ));
                continue;
            }
            let entry_id = text(entry.get("id")).unwrap_or_default();
            let from =
                text(entry.get("from_state")).and_then(|state| state_index.get(state).copied());
            let to = text(entry.get("to_state")).and_then(|state| state_index.get(state).copied());
            let cost = finite(entry.get("cost")).unwrap_or(-1.0);
            if !safe_id(entry_id)
                || !transition_cost_ids.insert(entry_id.to_string())
                || text(entry.get("rationale")).is_none()
                || from.is_none()
                || to.is_none()
                || from == to
                || cost < 0.0
                || transition_costs
                    .insert((from.unwrap_or_default(), to.unwrap_or_default()), cost)
                    .is_some()
            {
                errors.push(format!(
                    "microsimulation strategy {id} transition cost is invalid"
                ));
            }
            evidence_ids(
                entry.get("evidence_record_ids"),
                &available_evidence,
                "microsimulation transition cost",
                errors,
            );
        }
        facts.strategies.push(Strategy {
            id: id.into(),
            label: label.into(),
            rules: rules_by_state,
            transition_costs,
        });
    }
    if !(2..=4).contains(&facts.strategies.len()) || strategy_ids.len() != facts.strategies.len() {
        errors.push("microsimulation requires 2-4 unique strategies".into());
    }

    let economics = &request["economics"];
    if !exact(
        economics,
        &[
            "currency",
            "price_year",
            "discount_rate_costs",
            "discount_rate_outcomes",
            "willingness_to_pay",
        ],
    ) {
        errors.push("microsimulation economics fields are invalid".into());
    }
    facts.currency = text(economics.get("currency")).unwrap_or_default().into();
    facts.price_year = economics
        .get("price_year")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or_default();
    facts.discount_costs = finite(economics.get("discount_rate_costs")).unwrap_or(-1.0);
    facts.discount_outcomes = finite(economics.get("discount_rate_outcomes")).unwrap_or(-1.0);
    facts.willingness_to_pay = finite(economics.get("willingness_to_pay")).unwrap_or_default();
    if facts.currency.len() != 3
        || !facts.currency.bytes().all(|byte| byte.is_ascii_uppercase())
        || !(1900..=2100).contains(&facts.price_year)
        || !(0.0..=1.0).contains(&facts.discount_costs)
        || !(0.0..=1.0).contains(&facts.discount_outcomes)
        || facts.willingness_to_pay <= 0.0
    {
        errors.push("microsimulation economics values are invalid".into());
    }

    let simulation = &request["simulation"];
    let simulation_fields = [
        "patients_per_replicate",
        "replicates",
        "base_seed",
        "random_number_generator",
        "common_random_numbers",
        "trace_replicate",
        "trace_patient_indices",
        "maximum_simulation_steps",
    ];
    if !exact(simulation, &simulation_fields)
        || text(simulation.get("random_number_generator")) != Some("splitmix64_counter_top53_v1")
        || text(simulation.get("common_random_numbers"))
            != Some("synchronized_initial_and_cycle_transition_uniforms")
        || simulation
            .get("maximum_simulation_steps")
            .and_then(serde_json::Value::as_u64)
            != Some(MAX_SIMULATION_STEPS as u64)
    {
        errors.push("microsimulation random-number or performance contract is invalid".into());
    }
    facts.patients = simulation
        .get("patients_per_replicate")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or_default() as usize;
    facts.replicates = simulation
        .get("replicates")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or_default() as usize;
    facts.seed = simulation
        .get("base_seed")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or(u64::MAX);
    facts.trace_replicate = simulation
        .get("trace_replicate")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or(u64::MAX) as usize;
    facts.trace_patients = simulation
        .get("trace_patient_indices")
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(serde_json::Value::as_u64)
                .map(|value| value as usize)
                .collect()
        })
        .unwrap_or_default();
    let steps = facts
        .patients
        .saturating_mul(facts.replicates)
        .saturating_mul(facts.cycles)
        .saturating_mul(facts.strategies.len());
    if !(100..=50_000).contains(&facts.patients)
        || !(3..=20).contains(&facts.replicates)
        || facts.seed > (1_u64 << 53) - 1
        || facts.trace_replicate >= facts.replicates
        || facts.trace_patients.is_empty()
        || facts.trace_patients.len() > 20
        || facts.trace_patients.iter().collect::<HashSet<_>>().len() != facts.trace_patients.len()
        || facts
            .trace_patients
            .iter()
            .any(|patient| *patient >= facts.patients)
        || steps > MAX_SIMULATION_STEPS
    {
        errors.push("microsimulation sample, trace, seed, or step count is invalid".into());
    }

    facts.output_directory = text(request.pointer("/output/directory"))
        .unwrap_or_default()
        .into();
    let expected_output = format!(
        "heor/semi-markov-microsimulation-runs/{}",
        facts.simulation_id
    );
    if !exact(&request["output"], &["directory"]) || facts.output_directory != expected_output {
        errors.push("microsimulation output directory is invalid".into());
    }
    let authorization = &request["human_authorization"];
    if !exact(authorization, &["actor", "authorized_at", "scope"])
        || text(authorization.get("actor")).is_none()
        || text(authorization.get("authorized_at")).is_none()
        || text(authorization.get("scope")) != Some("execute_local_semi_markov_microsimulation")
    {
        errors.push("microsimulation Human execution authorization is invalid".into());
    }
    facts.limitations = string_array(request.get("limitations")).unwrap_or_default();
    if facts.limitations.is_empty() {
        errors.push("microsimulation limitations are invalid".into());
    }
    let expected_gate = serde_json::json!({
        "status": "awaiting_method_review",
        "required_checks": REVIEW_CHECKS,
    });
    if request.get("human_gate") != Some(&expected_gate) {
        errors.push("microsimulation Human method gate is invalid".into());
    }
    facts
}

fn splitmix64(mut value: u64) -> u64 {
    value = value.wrapping_add(0x9E3779B97F4A7C15);
    value = (value ^ (value >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
    value = (value ^ (value >> 27)).wrapping_mul(0x94D049BB133111EB);
    value ^ (value >> 31)
}

fn counter_uniform(
    seed: u64,
    replicate: usize,
    patient: usize,
    cycle: usize,
    stream: usize,
) -> f64 {
    let mut value = seed & MASK64;
    value ^= (replicate as u64 + 1).wrapping_mul(0xD2B74407B1CE6E93);
    value ^= (patient as u64 + 1).wrapping_mul(0xCA5A826395121157);
    value ^= (cycle as u64 + 1).wrapping_mul(0x9E3779B185EBCA87);
    value ^= (stream as u64 + 1).wrapping_mul(0xA24BAED4963EE407);
    ((splitmix64(value) >> 11) as f64) * (1.0 / ((1_u64 << 53) as f64))
}

fn draw(probabilities: &[f64], uniform: f64) -> usize {
    let mut cumulative = 0.0;
    for (index, probability) in probabilities.iter().enumerate() {
        cumulative += probability;
        if uniform < cumulative || index + 1 == probabilities.len() {
            return index;
        }
    }
    probabilities.len().saturating_sub(1)
}

fn rule_matches(condition: &Condition, dwell: usize, trackers: &[usize]) -> bool {
    condition.time.0 <= dwell
        && dwell <= condition.time.1
        && condition.trackers.iter().all(|(index, interval)| {
            interval.0 <= trackers[*index] && trackers[*index] <= interval.1
        })
}

fn select_rule<'a>(
    rules: &'a [Rule],
    dwell: usize,
    trackers: &[usize],
) -> Result<&'a Rule, String> {
    let matches: Vec<&Rule> = rules
        .iter()
        .filter(|rule| {
            rule.condition
                .as_ref()
                .is_some_and(|condition| rule_matches(condition, dwell, trackers))
        })
        .collect();
    if matches.len() > 1 {
        return Err("native microsimulation matched overlapping conditional rules".into());
    }
    matches
        .first()
        .copied()
        .or_else(|| rules.iter().find(|rule| rule.condition.is_none()))
        .ok_or_else(|| "native microsimulation found no applicable rule".into())
}

#[derive(Clone)]
struct PatientResult {
    cost: f64,
    qaly: f64,
    life_years: f64,
    trackers: Vec<usize>,
}

#[derive(Clone)]
struct ReplicateResult {
    cost: f64,
    qaly: f64,
    life_years: f64,
}

fn mean_se(values: &[f64]) -> (f64, f64) {
    let mean = values.iter().sum::<f64>() / values.len() as f64;
    if values.len() == 1 {
        return (mean, 0.0);
    }
    let variance = values
        .iter()
        .map(|value| (value - mean).powi(2))
        .sum::<f64>()
        / (values.len() - 1) as f64;
    (mean, (variance / values.len() as f64).sqrt())
}

fn sample_sd(values: &[f64]) -> f64 {
    if values.len() < 2 {
        return 0.0;
    }
    let mean = values.iter().sum::<f64>() / values.len() as f64;
    (values
        .iter()
        .map(|value| (value - mean).powi(2))
        .sum::<f64>()
        / (values.len() - 1) as f64)
        .sqrt()
}

struct NativeExecution {
    method: serde_json::Value,
    performance: serde_json::Value,
    strategies: serde_json::Value,
    comparisons: serde_json::Value,
    monte_carlo_error: serde_json::Value,
    warnings: serde_json::Value,
    traces: Vec<serde_json::Value>,
}

fn execute_native(facts: &RequestFacts) -> Result<NativeExecution, String> {
    let total_people = facts.patients * facts.replicates;
    let trace_patients: HashSet<usize> = facts.trace_patients.iter().copied().collect();
    let mut all_patient_results = HashMap::<String, Vec<PatientResult>>::new();
    let mut all_replicates = HashMap::<String, Vec<ReplicateResult>>::new();
    let mut strategy_values = Vec::new();
    let mut traces = Vec::new();
    for strategy in &facts.strategies {
        let mut patient_results = Vec::with_capacity(total_people);
        let mut replicate_results = Vec::with_capacity(facts.replicates);
        let mut occupancy = vec![vec![0_usize; facts.states.len()]; facts.cycles + 1];
        for replicate in 0..facts.replicates {
            let replicate_start = patient_results.len();
            for patient in 0..facts.patients {
                let initial_uniform = counter_uniform(facts.seed, replicate, patient, 0, 0);
                let mut state = draw(&facts.initial, initial_uniform);
                let mut dwell = 0_usize;
                let mut tracker_counts = vec![0_usize; facts.trackers.len()];
                let mut total_cost = 0.0;
                let mut total_qaly = 0.0;
                let mut total_life = 0.0;
                occupancy[0][state] += 1;
                for (cycle, occupancy_row) in occupancy
                    .iter_mut()
                    .enumerate()
                    .take(facts.cycles + 1)
                    .skip(1)
                {
                    let start_state = state;
                    let start_dwell = dwell;
                    let start_trackers = tracker_counts.clone();
                    let start_rule =
                        select_rule(&strategy.rules[start_state], start_dwell, &start_trackers)?;
                    let transition_uniform =
                        counter_uniform(facts.seed, replicate, patient, cycle, 1);
                    let end_state = draw(&start_rule.probabilities, transition_uniform);
                    let mut end_trackers = start_trackers.clone();
                    for (index, tracker) in facts.trackers.iter().enumerate() {
                        if tracker.from_states.contains(&start_state)
                            && tracker.to_state == end_state
                        {
                            end_trackers[index] = (end_trackers[index] + 1).min(tracker.cap);
                        }
                    }
                    let end_dwell = if start_state == end_state {
                        start_dwell + 1
                    } else {
                        0
                    };
                    let end_rule =
                        select_rule(&strategy.rules[end_state], end_dwell, &end_trackers)?;
                    let start_time = (cycle - 1) as f64 * facts.cycle_length;
                    let end_time = cycle as f64 * facts.cycle_length;
                    let start_cost = 0.5 * start_rule.annual_cost * facts.cycle_length
                        / (1.0 + facts.discount_costs).powf(start_time);
                    let end_cost = 0.5 * end_rule.annual_cost * facts.cycle_length
                        / (1.0 + facts.discount_costs).powf(end_time);
                    let transition_cost = strategy
                        .transition_costs
                        .get(&(start_state, end_state))
                        .copied()
                        .unwrap_or_default()
                        / (1.0 + facts.discount_costs).powf(end_time);
                    let qaly = 0.5 * start_rule.utility * facts.cycle_length
                        / (1.0 + facts.discount_outcomes).powf(start_time)
                        + 0.5 * end_rule.utility * facts.cycle_length
                            / (1.0 + facts.discount_outcomes).powf(end_time);
                    let life =
                        0.5 * (if start_state == facts.death {
                            0.0
                        } else {
                            facts.cycle_length
                        }) / (1.0 + facts.discount_outcomes).powf(start_time)
                            + 0.5
                                * (if end_state == facts.death {
                                    0.0
                                } else {
                                    facts.cycle_length
                                })
                                / (1.0 + facts.discount_outcomes).powf(end_time);
                    total_cost += start_cost + end_cost + transition_cost;
                    total_qaly += qaly;
                    total_life += life;
                    if replicate == facts.trace_replicate && trace_patients.contains(&patient) {
                        let start_tracker_json: serde_json::Map<String, serde_json::Value> = facts
                            .trackers
                            .iter()
                            .enumerate()
                            .map(|(index, tracker)| {
                                (tracker.id.clone(), serde_json::json!(start_trackers[index]))
                            })
                            .collect();
                        let end_tracker_json: serde_json::Map<String, serde_json::Value> = facts
                            .trackers
                            .iter()
                            .enumerate()
                            .map(|(index, tracker)| {
                                (tracker.id.clone(), serde_json::json!(end_trackers[index]))
                            })
                            .collect();
                        traces.push(serde_json::json!({
                            "simulation_id": facts.simulation_id,
                            "strategy_id": strategy.id,
                            "replicate": replicate,
                            "patient_index": patient,
                            "cycle": cycle,
                            "initial_uniform": if cycle == 1 { Some(initial_uniform) } else { None },
                            "transition_uniform": transition_uniform,
                            "start_state": facts.states[start_state],
                            "start_time_in_state_cycles": start_dwell,
                            "start_tracker_counts": start_tracker_json,
                            "rule_id": start_rule.id,
                            "end_state": facts.states[end_state],
                            "end_time_in_state_cycles": end_dwell,
                            "end_tracker_counts": end_tracker_json,
                            "state_cost": start_cost + end_cost,
                            "transition_cost": transition_cost,
                            "discounted_qaly": qaly,
                            "discounted_life_years": life,
                            "cumulative_cost": total_cost,
                            "cumulative_qaly": total_qaly,
                        }));
                    }
                    state = end_state;
                    dwell = end_dwell;
                    tracker_counts = end_trackers;
                    occupancy_row[state] += 1;
                }
                patient_results.push(PatientResult {
                    cost: total_cost,
                    qaly: total_qaly,
                    life_years: total_life,
                    trackers: tracker_counts,
                });
            }
            let rows = &patient_results[replicate_start..];
            replicate_results.push(ReplicateResult {
                cost: rows.iter().map(|row| row.cost).sum::<f64>() / facts.patients as f64,
                qaly: rows.iter().map(|row| row.qaly).sum::<f64>() / facts.patients as f64,
                life_years: rows.iter().map(|row| row.life_years).sum::<f64>()
                    / facts.patients as f64,
            });
        }
        let costs: Vec<f64> = patient_results.iter().map(|row| row.cost).collect();
        let qalys: Vec<f64> = patient_results.iter().map(|row| row.qaly).collect();
        let life: Vec<f64> = patient_results.iter().map(|row| row.life_years).collect();
        let (mean_cost, se_cost) = mean_se(&costs);
        let (mean_qaly, se_qaly) = mean_se(&qalys);
        let (mean_life, se_life) = mean_se(&life);
        let tracker_summary: serde_json::Map<String, serde_json::Value> = facts.trackers.iter().enumerate().map(|(index, tracker)| {
            let values: Vec<usize> = patient_results.iter().map(|row| row.trackers[index]).collect();
            (tracker.id.clone(), serde_json::json!({
                "mean_final_count": values.iter().sum::<usize>() as f64 / values.len() as f64,
                "proportion_with_any": values.iter().filter(|value| **value > 0).count() as f64 / values.len() as f64,
                "proportion_at_cap": values.iter().filter(|value| **value >= tracker.cap).count() as f64 / values.len() as f64,
            }))
        }).collect();
        let occupancy_json: Vec<serde_json::Value> = occupancy
            .iter()
            .enumerate()
            .map(|(cycle, counts)| {
                let proportions: serde_json::Map<String, serde_json::Value> = facts
                    .states
                    .iter()
                    .enumerate()
                    .map(|(index, state)| {
                        (
                            state.clone(),
                            serde_json::json!(counts[index] as f64 / total_people as f64),
                        )
                    })
                    .collect();
                serde_json::json!({"cycle": cycle, "proportions": proportions})
            })
            .collect();
        let replicate_json: Vec<serde_json::Value> = replicate_results
            .iter()
            .enumerate()
            .map(|(replicate, row)| {
                serde_json::json!({
                    "replicate": replicate,
                    "mean_cost": row.cost,
                    "mean_qaly": row.qaly,
                    "mean_life_years": row.life_years,
                })
            })
            .collect();
        strategy_values.push(serde_json::json!({
            "id": strategy.id,
            "label": strategy.label,
            "mean_cost": mean_cost,
            "standard_error_cost": se_cost,
            "mean_qaly": mean_qaly,
            "standard_error_qaly": se_qaly,
            "mean_life_years": mean_life,
            "standard_error_life_years": se_life,
            "tracker_summary": tracker_summary,
            "state_occupancy": occupancy_json,
            "replicate_estimates": replicate_json,
        }));
        all_patient_results.insert(strategy.id.clone(), patient_results);
        all_replicates.insert(strategy.id.clone(), replicate_results);
    }

    let baseline = &facts.strategies[0].id;
    let mut comparison_values = Vec::new();
    let baseline_rows = &all_patient_results[baseline];
    for strategy in facts.strategies.iter().skip(1) {
        let rows = &all_patient_results[&strategy.id];
        let delta_costs: Vec<f64> = baseline_rows
            .iter()
            .zip(rows)
            .map(|(left, right)| right.cost - left.cost)
            .collect();
        let delta_qalys: Vec<f64> = baseline_rows
            .iter()
            .zip(rows)
            .map(|(left, right)| right.qaly - left.qaly)
            .collect();
        let delta_nmbs: Vec<f64> = delta_costs
            .iter()
            .zip(&delta_qalys)
            .map(|(cost, qaly)| facts.willingness_to_pay * qaly - cost)
            .collect();
        let (delta_cost, se_cost) = mean_se(&delta_costs);
        let (delta_qaly, se_qaly) = mean_se(&delta_qalys);
        let (delta_nmb, se_nmb) = mean_se(&delta_nmbs);
        let (classification, icer) = if delta_qaly > 0.0 && delta_cost < 0.0 {
            ("dominant_arithmetic_pattern", None)
        } else if delta_qaly < 0.0 && delta_cost > 0.0 {
            ("dominated_arithmetic_pattern", None)
        } else if delta_qaly.abs() <= 1e-15 {
            ("incremental_qaly_near_zero", None)
        } else {
            (
                "ratio_reported_without_decision_rule",
                Some(delta_cost / delta_qaly),
            )
        };
        let replicate_values: Vec<serde_json::Value> = all_replicates[baseline]
            .iter()
            .zip(&all_replicates[&strategy.id])
            .enumerate()
            .map(|(replicate, (left, right))| {
                let cost = right.cost - left.cost;
                let qaly = right.qaly - left.qaly;
                serde_json::json!({
                    "replicate": replicate,
                    "incremental_cost": cost,
                    "incremental_qaly": qaly,
                    "incremental_net_monetary_benefit": facts.willingness_to_pay * qaly - cost,
                })
            })
            .collect();
        let replicate_nmbs: Vec<f64> = replicate_values
            .iter()
            .filter_map(|value| finite(value.get("incremental_net_monetary_benefit")))
            .collect();
        comparison_values.push(serde_json::json!({
            "baseline_strategy_id": baseline,
            "strategy_id": strategy.id,
            "incremental_cost": delta_cost,
            "standard_error_incremental_cost": se_cost,
            "incremental_qaly": delta_qaly,
            "standard_error_incremental_qaly": se_qaly,
            "incremental_net_monetary_benefit": delta_nmb,
            "standard_error_incremental_net_monetary_benefit": se_nmb,
            "icer": icer,
            "icer_classification": classification,
            "replicate_estimates": replicate_values,
            "replicate_sd_incremental_net_monetary_benefit": sample_sd(&replicate_nmbs),
        }));
    }
    let steps = facts.patients * facts.replicates * facts.cycles * facts.strategies.len();
    Ok(NativeExecution {
        method: serde_json::json!({
            "model_type": "discrete_time_individual_state_transition",
            "random_number_generator": "splitmix64_counter_top53_v1",
            "common_random_numbers": "synchronized_initial_and_cycle_transition_uniforms",
            "transition_timing": "one_transition_at_cycle_end",
            "reward_timing": "trapezoidal_state_rewards_transition_costs_at_cycle_end",
            "parameter_uncertainty": "not_modeled",
            "automatic_strategy_selection": "none",
        }),
        performance: serde_json::json!({
            "patients_per_replicate": facts.patients,
            "replicates": facts.replicates,
            "strategy_count": facts.strategies.len(),
            "cycles": facts.cycles,
            "simulation_steps": steps,
            "maximum_simulation_steps": MAX_SIMULATION_STEPS,
        }),
        strategies: serde_json::Value::Array(strategy_values),
        comparisons: serde_json::Value::Array(comparison_values),
        monte_carlo_error: serde_json::json!({
            "patient_level_method": "sample_standard_error_with_paired_strategy_differences",
            "replicate_method": "independent_counter_replicates_with_common_random_numbers_within_replicate",
            "automatic_stability_thresholds": "none",
        }),
        warnings: serde_json::json!([
            "First-order Monte Carlo error remains; inspect paired standard errors and replicate variation before interpretation.",
            "Parameter uncertainty and structural uncertainty are not propagated by this bounded engine.",
            "Arithmetic dominance labels and ICER ratios are descriptive and do not authorize a cost-effectiveness or reimbursement conclusion."
        ]),
        traces,
    })
}

fn close(actual: &serde_json::Value, expected: &serde_json::Value) -> bool {
    match (actual.as_f64(), expected.as_f64()) {
        (Some(actual), Some(expected)) => {
            (actual - expected).abs() <= TOLERANCE * actual.abs().max(expected.abs()).max(1.0)
        }
        _ => actual == expected,
    }
}

fn deep_close(
    actual: &serde_json::Value,
    expected: &serde_json::Value,
    path: &str,
    errors: &mut Vec<String>,
) {
    match expected {
        serde_json::Value::Object(expected) => {
            let Some(actual) = actual.as_object() else {
                errors.push(format!("{path} differs from native replay"));
                return;
            };
            if actual.len() != expected.len()
                || expected.keys().any(|key| !actual.contains_key(key))
            {
                errors.push(format!("{path} fields differ from native replay"));
                return;
            }
            for (key, value) in expected {
                deep_close(&actual[key], value, &format!("{path}.{key}"), errors);
            }
        }
        serde_json::Value::Array(expected) => {
            let Some(actual) = actual.as_array() else {
                errors.push(format!("{path} differs from native replay"));
                return;
            };
            if actual.len() != expected.len() {
                errors.push(format!("{path} length differs from native replay"));
                return;
            }
            for (index, value) in expected.iter().enumerate() {
                deep_close(&actual[index], value, &format!("{path}[{index}]"), errors);
            }
        }
        _ if !close(actual, expected) => {
            errors.push(format!("{path} differs from native replay"));
        }
        _ => {}
    }
}

fn dedup_errors(errors: &mut Vec<String>) {
    let mut seen = HashSet::new();
    errors.retain(|error| seen.insert(error.clone()));
}

fn audit_path(workspace: &Path, result_path: &str) -> MicrosimulationAudit {
    let mut audit = MicrosimulationAudit {
        result_path: result_path.into(),
        ..MicrosimulationAudit::default()
    };
    let request_path = match resolve_file(workspace, REQUEST_PATH, "microsimulation request") {
        Ok(path) => path,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let request_raw = match read_capped(&request_path, MAX_JSON_BYTES, "microsimulation request") {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    audit.request_sha256 = Some(sha256(&request_raw));
    let request: serde_json::Value = match serde_json::from_slice(&request_raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("microsimulation request is invalid JSON: {error}"));
            return audit;
        }
    };
    let facts = validate_request(workspace, &request, &mut audit.errors);
    audit.simulation_id = facts.simulation_id.clone();
    audit.state_count = facts.states.len();
    audit.strategy_count = facts.strategies.len();
    audit.tracker_count = facts.trackers.len();
    audit.patients_per_replicate = facts.patients;
    audit.replicates = facts.replicates;
    audit.cycles = facts.cycles;
    audit.simulation_steps = facts
        .patients
        .saturating_mul(facts.replicates)
        .saturating_mul(facts.cycles)
        .saturating_mul(facts.strategies.len());
    audit.limitations = facts.limitations.clone();
    if !audit.errors.is_empty() {
        dedup_errors(&mut audit.errors);
        return audit;
    }
    let result_file = match resolve_file(workspace, result_path, "microsimulation result") {
        Ok(path) => path,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let result_raw = match read_capped(&result_file, MAX_JSON_BYTES, "microsimulation result") {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    audit.result_sha256 = Some(sha256(&result_raw));
    let result: serde_json::Value = match serde_json::from_slice(&result_raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("microsimulation result is invalid JSON: {error}"));
            return audit;
        }
    };
    let result_fields = [
        "schema_version",
        "simulation_id",
        "status",
        "request",
        "evidence_synthesis",
        "runtime",
        "method",
        "performance",
        "strategies",
        "comparisons",
        "monte_carlo_error",
        "trace",
        "warnings",
        "limitations",
        "human_gate",
    ];
    if !exact(&result, &result_fields)
        || text(result.get("schema_version")) != Some(RESULT_SCHEMA)
        || text(result.get("simulation_id")) != Some(&facts.simulation_id)
        || text(result.get("status")) != Some("awaiting_method_review")
    {
        audit
            .errors
            .push("microsimulation result top-level contract is invalid".into());
    }
    audit.status = text(result.get("status")).unwrap_or("invalid").into();
    if !exact(&result["request"], &["path", "sha256"])
        || text(result.pointer("/request/path")) != Some(REQUEST_PATH)
        || text(result.pointer("/request/sha256")) != audit.request_sha256.as_deref()
    {
        audit
            .errors
            .push("microsimulation result does not bind the current request".into());
    }
    if result.get("evidence_synthesis")
        != Some(&serde_json::json!({"path": facts.evidence_path, "sha256": facts.evidence_sha256}))
    {
        audit
            .errors
            .push("microsimulation evidence binding drifted".into());
    }
    let runtime = &result["runtime"];
    if !exact(
        runtime,
        &[
            "evaluator",
            "python_version",
            "python_executable_sha256",
            "evaluator_source",
        ],
    ) || text(runtime.get("evaluator")) != Some(EVALUATOR)
        || text(runtime.get("python_version")).is_none()
        || text(runtime.get("python_executable_sha256")).is_none_or(|hash| !is_sha256(hash))
        || !exact(&runtime["evaluator_source"], &["path", "sha256"])
    {
        audit
            .errors
            .push("microsimulation runtime identity is invalid".into());
    }
    if let Some((_, raw)) = bound_bytes(
        workspace,
        &runtime["evaluator_source"],
        None,
        "microsimulation evaluator",
        &mut audit.errors,
    ) {
        if raw != EVALUATOR_BYTES
            || text(runtime.pointer("/evaluator_source/sha256"))
                != Some(sha256(EVALUATOR_BYTES).as_str())
        {
            audit
                .errors
                .push("microsimulation evaluator is not the current bundled source".into());
        }
    }
    let trace_binding = &result["trace"];
    let trace_raw = bound_bytes(
        workspace,
        trace_binding,
        None,
        "microsimulation trace",
        &mut audit.errors,
    )
    .map(|(_, raw)| raw);
    if !exact(
        trace_binding,
        &[
            "path",
            "sha256",
            "row_count",
            "replicate",
            "patient_indices",
        ],
    ) || trace_binding
        .get("replicate")
        .and_then(serde_json::Value::as_u64)
        != Some(facts.trace_replicate as u64)
        || trace_binding.get("patient_indices") != Some(&serde_json::json!(facts.trace_patients))
    {
        audit
            .errors
            .push("microsimulation trace contract is invalid".into());
    }
    match execute_native(&facts) {
        Ok(expected) => {
            deep_close(
                &result["method"],
                &expected.method,
                "method",
                &mut audit.errors,
            );
            deep_close(
                &result["performance"],
                &expected.performance,
                "performance",
                &mut audit.errors,
            );
            deep_close(
                &result["strategies"],
                &expected.strategies,
                "strategies",
                &mut audit.errors,
            );
            deep_close(
                &result["comparisons"],
                &expected.comparisons,
                "comparisons",
                &mut audit.errors,
            );
            deep_close(
                &result["monte_carlo_error"],
                &expected.monte_carlo_error,
                "monte_carlo_error",
                &mut audit.errors,
            );
            deep_close(
                &result["warnings"],
                &expected.warnings,
                "warnings",
                &mut audit.errors,
            );
            if let Some(raw) = trace_raw {
                let lines: Vec<&[u8]> = raw
                    .split(|byte| *byte == b'\n')
                    .filter(|line| !line.is_empty())
                    .collect();
                audit.trace_rows = lines.len();
                if lines.len() != expected.traces.len()
                    || trace_binding
                        .get("row_count")
                        .and_then(serde_json::Value::as_u64)
                        != Some(lines.len() as u64)
                {
                    audit
                        .errors
                        .push("microsimulation trace row count differs from native replay".into());
                } else {
                    for (index, (line, expected_row)) in
                        lines.iter().zip(&expected.traces).enumerate()
                    {
                        match serde_json::from_slice::<serde_json::Value>(line) {
                            Ok(actual) => deep_close(
                                &actual,
                                expected_row,
                                &format!("trace[{index}]"),
                                &mut audit.errors,
                            ),
                            Err(error) => audit.errors.push(format!(
                                "microsimulation trace line {} is invalid JSON: {error}",
                                index + 1
                            )),
                        }
                    }
                }
            }
            audit.comparisons = expected
                .comparisons
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|value| {
                    Some(MicrosimulationComparisonAudit {
                        baseline_strategy_id: text(value.get("baseline_strategy_id"))?.into(),
                        strategy_id: text(value.get("strategy_id"))?.into(),
                        incremental_cost: finite(value.get("incremental_cost"))?,
                        incremental_qaly: finite(value.get("incremental_qaly"))?,
                        incremental_net_monetary_benefit: finite(
                            value.get("incremental_net_monetary_benefit"),
                        )?,
                        standard_error_incremental_net_monetary_benefit: finite(
                            value.get("standard_error_incremental_net_monetary_benefit"),
                        )?,
                    })
                })
                .collect();
        }
        Err(error) => audit
            .errors
            .push(format!("native microsimulation replay failed: {error}")),
    }
    if string_array(result.get("limitations")) != Some(facts.limitations.clone())
        || result.get("human_gate") != request.get("human_gate")
    {
        audit
            .errors
            .push("microsimulation limitations or Human gate drifted".into());
    }
    dedup_errors(&mut audit.errors);
    audit.complete = audit.errors.is_empty();
    audit.reviewable = audit.complete && audit.status == "awaiting_method_review";
    audit
}

fn result_path_from_request(workspace: &Path) -> Result<String, String> {
    let request_path = resolve_file(workspace, REQUEST_PATH, "microsimulation request")?;
    let raw = read_capped(&request_path, MAX_JSON_BYTES, "microsimulation request")?;
    let value: serde_json::Value = serde_json::from_slice(&raw)
        .map_err(|error| format!("microsimulation request is invalid JSON: {error}"))?;
    let output = text(value.pointer("/output/directory"))
        .ok_or_else(|| "microsimulation output.directory is invalid".to_string())?;
    Ok(format!("{output}/manifest.json"))
}

#[tauri::command]
pub fn audit_heor_microsimulation(app: AppHandle) -> Result<MicrosimulationAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    match result_path_from_request(&workspace) {
        Ok(path) => Ok(audit_path(&workspace, &path)),
        Err(error) => Ok(MicrosimulationAudit {
            errors: vec![error],
            ..MicrosimulationAudit::default()
        }),
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MicrosimulationReviewAction {
    Accept,
    Reject,
}

#[derive(Clone, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct MicrosimulationChecklist {
    pub decision_problem_individual_model_justification_reviewed: bool,
    pub states_horizon_timing_absorbing_death_reviewed: bool,
    pub input_provenance_population_alignment_reviewed: bool,
    pub time_in_state_rules_state_rewards_reviewed: bool,
    pub history_trackers_transition_event_costs_reviewed: bool,
    pub prng_seeds_common_random_numbers_traces_reviewed: bool,
    pub monte_carlo_error_replicates_performance_reviewed: bool,
    pub structural_parameter_uncertainty_downstream_limits_reviewed: bool,
}

impl MicrosimulationChecklist {
    fn all_confirmed(&self) -> bool {
        self.decision_problem_individual_model_justification_reviewed
            && self.states_horizon_timing_absorbing_death_reviewed
            && self.input_provenance_population_alignment_reviewed
            && self.time_in_state_rules_state_rewards_reviewed
            && self.history_trackers_transition_event_costs_reviewed
            && self.prng_seeds_common_random_numbers_traces_reviewed
            && self.monte_carlo_error_replicates_performance_reviewed
            && self.structural_parameter_uncertainty_downstream_limits_reviewed
    }
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct MicrosimulationReviewRequest {
    pub project_id: String,
    pub result_path: String,
    pub result_sha256: String,
    pub action: MicrosimulationReviewAction,
    pub checklist: MicrosimulationChecklist,
    pub actor_label: String,
    pub rationale: String,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct MicrosimulationReviewEvent {
    pub schema_version: u32,
    pub sequence: u64,
    pub review_id: String,
    pub project_id: String,
    pub simulation_id: String,
    pub action: MicrosimulationReviewAction,
    pub result_path: String,
    pub result_sha256: String,
    pub related_artifacts: Vec<crate::heor_approval::ArtifactBinding>,
    pub checklist: MicrosimulationChecklist,
    pub actor_label: String,
    pub rationale: String,
    pub timestamp: u64,
    pub record_path: String,
    pub record_sha256: String,
    pub assurance: String,
    pub previous_hash: Option<String>,
    pub event_hash: String,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MicrosimulationReviewLog {
    pub events: Vec<MicrosimulationReviewEvent>,
    pub chain_head: Option<String>,
    pub integrity: &'static str,
    pub identity_assurance: &'static str,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct ReviewSnapshot<'a> {
    schema_version: &'static str,
    review_id: &'a str,
    project_id: &'a str,
    simulation_id: &'a str,
    action: MicrosimulationReviewAction,
    status: &'static str,
    result_path: &'a str,
    result_sha256: &'a str,
    related_artifacts: &'a [crate::heor_approval::ArtifactBinding],
    checklist: &'a MicrosimulationChecklist,
    actor_label: &'a str,
    rationale: &'a str,
    timestamp: u64,
    assurance: &'static str,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct ReviewHashPayload<'a> {
    schema_version: u32,
    sequence: u64,
    review_id: &'a str,
    project_id: &'a str,
    simulation_id: &'a str,
    action: MicrosimulationReviewAction,
    result_path: &'a str,
    result_sha256: &'a str,
    related_artifacts: &'a [crate::heor_approval::ArtifactBinding],
    checklist: &'a MicrosimulationChecklist,
    actor_label: &'a str,
    rationale: &'a str,
    timestamp: u64,
    record_path: &'a str,
    record_sha256: &'a str,
    assurance: &'a str,
    previous_hash: &'a Option<String>,
}

fn validate_project_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 80
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn validate_review_text(value: &str, maximum: usize) -> bool {
    value == value.trim() && !value.is_empty() && value.chars().count() <= maximum
}

fn review_root(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?
        .join("heor")
        .join("semi-markov-microsimulation-reviews"))
}

fn review_log_path(root: &Path, project_id: &str) -> Result<PathBuf, String> {
    if !validate_project_id(project_id) {
        return Err("projectId must be a safe identifier".into());
    }
    Ok(root.join(format!("{project_id}.jsonl")))
}

fn hash_review_event(event: &MicrosimulationReviewEvent) -> Result<String, String> {
    let raw = serde_json::to_vec(&ReviewHashPayload {
        schema_version: event.schema_version,
        sequence: event.sequence,
        review_id: &event.review_id,
        project_id: &event.project_id,
        simulation_id: &event.simulation_id,
        action: event.action,
        result_path: &event.result_path,
        result_sha256: &event.result_sha256,
        related_artifacts: &event.related_artifacts,
        checklist: &event.checklist,
        actor_label: &event.actor_label,
        rationale: &event.rationale,
        timestamp: event.timestamp,
        record_path: &event.record_path,
        record_sha256: &event.record_sha256,
        assurance: &event.assurance,
        previous_hash: &event.previous_hash,
    })
    .map_err(|error| error.to_string())?;
    Ok(sha256(&raw))
}

fn snapshot_bytes(event: &MicrosimulationReviewEvent) -> Result<Vec<u8>, String> {
    let snapshot = ReviewSnapshot {
        schema_version: REVIEW_SCHEMA,
        review_id: &event.review_id,
        project_id: &event.project_id,
        simulation_id: &event.simulation_id,
        action: event.action,
        status: if event.action == MicrosimulationReviewAction::Accept {
            "accepted_simulation_for_later_model_use"
        } else {
            "rejected_simulation_for_later_model_use"
        },
        result_path: &event.result_path,
        result_sha256: &event.result_sha256,
        related_artifacts: &event.related_artifacts,
        checklist: &event.checklist,
        actor_label: &event.actor_label,
        rationale: &event.rationale,
        timestamp: event.timestamp,
        assurance: REVIEW_ASSURANCE,
    };
    let mut raw = serde_json::to_vec_pretty(&snapshot).map_err(|error| error.to_string())?;
    raw.push(b'\n');
    Ok(raw)
}

fn collect_related_artifacts(
    workspace: &Path,
    audit: &MicrosimulationAudit,
) -> Result<Vec<crate::heor_approval::ArtifactBinding>, String> {
    let result_path = resolve_file(workspace, &audit.result_path, "microsimulation result")?;
    let result_raw = read_capped(&result_path, MAX_JSON_BYTES, "microsimulation result")?;
    let result: serde_json::Value =
        serde_json::from_slice(&result_raw).map_err(|error| error.to_string())?;
    let mut bindings = vec![crate::heor_approval::ArtifactBinding {
        path: audit.result_path.clone(),
        sha256: audit.result_sha256.clone().unwrap_or_default(),
    }];
    let mut add = |binding: &serde_json::Value| {
        if let (Some(path), Some(hash)) = (text(binding.get("path")), text(binding.get("sha256"))) {
            bindings.push(crate::heor_approval::ArtifactBinding {
                path: path.into(),
                sha256: hash.into(),
            });
        }
    };
    add(&result["request"]);
    add(&result["evidence_synthesis"]);
    add(&result["runtime"]["evaluator_source"]);
    add(&result["trace"]);
    let mut seen = HashSet::new();
    bindings.retain(|binding| seen.insert(binding.path.clone()));
    if bindings.len() != 5 || bindings.iter().any(|binding| !is_sha256(&binding.sha256)) {
        return Err(
            "microsimulation review could not bind the complete five-artifact graph".into(),
        );
    }
    for binding in &bindings {
        let path = resolve_file(workspace, &binding.path, "microsimulation review artifact")?;
        let raw = read_capped(&path, MAX_TRACE_BYTES, "microsimulation review artifact")?;
        if sha256(&raw) != binding.sha256 {
            return Err("microsimulation review artifact changed during submission".into());
        }
    }
    Ok(bindings)
}

fn read_review_events(
    root: &Path,
    workspace: &Path,
    project_id: &str,
) -> Result<Vec<MicrosimulationReviewEvent>, String> {
    let path = review_log_path(root, project_id)?;
    let raw = match std::fs::read(&path) {
        Ok(raw) => raw,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("microsimulation review log unavailable: {error}")),
    };
    if raw.len() > 4 * 1024 * 1024 {
        return Err("microsimulation review log exceeds 4 MB".into());
    }
    let mut events = Vec::new();
    let mut previous_hash = None;
    for (index, line) in raw
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
        .enumerate()
    {
        if events.len() >= 2_000 {
            return Err("microsimulation review log exceeds 2,000 events".into());
        }
        let event: MicrosimulationReviewEvent = serde_json::from_slice(line).map_err(|error| {
            format!(
                "microsimulation review log line {} is invalid: {error}",
                index + 1
            )
        })?;
        if event.schema_version != REVIEW_EVENT_SCHEMA
            || event.sequence != index as u64 + 1
            || event.project_id != project_id
            || !safe_id(&event.simulation_id)
            || event.review_id.len() != 32
            || !event.review_id.bytes().all(|byte| byte.is_ascii_hexdigit())
            || !is_sha256(&event.result_sha256)
            || !is_sha256(&event.record_sha256)
            || !is_sha256(&event.event_hash)
            || event.assurance != REVIEW_ASSURANCE
            || event.previous_hash != previous_hash
            || !validate_review_text(&event.actor_label, 120)
            || !validate_review_text(&event.rationale, 2_000)
            || hash_review_event(&event)? != event.event_hash
        {
            return Err(format!(
                "microsimulation review log line {} violates the event contract",
                index + 1
            ));
        }
        let record = resolve_file(
            workspace,
            &event.record_path,
            "microsimulation review record",
        )?;
        let record_raw = read_capped(&record, MAX_JSON_BYTES, "microsimulation review record")?;
        if sha256(&record_raw) != event.record_sha256 || record_raw != snapshot_bytes(&event)? {
            return Err(format!(
                "microsimulation review log line {} record binding is invalid",
                index + 1
            ));
        }
        previous_hash = Some(event.event_hash.clone());
        events.push(event);
    }
    Ok(events)
}

fn write_review_record(workspace: &Path, event: &MicrosimulationReviewEvent) -> Result<(), String> {
    let root = workspace
        .canonicalize()
        .map_err(|error| error.to_string())?;
    let relative = Path::new(&event.record_path);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err("microsimulation review record path is unsafe".into());
    }
    let target = root.join(relative);
    let parent = target
        .parent()
        .ok_or_else(|| "microsimulation review record parent is invalid".to_string())?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("microsimulation review directory failed: {error}"))?;
    if std::fs::symlink_metadata(parent).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err("microsimulation review directory must not be a symlink".into());
    }
    let raw = snapshot_bytes(event)?;
    if sha256(&raw) != event.record_sha256 {
        return Err("microsimulation review record hash changed before write".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&target)
        .map_err(|error| format!("microsimulation review record write failed: {error}"))?;
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("microsimulation review record write failed: {error}"))
}

fn append_review_event(root: &Path, event: &MicrosimulationReviewEvent) -> Result<(), String> {
    let path = review_log_path(root, &event.project_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("microsimulation review log directory failed: {error}"))?;
        crate::runtime::tighten_private(parent);
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| format!("microsimulation review log write failed: {error}"))?;
    let mut raw = serde_json::to_vec(event).map_err(|error| error.to_string())?;
    raw.push(b'\n');
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("microsimulation review log write failed: {error}"))
}

#[tauri::command]
pub fn append_heor_microsimulation_review(
    app: AppHandle,
    state: tauri::State<MicrosimulationReviewState>,
    request: MicrosimulationReviewRequest,
) -> Result<MicrosimulationReviewEvent, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "microsimulation review lock poisoned".to_string())?;
    if !validate_project_id(&request.project_id)
        || !is_sha256(&request.result_sha256)
        || !validate_review_text(&request.actor_label, 120)
        || !validate_review_text(&request.rationale, 2_000)
    {
        return Err(
            "microsimulation review request contains invalid identity, hash, or text".into(),
        );
    }
    if request.action == MicrosimulationReviewAction::Accept && !request.checklist.all_confirmed() {
        return Err("all eight microsimulation method checks are required for acceptance".into());
    }
    let workspace = crate::runtime::workspace_dir(&app)?;
    let audit = audit_path(&workspace, &request.result_path);
    if !audit.complete || !audit.reviewable {
        return Err(format!(
            "microsimulation result is not reviewable: {}",
            audit.errors.join("; ")
        ));
    }
    if audit.result_path != request.result_path
        || audit.result_sha256.as_deref() != Some(&request.result_sha256)
    {
        return Err(
            "microsimulation review request does not bind the current audited result".into(),
        );
    }
    let related_artifacts = collect_related_artifacts(&workspace, &audit)?;
    let root = review_root(&app)?;
    let events = read_review_events(&root, &workspace, &request.project_id)?;
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_secs();
    let sequence = events.len() as u64 + 1;
    let review_id = sha256(
        format!(
            "{}:{}:{}:{}",
            request.project_id, audit.simulation_id, sequence, timestamp
        )
        .as_bytes(),
    )[..32]
        .to_string();
    let record_path = format!("heor/semi-markov-microsimulation-reviews/{review_id}.json");
    let mut event = MicrosimulationReviewEvent {
        schema_version: REVIEW_EVENT_SCHEMA,
        sequence,
        review_id,
        project_id: request.project_id,
        simulation_id: audit.simulation_id,
        action: request.action,
        result_path: request.result_path,
        result_sha256: request.result_sha256,
        related_artifacts,
        checklist: request.checklist,
        actor_label: request.actor_label,
        rationale: request.rationale,
        timestamp,
        record_path,
        record_sha256: String::new(),
        assurance: REVIEW_ASSURANCE.into(),
        previous_hash: events.last().map(|event| event.event_hash.clone()),
        event_hash: String::new(),
    };
    event.record_sha256 = sha256(&snapshot_bytes(&event)?);
    event.event_hash = hash_review_event(&event)?;
    write_review_record(&workspace, &event)?;
    append_review_event(&root, &event)?;
    Ok(event)
}

#[tauri::command]
pub fn list_heor_microsimulation_reviews(
    app: AppHandle,
    state: tauri::State<MicrosimulationReviewState>,
    project_id: String,
) -> Result<MicrosimulationReviewLog, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "microsimulation review lock poisoned".to_string())?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    let events = read_review_events(&review_root(&app)?, &workspace, &project_id)?;
    Ok(MicrosimulationReviewLog {
        chain_head: events.last().map(|event| event.event_hash.clone()),
        events,
        integrity: "verified_unanchored_sha256_chain",
        identity_assurance: REVIEW_ASSURANCE,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn checklist(value: bool) -> MicrosimulationChecklist {
        MicrosimulationChecklist {
            decision_problem_individual_model_justification_reviewed: value,
            states_horizon_timing_absorbing_death_reviewed: value,
            input_provenance_population_alignment_reviewed: value,
            time_in_state_rules_state_rewards_reviewed: value,
            history_trackers_transition_event_costs_reviewed: value,
            prng_seeds_common_random_numbers_traces_reviewed: value,
            monte_carlo_error_replicates_performance_reviewed: value,
            structural_parameter_uncertainty_downstream_limits_reviewed: value,
        }
    }

    #[test]
    fn acceptance_requires_all_eight_method_checks() {
        assert!(checklist(true).all_confirmed());
        let mut incomplete = checklist(true);
        incomplete.prng_seeds_common_random_numbers_traces_reviewed = false;
        assert!(!incomplete.all_confirmed());
    }

    #[test]
    fn splitmix64_counter_matches_portable_reference_vectors() {
        let vectors = [
            ((0, 0, 0, 0, 0), 0.14496552426123632),
            ((20_260_717, 0, 0, 1, 1), 0.511_275_059_465_522_7),
            ((20_260_717, 2, 99, 8, 1), 0.28400037087347296),
        ];
        for ((seed, replicate, patient, cycle, stream), expected) in vectors {
            let actual = counter_uniform(seed, replicate, patient, cycle, stream);
            assert!((actual - expected).abs() < 1e-15, "{actual} != {expected}");
        }
    }

    #[test]
    fn native_audit_accepts_the_portable_runner_fixture() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
        let root = std::env::temp_dir().join(format!(
            "ai4heor-microsimulation-native-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).expect("fixture root");
        let prepare = std::process::Command::new("python3")
            .current_dir(&repo)
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .args([
                "-c",
                "import sys; from pathlib import Path; from scripts.dev.test_semi_markov_microsimulation import build_workspace; build_workspace(Path(sys.argv[1]))",
                root.to_str().expect("UTF-8 fixture path"),
            ])
            .status();
        let Ok(prepare) = prepare else {
            let _ = std::fs::remove_dir_all(&root);
            return;
        };
        assert!(prepare.success(), "portable fixture preparation failed");
        let runner = repo.join(
            "runtime/skills/core/heor-semi-markov-microsimulation/scripts/run_microsimulation.py",
        );
        let run = std::process::Command::new("python3")
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .args([
                runner.to_str().expect("UTF-8 runner path"),
                "--workspace",
                root.to_str().expect("UTF-8 fixture path"),
                "--request",
                REQUEST_PATH,
            ])
            .status()
            .expect("portable runner should launch");
        assert!(run.success(), "portable microsimulation runner failed");
        let result_path = "heor/semi-markov-microsimulation-runs/microsim-test-001/manifest.json";
        let audit = audit_path(&root, result_path);
        assert!(audit.complete, "{}", audit.errors.join("; "));
        assert!(audit.reviewable);
        assert_eq!(audit.simulation_steps, 4_800);
        assert_eq!(audit.trace_rows, 160);

        let request_path = root.join(REQUEST_PATH);
        let mut malformed: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&request_path).expect("read fixture request"))
                .expect("parse fixture request");
        malformed["model"]["states"][1]["label"] = serde_json::Value::Null;
        std::fs::write(
            &request_path,
            serde_json::to_vec(&malformed).expect("serialize malformed request"),
        )
        .expect("write malformed request");
        let malformed_audit = audit_path(&root, result_path);
        assert!(!malformed_audit.complete);
        assert!(malformed_audit
            .errors
            .iter()
            .any(|error| error.contains("state 1 values are invalid")));
        let _ = std::fs::remove_dir_all(&root);
    }
}
