use sha2::{Digest, Sha256};
use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::Path;
use tauri::AppHandle;

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EvidenceAudit {
    pub complete: bool,
    pub status: &'static str,
    pub required_inputs: usize,
    pub covered_inputs: usize,
    pub unsupported_inputs: Vec<String>,
    pub invalid_mappings: Vec<String>,
    pub unresolved_assumptions: Vec<String>,
    pub source_count: usize,
    pub mapping_count: usize,
    pub source_based_inputs: usize,
    pub selected_extraction_count: usize,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EvidenceSelectionAudit {
    pub complete: bool,
    pub status: &'static str,
    pub synthesis_sha256: String,
    pub selected_input_count: usize,
    pub selected_extraction_count: usize,
    pub verified_extraction_count: usize,
    pub unverified_extraction_ids: Vec<String>,
    pub rejected_extraction_ids: Vec<String>,
    pub invalid_selections: Vec<String>,
    pub errors: Vec<String>,
    pub verification_integrity: &'static str,
}

fn nonempty(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| !value.trim().is_empty())
}

fn string_list(value: Option<&serde_json::Value>) -> Option<Vec<&str>> {
    value?.as_array().map(|items| {
        items
            .iter()
            .filter_map(serde_json::Value::as_str)
            .filter(|value| !value.trim().is_empty())
            .collect()
    })
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn safe_strategy_id(value: &str) -> bool {
    let mut bytes = value.bytes();
    bytes.next().is_some_and(|byte| byte.is_ascii_lowercase())
        && value.len() <= 64
        && bytes.all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'_' | b'-')
        })
}

fn strategy_ids(plan: &serde_json::Value) -> Vec<&str> {
    if matches!(
        plan.get("schema_version")
            .and_then(serde_json::Value::as_str),
        Some("0.8.0" | "0.9.0" | "0.10.0" | "0.11.0" | "0.12.0" | "0.13.0" | "0.14.0")
    ) {
        return plan
            .get("strategy_order")
            .and_then(serde_json::Value::as_array)
            .and_then(|items| {
                items
                    .iter()
                    .map(serde_json::Value::as_str)
                    .collect::<Option<Vec<_>>>()
            })
            .unwrap_or_default();
    }
    vec!["comparator", "intervention"]
}

fn required_input_paths(plan: &serde_json::Value) -> Vec<String> {
    let mut paths = vec![
        "cycles".into(),
        "cycle_length_years".into(),
        "discount_rates.costs".into(),
        "discount_rates.outcomes".into(),
        "half_cycle_correction".into(),
    ];
    let structure_neutral = plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        .is_some_and(|version| matches!(version, "0.12.0" | "0.13.0" | "0.14.0"));
    for role in strategy_ids(plan) {
        if !structure_neutral {
            paths.push(format!("strategies.{role}.initial_distribution"));
        }
        let transition_field = if plan
            .pointer(&format!("/strategies/{role}/transition_schedule"))
            .is_some_and(|value| !value.is_null())
        {
            "transition_schedule"
        } else {
            "transition_matrix"
        };
        if !structure_neutral {
            paths.push(format!("strategies.{role}.{transition_field}"));
        }
        paths.push(format!("strategies.{role}.state_costs"));
        paths.push(format!("strategies.{role}.state_utilities"));
    }
    if !plan
        .get("willingness_to_pay")
        .is_none_or(serde_json::Value::is_null)
    {
        paths.push("willingness_to_pay".into());
    }
    paths
}

fn monetary_path(path: &str) -> bool {
    path.ends_with("state_costs") || path == "willingness_to_pay"
}

fn currency_code(value: Option<&serde_json::Value>) -> Option<&str> {
    value.and_then(serde_json::Value::as_str).filter(|value| {
        value.len() == 3
            && value
                .bytes()
                .all(|byte| byte.is_ascii_alphabetic() && byte.is_ascii_uppercase())
    })
}

fn model_value<'a>(plan: &'a serde_json::Value, path: &str) -> Option<&'a serde_json::Value> {
    path.split('.')
        .try_fold(plan, |current, token| current.get(token))
}

fn json_equivalent(left: &serde_json::Value, right: &serde_json::Value) -> bool {
    match (left, right) {
        (serde_json::Value::Number(a), serde_json::Value::Number(b)) => {
            match (a.as_f64(), b.as_f64()) {
                (Some(a), Some(b)) if a.is_finite() && b.is_finite() => {
                    let tolerance = (a.abs().max(b.abs()) * 1e-12).max(1e-12);
                    (a - b).abs() <= tolerance
                }
                _ => false,
            }
        }
        (serde_json::Value::Array(a), serde_json::Value::Array(b)) => {
            a.len() == b.len()
                && a.iter()
                    .zip(b.iter())
                    .all(|(left, right)| json_equivalent(left, right))
        }
        (serde_json::Value::Object(a), serde_json::Value::Object(b)) => {
            a.len() == b.len()
                && a.iter().all(|(key, value)| {
                    b.get(key)
                        .is_some_and(|other| json_equivalent(value, other))
                })
        }
        _ => left == right,
    }
}

fn transition_path(path: &str) -> bool {
    let parts = path.split('.').collect::<Vec<_>>();
    matches!(parts.as_slice(), ["strategies", strategy_id, "transition_matrix" | "transition_schedule"] if safe_strategy_id(strategy_id))
}

fn exact_fields(object: &serde_json::Map<String, serde_json::Value>, fields: &[&str]) -> bool {
    object.len() == fields.len() && fields.iter().all(|field| object.contains_key(*field))
}

fn collect_exact_basis(
    object: &serde_json::Map<String, serde_json::Value>,
    label: &str,
    value_field: Option<&str>,
    used_extractions: &mut HashSet<String>,
    used_assumptions: &mut HashSet<String>,
) -> Result<(), String> {
    let source_id = object
        .get("source_extraction_id")
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.trim().is_empty());
    let assumption_id = object
        .get("assumption_id")
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.trim().is_empty());
    if source_id.is_some() == assumption_id.is_some() {
        return Err(format!(
            "{label} must declare exactly one source_extraction_id or assumption_id"
        ));
    }
    let expected_len = usize::from(value_field.is_some())
        + 1
        + usize::from(source_id.is_some() && object.contains_key("source_pointer"));
    let allowed = [
        value_field.unwrap_or(""),
        "source_extraction_id",
        "source_pointer",
        "assumption_id",
    ];
    if object.len() != expected_len
        || object
            .keys()
            .any(|field| !allowed.contains(&field.as_str()))
    {
        return Err(format!(
            "{label} fields are not the exact supported contract"
        ));
    }
    if let Some(source_id) = source_id {
        let pointer = match object.get("source_pointer") {
            Some(value) => value
                .as_str()
                .ok_or_else(|| format!("{label}.source_pointer must be a string"))?,
            None => "",
        };
        if !pointer.is_empty() && !pointer.starts_with('/') {
            return Err(format!(
                "{label}.source_pointer must be empty or a JSON pointer"
            ));
        }
        used_extractions.insert(source_id.to_string());
    } else if let Some(assumption_id) = assumption_id {
        if object.contains_key("source_pointer") {
            return Err(format!(
                "{label}.source_pointer requires source_extraction_id"
            ));
        }
        used_assumptions.insert(assumption_id.to_string());
    }
    Ok(())
}

fn derive_background_mortality_schedule(
    plan: &serde_json::Value,
    path: &str,
    transformation: &serde_json::Value,
) -> Result<(serde_json::Value, HashSet<String>, HashSet<String>), String> {
    if !path.ends_with(".transition_schedule") {
        return Err(
            "background mortality transformation is allowed only for a transition schedule".into(),
        );
    }
    let transformation = transformation
        .as_object()
        .ok_or("derivation.transformation must be an object")?;
    if !exact_fields(
        transformation,
        &[
            "operation",
            "cycle_length_years",
            "from_state_index",
            "death_state_index",
            "life_table",
            "excess_mortality_rate_per_year",
            "review_bases",
        ],
    ) {
        return Err(
            "background mortality transformation fields are not the exact supported contract"
                .into(),
        );
    }
    if transformation
        .get("operation")
        .and_then(serde_json::Value::as_str)
        != Some("background_plus_excess_mortality_to_transition_schedule")
    {
        return Err("transformation.operation must be background_plus_excess_mortality_to_transition_schedule".into());
    }
    let state_count = plan
        .get("states")
        .and_then(serde_json::Value::as_array)
        .map(Vec::len)
        .unwrap_or_default();
    if state_count != 2 {
        return Err("background mortality transformation requires exactly two states".into());
    }
    let cycles = plan
        .get("cycles")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .filter(|value| (1..=10_000).contains(value))
        .ok_or("background mortality transformation supports 1-10000 cycles")?;
    let declared_cycle = transformation
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("transformation.cycle_length_years must be finite and positive")?;
    let plan_cycle = plan
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("analysis cycle_length_years is invalid")?;
    if (declared_cycle - plan_cycle).abs() > 1e-12 {
        return Err(
            "transformation.cycle_length_years must equal the analysis cycle length".into(),
        );
    }
    let from_index = transformation
        .get("from_state_index")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok());
    let death_index = transformation
        .get("death_state_index")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok());
    if !matches!(
        (from_index, death_index),
        (Some(0), Some(1)) | (Some(1), Some(0))
    ) {
        return Err(
            "from_state_index and death_state_index must be the two distinct state indices".into(),
        );
    }
    let from_index = from_index.unwrap();
    let death_index = death_index.unwrap();
    let life_table = transformation
        .get("life_table")
        .and_then(serde_json::Value::as_object)
        .ok_or("transformation.life_table must be an object")?;
    if !exact_fields(
        life_table,
        &[
            "jurisdiction",
            "table_year",
            "population",
            "sex",
            "start_age_years",
            "cycle_probabilities",
        ],
    ) {
        return Err("transformation.life_table fields are not the exact supported contract".into());
    }
    for field in ["jurisdiction", "population", "sex"] {
        if !nonempty(life_table.get(field)) {
            return Err(format!("transformation.life_table.{field} is required"));
        }
    }
    if !life_table
        .get("table_year")
        .and_then(serde_json::Value::as_u64)
        .is_some_and(|value| (1900..=2100).contains(&value))
    {
        return Err("transformation.life_table.table_year must be 1900-2100".into());
    }
    let start_age = life_table
        .get("start_age_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value >= 0.0)
        .ok_or("transformation.life_table.start_age_years must be finite and non-negative")?;
    let cycle_probabilities = life_table
        .get("cycle_probabilities")
        .and_then(serde_json::Value::as_array)
        .filter(|values| values.len() == cycles)
        .ok_or("transformation.life_table.cycle_probabilities must cover every model cycle")?;
    let excess = transformation
        .get("excess_mortality_rate_per_year")
        .and_then(serde_json::Value::as_object)
        .ok_or("transformation.excess_mortality_rate_per_year must be an object")?;
    let excess_value = excess
        .get("value")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value >= 0.0)
        .ok_or("transformation.excess_mortality_rate_per_year.value must be non-negative")?;
    let mut used_extractions = HashSet::new();
    let mut used_assumptions = HashSet::new();
    collect_exact_basis(
        excess,
        "transformation.excess_mortality_rate_per_year",
        Some("value"),
        &mut used_extractions,
        &mut used_assumptions,
    )?;
    let review_bases = transformation
        .get("review_bases")
        .and_then(serde_json::Value::as_object)
        .ok_or("transformation.review_bases must be an object")?;
    if !exact_fields(
        review_bases,
        &["population_exchangeability", "no_double_counting"],
    ) {
        return Err(
            "transformation.review_bases fields are not the exact supported contract".into(),
        );
    }
    for name in ["population_exchangeability", "no_double_counting"] {
        let basis = review_bases
            .get(name)
            .and_then(serde_json::Value::as_object)
            .ok_or_else(|| format!("transformation.review_bases.{name} must be an object"))?;
        collect_exact_basis(
            basis,
            &format!("transformation.review_bases.{name}"),
            None,
            &mut used_extractions,
            &mut used_assumptions,
        )?;
    }
    let mut schedule = Vec::with_capacity(cycles);
    for (index, raw_cycle) in cycle_probabilities.iter().enumerate() {
        let label = format!("transformation.life_table.cycle_probabilities[{index}]");
        let raw_cycle = raw_cycle
            .as_object()
            .ok_or_else(|| format!("{label} must be an object"))?;
        if !exact_fields(
            raw_cycle,
            &["cycle", "attained_age_years", "annual_probability"],
        ) {
            return Err(format!(
                "{label} fields are not the exact supported contract"
            ));
        }
        let cycle = index + 1;
        if raw_cycle
            .get("cycle")
            .and_then(serde_json::Value::as_u64)
            .and_then(|value| usize::try_from(value).ok())
            != Some(cycle)
        {
            return Err(format!("{label}.cycle must equal {cycle}"));
        }
        let expected_age = (start_age + index as f64 * declared_cycle).floor();
        let attained_age = raw_cycle
            .get("attained_age_years")
            .and_then(serde_json::Value::as_f64)
            .filter(|value| value.is_finite())
            .ok_or_else(|| format!("{label}.attained_age_years must be finite"))?;
        if (attained_age - expected_age).abs() > 1e-9 {
            return Err(format!(
                "{label}.attained_age_years must equal floor(start_age_years + (cycle - 1) * cycle_length_years)"
            ));
        }
        let annual = raw_cycle
            .get("annual_probability")
            .and_then(serde_json::Value::as_object)
            .ok_or_else(|| format!("{label}.annual_probability must be an object"))?;
        let q = annual
            .get("value")
            .and_then(serde_json::Value::as_f64)
            .filter(|value| value.is_finite() && *value >= 0.0 && *value < 1.0)
            .ok_or_else(|| format!("{label}.annual_probability.value must be in [0,1)"))?;
        collect_exact_basis(
            annual,
            &format!("{label}.annual_probability"),
            Some("value"),
            &mut used_extractions,
            &mut used_assumptions,
        )?;
        let background_hazard = -(-q).ln_1p();
        let integrated_hazard = (background_hazard + excess_value) * declared_cycle;
        if !integrated_hazard.is_finite() || integrated_hazard < 0.0 {
            return Err(format!("{label} produced a non-finite integrated hazard"));
        }
        let death_probability = -(-integrated_hazard).exp_m1();
        if !death_probability.is_finite() || !(0.0..1.0).contains(&death_probability) {
            return Err(format!("{label} produced an invalid death probability"));
        }
        let mut matrix = vec![vec![0.0; 2]; 2];
        matrix[from_index][from_index] = 1.0 - death_probability;
        matrix[from_index][death_index] = death_probability;
        matrix[death_index][death_index] = 1.0;
        schedule.push(serde_json::json!({"start_cycle": cycle, "matrix": matrix}));
    }
    Ok((
        serde_json::Value::Array(schedule),
        used_extractions,
        used_assumptions,
    ))
}

fn derive_relative_effect_schedule(
    plan: &serde_json::Value,
    path: &str,
    transformation: &serde_json::Value,
) -> Result<(serde_json::Value, HashSet<String>, HashSet<String>), String> {
    if !path.ends_with(".transition_schedule") {
        return Err(
            "relative-effect transformation is allowed only for a transition schedule".into(),
        );
    }
    let transformation = transformation
        .as_object()
        .ok_or("derivation.transformation must be an object")?;
    if !exact_fields(
        transformation,
        &[
            "operation",
            "cycle_length_years",
            "effect_interval_years",
            "from_state_index",
            "event_state_index",
            "measure",
            "baseline_cycle_probabilities",
            "relative_effect",
            "review_bases",
        ],
    ) {
        return Err(
            "relative-effect transformation fields are not the exact supported contract".into(),
        );
    }
    if transformation
        .get("operation")
        .and_then(serde_json::Value::as_str)
        != Some("relative_effect_to_transition_schedule")
    {
        return Err(
            "transformation.operation must be relative_effect_to_transition_schedule".into(),
        );
    }
    let state_count = plan
        .get("states")
        .and_then(serde_json::Value::as_array)
        .map(Vec::len)
        .unwrap_or_default();
    if state_count != 2 {
        return Err("relative-effect transformation requires exactly two states".into());
    }
    let cycles = plan
        .get("cycles")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .filter(|value| (1..=10_000).contains(value))
        .ok_or("relative-effect transformation supports 1-10000 cycles")?;
    let plan_cycle = plan
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("analysis cycle_length_years is invalid")?;
    let declared_cycle = transformation
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("transformation.cycle_length_years must be finite and positive")?;
    let effect_interval = transformation
        .get("effect_interval_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("transformation.effect_interval_years must be finite and positive")?;
    if (declared_cycle - plan_cycle).abs() > 1e-12
        || (effect_interval - declared_cycle).abs() > 1e-12
    {
        return Err("transformation cycle_length_years and effect_interval_years must equal the analysis cycle length".into());
    }
    let from_index = transformation
        .get("from_state_index")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok());
    let event_index = transformation
        .get("event_state_index")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok());
    if !matches!(
        (from_index, event_index),
        (Some(0), Some(1)) | (Some(1), Some(0))
    ) {
        return Err(
            "from_state_index and event_state_index must be the two distinct state indices".into(),
        );
    }
    let from_index = from_index.unwrap();
    let event_index = event_index.unwrap();
    let measure = transformation
        .get("measure")
        .and_then(serde_json::Value::as_str)
        .filter(|value| matches!(*value, "risk_ratio" | "odds_ratio"))
        .ok_or("transformation.measure must be risk_ratio or odds_ratio")?;
    let mut used_extractions = HashSet::new();
    let mut used_assumptions = HashSet::new();
    let effect = transformation
        .get("relative_effect")
        .and_then(serde_json::Value::as_object)
        .ok_or("transformation.relative_effect must be an object")?;
    let effect_value = effect
        .get("value")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("transformation.relative_effect.value must be finite and positive")?;
    collect_exact_basis(
        effect,
        "transformation.relative_effect",
        Some("value"),
        &mut used_extractions,
        &mut used_assumptions,
    )?;
    let review_bases = transformation
        .get("review_bases")
        .and_then(serde_json::Value::as_object)
        .ok_or("transformation.review_bases must be an object")?;
    if !exact_fields(
        review_bases,
        &[
            "endpoint_alignment",
            "population_transportability",
            "effect_constancy_over_cycles",
        ],
    ) {
        return Err(
            "transformation.review_bases fields are not the exact supported contract".into(),
        );
    }
    for name in [
        "endpoint_alignment",
        "population_transportability",
        "effect_constancy_over_cycles",
    ] {
        let basis = review_bases
            .get(name)
            .and_then(serde_json::Value::as_object)
            .ok_or_else(|| format!("transformation.review_bases.{name} must be an object"))?;
        collect_exact_basis(
            basis,
            &format!("transformation.review_bases.{name}"),
            None,
            &mut used_extractions,
            &mut used_assumptions,
        )?;
    }
    let baseline = transformation
        .get("baseline_cycle_probabilities")
        .and_then(serde_json::Value::as_array)
        .filter(|items| items.len() == cycles)
        .ok_or("transformation.baseline_cycle_probabilities must cover every model cycle")?;
    let mut any_positive = false;
    let mut schedule = Vec::with_capacity(cycles);
    for (index, entry) in baseline.iter().enumerate() {
        let label = format!("transformation.baseline_cycle_probabilities[{index}]");
        let entry = entry
            .as_object()
            .ok_or_else(|| format!("{label} must be an object"))?;
        if !exact_fields(entry, &["cycle", "probability"]) {
            return Err(format!(
                "{label} fields are not the exact supported contract"
            ));
        }
        let cycle = index + 1;
        if entry
            .get("cycle")
            .and_then(serde_json::Value::as_u64)
            .and_then(|value| usize::try_from(value).ok())
            != Some(cycle)
        {
            return Err(format!("{label}.cycle must equal {cycle}"));
        }
        let probability = entry
            .get("probability")
            .and_then(serde_json::Value::as_object)
            .ok_or_else(|| format!("{label}.probability must be an object"))?;
        let q = probability
            .get("value")
            .and_then(serde_json::Value::as_f64)
            .filter(|value| value.is_finite() && *value >= 0.0 && *value < 1.0)
            .ok_or_else(|| format!("{label}.probability.value must be in [0,1)"))?;
        any_positive |= q > 0.0;
        collect_exact_basis(
            probability,
            &format!("{label}.probability"),
            Some("value"),
            &mut used_extractions,
            &mut used_assumptions,
        )?;
        let event_probability = match measure {
            "risk_ratio" => q * effect_value,
            "odds_ratio" => {
                if q == 0.0 {
                    0.0
                } else {
                    let numerator = effect_value * q;
                    numerator / ((1.0 - q) + numerator)
                }
            }
            _ => unreachable!(),
        };
        if !event_probability.is_finite() || !(0.0..1.0).contains(&event_probability) {
            return Err(format!("{label} produced an invalid event probability"));
        }
        let mut matrix = vec![vec![0.0; 2]; 2];
        matrix[from_index][from_index] = 1.0 - event_probability;
        matrix[from_index][event_index] = event_probability;
        matrix[event_index][event_index] = 1.0;
        schedule.push(serde_json::json!({"start_cycle": cycle, "matrix": matrix}));
    }
    if !any_positive {
        return Err(
            "baseline_cycle_probabilities must contain at least one positive probability".into(),
        );
    }
    Ok((
        serde_json::Value::Array(schedule),
        used_extractions,
        used_assumptions,
    ))
}

fn derive_hazard_ratio_schedule(
    plan: &serde_json::Value,
    path: &str,
    transformation: &serde_json::Value,
) -> Result<(serde_json::Value, HashSet<String>, HashSet<String>), String> {
    if !path.ends_with(".transition_schedule") {
        return Err("hazard-ratio transformation is allowed only for a transition schedule".into());
    }
    let transformation = transformation
        .as_object()
        .ok_or("derivation.transformation must be an object")?;
    if !exact_fields(
        transformation,
        &[
            "operation",
            "cycle_length_years",
            "from_state_index",
            "event_state_index",
            "baseline_cumulative_hazards",
            "hazard_ratio",
            "review_bases",
        ],
    ) {
        return Err(
            "hazard-ratio transformation fields are not the exact supported contract".into(),
        );
    }
    if transformation
        .get("operation")
        .and_then(serde_json::Value::as_str)
        != Some("hazard_ratio_to_transition_schedule")
    {
        return Err("transformation.operation must be hazard_ratio_to_transition_schedule".into());
    }
    let state_count = plan
        .get("states")
        .and_then(serde_json::Value::as_array)
        .map(Vec::len)
        .unwrap_or_default();
    if state_count != 2 {
        return Err("hazard-ratio transformation requires exactly two states".into());
    }
    let cycles = plan
        .get("cycles")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .filter(|value| (1..=10_000).contains(value))
        .ok_or("hazard-ratio transformation supports 1-10000 cycles")?;
    let plan_cycle = plan
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("analysis cycle_length_years is invalid")?;
    let declared_cycle = transformation
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("transformation.cycle_length_years must be finite and positive")?;
    if (declared_cycle - plan_cycle).abs() > 1e-12 {
        return Err(
            "transformation.cycle_length_years must equal the analysis cycle length".into(),
        );
    }
    let from_index = transformation
        .get("from_state_index")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok());
    let event_index = transformation
        .get("event_state_index")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok());
    if !matches!(
        (from_index, event_index),
        (Some(0), Some(1)) | (Some(1), Some(0))
    ) {
        return Err(
            "from_state_index and event_state_index must be the two distinct state indices".into(),
        );
    }
    let from_index = from_index.unwrap();
    let event_index = event_index.unwrap();
    let mut used_extractions = HashSet::new();
    let mut used_assumptions = HashSet::new();
    let hazard_ratio = transformation
        .get("hazard_ratio")
        .and_then(serde_json::Value::as_object)
        .ok_or("transformation.hazard_ratio must be an object")?;
    let hazard_ratio_value = hazard_ratio
        .get("value")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("transformation.hazard_ratio.value must be finite and positive")?;
    collect_exact_basis(
        hazard_ratio,
        "transformation.hazard_ratio",
        Some("value"),
        &mut used_extractions,
        &mut used_assumptions,
    )?;
    let review_bases = transformation
        .get("review_bases")
        .and_then(serde_json::Value::as_object)
        .ok_or("transformation.review_bases must be an object")?;
    let review_names = [
        "endpoint_alignment",
        "population_transportability",
        "proportional_hazards_assumption",
        "effect_constancy_over_horizon",
        "treatment_switching_assessment",
    ];
    if !exact_fields(review_bases, &review_names) {
        return Err(
            "transformation.review_bases fields are not the exact supported contract".into(),
        );
    }
    for name in review_names {
        let basis = review_bases
            .get(name)
            .and_then(serde_json::Value::as_object)
            .ok_or_else(|| format!("transformation.review_bases.{name} must be an object"))?;
        collect_exact_basis(
            basis,
            &format!("transformation.review_bases.{name}"),
            None,
            &mut used_extractions,
            &mut used_assumptions,
        )?;
    }
    let baseline = transformation
        .get("baseline_cumulative_hazards")
        .and_then(serde_json::Value::as_array)
        .filter(|items| items.len() == cycles)
        .ok_or("transformation.baseline_cumulative_hazards must cover every model cycle")?;
    let mut previous_hazard = 0.0;
    let mut any_positive = false;
    let mut schedule = Vec::with_capacity(cycles);
    for (index, entry) in baseline.iter().enumerate() {
        let label = format!("transformation.baseline_cumulative_hazards[{index}]");
        let entry = entry
            .as_object()
            .ok_or_else(|| format!("{label} must be an object"))?;
        if !exact_fields(entry, &["cycle", "cumulative_hazard"]) {
            return Err(format!(
                "{label} fields are not the exact supported contract"
            ));
        }
        let cycle = index + 1;
        if entry
            .get("cycle")
            .and_then(serde_json::Value::as_u64)
            .and_then(|value| usize::try_from(value).ok())
            != Some(cycle)
        {
            return Err(format!("{label}.cycle must equal {cycle}"));
        }
        let cumulative_hazard = entry
            .get("cumulative_hazard")
            .and_then(serde_json::Value::as_object)
            .ok_or_else(|| format!("{label}.cumulative_hazard must be an object"))?;
        let cumulative_hazard_value = cumulative_hazard
            .get("value")
            .and_then(serde_json::Value::as_f64)
            .filter(|value| value.is_finite() && *value >= 0.0)
            .ok_or_else(|| {
                format!("{label}.cumulative_hazard.value must be finite and non-negative")
            })?;
        collect_exact_basis(
            cumulative_hazard,
            &format!("{label}.cumulative_hazard"),
            Some("value"),
            &mut used_extractions,
            &mut used_assumptions,
        )?;
        if cumulative_hazard_value + 1e-12 < previous_hazard {
            return Err("baseline_cumulative_hazards must be non-decreasing across cycles".into());
        }
        let increment = (cumulative_hazard_value - previous_hazard).max(0.0);
        any_positive |= increment > 1e-12;
        let integrated_hazard = hazard_ratio_value * increment;
        let event_probability = -(-integrated_hazard).exp_m1();
        if !integrated_hazard.is_finite()
            || integrated_hazard < 0.0
            || !event_probability.is_finite()
            || !(0.0..1.0).contains(&event_probability)
        {
            return Err(format!(
                "{label} produced a non-finite or invalid event probability"
            ));
        }
        let mut matrix = vec![vec![0.0; 2]; 2];
        matrix[from_index][from_index] = 1.0 - event_probability;
        matrix[from_index][event_index] = event_probability;
        matrix[event_index][event_index] = 1.0;
        schedule.push(serde_json::json!({"start_cycle": cycle, "matrix": matrix}));
        previous_hazard = cumulative_hazard_value;
    }
    if !any_positive {
        return Err(
            "baseline_cumulative_hazards must contain at least one positive increment".into(),
        );
    }
    Ok((
        serde_json::Value::Array(schedule),
        used_extractions,
        used_assumptions,
    ))
}

fn derive_competing_rates(
    plan: &serde_json::Value,
    path: &str,
    transformation: &serde_json::Value,
) -> Result<(serde_json::Value, HashSet<String>, HashSet<String>), String> {
    let transformation = transformation
        .as_object()
        .ok_or("derivation.transformation must be an object")?;
    if !exact_fields(
        transformation,
        &["operation", "cycle_length_years", "phases"],
    ) {
        return Err("transformation fields are not the exact supported contract".into());
    }
    if transformation
        .get("operation")
        .and_then(serde_json::Value::as_str)
        != Some("constant_competing_rates")
    {
        return Err("transformation.operation must be constant_competing_rates".into());
    }
    let declared_cycle = transformation
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("transformation.cycle_length_years must be finite and positive")?;
    let plan_cycle = plan
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("analysis cycle_length_years is invalid")?;
    if (declared_cycle - plan_cycle).abs() > 1e-12 {
        return Err("transformation cycle length must equal the analysis cycle length".into());
    }
    let state_count = plan
        .get("states")
        .and_then(serde_json::Value::as_array)
        .map(Vec::len)
        .filter(|count| *count > 0)
        .ok_or("analysis states are missing")?;
    let cycles = plan
        .get("cycles")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .filter(|value| *value > 0)
        .ok_or("analysis cycles are invalid")?;
    let phases = transformation
        .get("phases")
        .and_then(serde_json::Value::as_array)
        .filter(|values| !values.is_empty() && values.len() <= cycles)
        .ok_or("transformation.phases count is invalid")?;
    let mut starts = Vec::new();
    let mut matrices: Vec<Vec<Vec<f64>>> = Vec::new();
    let mut used_extractions = HashSet::new();
    let mut used_assumptions = HashSet::new();
    for (phase_index, phase) in phases.iter().enumerate() {
        let label = format!("transformation.phases[{phase_index}]");
        let phase = phase
            .as_object()
            .ok_or_else(|| format!("{label} must be an object"))?;
        if !exact_fields(phase, &["start_cycle", "rows"]) {
            return Err(format!("{label} fields are invalid"));
        }
        let start = phase
            .get("start_cycle")
            .and_then(serde_json::Value::as_u64)
            .and_then(|value| usize::try_from(value).ok())
            .filter(|value| (1..=cycles).contains(value))
            .ok_or_else(|| format!("{label}.start_cycle is invalid"))?;
        starts.push(start);
        let rows = phase
            .get("rows")
            .and_then(serde_json::Value::as_array)
            .filter(|values| values.len() == state_count)
            .ok_or_else(|| format!("{label}.rows must contain {state_count} rows"))?;
        let mut matrix = Vec::new();
        for (row_index, row) in rows.iter().enumerate() {
            let row_label = format!("{label}.rows[{row_index}]");
            let row = row
                .as_object()
                .ok_or_else(|| format!("{row_label} must be an object"))?;
            if !exact_fields(row, &["self_index", "events"]) {
                return Err(format!("{row_label} fields are invalid"));
            }
            if row
                .get("self_index")
                .and_then(serde_json::Value::as_u64)
                .and_then(|value| usize::try_from(value).ok())
                != Some(row_index)
            {
                return Err(format!(
                    "{row_label}.self_index must equal the row position"
                ));
            }
            let events = row
                .get("events")
                .and_then(serde_json::Value::as_array)
                .filter(|values| values.len() < state_count)
                .ok_or_else(|| format!("{row_label}.events count is invalid"))?;
            let mut targets = HashSet::new();
            let mut parsed = Vec::new();
            let mut total_rate = 0.0;
            for (event_index, event) in events.iter().enumerate() {
                let event_label = format!("{row_label}.events[{event_index}]");
                let event = event
                    .as_object()
                    .ok_or_else(|| format!("{event_label} must be an object"))?;
                let allowed = [
                    "target_index",
                    "rate_per_year",
                    "source_extraction_id",
                    "source_pointer",
                    "assumption_id",
                ];
                if event.keys().any(|field| !allowed.contains(&field.as_str())) {
                    return Err(format!("{event_label} contains unsupported fields"));
                }
                let target = event
                    .get("target_index")
                    .and_then(serde_json::Value::as_u64)
                    .and_then(|value| usize::try_from(value).ok())
                    .filter(|value| *value < state_count && *value != row_index)
                    .ok_or_else(|| format!("{event_label}.target_index is invalid"))?;
                if !targets.insert(target) {
                    return Err(format!("{event_label}.target_index is duplicated"));
                }
                let rate = event
                    .get("rate_per_year")
                    .and_then(serde_json::Value::as_f64)
                    .filter(|value| value.is_finite() && *value > 0.0)
                    .ok_or_else(|| format!("{event_label}.rate_per_year must be positive"))?;
                let source_id = event
                    .get("source_extraction_id")
                    .and_then(serde_json::Value::as_str)
                    .filter(|value| !value.trim().is_empty());
                let assumption_id = event
                    .get("assumption_id")
                    .and_then(serde_json::Value::as_str)
                    .filter(|value| !value.trim().is_empty());
                if source_id.is_some() == assumption_id.is_some() {
                    return Err(format!(
                        "{event_label} must declare one extraction or assumption basis"
                    ));
                }
                if let Some(source_id) = source_id {
                    let pointer = match event.get("source_pointer") {
                        Some(value) => value.as_str().ok_or_else(|| {
                            format!("{event_label}.source_pointer must be a string")
                        })?,
                        None => "",
                    };
                    if !pointer.is_empty() && !pointer.starts_with('/') {
                        return Err(format!(
                            "{event_label}.source_pointer must be empty or a JSON pointer"
                        ));
                    }
                    used_extractions.insert(source_id.to_string());
                } else if let Some(assumption_id) = assumption_id {
                    if event.contains_key("source_pointer") {
                        return Err(format!(
                            "{event_label}.source_pointer requires an extraction"
                        ));
                    }
                    used_assumptions.insert(assumption_id.to_string());
                }
                total_rate += rate;
                if !(total_rate * declared_cycle).is_finite() {
                    return Err(format!("{row_label} integrated rate is non-finite"));
                }
                parsed.push((target, rate));
            }
            let mut output_row = vec![0.0; state_count];
            if total_rate == 0.0 {
                output_row[row_index] = 1.0;
            } else {
                let event_mass = -(-total_rate * declared_cycle).exp_m1();
                output_row[row_index] = 1.0 - event_mass;
                for (target, rate) in parsed {
                    output_row[target] = event_mass * rate / total_rate;
                }
            }
            matrix.push(output_row);
        }
        matrices.push(matrix);
    }
    if starts.first() != Some(&1) || starts.windows(2).any(|pair| pair[0] >= pair[1]) {
        return Err("transformation phases must start at cycle 1 and strictly increase".into());
    }
    let output = if path.ends_with(".transition_matrix") {
        if matrices.len() != 1 {
            return Err("a static matrix transformation requires exactly one phase".into());
        }
        serde_json::to_value(&matrices[0]).map_err(|error| error.to_string())?
    } else if path.ends_with(".transition_schedule") {
        serde_json::Value::Array(
            starts
                .into_iter()
                .zip(matrices)
                .map(|(start_cycle, matrix)| {
                    serde_json::json!({"start_cycle": start_cycle, "matrix": matrix})
                })
                .collect(),
        )
    } else {
        return Err("deterministic transformation target is unsupported".into());
    };
    Ok((output, used_extractions, used_assumptions))
}

fn derive_survival_schedule(
    plan: &serde_json::Value,
    path: &str,
    transformation: &serde_json::Value,
) -> Result<(serde_json::Value, HashSet<String>, HashSet<String>), String> {
    if !path.ends_with(".transition_schedule") {
        return Err(
            "parametric survival transformation is allowed only for a transition schedule".into(),
        );
    }
    let transformation = transformation
        .as_object()
        .ok_or("derivation.transformation must be an object")?;
    if !exact_fields(
        transformation,
        &[
            "operation",
            "cycle_length_years",
            "from_state_index",
            "event_state_index",
            "distribution",
            "parameters",
        ],
    ) {
        return Err("survival transformation fields are not the exact supported contract".into());
    }
    if transformation
        .get("operation")
        .and_then(serde_json::Value::as_str)
        != Some("parametric_survival_to_transition_schedule")
    {
        return Err(
            "transformation.operation must be parametric_survival_to_transition_schedule".into(),
        );
    }
    let state_count = plan
        .get("states")
        .and_then(serde_json::Value::as_array)
        .map(Vec::len)
        .unwrap_or_default();
    if state_count != 2 {
        return Err("parametric survival transformation requires exactly two states".into());
    }
    let cycles = plan
        .get("cycles")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .filter(|value| (1..=10_000).contains(value))
        .ok_or("parametric survival transformation supports 1-10000 cycles")?;
    let declared_cycle = transformation
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("transformation.cycle_length_years must be finite and positive")?;
    let plan_cycle = plan
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("analysis cycle_length_years is invalid")?;
    if (declared_cycle - plan_cycle).abs() > 1e-12 {
        return Err(
            "transformation.cycle_length_years must equal the analysis cycle length".into(),
        );
    }
    let from_index = transformation
        .get("from_state_index")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .ok_or("transformation.from_state_index must be an integer")?;
    let event_index = transformation
        .get("event_state_index")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .ok_or("transformation.event_state_index must be an integer")?;
    if !matches!((from_index, event_index), (0, 1) | (1, 0)) {
        return Err(
            "from_state_index and event_state_index must be the two distinct state indices".into(),
        );
    }
    let distribution = transformation
        .get("distribution")
        .and_then(serde_json::Value::as_str)
        .ok_or("transformation.distribution must be exponential or weibull")?;
    let expected_parameters: &[&str] = match distribution {
        "exponential" => &["rate_per_year"],
        "weibull" => &["shape", "scale_years"],
        _ => return Err("transformation.distribution must be exponential or weibull".into()),
    };
    let parameters = transformation
        .get("parameters")
        .and_then(serde_json::Value::as_object)
        .ok_or("transformation.parameters must be an object")?;
    if !exact_fields(parameters, expected_parameters) {
        return Err("transformation.parameters fields do not match the distribution".into());
    }
    let mut parsed = HashMap::new();
    let mut used_extractions = HashSet::new();
    let mut used_assumptions = HashSet::new();
    for name in expected_parameters {
        let label = format!("transformation.parameters.{name}");
        let parameter = parameters
            .get(*name)
            .and_then(serde_json::Value::as_object)
            .ok_or_else(|| format!("{label} must be an object"))?;
        let allowed = [
            "value",
            "source_extraction_id",
            "source_pointer",
            "assumption_id",
        ];
        if parameter
            .keys()
            .any(|field| !allowed.contains(&field.as_str()))
        {
            return Err(format!("{label} contains unsupported fields"));
        }
        let value = parameter
            .get("value")
            .and_then(serde_json::Value::as_f64)
            .filter(|value| value.is_finite() && *value > 0.0)
            .ok_or_else(|| format!("{label}.value must be positive"))?;
        parsed.insert(*name, value);
        let source_id = parameter
            .get("source_extraction_id")
            .and_then(serde_json::Value::as_str)
            .filter(|value| !value.trim().is_empty());
        let assumption_id = parameter
            .get("assumption_id")
            .and_then(serde_json::Value::as_str)
            .filter(|value| !value.trim().is_empty());
        if source_id.is_some() == assumption_id.is_some() {
            return Err(format!(
                "{label} must declare exactly one source_extraction_id or assumption_id"
            ));
        }
        if let Some(source_id) = source_id {
            let pointer = match parameter.get("source_pointer") {
                Some(value) => value
                    .as_str()
                    .ok_or_else(|| format!("{label}.source_pointer must be a string"))?,
                None => "",
            };
            if !pointer.is_empty() && !pointer.starts_with('/') {
                return Err(format!(
                    "{label}.source_pointer must be empty or a JSON pointer"
                ));
            }
            used_extractions.insert(source_id.to_string());
        } else if let Some(assumption_id) = assumption_id {
            if parameter.contains_key("source_pointer") {
                return Err(format!("{label}.source_pointer requires an extraction"));
            }
            used_assumptions.insert(assumption_id.to_string());
        }
    }
    let mut previous_hazard = 0.0;
    let mut schedule = Vec::with_capacity(cycles);
    for cycle in 1..=cycles {
        let time_years = cycle as f64 * declared_cycle;
        let cumulative_hazard = if distribution == "exponential" {
            parsed["rate_per_year"] * time_years
        } else {
            (time_years / parsed["scale_years"]).powf(parsed["shape"])
        };
        let increment = cumulative_hazard - previous_hazard;
        if !increment.is_finite() || increment < -1e-12 {
            return Err(
                "parametric survival cumulative hazard must be finite and non-decreasing".into(),
            );
        }
        let event_probability = -(-increment.max(0.0)).exp_m1();
        let mut matrix = vec![vec![0.0; 2]; 2];
        matrix[from_index][from_index] = 1.0 - event_probability;
        matrix[from_index][event_index] = event_probability;
        matrix[event_index][event_index] = 1.0;
        schedule.push(serde_json::json!({"start_cycle": cycle, "matrix": matrix}));
        previous_hazard = cumulative_hazard;
    }
    Ok((
        serde_json::Value::Array(schedule),
        used_extractions,
        used_assumptions,
    ))
}

fn derive_probability_time(
    plan: &serde_json::Value,
    path: &str,
    transformation: &serde_json::Value,
) -> Result<(serde_json::Value, HashSet<String>, HashSet<String>), String> {
    let transformation = transformation
        .as_object()
        .ok_or("derivation.transformation must be an object")?;
    if !exact_fields(
        transformation,
        &["operation", "cycle_length_years", "phases"],
    ) {
        return Err(
            "probability-time transformation fields are not the exact supported contract".into(),
        );
    }
    if transformation
        .get("operation")
        .and_then(serde_json::Value::as_str)
        != Some("single_event_probability_time_conversion")
    {
        return Err(
            "transformation.operation must be single_event_probability_time_conversion".into(),
        );
    }
    let declared_cycle = transformation
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("transformation.cycle_length_years must be finite and positive")?;
    let plan_cycle = plan
        .get("cycle_length_years")
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or("analysis cycle_length_years is invalid")?;
    if (declared_cycle - plan_cycle).abs() > 1e-12 {
        return Err(
            "transformation.cycle_length_years must equal the analysis cycle length".into(),
        );
    }
    let state_count = plan
        .get("states")
        .and_then(serde_json::Value::as_array)
        .map(Vec::len)
        .filter(|value| *value > 0)
        .ok_or("analysis states are invalid")?;
    let cycles = plan
        .get("cycles")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .filter(|value| *value > 0)
        .ok_or("analysis cycles are invalid")?;
    let phases = transformation
        .get("phases")
        .and_then(serde_json::Value::as_array)
        .filter(|value| !value.is_empty() && value.len() <= cycles)
        .ok_or("transformation.phases count is invalid")?;
    let mut starts = Vec::with_capacity(phases.len());
    let mut matrices = Vec::with_capacity(phases.len());
    let mut used_extractions = HashSet::new();
    let mut used_assumptions = HashSet::new();
    for (phase_index, phase) in phases.iter().enumerate() {
        let phase_label = format!("transformation.phases[{phase_index}]");
        let phase = phase
            .as_object()
            .ok_or_else(|| format!("{phase_label} must be an object"))?;
        if !exact_fields(phase, &["start_cycle", "rows"]) {
            return Err(format!("{phase_label} fields are invalid"));
        }
        let start = phase
            .get("start_cycle")
            .and_then(serde_json::Value::as_u64)
            .and_then(|value| usize::try_from(value).ok())
            .filter(|value| (1..=cycles).contains(value))
            .ok_or_else(|| format!("{phase_label}.start_cycle is invalid"))?;
        starts.push(start);
        let rows = phase
            .get("rows")
            .and_then(serde_json::Value::as_array)
            .filter(|value| value.len() == state_count)
            .ok_or_else(|| format!("{phase_label}.rows must contain {state_count} rows"))?;
        let mut matrix = Vec::with_capacity(state_count);
        for (row_index, row) in rows.iter().enumerate() {
            let row_label = format!("{phase_label}.rows[{row_index}]");
            let row = row
                .as_object()
                .ok_or_else(|| format!("{row_label} must be an object"))?;
            if !exact_fields(row, &["self_index", "event"]) {
                return Err(format!("{row_label} fields are invalid"));
            }
            if row
                .get("self_index")
                .and_then(serde_json::Value::as_u64)
                .and_then(|value| usize::try_from(value).ok())
                != Some(row_index)
            {
                return Err(format!(
                    "{row_label}.self_index must equal the row position"
                ));
            }
            let mut output_row = vec![0.0; state_count];
            output_row[row_index] = 1.0;
            if let Some(event) = row.get("event").filter(|value| !value.is_null()) {
                let event_label = format!("{row_label}.event");
                let event = event
                    .as_object()
                    .ok_or_else(|| format!("{event_label} must be an object"))?;
                let allowed = [
                    "target_index",
                    "source_probability",
                    "source_interval_years",
                    "source_extraction_id",
                    "source_pointer",
                    "assumption_id",
                ];
                if event.keys().any(|field| !allowed.contains(&field.as_str())) {
                    return Err(format!("{event_label} contains unsupported fields"));
                }
                let target = event
                    .get("target_index")
                    .and_then(serde_json::Value::as_u64)
                    .and_then(|value| usize::try_from(value).ok())
                    .filter(|value| *value < state_count && *value != row_index)
                    .ok_or_else(|| format!("{event_label}.target_index is invalid"))?;
                let probability = event
                    .get("source_probability")
                    .and_then(serde_json::Value::as_f64)
                    .filter(|value| value.is_finite() && *value > 0.0 && *value < 1.0)
                    .ok_or_else(|| {
                        format!("{event_label}.source_probability must be strictly between 0 and 1")
                    })?;
                let source_interval = event
                    .get("source_interval_years")
                    .and_then(serde_json::Value::as_f64)
                    .filter(|value| value.is_finite() && *value > 0.0)
                    .ok_or_else(|| {
                        format!("{event_label}.source_interval_years must be positive")
                    })?;
                let source_id = event
                    .get("source_extraction_id")
                    .and_then(serde_json::Value::as_str)
                    .filter(|value| !value.trim().is_empty());
                let assumption_id = event
                    .get("assumption_id")
                    .and_then(serde_json::Value::as_str)
                    .filter(|value| !value.trim().is_empty());
                if source_id.is_some() == assumption_id.is_some() {
                    return Err(format!(
                        "{event_label} must declare exactly one source extraction or assumption"
                    ));
                }
                if let Some(source_id) = source_id {
                    let pointer = match event.get("source_pointer") {
                        Some(value) => value.as_str().ok_or_else(|| {
                            format!("{event_label}.source_pointer must be a string")
                        })?,
                        None => "",
                    };
                    if !pointer.is_empty() && !pointer.starts_with('/') {
                        return Err(format!(
                            "{event_label}.source_pointer must be empty or a JSON pointer"
                        ));
                    }
                    used_extractions.insert(source_id.to_string());
                } else if let Some(assumption_id) = assumption_id {
                    if event.contains_key("source_pointer") {
                        return Err(format!(
                            "{event_label}.source_pointer requires an extraction"
                        ));
                    }
                    used_assumptions.insert(assumption_id.to_string());
                }
                let converted =
                    -((-probability).ln_1p() * declared_cycle / source_interval).exp_m1();
                if !converted.is_finite() || converted <= 0.0 || converted >= 1.0 {
                    return Err(format!(
                        "{event_label} conversion produced an invalid probability"
                    ));
                }
                output_row[row_index] = 1.0 - converted;
                output_row[target] = converted;
            }
            matrix.push(output_row);
        }
        matrices.push(matrix);
    }
    if starts.first() != Some(&1) || starts.windows(2).any(|pair| pair[0] >= pair[1]) {
        return Err("transformation phases must start at cycle 1 and strictly increase".into());
    }
    let output = if path.ends_with(".transition_matrix") {
        if matrices.len() != 1 {
            return Err("a static matrix transformation requires exactly one phase".into());
        }
        serde_json::to_value(&matrices[0]).map_err(|error| error.to_string())?
    } else if path.ends_with(".transition_schedule") {
        serde_json::Value::Array(
            starts
                .into_iter()
                .zip(matrices)
                .map(|(start_cycle, matrix)| {
                    serde_json::json!({"start_cycle": start_cycle, "matrix": matrix})
                })
                .collect(),
        )
    } else {
        return Err("probability-time transformation target is unsupported".into());
    };
    Ok((output, used_extractions, used_assumptions))
}

fn transition_rate_declaration_reasons(
    plan: &serde_json::Value,
    path: &str,
    mapping: &serde_json::Value,
    derivation: &serde_json::Map<String, serde_json::Value>,
) -> Vec<String> {
    if !matches!(
        plan.get("schema_version")
            .and_then(serde_json::Value::as_str),
        Some("0.5.0" | "0.8.0" | "0.9.0" | "0.10.0" | "0.11.0")
    ) {
        return vec![
            "deterministic transition-rate transformations require schema_version 0.5.0 through 0.11.0"
                .into(),
        ];
    }
    if !transition_path(path) {
        return vec!["deterministic transformation is allowed only for transition inputs".into()];
    }
    let Some(transformation) = derivation.get("transformation") else {
        return vec!["derivation.transformation must be an object".into()];
    };
    let (output, used_extractions, used_assumptions) =
        match derive_competing_rates(plan, path, transformation) {
            Ok(value) => value,
            Err(error) => return vec![error],
        };
    let mut reasons = Vec::new();
    if !model_value(plan, path).is_some_and(|target| json_equivalent(&output, target)) {
        reasons
            .push("constant competing rates do not reproduce the current transition input".into());
    }
    let selected_extractions = string_list(mapping.get("extraction_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let selected_assumptions = string_list(mapping.get("assumption_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    if used_extractions != selected_extractions {
        reasons.push("transformation must use every selected extraction".into());
    }
    if used_assumptions != selected_assumptions {
        reasons.push("transformation must use every proposed assumption".into());
    }
    reasons
}

fn survival_curve_declaration_reasons(
    plan: &serde_json::Value,
    path: &str,
    mapping: &serde_json::Value,
    derivation: &serde_json::Map<String, serde_json::Value>,
) -> Vec<String> {
    if !matches!(
        plan.get("schema_version")
            .and_then(serde_json::Value::as_str),
        Some("0.6.0" | "0.8.0" | "0.9.0" | "0.10.0" | "0.11.0")
    ) {
        return vec![
            "parametric survival transformations require schema_version 0.6.0 through 0.11.0"
                .into(),
        ];
    }
    let Some(transformation) = derivation.get("transformation") else {
        return vec!["derivation.transformation must be an object".into()];
    };
    let (output, used_extractions, used_assumptions) =
        match derive_survival_schedule(plan, path, transformation) {
            Ok(value) => value,
            Err(error) => return vec![error],
        };
    let mut reasons = Vec::new();
    if !model_value(plan, path).is_some_and(|target| json_equivalent(&output, target)) {
        reasons.push(
            "parametric survival curve does not reproduce the current transition schedule".into(),
        );
    }
    let selected_extractions = string_list(mapping.get("extraction_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let selected_assumptions = string_list(mapping.get("assumption_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    if used_extractions != selected_extractions {
        reasons.push("transformation must use every selected extraction".into());
    }
    if used_assumptions != selected_assumptions {
        reasons.push("transformation must use every proposed assumption".into());
    }
    reasons
}

fn probability_time_declaration_reasons(
    plan: &serde_json::Value,
    path: &str,
    mapping: &serde_json::Value,
    derivation: &serde_json::Map<String, serde_json::Value>,
) -> Vec<String> {
    if !matches!(
        plan.get("schema_version")
            .and_then(serde_json::Value::as_str),
        Some("0.7.0" | "0.8.0" | "0.9.0" | "0.10.0" | "0.11.0")
    ) {
        return vec![
            "probability-time transformations require schema_version 0.7.0 through 0.11.0".into(),
        ];
    }
    if !transition_path(path) {
        return vec![
            "probability-time transformation is allowed only for transition inputs".into(),
        ];
    }
    let Some(transformation) = derivation.get("transformation") else {
        return vec!["derivation.transformation must be an object".into()];
    };
    let (output, used_extractions, used_assumptions) =
        match derive_probability_time(plan, path, transformation) {
            Ok(value) => value,
            Err(error) => return vec![error],
        };
    let mut reasons = Vec::new();
    if !model_value(plan, path).is_some_and(|target| json_equivalent(&output, target)) {
        reasons.push("source probabilities do not reproduce the current transition input".into());
    }
    let selected_extractions = string_list(mapping.get("extraction_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let selected_assumptions = string_list(mapping.get("assumption_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    if used_extractions != selected_extractions {
        reasons.push("transformation must use every selected extraction".into());
    }
    if used_assumptions != selected_assumptions {
        reasons.push("transformation must use every proposed assumption".into());
    }
    reasons
}

fn background_mortality_declaration_reasons(
    plan: &serde_json::Value,
    path: &str,
    mapping: &serde_json::Value,
    derivation: &serde_json::Map<String, serde_json::Value>,
) -> Vec<String> {
    if plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        .is_none_or(|version| !matches!(version, "0.9.0" | "0.10.0" | "0.11.0"))
    {
        return vec![
            "background mortality transformations require schema_version 0.9.0 through 0.11.0"
                .into(),
        ];
    }
    let Some(transformation) = derivation.get("transformation") else {
        return vec!["derivation.transformation must be an object".into()];
    };
    let (output, used_extractions, used_assumptions) =
        match derive_background_mortality_schedule(plan, path, transformation) {
            Ok(value) => value,
            Err(error) => return vec![error],
        };
    let mut reasons = Vec::new();
    if mapping.get("jurisdiction") != transformation.pointer("/life_table/jurisdiction") {
        reasons.push("life-table jurisdiction must match the input-provenance jurisdiction".into());
    }
    if !model_value(plan, path).is_some_and(|target| json_equivalent(&output, target)) {
        reasons.push(
            "background plus excess mortality does not reproduce the current transition schedule"
                .into(),
        );
    }
    let selected_extractions = string_list(mapping.get("extraction_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let selected_assumptions = string_list(mapping.get("assumption_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    if used_extractions != selected_extractions {
        reasons.push("transformation must use every selected extraction".into());
    }
    if used_assumptions != selected_assumptions {
        reasons.push("transformation must use every proposed assumption".into());
    }
    reasons
}

fn relative_effect_declaration_reasons(
    plan: &serde_json::Value,
    path: &str,
    mapping: &serde_json::Value,
    derivation: &serde_json::Map<String, serde_json::Value>,
) -> Vec<String> {
    if plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        .is_none_or(|version| !matches!(version, "0.10.0" | "0.11.0"))
    {
        return vec![
            "relative-effect transformations require schema_version 0.10.0 or 0.11.0".into(),
        ];
    }
    let Some(transformation) = derivation.get("transformation") else {
        return vec!["derivation.transformation must be an object".into()];
    };
    let (output, used_extractions, used_assumptions) =
        match derive_relative_effect_schedule(plan, path, transformation) {
            Ok(value) => value,
            Err(error) => return vec![error],
        };
    let mut reasons = Vec::new();
    if !model_value(plan, path).is_some_and(|target| json_equivalent(&output, target)) {
        reasons.push("relative effect does not reproduce the current transition schedule".into());
    }
    let selected_extractions = string_list(mapping.get("extraction_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let selected_assumptions = string_list(mapping.get("assumption_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    if used_extractions != selected_extractions {
        reasons.push("transformation must use every selected extraction".into());
    }
    if used_assumptions != selected_assumptions {
        reasons.push("transformation must use every proposed assumption".into());
    }
    reasons
}

fn hazard_ratio_declaration_reasons(
    plan: &serde_json::Value,
    path: &str,
    mapping: &serde_json::Value,
    derivation: &serde_json::Map<String, serde_json::Value>,
) -> Vec<String> {
    if plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.11.0")
    {
        return vec!["hazard-ratio transformations require schema_version 0.11.0".into()];
    }
    let Some(transformation) = derivation.get("transformation") else {
        return vec!["derivation.transformation must be an object".into()];
    };
    let (output, used_extractions, used_assumptions) =
        match derive_hazard_ratio_schedule(plan, path, transformation) {
            Ok(value) => value,
            Err(error) => return vec![error],
        };
    let mut reasons = Vec::new();
    if !model_value(plan, path).is_some_and(|target| json_equivalent(&output, target)) {
        reasons.push("hazard ratio does not reproduce the current transition schedule".into());
    }
    let selected_extractions = string_list(mapping.get("extraction_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let selected_assumptions = string_list(mapping.get("assumption_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    if used_extractions != selected_extractions {
        reasons.push("transformation must use every selected extraction".into());
    }
    if used_assumptions != selected_assumptions {
        reasons.push("transformation must use every proposed assumption".into());
    }
    reasons
}

fn derivation_declaration_reasons(
    plan: &serde_json::Value,
    path: &str,
    mapping: &serde_json::Value,
    source_ids: &[&str],
    assumption_ids: &[&str],
    extraction_ids: &[&str],
) -> Vec<String> {
    let mut reasons = Vec::new();
    let Some(derivation) = mapping
        .get("derivation")
        .and_then(serde_json::Value::as_object)
    else {
        return vec!["derivation must be an object".into()];
    };
    let target_matches = model_value(plan, path)
        .filter(|target| !target.is_null())
        .is_some_and(|target| {
            derivation
                .get("model_value")
                .is_some_and(|value| json_equivalent(value, target))
        });
    if !target_matches {
        reasons.push("derivation.model_value does not match the current model input".into());
    }
    let method = derivation
        .get("method")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    if method == "deterministic_transformation" {
        match derivation
            .get("transformation")
            .and_then(|value| value.get("operation"))
            .and_then(serde_json::Value::as_str)
        {
            Some("constant_competing_rates") => reasons.extend(
                transition_rate_declaration_reasons(plan, path, mapping, derivation),
            ),
            Some("parametric_survival_to_transition_schedule") => reasons.extend(
                survival_curve_declaration_reasons(plan, path, mapping, derivation),
            ),
            Some("single_event_probability_time_conversion") => reasons.extend(
                probability_time_declaration_reasons(plan, path, mapping, derivation),
            ),
            Some("background_plus_excess_mortality_to_transition_schedule") => reasons.extend(
                background_mortality_declaration_reasons(plan, path, mapping, derivation),
            ),
            Some("relative_effect_to_transition_schedule") => reasons.extend(
                relative_effect_declaration_reasons(plan, path, mapping, derivation),
            ),
            Some("hazard_ratio_to_transition_schedule") => reasons.extend(
                hazard_ratio_declaration_reasons(plan, path, mapping, derivation),
            ),
            _ => reasons.push("deterministic transformation operation is unsupported".into()),
        }
        return reasons;
    }
    if source_ids.is_empty() {
        if method != "explicit_assumption" {
            reasons.push(
                "assumption-only input must use derivation method explicit_assumption".into(),
            );
        }
        if !extraction_ids.is_empty() {
            reasons.push("explicit_assumption derivation must not claim extraction IDs".into());
        }
        if assumption_ids.is_empty() {
            reasons.push("explicit_assumption derivation requires a proposed assumption".into());
        }
    } else {
        let expected = if monetary_path(path) {
            "monetary_adjustment"
        } else {
            "direct_evidence"
        };
        if method != expected {
            reasons.push(format!(
                "source-based input must use derivation method {expected}"
            ));
        } else if method == "direct_evidence" && extraction_ids.len() != 1 {
            reasons.push("direct_evidence requires exactly one extraction".into());
        }
    }
    reasons
}

fn monetary_adjustment_reasons(
    plan: &serde_json::Value,
    path: &str,
    mapping: &serde_json::Value,
    economic_basis: Option<(&str, u64)>,
    valid_sources: &HashSet<&str>,
    assumption_statuses: &HashMap<&str, &str>,
) -> Vec<String> {
    let Some((currency, price_year)) = economic_basis else {
        return vec!["current economic_basis is missing or invalid".into()];
    };
    let mut reasons = Vec::new();
    if currency_code(mapping.get("currency")) != Some(currency) {
        reasons.push("currency does not match economic_basis.currency".into());
    }
    if mapping
        .get("price_year")
        .and_then(serde_json::Value::as_u64)
        != Some(price_year)
    {
        reasons.push("price_year does not match economic_basis.price_year".into());
    }
    let Some(target) = model_value(plan, path) else {
        reasons.push("model monetary value is missing".into());
        return reasons;
    };
    let target_values = match target.as_array() {
        Some(values) if !values.is_empty() => values
            .iter()
            .filter_map(serde_json::Value::as_f64)
            .collect::<Vec<_>>(),
        Some(_) => Vec::new(),
        None => target.as_f64().into_iter().collect::<Vec<_>>(),
    };
    if target_values.is_empty()
        || target_values.len() != target.as_array().map_or(1, Vec::len)
        || target_values
            .iter()
            .any(|value| !value.is_finite() || *value < 0.0)
    {
        reasons.push("model monetary value is missing, non-finite, or negative".into());
        return reasons;
    }
    let Some(adjustments) = mapping
        .get("monetary_adjustments")
        .and_then(serde_json::Value::as_array)
    else {
        reasons.push("monetary_adjustments must cover every model value exactly once".into());
        return reasons;
    };
    if adjustments.len() != target_values.len() {
        reasons.push("monetary_adjustments must cover every model value exactly once".into());
        return reasons;
    }
    let target_is_array = target.is_array();
    let mut seen = HashSet::new();
    for (position, adjustment) in adjustments.iter().enumerate() {
        let label = format!("monetary_adjustments[{position}]");
        let Some(adjustment) = adjustment.as_object() else {
            reasons.push(format!("{label} must be an object"));
            continue;
        };
        let target_index = if target_is_array {
            let Some(index) = adjustment
                .get("target_index")
                .and_then(serde_json::Value::as_u64)
                .and_then(|value| usize::try_from(value).ok())
                .filter(|value| *value < target_values.len())
            else {
                reasons.push(format!("{label}.target_index is invalid"));
                continue;
            };
            index
        } else {
            if adjustment.contains_key("target_index") {
                reasons.push(format!("{label}.target_index must be omitted for a scalar"));
            }
            0
        };
        if !seen.insert(target_index) {
            reasons.push(format!("{label}.target_index is duplicated"));
            continue;
        }
        let Some(source_value) = adjustment
            .get("source_value")
            .and_then(serde_json::Value::as_f64)
            .filter(|value| value.is_finite() && *value >= 0.0)
        else {
            reasons.push(format!(
                "{label}.source_value must be finite and non-negative"
            ));
            continue;
        };
        let Some(factor) = adjustment
            .get("factor")
            .and_then(serde_json::Value::as_f64)
            .filter(|value| value.is_finite() && *value > 0.0)
        else {
            reasons.push(format!("{label}.factor must be finite and positive"));
            continue;
        };
        let source_currency = currency_code(adjustment.get("source_currency"));
        if source_currency.is_none() {
            reasons.push(format!(
                "{label}.source_currency must be an ISO 4217-format code"
            ));
        }
        let source_year = adjustment
            .get("source_price_year")
            .and_then(serde_json::Value::as_u64)
            .filter(|year| (1900..=2100).contains(year));
        if source_year.is_none() {
            reasons.push(format!(
                "{label}.source_price_year must be from 1900 to 2100"
            ));
        }
        let target_value = target_values[target_index];
        let difference = (source_value * factor - target_value).abs();
        let tolerance = (target_value.abs() * 1e-9).max(1e-6);
        if difference > tolerance {
            reasons.push(format!("{label} does not reproduce model value"));
        }
        let basis_ids = adjustment
            .get("basis_ids")
            .and_then(serde_json::Value::as_array)
            .filter(|values| {
                values.iter().all(|value| {
                    value
                        .as_str()
                        .is_some_and(|identifier| !identifier.trim().is_empty())
                })
            });
        if basis_ids.is_none() {
            reasons.push(format!("{label}.basis_ids must be an array"));
        }
        let basis_ids = basis_ids
            .into_iter()
            .flatten()
            .filter_map(serde_json::Value::as_str);
        let basis_ids = basis_ids.collect::<Vec<_>>();
        let same_basis = source_currency == Some(currency) && source_year == Some(price_year);
        let method = adjustment
            .get("method")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("");
        if same_basis && (factor - 1.0).abs() <= 1e-12 {
            if method != "none" || !basis_ids.is_empty() {
                reasons.push(format!(
                    "{label} must use method none and no basis_ids when no adjustment is needed"
                ));
            }
        } else {
            if method.trim().is_empty() || method.eq_ignore_ascii_case("none") {
                reasons.push(format!(
                    "{label}.method must explain the applied adjustment"
                ));
            }
            if basis_ids.is_empty()
                || basis_ids.iter().any(|identifier| {
                    !valid_sources.contains(identifier)
                        && assumption_statuses.get(identifier).copied() != Some("proposed")
                })
            {
                reasons.push(format!(
                    "{label}.basis_ids must link valid evidence or proposed assumptions"
                ));
            }
        }
    }
    if seen.len() != target_values.len() {
        reasons.push("monetary_adjustments do not cover every target index".into());
    }
    reasons
}

pub fn audit_plan_bytes(raw: &[u8]) -> Result<EvidenceAudit, String> {
    let plan: serde_json::Value = serde_json::from_slice(raw)
        .map_err(|error| format!("analysis plan evidence audit failed: {error}"))?;
    Ok(audit_plan(&plan))
}

pub fn audit_plan(plan: &serde_json::Value) -> EvidenceAudit {
    let required = required_input_paths(plan);
    let required_set: HashSet<&str> = required.iter().map(String::as_str).collect();
    let sources = plan
        .get("evidence_sources")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let assumptions = plan
        .get("assumptions")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let mappings = plan
        .get("input_provenance")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);

    let source_id_counts = sources.iter().fold(HashMap::new(), |mut counts, source| {
        if let Some(id) = source.get("id").and_then(serde_json::Value::as_str) {
            *counts.entry(id).or_insert(0usize) += 1;
        }
        counts
    });
    let mut valid_sources = HashSet::new();
    for source in sources {
        let Some(id) = source.get("id").and_then(serde_json::Value::as_str) else {
            continue;
        };
        let local_path = source.get("local_path").and_then(serde_json::Value::as_str);
        let locator_valid =
            nonempty(source.get("url")) || local_path.is_some_and(|v| !v.trim().is_empty());
        let local_snapshot_valid = local_path.is_none_or(|_| {
            source
                .get("content_sha256")
                .and_then(serde_json::Value::as_str)
                .is_some_and(is_sha256)
        });
        if !id.trim().is_empty()
            && source_id_counts.get(id) == Some(&1)
            && nonempty(source.get("title"))
            && nonempty(source.get("source_type"))
            && nonempty(source.get("accessed_on"))
            && locator_valid
            && local_snapshot_valid
        {
            valid_sources.insert(id);
        }
    }

    let mut assumption_statuses = HashMap::new();
    let mut unresolved_assumptions = Vec::new();
    for assumption in assumptions {
        let Some(id) = assumption.get("id").and_then(serde_json::Value::as_str) else {
            continue;
        };
        let status = assumption
            .get("status")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("unresolved");
        if !id.trim().is_empty()
            && nonempty(assumption.get("statement"))
            && nonempty(assumption.get("reason"))
        {
            assumption_statuses.insert(id, status);
        }
        if status == "unresolved" {
            unresolved_assumptions.push(id.to_string());
        }
    }

    let mut seen = HashSet::new();
    let mut covered = HashSet::new();
    let mut invalid_mappings = Vec::new();
    if !matches!(
        plan.get("schema_version")
            .and_then(serde_json::Value::as_str),
        Some(
            "0.3.0"
                | "0.4.0"
                | "0.5.0"
                | "0.6.0"
                | "0.7.0"
                | "0.8.0"
                | "0.9.0"
                | "0.10.0"
                | "0.11.0"
                | "0.12.0"
                | "0.13.0"
                | "0.14.0"
        )
    ) {
        invalid_mappings
            .push("schema_version must be 0.3.0 through 0.14.0 for approval review".into());
    }
    let declared_strategy_ids = strategy_ids(plan);
    if plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        .is_some_and(|version| {
            matches!(
                version,
                "0.8.0" | "0.9.0" | "0.10.0" | "0.11.0" | "0.12.0" | "0.13.0" | "0.14.0"
            )
        })
    {
        let raw_strategy_count = plan
            .get("strategy_order")
            .and_then(serde_json::Value::as_array)
            .map(Vec::len);
        let unique = declared_strategy_ids
            .iter()
            .copied()
            .collect::<HashSet<_>>();
        let baseline = plan
            .get("baseline_strategy_id")
            .and_then(serde_json::Value::as_str);
        let actual = plan
            .get("strategies")
            .and_then(serde_json::Value::as_object)
            .map(|items| items.keys().map(String::as_str).collect::<HashSet<_>>())
            .unwrap_or_default();
        if raw_strategy_count != Some(declared_strategy_ids.len())
            || !(2..=16).contains(&declared_strategy_ids.len())
            || unique.len() != declared_strategy_ids.len()
            || declared_strategy_ids
                .iter()
                .any(|item| !safe_strategy_id(item))
            || baseline != declared_strategy_ids.first().copied()
            || actual != unique
        {
            invalid_mappings.push(
                "schema 0.8.0 through 0.14.0 requires 2-16 unique safe strategy ids, an exact strategies object, and baseline_strategy_id first".into(),
            );
        }
    }
    for role in declared_strategy_ids {
        let strategy = plan.pointer(&format!("/strategies/{role}"));
        let has_matrix = strategy
            .and_then(|value| value.get("transition_matrix"))
            .is_some_and(|value| !value.is_null());
        let has_schedule = strategy
            .and_then(|value| value.get("transition_schedule"))
            .is_some_and(|value| !value.is_null());
        if plan
            .get("schema_version")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|version| matches!(version, "0.12.0" | "0.13.0" | "0.14.0"))
            && (has_matrix || has_schedule)
        {
            invalid_mappings.push(format!(
                "strategies.{role} transition structure is forbidden for partitioned survival"
            ));
        } else if plan
            .get("schema_version")
            .and_then(serde_json::Value::as_str)
            .is_none_or(|version| !matches!(version, "0.12.0" | "0.13.0" | "0.14.0"))
            && has_matrix == has_schedule
        {
            invalid_mappings.push(format!(
                "strategies.{role} must define exactly one of transition_matrix or transition_schedule"
            ));
        }
        if has_schedule
            && !matches!(
                plan.get("schema_version")
                    .and_then(serde_json::Value::as_str),
                Some(
                    "0.4.0" | "0.5.0" | "0.6.0" | "0.7.0" | "0.8.0" | "0.9.0" | "0.10.0" | "0.11.0"
                )
            )
        {
            invalid_mappings.push(format!(
                "strategies.{role}.transition_schedule requires schema_version 0.4.0 through 0.11.0"
            ));
        }
    }
    let economic_basis = plan
        .get("economic_basis")
        .and_then(serde_json::Value::as_object)
        .and_then(|basis| {
            let currency = currency_code(basis.get("currency"))?;
            let price_year = basis
                .get("price_year")
                .and_then(serde_json::Value::as_u64)
                .filter(|year| (1900..=2100).contains(year))?;
            Some((currency, price_year))
        });
    if economic_basis.is_none() {
        invalid_mappings.push("economic_basis must declare a valid currency and price_year".into());
    }
    let mut source_based_inputs = 0usize;
    let mut selected_extractions = HashSet::new();
    let synthesis_binding = plan
        .get("evidence_synthesis")
        .and_then(serde_json::Value::as_object);
    let synthesis_binding_valid = synthesis_binding.is_some_and(|binding| {
        binding.get("path").and_then(serde_json::Value::as_str)
            == Some(crate::heor_synthesis::EVIDENCE_SYNTHESIS_PATH)
            && binding
                .get("content_sha256")
                .and_then(serde_json::Value::as_str)
                .is_some_and(is_sha256)
    });
    for mapping in mappings {
        let Some(path) = mapping.get("path").and_then(serde_json::Value::as_str) else {
            invalid_mappings.push("mapping omitted path".into());
            continue;
        };
        let mut reasons: Vec<String> = Vec::new();
        if !required_set.contains(path) {
            reasons.push("path is not a required model input".into());
        }
        if !seen.insert(path) {
            reasons.push("path is duplicated".into());
        }
        if !nonempty(mapping.get("unit")) {
            reasons.push("unit is missing".into());
        }
        if !nonempty(mapping.get("jurisdiction")) {
            reasons.push("jurisdiction is missing".into());
        }
        if !nonempty(mapping.get("selection_rationale")) {
            reasons.push("selection rationale is missing".into());
        }
        let uncertainty_valid = mapping
            .get("uncertainty_status")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|value| {
                matches!(
                    value,
                    "fixed" | "range_available" | "distribution_available"
                )
            });
        if !uncertainty_valid {
            reasons.push("uncertainty status is invalid".into());
        }
        let source_ids = string_list(mapping.get("source_ids")).unwrap_or_default();
        let assumption_ids = string_list(mapping.get("assumption_ids")).unwrap_or_default();
        let extraction_ids = string_list(mapping.get("extraction_ids")).unwrap_or_default();
        if monetary_path(path) {
            reasons.extend(monetary_adjustment_reasons(
                plan,
                path,
                mapping,
                economic_basis,
                &valid_sources,
                &assumption_statuses,
            ));
        }
        reasons.extend(derivation_declaration_reasons(
            plan,
            path,
            mapping,
            &source_ids,
            &assumption_ids,
            &extraction_ids,
        ));
        if source_ids.is_empty() && assumption_ids.is_empty() {
            reasons.push("no evidence source or reviewable assumption is linked".into());
        }
        if source_ids.iter().any(|id| !valid_sources.contains(id)) {
            reasons.push("source link is missing or source metadata is incomplete".into());
        }
        if !source_ids.is_empty() {
            source_based_inputs += 1;
            if !synthesis_binding_valid {
                reasons.push("current evidence synthesis binding is missing or invalid".into());
            }
            if extraction_ids.is_empty() {
                reasons.push("source-based input has no selected extraction".into());
            }
            let unique = extraction_ids.iter().copied().collect::<HashSet<_>>();
            if unique.len() != extraction_ids.len() {
                reasons.push("selected extraction IDs are duplicated".into());
            }
            selected_extractions.extend(extraction_ids.iter().map(|id| (*id).to_string()));
        } else if !extraction_ids.is_empty() {
            reasons.push("extraction IDs require at least one evidence source".into());
        }
        if assumption_ids
            .iter()
            .any(|id| assumption_statuses.get(id).copied() != Some("proposed"))
        {
            reasons.push("assumption link is missing or is not proposed for human review".into());
        }

        if reasons.is_empty() {
            covered.insert(path);
        } else {
            invalid_mappings.push(format!("{path}: {}", reasons.join("; ")));
        }
    }

    let unsupported_inputs = required
        .iter()
        .filter(|path| !covered.contains(path.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    let complete = unsupported_inputs.is_empty()
        && invalid_mappings.is_empty()
        && unresolved_assumptions.is_empty();
    EvidenceAudit {
        complete,
        status: if complete { "complete" } else { "incomplete" },
        required_inputs: required.len(),
        covered_inputs: covered.len(),
        unsupported_inputs,
        invalid_mappings,
        unresolved_assumptions,
        source_count: valid_sources.len(),
        mapping_count: mappings.len(),
        source_based_inputs,
        selected_extraction_count: selected_extractions.len(),
    }
}

fn incomplete_selection(error: String) -> EvidenceSelectionAudit {
    EvidenceSelectionAudit {
        complete: false,
        status: "incomplete",
        synthesis_sha256: String::new(),
        selected_input_count: 0,
        selected_extraction_count: 0,
        verified_extraction_count: 0,
        unverified_extraction_ids: Vec::new(),
        rejected_extraction_ids: Vec::new(),
        invalid_selections: Vec::new(),
        errors: vec![error],
        verification_integrity: "not_checked",
    }
}

fn transition_rate_extraction_reasons(
    mapping: &serde_json::Value,
    extraction_index: &HashMap<String, crate::heor_synthesis::ExtractionLink>,
) -> Vec<String> {
    let selected = string_list(mapping.get("extraction_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let mut used = HashSet::new();
    let mut reasons = Vec::new();
    let phases = mapping
        .pointer("/derivation/transformation/phases")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    for (phase_index, phase) in phases.iter().enumerate() {
        for (row_index, row) in phase
            .get("rows")
            .and_then(serde_json::Value::as_array)
            .into_iter()
            .flatten()
            .enumerate()
        {
            for (event_index, event) in row
                .get("events")
                .and_then(serde_json::Value::as_array)
                .into_iter()
                .flatten()
                .enumerate()
            {
                let label = format!(
                    "transformation.phases[{phase_index}].rows[{row_index}].events[{event_index}]"
                );
                let Some(extraction_id) = event
                    .get("source_extraction_id")
                    .and_then(serde_json::Value::as_str)
                else {
                    continue;
                };
                if !selected.contains(extraction_id) {
                    reasons.push(format!(
                        "{label}.source_extraction_id must reference a selected extraction"
                    ));
                    continue;
                }
                used.insert(extraction_id.to_string());
                let Some(extraction) = extraction_index.get(extraction_id) else {
                    continue;
                };
                let Ok(extracted) =
                    serde_json::from_str::<serde_json::Value>(&extraction.extracted_value)
                else {
                    reasons.push(format!(
                        "{label} source extraction must contain strict JSON"
                    ));
                    continue;
                };
                let pointer = event
                    .get("source_pointer")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or_default();
                let extracted_source = if pointer.is_empty() {
                    Some(&extracted)
                } else {
                    extracted.pointer(pointer)
                };
                let Some(extracted_source) = extracted_source else {
                    reasons.push(format!("{label}.source_pointer does not resolve"));
                    continue;
                };
                if !event
                    .get("rate_per_year")
                    .is_some_and(|value| json_equivalent(value, extracted_source))
                {
                    reasons.push(format!(
                        "{label}.rate_per_year does not match the bound extraction"
                    ));
                }
            }
        }
    }
    if used != selected {
        reasons.push("transformation must use every selected extraction".into());
    }
    reasons
}

fn survival_curve_extraction_reasons(
    mapping: &serde_json::Value,
    extraction_index: &HashMap<String, crate::heor_synthesis::ExtractionLink>,
) -> Vec<String> {
    let selected = string_list(mapping.get("extraction_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let mut used = HashSet::new();
    let mut reasons = Vec::new();
    let Some(parameters) = mapping
        .pointer("/derivation/transformation/parameters")
        .and_then(serde_json::Value::as_object)
    else {
        return vec!["transformation.parameters must be an object".into()];
    };
    for (name, parameter) in parameters {
        let label = format!("transformation.parameters.{name}");
        let Some(extraction_id) = parameter
            .get("source_extraction_id")
            .and_then(serde_json::Value::as_str)
        else {
            continue;
        };
        if !selected.contains(extraction_id) {
            reasons.push(format!(
                "{label}.source_extraction_id must reference a selected extraction"
            ));
            continue;
        }
        used.insert(extraction_id.to_string());
        let Some(extraction) = extraction_index.get(extraction_id) else {
            continue;
        };
        let Ok(extracted) = serde_json::from_str::<serde_json::Value>(&extraction.extracted_value)
        else {
            reasons.push(format!(
                "{label} source extraction must contain strict JSON"
            ));
            continue;
        };
        let pointer = parameter
            .get("source_pointer")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let extracted_source = if pointer.is_empty() {
            Some(&extracted)
        } else {
            extracted.pointer(pointer)
        };
        let Some(extracted_source) = extracted_source else {
            reasons.push(format!("{label}.source_pointer does not resolve"));
            continue;
        };
        if !parameter
            .get("value")
            .is_some_and(|value| json_equivalent(value, extracted_source))
        {
            reasons.push(format!("{label}.value does not match the bound extraction"));
        }
    }
    if used != selected {
        reasons.push("transformation must use every selected extraction".into());
    }
    reasons
}

fn probability_time_extraction_reasons(
    mapping: &serde_json::Value,
    extraction_index: &HashMap<String, crate::heor_synthesis::ExtractionLink>,
) -> Vec<String> {
    let selected = string_list(mapping.get("extraction_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let mut used = HashSet::new();
    let mut reasons = Vec::new();
    let Some(phases) = mapping
        .pointer("/derivation/transformation/phases")
        .and_then(serde_json::Value::as_array)
    else {
        return vec!["transformation.phases must be an array".into()];
    };
    for (phase_index, phase) in phases.iter().enumerate() {
        let rows = phase
            .get("rows")
            .and_then(serde_json::Value::as_array)
            .map(Vec::as_slice)
            .unwrap_or(&[]);
        for (row_index, row) in rows.iter().enumerate() {
            let Some(event) = row.get("event").and_then(serde_json::Value::as_object) else {
                continue;
            };
            let label = format!("transformation.phases[{phase_index}].rows[{row_index}].event");
            let Some(extraction_id) = event
                .get("source_extraction_id")
                .and_then(serde_json::Value::as_str)
            else {
                continue;
            };
            if !selected.contains(extraction_id) {
                reasons.push(format!(
                    "{label}.source_extraction_id must reference a selected extraction"
                ));
                continue;
            }
            used.insert(extraction_id.to_string());
            let Some(extraction) = extraction_index.get(extraction_id) else {
                continue;
            };
            let Ok(extracted) =
                serde_json::from_str::<serde_json::Value>(&extraction.extracted_value)
            else {
                reasons.push(format!(
                    "{label} source extraction must contain strict JSON"
                ));
                continue;
            };
            let pointer = event
                .get("source_pointer")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            let extracted_source = if pointer.is_empty() {
                Some(&extracted)
            } else {
                extracted.pointer(pointer)
            };
            let Some(extracted_source) = extracted_source else {
                reasons.push(format!("{label}.source_pointer does not resolve"));
                continue;
            };
            if !event
                .get("source_probability")
                .is_some_and(|value| json_equivalent(value, extracted_source))
            {
                reasons.push(format!(
                    "{label}.source_probability does not match the bound extraction"
                ));
            }
        }
    }
    if used != selected {
        reasons.push("transformation must use every selected extraction".into());
    }
    reasons
}

fn validate_background_extraction_basis(
    basis: &serde_json::Value,
    expected_value: Option<&serde_json::Value>,
    label: &str,
    selected: &HashSet<String>,
    used: &mut HashSet<String>,
    extraction_index: &HashMap<String, crate::heor_synthesis::ExtractionLink>,
    reasons: &mut Vec<String>,
) {
    let Some(extraction_id) = basis
        .get("source_extraction_id")
        .and_then(serde_json::Value::as_str)
    else {
        return;
    };
    if !selected.contains(extraction_id) {
        reasons.push(format!(
            "{label}.source_extraction_id must reference a selected extraction"
        ));
        return;
    }
    used.insert(extraction_id.to_string());
    let Some(extraction) = extraction_index.get(extraction_id) else {
        return;
    };
    let Ok(extracted) = serde_json::from_str::<serde_json::Value>(&extraction.extracted_value)
    else {
        reasons.push(format!(
            "{label} source extraction must contain strict JSON"
        ));
        return;
    };
    let pointer = basis
        .get("source_pointer")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let extracted_source = if pointer.is_empty() {
        Some(&extracted)
    } else {
        extracted.pointer(pointer)
    };
    let Some(extracted_source) = extracted_source else {
        reasons.push(format!("{label}.source_pointer does not resolve"));
        return;
    };
    if expected_value.is_some_and(|value| !json_equivalent(value, extracted_source)) {
        reasons.push(format!("{label}.value does not match the bound extraction"));
    }
}

fn background_mortality_extraction_reasons(
    mapping: &serde_json::Value,
    extraction_index: &HashMap<String, crate::heor_synthesis::ExtractionLink>,
) -> Vec<String> {
    let selected = string_list(mapping.get("extraction_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let transformation = mapping
        .pointer("/derivation/transformation")
        .unwrap_or(&serde_json::Value::Null);
    let mut used = HashSet::new();
    let mut reasons = Vec::new();
    if let Some(excess) = transformation.get("excess_mortality_rate_per_year") {
        validate_background_extraction_basis(
            excess,
            excess.get("value"),
            "transformation.excess_mortality_rate_per_year",
            &selected,
            &mut used,
            extraction_index,
            &mut reasons,
        );
    }
    if let Some(cycles) = transformation
        .pointer("/life_table/cycle_probabilities")
        .and_then(serde_json::Value::as_array)
    {
        for (index, cycle) in cycles.iter().enumerate() {
            if let Some(annual) = cycle.get("annual_probability") {
                validate_background_extraction_basis(
                    annual,
                    annual.get("value"),
                    &format!(
                        "transformation.life_table.cycle_probabilities[{index}].annual_probability"
                    ),
                    &selected,
                    &mut used,
                    extraction_index,
                    &mut reasons,
                );
            }
        }
    }
    for name in ["population_exchangeability", "no_double_counting"] {
        if let Some(basis) = transformation.pointer(&format!("/review_bases/{name}")) {
            validate_background_extraction_basis(
                basis,
                None,
                &format!("transformation.review_bases.{name}"),
                &selected,
                &mut used,
                extraction_index,
                &mut reasons,
            );
        }
    }
    if used != selected {
        reasons.push("transformation must use every selected extraction".into());
    }
    reasons
}

fn relative_effect_extraction_reasons(
    mapping: &serde_json::Value,
    extraction_index: &HashMap<String, crate::heor_synthesis::ExtractionLink>,
) -> Vec<String> {
    let selected = string_list(mapping.get("extraction_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let transformation = mapping
        .pointer("/derivation/transformation")
        .unwrap_or(&serde_json::Value::Null);
    let mut used = HashSet::new();
    let mut reasons = Vec::new();
    if let Some(effect) = transformation.get("relative_effect") {
        validate_background_extraction_basis(
            effect,
            effect.get("value"),
            "transformation.relative_effect",
            &selected,
            &mut used,
            extraction_index,
            &mut reasons,
        );
    }
    if let Some(cycles) = transformation
        .get("baseline_cycle_probabilities")
        .and_then(serde_json::Value::as_array)
    {
        for (index, cycle) in cycles.iter().enumerate() {
            if let Some(probability) = cycle.get("probability") {
                validate_background_extraction_basis(
                    probability,
                    probability.get("value"),
                    &format!("transformation.baseline_cycle_probabilities[{index}].probability"),
                    &selected,
                    &mut used,
                    extraction_index,
                    &mut reasons,
                );
            }
        }
    }
    for name in [
        "endpoint_alignment",
        "population_transportability",
        "effect_constancy_over_cycles",
    ] {
        if let Some(basis) = transformation.pointer(&format!("/review_bases/{name}")) {
            validate_background_extraction_basis(
                basis,
                None,
                &format!("transformation.review_bases.{name}"),
                &selected,
                &mut used,
                extraction_index,
                &mut reasons,
            );
        }
    }
    if used != selected {
        reasons.push("transformation must use every selected extraction".into());
    }
    reasons
}

fn hazard_ratio_extraction_reasons(
    mapping: &serde_json::Value,
    extraction_index: &HashMap<String, crate::heor_synthesis::ExtractionLink>,
) -> Vec<String> {
    let selected = string_list(mapping.get("extraction_ids"))
        .unwrap_or_default()
        .into_iter()
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let transformation = mapping
        .pointer("/derivation/transformation")
        .unwrap_or(&serde_json::Value::Null);
    let mut used = HashSet::new();
    let mut reasons = Vec::new();
    if let Some(effect) = transformation.get("hazard_ratio") {
        validate_background_extraction_basis(
            effect,
            effect.get("value"),
            "transformation.hazard_ratio",
            &selected,
            &mut used,
            extraction_index,
            &mut reasons,
        );
    }
    if let Some(cycles) = transformation
        .get("baseline_cumulative_hazards")
        .and_then(serde_json::Value::as_array)
    {
        for (index, cycle) in cycles.iter().enumerate() {
            if let Some(hazard) = cycle.get("cumulative_hazard") {
                validate_background_extraction_basis(
                    hazard,
                    hazard.get("value"),
                    &format!(
                        "transformation.baseline_cumulative_hazards[{index}].cumulative_hazard"
                    ),
                    &selected,
                    &mut used,
                    extraction_index,
                    &mut reasons,
                );
            }
        }
    }
    for name in [
        "endpoint_alignment",
        "population_transportability",
        "proportional_hazards_assumption",
        "effect_constancy_over_horizon",
        "treatment_switching_assessment",
    ] {
        if let Some(basis) = transformation.pointer(&format!("/review_bases/{name}")) {
            validate_background_extraction_basis(
                basis,
                None,
                &format!("transformation.review_bases.{name}"),
                &selected,
                &mut used,
                extraction_index,
                &mut reasons,
            );
        }
    }
    if used != selected {
        reasons.push("transformation must use every selected extraction".into());
    }
    reasons
}

fn extraction_derivation_reasons(
    plan: &serde_json::Value,
    mapping: &serde_json::Value,
    extraction_index: &HashMap<String, crate::heor_synthesis::ExtractionLink>,
) -> Vec<String> {
    let path = mapping
        .get("path")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("mapping");
    let source_ids = string_list(mapping.get("source_ids")).unwrap_or_default();
    if source_ids.is_empty() {
        return Vec::new();
    }
    let extraction_ids = string_list(mapping.get("extraction_ids")).unwrap_or_default();
    let method = mapping
        .pointer("/derivation/method")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    if method == "deterministic_transformation" {
        return match mapping
            .pointer("/derivation/transformation/operation")
            .and_then(serde_json::Value::as_str)
        {
            Some("constant_competing_rates") => {
                transition_rate_extraction_reasons(mapping, extraction_index)
            }
            Some("parametric_survival_to_transition_schedule") => {
                survival_curve_extraction_reasons(mapping, extraction_index)
            }
            Some("single_event_probability_time_conversion") => {
                probability_time_extraction_reasons(mapping, extraction_index)
            }
            Some("background_plus_excess_mortality_to_transition_schedule") => {
                background_mortality_extraction_reasons(mapping, extraction_index)
            }
            Some("relative_effect_to_transition_schedule") => {
                relative_effect_extraction_reasons(mapping, extraction_index)
            }
            Some("hazard_ratio_to_transition_schedule") => {
                hazard_ratio_extraction_reasons(mapping, extraction_index)
            }
            _ => vec!["deterministic transformation operation is unsupported".into()],
        };
    }
    if !monetary_path(path) {
        let [extraction_id] = extraction_ids.as_slice() else {
            return Vec::new();
        };
        let Some(extraction) = extraction_index.get(*extraction_id) else {
            return Vec::new();
        };
        let Ok(extracted) = serde_json::from_str::<serde_json::Value>(&extraction.extracted_value)
        else {
            return vec![format!(
                "{extraction_id}.extracted_value must be strict JSON"
            )];
        };
        if model_value(plan, path).is_some_and(|target| json_equivalent(&extracted, target)) {
            return Vec::new();
        }
        return vec![format!(
            "{extraction_id}.extracted_value does not equal the model input"
        )];
    }

    let selected = extraction_ids.iter().copied().collect::<HashSet<_>>();
    let mut used = HashSet::new();
    let mut reasons = Vec::new();
    let adjustments = mapping
        .get("monetary_adjustments")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    for (position, adjustment) in adjustments.iter().enumerate() {
        let label = format!("monetary_adjustments[{position}]");
        let Some(adjustment) = adjustment.as_object() else {
            continue;
        };
        let Some(extraction_id) = adjustment
            .get("source_extraction_id")
            .and_then(serde_json::Value::as_str)
            .filter(|identifier| selected.contains(identifier))
        else {
            reasons.push(format!(
                "{label}.source_extraction_id must reference a selected extraction"
            ));
            continue;
        };
        used.insert(extraction_id);
        let Some(extraction) = extraction_index.get(extraction_id) else {
            continue;
        };
        let Ok(extracted) = serde_json::from_str::<serde_json::Value>(&extraction.extracted_value)
        else {
            reasons.push(format!(
                "{label} source extraction must contain strict JSON"
            ));
            continue;
        };
        let extracted_source = if let Some(values) = extracted.as_array() {
            let Some(index) = adjustment
                .get("source_index")
                .and_then(serde_json::Value::as_u64)
                .and_then(|value| usize::try_from(value).ok())
                .filter(|value| *value < values.len())
            else {
                reasons.push(format!("{label}.source_index is invalid"));
                continue;
            };
            &values[index]
        } else {
            if adjustment.contains_key("source_index") {
                reasons.push(format!(
                    "{label}.source_index must be omitted for a scalar extraction"
                ));
            }
            &extracted
        };
        if !adjustment
            .get("source_value")
            .is_some_and(|value| json_equivalent(value, extracted_source))
        {
            reasons.push(format!(
                "{label}.source_value does not match the bound extraction"
            ));
        }
    }
    if used != selected {
        reasons.push("monetary_adjustments must use every selected extraction".into());
    }
    reasons
}

pub(crate) fn audit_evidence_selection_for_plan(
    app: &AppHandle,
    workspace: &Path,
    project_id: &str,
    plan_raw: &[u8],
) -> EvidenceSelectionAudit {
    let plan: serde_json::Value = match serde_json::from_slice(plan_raw) {
        Ok(value) => value,
        Err(error) => {
            return incomplete_selection(format!("analysis plan is invalid JSON: {error}"))
        }
    };
    let source_based_input_count = plan
        .get("input_provenance")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
        .filter(|mapping| string_list(mapping.get("source_ids")).is_some_and(|ids| !ids.is_empty()))
        .count();
    if source_based_input_count == 0 {
        return EvidenceSelectionAudit {
            complete: true,
            status: "complete",
            synthesis_sha256: String::new(),
            selected_input_count: 0,
            selected_extraction_count: 0,
            verified_extraction_count: 0,
            unverified_extraction_ids: Vec::new(),
            rejected_extraction_ids: Vec::new(),
            invalid_selections: Vec::new(),
            errors: Vec::new(),
            verification_integrity: "not_applicable_no_source_based_inputs",
        };
    }
    let binding = plan
        .get("evidence_synthesis")
        .and_then(serde_json::Value::as_object);
    let claimed_path = binding
        .and_then(|value| value.get("path"))
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let claimed_sha256 = binding
        .and_then(|value| value.get("content_sha256"))
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let synthesis_raw = match crate::heor_uncertainty::read_workspace_capped(
        workspace,
        crate::heor_synthesis::EVIDENCE_SYNTHESIS_PATH,
    ) {
        Ok(raw) => raw,
        Err(error) => return incomplete_selection(error),
    };
    let synthesis_sha256 = format!("{:x}", Sha256::digest(&synthesis_raw));
    let mut errors = Vec::new();
    if claimed_path != crate::heor_synthesis::EVIDENCE_SYNTHESIS_PATH {
        errors.push("analysis plan must bind heor/evidence-synthesis.json".into());
    }
    if claimed_sha256 != synthesis_sha256 {
        errors.push("analysis plan evidence-synthesis hash is stale or missing".into());
    }
    let extraction_index = match crate::heor_synthesis::extraction_index(&synthesis_raw) {
        Ok(index) => index,
        Err(error) => {
            errors.push(error);
            HashMap::new()
        }
    };
    let verification_log = match crate::heor_evidence_review::verified_log(app, project_id) {
        Ok(log) => log,
        Err(error) => return incomplete_selection(error),
    };
    let eligible = extraction_index.keys().cloned().collect::<BTreeSet<_>>();
    let review =
        crate::heor_evidence_review::review_status(&verification_log, &synthesis_sha256, &eligible);
    let verified = review.verified_extraction_ids;
    let rejected = review.rejected_extraction_ids;
    let mut selected_inputs = 0usize;
    let mut selected_ids = BTreeSet::new();
    let mut unverified = BTreeSet::new();
    let mut invalid_selections = Vec::new();
    for mapping in plan
        .get("input_provenance")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
    {
        let path = mapping
            .get("path")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("mapping");
        let source_ids = string_list(mapping.get("source_ids")).unwrap_or_default();
        if source_ids.is_empty() {
            continue;
        }
        selected_inputs += 1;
        let extraction_ids = string_list(mapping.get("extraction_ids")).unwrap_or_default();
        if extraction_ids.is_empty() {
            invalid_selections.push(format!("{path}: no selected extraction"));
            continue;
        }
        let unique = extraction_ids.iter().copied().collect::<HashSet<_>>();
        if unique.len() != extraction_ids.len() {
            invalid_selections.push(format!("{path}: selected extraction IDs are duplicated"));
        }
        for extraction_id in unique {
            selected_ids.insert(extraction_id.to_string());
            match extraction_index.get(extraction_id) {
                Some(extraction)
                    if extraction.target == path
                        && source_ids.contains(&extraction.record_id.as_str()) => {}
                Some(extraction) if extraction.target != path => invalid_selections.push(format!(
                    "{path}: {extraction_id} targets {}",
                    extraction.target
                )),
                Some(extraction) => invalid_selections.push(format!(
                    "{path}: {extraction_id} record {} is not a linked source",
                    extraction.record_id
                )),
                None => invalid_selections.push(format!(
                    "{path}: {extraction_id} is absent, conflicting, or ineligible"
                )),
            }
            if !verified.contains(extraction_id) {
                unverified.insert(extraction_id.to_string());
            }
        }
        invalid_selections.extend(
            extraction_derivation_reasons(&plan, mapping, &extraction_index)
                .into_iter()
                .map(|reason| format!("{path}: {reason}")),
        );
    }
    let complete = errors.is_empty()
        && invalid_selections.is_empty()
        && unverified.is_empty()
        && selected_inputs > 0;
    EvidenceSelectionAudit {
        complete,
        status: if complete { "complete" } else { "incomplete" },
        synthesis_sha256,
        selected_input_count: selected_inputs,
        selected_extraction_count: selected_ids.len(),
        verified_extraction_count: selected_ids.intersection(&verified).count(),
        unverified_extraction_ids: unverified.into_iter().collect(),
        rejected_extraction_ids: selected_ids.intersection(&rejected).cloned().collect(),
        invalid_selections,
        errors,
        verification_integrity: verification_log.integrity,
    }
}

pub(crate) fn require_evidence_selection_approvable(
    app: &AppHandle,
    workspace: &Path,
    project_id: &str,
    plan_raw: &[u8],
) -> Result<EvidenceSelectionAudit, String> {
    let audit = audit_evidence_selection_for_plan(app, workspace, project_id, plan_raw);
    if !audit.complete {
        return Err(format!(
            "evidence-to-input selection is incomplete: {} unverified extractions, {} invalid selections, {} errors",
            audit.unverified_extraction_ids.len(),
            audit.invalid_selections.len(),
            audit.errors.len()
        ));
    }
    Ok(audit)
}

#[tauri::command]
pub fn audit_heor_evidence_selection(app: AppHandle) -> Result<EvidenceSelectionAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    let project_id = crate::project::require_project_id(&workspace)?;
    let raw =
        crate::heor_uncertainty::read_workspace_capped(&workspace, "heor/analysis-plan.json")?;
    Ok(audit_evidence_selection_for_plan(
        &app,
        &workspace,
        &project_id,
        &raw,
    ))
}

pub fn require_analysis_plan_approvable(raw: &[u8], expected_sha256: &str) -> Result<(), String> {
    let actual_sha256 = format!("{:x}", Sha256::digest(raw));
    if actual_sha256 != expected_sha256 {
        return Err(
            "analysis-plan approval must target the current heor/analysis-plan.json".into(),
        );
    }
    let audit = audit_plan_bytes(raw)?;
    if !audit.complete {
        return Err(format!(
            "analysis plan evidence audit is incomplete: {}/{} inputs covered, {} unresolved assumptions, {} invalid mappings",
            audit.covered_inputs,
            audit.required_inputs,
            audit.unresolved_assumptions.len(),
            audit.invalid_mappings.len()
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn monetary_adjustments(path: &str) -> serde_json::Value {
        let values: Vec<f64> = match path {
            "strategies.comparator.state_costs" => vec![1000.0, 3000.0, 0.0],
            "strategies.intervention.state_costs" => vec![4000.0, 3000.0, 0.0],
            "willingness_to_pay" => vec![100000.0],
            _ => return serde_json::Value::Null,
        };
        serde_json::Value::Array(
            values
                .into_iter()
                .enumerate()
                .map(|(index, value)| {
                    let mut item = serde_json::json!({
                        "source_value": value,
                        "source_currency": "CNY",
                        "source_price_year": 2026,
                        "factor": 1.0,
                        "method": "none",
                        "basis_ids": [],
                        "source_extraction_id": format!("extract-{}", path.replace('.', "-"))
                    });
                    if path.ends_with("state_costs") {
                        item["target_index"] = serde_json::json!(index);
                        item["source_index"] = serde_json::json!(index);
                    }
                    item
                })
                .collect(),
        )
    }

    fn complete_plan() -> serde_json::Value {
        let paths = required_input_paths(&serde_json::json!({ "willingness_to_pay": 100000 }));
        let mut plan = serde_json::json!({
            "schema_version": "0.3.0",
            "economic_basis": {"currency": "CNY", "price_year": 2026},
            "states": ["stable", "progressed", "dead"],
            "willingness_to_pay": 100000,
            "cycles": 3,
            "cycle_length_years": 1.0,
            "discount_rates": {"costs": 0.05, "outcomes": 0.05},
            "half_cycle_correction": true,
            "strategies": {
                "comparator": {
                    "initial_distribution": [1.0, 0.0, 0.0],
                    "transition_matrix": [[0.7, 0.2, 0.1], [0.0, 0.7, 0.3], [0.0, 0.0, 1.0]],
                    "state_costs": [1000.0, 3000.0, 0.0],
                    "state_utilities": [0.8, 0.5, 0.0]
                },
                "intervention": {
                    "initial_distribution": [1.0, 0.0, 0.0],
                    "transition_matrix": [[0.8, 0.15, 0.05], [0.0, 0.75, 0.25], [0.0, 0.0, 1.0]],
                    "state_costs": [4000.0, 3000.0, 0.0],
                    "state_utilities": [0.8, 0.5, 0.0]
                }
            },
            "evidence_synthesis": {
                "path": "heor/evidence-synthesis.json",
                "content_sha256": "a".repeat(64)
            },
            "evidence_sources": [{
                "id": "source-1",
                "title": "Model inputs",
                "source_type": "peer_reviewed_study",
                "url": "https://example.test/study",
                "accessed_on": "2026-07-14"
            }],
            "assumptions": [],
            "input_provenance": []
        });
        plan["input_provenance"] = serde_json::Value::Array(paths.into_iter().map(|path| serde_json::json!({
                "path": path,
                "source_ids": ["source-1"],
                "extraction_ids": [format!("extract-{}", path.replace('.', "-"))],
                "assumption_ids": [],
                "unit": "model-specific",
                "jurisdiction": "China",
                "currency": if monetary_path(&path) { Some("CNY") } else { None },
                "price_year": if monetary_path(&path) { Some(2026) } else { None },
                "monetary_adjustments": monetary_adjustments(&path),
                "derivation": {
                    "method": if monetary_path(&path) { "monetary_adjustment" } else { "direct_evidence" },
                    "model_value": model_value(&plan, &path).cloned().unwrap()
                },
                "selection_rationale": "Pre-specified source",
                "uncertainty_status": "fixed"
            })).collect());
        plan
    }

    #[test]
    fn every_required_input_can_be_covered() {
        let audit = audit_plan(&complete_plan());
        assert!(audit.complete);
        assert_eq!(audit.required_inputs, 14);
        assert_eq!(audit.covered_inputs, 14);
    }

    #[test]
    fn scheduled_transition_replaces_the_static_required_path() {
        let plan = serde_json::json!({
            "willingness_to_pay": null,
            "strategies": {
                "comparator": {"transition_matrix": [[1.0]]},
                "intervention": {
                    "transition_schedule": [{"start_cycle": 1, "matrix": [[1.0]]}]
                }
            }
        });

        let paths = required_input_paths(&plan);

        assert!(paths.contains(&"strategies.comparator.transition_matrix".into()));
        assert!(paths.contains(&"strategies.intervention.transition_schedule".into()));
        assert!(!paths.contains(&"strategies.intervention.transition_matrix".into()));
    }

    #[test]
    fn structure_neutral_required_paths_exclude_markov_structure() {
        let plan = serde_json::json!({
            "schema_version": "0.12.0",
            "strategy_order": ["usual_care", "new_treatment"],
            "baseline_strategy_id": "usual_care",
            "willingness_to_pay": null,
            "strategies": {
                "usual_care": {"state_costs": [1.0, 2.0, 0.0], "state_utilities": [0.8, 0.5, 0.0]},
                "new_treatment": {"state_costs": [3.0, 2.0, 0.0], "state_utilities": [0.82, 0.5, 0.0]}
            }
        });

        let paths = required_input_paths(&plan);

        assert_eq!(paths.len(), 9);
        assert!(paths.contains(&"strategies.new_treatment.state_costs".into()));
        assert!(!paths
            .iter()
            .any(|path| path.contains("initial_distribution")));
        assert!(!paths.iter().any(|path| path.contains("transition_")));
    }

    #[test]
    fn multi_strategy_required_paths_follow_the_declared_order() {
        let plan = serde_json::json!({
            "schema_version": "0.8.0",
            "strategy_order": ["standard_care", "treatment_a", "treatment_b"],
            "baseline_strategy_id": "standard_care",
            "willingness_to_pay": 100000,
            "strategies": {
                "standard_care": {"transition_matrix": [[1.0]]},
                "treatment_a": {"transition_matrix": [[1.0]]},
                "treatment_b": {"transition_schedule": [{"start_cycle": 1, "matrix": [[1.0]]}]}
            }
        });

        let paths = required_input_paths(&plan);

        assert_eq!(paths.len(), 18);
        assert!(paths.contains(&"strategies.treatment_b.transition_schedule".into()));
        assert!(!paths.contains(&"strategies.treatment_b.transition_matrix".into()));
    }

    #[test]
    fn multi_strategy_contract_rejects_non_string_order_key_mismatch_and_baseline_drift() {
        let mut plan = complete_plan();
        plan["schema_version"] = serde_json::json!("0.8.0");
        plan["strategy_order"] = serde_json::json!(["comparator", 42, "intervention"]);
        plan["baseline_strategy_id"] = serde_json::json!("comparator");
        let audit = audit_plan(&plan);
        assert!(!audit.complete);
        assert!(audit
            .invalid_mappings
            .iter()
            .any(|error| error.contains("2-16 unique safe strategy ids")));

        plan["strategy_order"] = serde_json::json!(["comparator", "alternative"]);
        let audit = audit_plan(&plan);
        assert!(!audit.complete);
        assert!(audit
            .invalid_mappings
            .iter()
            .any(|error| error.contains("exact strategies object")));

        plan["strategy_order"] = serde_json::json!(["comparator", "intervention"]);
        plan["baseline_strategy_id"] = serde_json::json!("intervention");
        let audit = audit_plan(&plan);
        assert!(!audit.complete);
        assert!(audit
            .invalid_mappings
            .iter()
            .any(|error| error.contains("baseline_strategy_id first")));
    }

    #[test]
    fn complete_scheduled_plan_can_pass_approval_audit() {
        let mut plan = complete_plan();
        plan["schema_version"] = serde_json::json!("0.4.0");
        let matrix = plan["strategies"]["intervention"]
            .as_object_mut()
            .unwrap()
            .remove("transition_matrix")
            .unwrap();
        let schedule = serde_json::json!([
            {"start_cycle": 1, "matrix": matrix},
            {"start_cycle": 3, "matrix": [[0.75, 0.2, 0.05], [0.0, 0.7, 0.3], [0.0, 0.0, 1.0]]}
        ]);
        plan["strategies"]["intervention"]["transition_schedule"] = schedule.clone();

        let mapping = plan["input_provenance"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|mapping| {
                mapping.get("path").and_then(serde_json::Value::as_str)
                    == Some("strategies.intervention.transition_matrix")
            })
            .unwrap();
        mapping["path"] = serde_json::json!("strategies.intervention.transition_schedule");
        mapping["extraction_ids"] =
            serde_json::json!(["extract-strategies-intervention-transition_schedule"]);
        mapping["derivation"]["model_value"] = schedule;

        let audit = audit_plan(&plan);
        assert!(audit.complete, "{:?}", audit.invalid_mappings);
        assert_eq!(audit.required_inputs, 14);
        assert_eq!(audit.covered_inputs, 14);
    }

    #[test]
    fn complete_rate_derived_plan_can_pass_approval_audit() {
        let mut plan = complete_plan();
        plan["schema_version"] = serde_json::json!("0.5.0");
        plan["assumptions"] = serde_json::json!([
            {"id": "rate-01", "statement": "Stable to progressed rate", "reason": "Adapter test", "status": "proposed"},
            {"id": "rate-02", "statement": "Stable to dead rate", "reason": "Adapter test", "status": "proposed"},
            {"id": "rate-12", "statement": "Progressed to dead rate", "reason": "Adapter test", "status": "proposed"}
        ]);
        let mapping = plan["input_provenance"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|mapping| {
                mapping.get("path").and_then(serde_json::Value::as_str)
                    == Some("strategies.intervention.transition_matrix")
            })
            .unwrap();
        mapping["source_ids"] = serde_json::json!([]);
        mapping["extraction_ids"] = serde_json::json!([]);
        mapping["assumption_ids"] = serde_json::json!(["rate-01", "rate-02", "rate-12"]);
        mapping["derivation"] = serde_json::json!({
            "method": "deterministic_transformation",
            "model_value": [[0.8, 0.15, 0.05], [0.0, 0.75, 0.25], [0.0, 0.0, 1.0]],
            "transformation": {
                "operation": "constant_competing_rates",
                "cycle_length_years": 1.0,
                "phases": [{
                    "start_cycle": 1,
                    "rows": [
                        {"self_index": 0, "events": [
                            {"target_index": 1, "rate_per_year": 0.1673576634856573, "assumption_id": "rate-01"},
                            {"target_index": 2, "rate_per_year": 0.05578588782855244, "assumption_id": "rate-02"}
                        ]},
                        {"self_index": 1, "events": [
                            {"target_index": 2, "rate_per_year": 0.2876820724517809, "assumption_id": "rate-12"}
                        ]},
                        {"self_index": 2, "events": []}
                    ]
                }]
            }
        });

        let audit = audit_plan(&plan);

        assert!(audit.complete, "{:?}", audit.invalid_mappings);
        assert_eq!(audit.covered_inputs, 14);

        plan["input_provenance"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|mapping| {
                mapping.get("path").and_then(serde_json::Value::as_str)
                    == Some("strategies.intervention.transition_matrix")
            })
            .unwrap()["derivation"]["transformation"]["phases"][0]["rows"][0]["events"][0]
            ["rate_per_year"] = serde_json::json!(0.2);
        assert!(!audit_plan(&plan).complete);
    }

    #[test]
    fn background_mortality_is_recomputed_and_rejects_stale_or_unsafe_inputs() {
        let transformation = serde_json::json!({
            "operation": "background_plus_excess_mortality_to_transition_schedule",
            "cycle_length_years": 1.0,
            "from_state_index": 0,
            "death_state_index": 1,
            "life_table": {
                "jurisdiction": "China",
                "table_year": 2024,
                "population": "general population",
                "sex": "all",
                "start_age_years": 60.0,
                "cycle_probabilities": [
                    {"cycle": 1, "attained_age_years": 60.0, "annual_probability": {"value": 0.1, "assumption_id": "q-60"}},
                    {"cycle": 2, "attained_age_years": 61.0, "annual_probability": {"value": 0.2, "assumption_id": "q-61"}}
                ]
            },
            "excess_mortality_rate_per_year": {"value": 0.05, "assumption_id": "excess"},
            "review_bases": {
                "population_exchangeability": {"assumption_id": "exchangeability"},
                "no_double_counting": {"assumption_id": "no-double-counting"}
            }
        });
        let mut plan = serde_json::json!({
            "schema_version": "0.9.0",
            "states": ["alive", "dead"],
            "cycles": 2,
            "cycle_length_years": 1.0,
            "strategies": {
                "comparator": {"transition_schedule": []},
                "intervention": {"transition_matrix": [[0.9, 0.1], [0.0, 1.0]]}
            }
        });
        let (schedule, _, _) = derive_background_mortality_schedule(
            &plan,
            "strategies.comparator.transition_schedule",
            &transformation,
        )
        .unwrap();
        plan["strategies"]["comparator"]["transition_schedule"] = schedule.clone();
        let mapping = serde_json::json!({
            "path": "strategies.comparator.transition_schedule",
            "jurisdiction": "China",
            "extraction_ids": [],
            "assumption_ids": ["q-60", "q-61", "excess", "exchangeability", "no-double-counting"],
            "derivation": {
                "method": "deterministic_transformation",
                "model_value": schedule,
                "transformation": transformation
            }
        });
        let derivation = mapping["derivation"].as_object().unwrap();
        assert!(background_mortality_declaration_reasons(
            &plan,
            "strategies.comparator.transition_schedule",
            &mapping,
            derivation,
        )
        .is_empty());

        let mut half_year_plan = plan.clone();
        half_year_plan["cycle_length_years"] = serde_json::json!(0.5);
        let mut zero_excess = mapping["derivation"]["transformation"].clone();
        zero_excess["cycle_length_years"] = serde_json::json!(0.5);
        zero_excess["excess_mortality_rate_per_year"]["value"] = serde_json::json!(0.0);
        zero_excess["life_table"]["cycle_probabilities"][0]["annual_probability"]["value"] =
            serde_json::json!(0.0);
        zero_excess["life_table"]["cycle_probabilities"][1]["annual_probability"]["value"] =
            serde_json::json!(0.0);
        zero_excess["life_table"]["cycle_probabilities"][1]["attained_age_years"] =
            serde_json::json!(60);
        let (zero_schedule, _, _) = derive_background_mortality_schedule(
            &half_year_plan,
            "strategies.comparator.transition_schedule",
            &zero_excess,
        )
        .unwrap();
        assert_eq!(
            zero_schedule,
            serde_json::json!([
                {"start_cycle": 1, "matrix": [[1.0, 0.0], [0.0, 1.0]]},
                {"start_cycle": 2, "matrix": [[1.0, 0.0], [0.0, 1.0]]}
            ])
        );

        let mut stale = mapping.clone();
        stale["derivation"]["transformation"]["life_table"]["cycle_probabilities"][0]
            ["annual_probability"]["value"] = serde_json::json!(0.11);
        assert!(background_mortality_declaration_reasons(
            &plan,
            "strategies.comparator.transition_schedule",
            &stale,
            stale["derivation"].as_object().unwrap(),
        )
        .iter()
        .any(|error| error.contains("does not reproduce")));

        let mut wrong_age = mapping.clone();
        wrong_age["derivation"]["transformation"]["life_table"]["cycle_probabilities"][1]
            ["attained_age_years"] = serde_json::json!(62.0);
        assert!(background_mortality_declaration_reasons(
            &plan,
            "strategies.comparator.transition_schedule",
            &wrong_age,
            wrong_age["derivation"].as_object().unwrap(),
        )
        .iter()
        .any(|error| error.contains("must equal floor")));

        let mut old_plan = plan.clone();
        old_plan["schema_version"] = serde_json::json!("0.8.0");
        assert!(background_mortality_declaration_reasons(
            &old_plan,
            "strategies.comparator.transition_schedule",
            &mapping,
            derivation,
        )
        .iter()
        .any(|error| error.contains("require schema_version 0.9.0")));

        let mut overflow_plan = plan.clone();
        overflow_plan["cycle_length_years"] = serde_json::json!(2.0);
        let mut overflow = mapping["derivation"]["transformation"].clone();
        overflow["cycle_length_years"] = serde_json::json!(2.0);
        overflow["life_table"]["cycle_probabilities"][1]["attained_age_years"] =
            serde_json::json!(62.0);
        overflow["excess_mortality_rate_per_year"]["value"] = serde_json::json!(f64::MAX);
        assert!(derive_background_mortality_schedule(
            &overflow_plan,
            "strategies.comparator.transition_schedule",
            &overflow,
        )
        .unwrap_err()
        .contains("non-finite integrated hazard"));
    }

    #[test]
    fn background_mortality_extractions_bind_numbers_but_do_not_self_authorize_review() {
        let mapping = serde_json::json!({
            "extraction_ids": ["mortality-inputs"],
            "derivation": {"transformation": {
                "life_table": {"cycle_probabilities": [
                    {"annual_probability": {"value": 0.1, "source_extraction_id": "mortality-inputs", "source_pointer": "/q"}}
                ]},
                "excess_mortality_rate_per_year": {"value": 0.05, "source_extraction_id": "mortality-inputs", "source_pointer": "/excess"},
                "review_bases": {
                    "population_exchangeability": {"source_extraction_id": "mortality-inputs", "source_pointer": "/exchangeability_note"},
                    "no_double_counting": {"source_extraction_id": "mortality-inputs", "source_pointer": "/double_counting_note"}
                }
            }}
        });
        let mut index = HashMap::new();
        index.insert(
            "mortality-inputs".to_string(),
            crate::heor_synthesis::ExtractionLink {
                record_id: "life-table-record".into(),
                target: "strategies.comparator.transition_schedule".into(),
                extracted_value: serde_json::json!({
                    "q": 0.1,
                    "excess": 0.05,
                    "exchangeability_note": "requires human review",
                    "double_counting_note": false
                })
                .to_string(),
            },
        );
        assert!(background_mortality_extraction_reasons(&mapping, &index).is_empty());

        index.get_mut("mortality-inputs").unwrap().extracted_value = serde_json::json!({
            "q": 0.2,
            "excess": 0.05,
            "exchangeability_note": "requires human review",
            "double_counting_note": false
        })
        .to_string();
        assert!(background_mortality_extraction_reasons(&mapping, &index)
            .join("; ")
            .contains("does not match the bound extraction"));
    }

    #[test]
    fn native_hazard_ratio_uses_cumulative_hazard_increments_and_fails_closed() {
        let plan = serde_json::json!({
            "schema_version": "0.11.0",
            "states": ["event_free", "event"],
            "cycles": 3,
            "cycle_length_years": 1.0
        });
        let mut transformation = serde_json::json!({
            "operation": "hazard_ratio_to_transition_schedule",
            "cycle_length_years": 1.0,
            "from_state_index": 0,
            "event_state_index": 1,
            "baseline_cumulative_hazards": [
                {"cycle": 1, "cumulative_hazard": {"value": 0.1, "source_extraction_id": "h1"}},
                {"cycle": 2, "cumulative_hazard": {"value": 0.3, "source_extraction_id": "h2"}},
                {"cycle": 3, "cumulative_hazard": {"value": 0.3, "source_extraction_id": "h3"}}
            ],
            "hazard_ratio": {"value": 0.5, "source_extraction_id": "hr"},
            "review_bases": {
                "endpoint_alignment": {"assumption_id": "endpoint"},
                "population_transportability": {"assumption_id": "population"},
                "proportional_hazards_assumption": {"assumption_id": "ph"},
                "effect_constancy_over_horizon": {"assumption_id": "constancy"},
                "treatment_switching_assessment": {"assumption_id": "switching"}
            }
        });
        let (schedule, extractions, assumptions) = derive_hazard_ratio_schedule(
            &plan,
            "strategies.treatment.transition_schedule",
            &transformation,
        )
        .unwrap();
        let probabilities = schedule
            .as_array()
            .unwrap()
            .iter()
            .map(|value| value.pointer("/matrix/0/1").unwrap().as_f64().unwrap())
            .collect::<Vec<_>>();
        assert!((probabilities[0] - (1.0 - (-0.05_f64).exp())).abs() < 1e-12);
        assert!((probabilities[1] - (1.0 - (-0.10_f64).exp())).abs() < 1e-12);
        assert_eq!(probabilities[2], 0.0);
        assert_eq!(
            extractions,
            HashSet::from(["h1".into(), "h2".into(), "h3".into(), "hr".into()])
        );
        assert_eq!(assumptions.len(), 5);

        transformation["baseline_cumulative_hazards"][1]["cumulative_hazard"]["value"] =
            serde_json::json!(0.05);
        assert!(derive_hazard_ratio_schedule(
            &plan,
            "strategies.treatment.transition_schedule",
            &transformation,
        )
        .unwrap_err()
        .contains("non-decreasing"));
        transformation["baseline_cumulative_hazards"][1]["cumulative_hazard"]["value"] =
            serde_json::json!(0.3);
        transformation["hazard_ratio"]["value"] = serde_json::json!(1e308);
        assert!(derive_hazard_ratio_schedule(
            &plan,
            "strategies.treatment.transition_schedule",
            &transformation,
        )
        .unwrap_err()
        .contains("invalid event probability"));
    }

    #[test]
    fn missing_mapping_and_unresolved_assumption_fail_closed() {
        let mut plan = complete_plan();
        plan["input_provenance"].as_array_mut().unwrap().pop();
        plan["assumptions"] = serde_json::json!([{
            "id": "open-1",
            "statement": "Unknown transition estimate",
            "reason": "Evidence has not been selected",
            "status": "unresolved"
        }]);
        let audit = audit_plan(&plan);
        assert!(!audit.complete);
        assert_eq!(audit.covered_inputs, 13);
        assert_eq!(audit.unresolved_assumptions, vec!["open-1"]);
    }

    #[test]
    fn proposed_assumption_is_explicitly_reviewable() {
        let mut plan = complete_plan();
        plan["assumptions"] = serde_json::json!([{
            "id": "assumption-1",
            "statement": "Synthetic terminal-state utility",
            "reason": "No directly applicable evidence",
            "status": "proposed"
        }]);
        let first = plan["input_provenance"]
            .as_array_mut()
            .unwrap()
            .first_mut()
            .unwrap();
        first["source_ids"] = serde_json::json!([]);
        first["extraction_ids"] = serde_json::json!([]);
        first["assumption_ids"] = serde_json::json!(["assumption-1"]);
        first["derivation"]["method"] = serde_json::json!("explicit_assumption");
        assert!(audit_plan(&plan).complete);
    }

    #[test]
    fn monetary_adjustment_must_reproduce_the_model_value() {
        let mut plan = complete_plan();
        let mapping = plan["input_provenance"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|item| item["path"] == "strategies.intervention.state_costs")
            .unwrap();
        mapping["monetary_adjustments"][0]["source_value"] = serde_json::json!(3999.0);

        let audit = audit_plan(&plan);

        assert!(!audit.complete);
        assert!(audit
            .invalid_mappings
            .join("; ")
            .contains("does not reproduce model value"));
    }

    #[test]
    fn documented_cross_basis_adjustment_is_eligible() {
        let mut plan = complete_plan();
        let mapping = plan["input_provenance"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|item| item["path"] == "willingness_to_pay")
            .unwrap();
        mapping["monetary_adjustments"] = serde_json::json!([{
            "source_value": 12500.0,
            "source_currency": "USD",
            "source_price_year": 2024,
            "factor": 8.0,
            "method": "Documented inflation and exchange-rate composite factor",
            "basis_ids": ["source-1"],
            "source_extraction_id": "extract-willingness_to_pay"
        }]);

        assert!(audit_plan(&plan).complete);
    }

    #[test]
    fn prior_schema_and_stale_derivation_snapshot_fail_closed() {
        let mut plan = complete_plan();
        plan["schema_version"] = serde_json::json!("0.2.0");
        plan["input_provenance"][0]["derivation"]["model_value"] = serde_json::json!(999);

        let audit = audit_plan(&plan);

        assert!(!audit.complete);
        let errors = audit.invalid_mappings.join("; ");
        assert!(errors.contains("schema_version must be 0.3.0 through 0.14.0"));
        assert!(errors.contains("does not match the current model input"));
    }

    #[test]
    fn native_derivation_rejects_changed_extracted_value() {
        let plan = complete_plan();
        let mapping = &plan["input_provenance"][0];
        let extraction_id = mapping["extraction_ids"][0].as_str().unwrap();
        let mut index = HashMap::new();
        index.insert(
            extraction_id.to_string(),
            crate::heor_synthesis::ExtractionLink {
                record_id: "source-1".into(),
                target: "cycles".into(),
                extracted_value: "4".into(),
            },
        );

        assert!(extraction_derivation_reasons(&plan, mapping, &index)
            .join("; ")
            .contains("does not equal the model input"));
    }

    #[test]
    fn native_rate_derivation_binds_nested_extracted_rates() {
        let mapping = serde_json::json!({
            "extraction_ids": ["rates"],
            "derivation": {
                "method": "deterministic_transformation",
                "transformation": {
                    "phases": [{"rows": [{"events": [
                        {"rate_per_year": 0.2, "source_extraction_id": "rates", "source_pointer": "/event"}
                    ]}]}]
                }
            }
        });
        let mut index = HashMap::new();
        index.insert(
            "rates".to_string(),
            crate::heor_synthesis::ExtractionLink {
                record_id: "source-1".into(),
                target: "strategies.intervention.transition_matrix".into(),
                extracted_value: r#"{"event":0.2}"#.into(),
            },
        );

        assert!(transition_rate_extraction_reasons(&mapping, &index).is_empty());
        index.get_mut("rates").unwrap().extracted_value = r#"{"event":0.3}"#.into();
        assert!(transition_rate_extraction_reasons(&mapping, &index)
            .join("; ")
            .contains("does not match the bound extraction"));
    }

    #[test]
    fn native_survival_derivation_recomputes_and_binds_the_schedule() {
        let transformation = serde_json::json!({
            "operation": "parametric_survival_to_transition_schedule",
            "cycle_length_years": 1.0,
            "from_state_index": 0,
            "event_state_index": 1,
            "distribution": "exponential",
            "parameters": {
                "rate_per_year": {
                    "value": 0.22314355131420976,
                    "source_extraction_id": "survival-rate",
                    "source_pointer": "/rate"
                }
            }
        });
        let mut plan = serde_json::json!({
            "schema_version": "0.6.0",
            "states": ["alive", "dead"],
            "cycles": 3,
            "cycle_length_years": 1.0,
            "strategies": {"intervention": {"transition_schedule": []}}
        });
        let (schedule, _, _) = derive_survival_schedule(
            &plan,
            "strategies.intervention.transition_schedule",
            &transformation,
        )
        .unwrap();
        plan["strategies"]["intervention"]["transition_schedule"] = schedule.clone();
        let mapping = serde_json::json!({
            "path": "strategies.intervention.transition_schedule",
            "extraction_ids": ["survival-rate"],
            "assumption_ids": [],
            "derivation": {
                "method": "deterministic_transformation",
                "model_value": schedule,
                "transformation": transformation
            }
        });
        let derivation = mapping["derivation"].as_object().unwrap();
        assert!(survival_curve_declaration_reasons(
            &plan,
            "strategies.intervention.transition_schedule",
            &mapping,
            derivation,
        )
        .is_empty());

        let mut index = HashMap::new();
        index.insert(
            "survival-rate".to_string(),
            crate::heor_synthesis::ExtractionLink {
                record_id: "source-1".into(),
                target: "strategies.intervention.transition_schedule".into(),
                extracted_value: r#"{"rate":0.22314355131420976}"#.into(),
            },
        );
        assert!(survival_curve_extraction_reasons(&mapping, &index).is_empty());
        index.get_mut("survival-rate").unwrap().extracted_value = r#"{"rate":0.3}"#.into();
        assert!(survival_curve_extraction_reasons(&mapping, &index)
            .join("; ")
            .contains("does not match the bound extraction"));
    }

    #[test]
    fn native_probability_time_derivation_recomputes_and_binds_the_matrix() {
        let transformation = serde_json::json!({
            "operation": "single_event_probability_time_conversion",
            "cycle_length_years": 1.0,
            "phases": [{
                "start_cycle": 1,
                "rows": [
                    {"self_index": 0, "event": {
                        "target_index": 1,
                        "source_probability": 0.36,
                        "source_interval_years": 2.0,
                        "source_extraction_id": "event-probability",
                        "source_pointer": "/probability"
                    }},
                    {"self_index": 1, "event": null}
                ]
            }]
        });
        let mut plan = serde_json::json!({
            "schema_version": "0.7.0",
            "states": ["alive", "event"],
            "cycles": 3,
            "cycle_length_years": 1.0,
            "strategies": {"intervention": {"transition_matrix": []}}
        });
        let (matrix, _, _) = derive_probability_time(
            &plan,
            "strategies.intervention.transition_matrix",
            &transformation,
        )
        .unwrap();
        assert!((matrix[0][1].as_f64().unwrap() - 0.2).abs() < 1e-12);
        let mut tiny = transformation.clone();
        tiny["phases"][0]["rows"][0]["event"]["source_probability"] = serde_json::json!(1e-12);
        tiny["phases"][0]["rows"][0]["event"]["source_interval_years"] = serde_json::json!(1e6);
        let (tiny_matrix, _, _) =
            derive_probability_time(&plan, "strategies.intervention.transition_matrix", &tiny)
                .unwrap();
        assert!(tiny_matrix[0][1].as_f64().unwrap() > 0.0);
        plan["strategies"]["intervention"]["transition_matrix"] = matrix.clone();
        let mapping = serde_json::json!({
            "path": "strategies.intervention.transition_matrix",
            "extraction_ids": ["event-probability"],
            "assumption_ids": [],
            "derivation": {
                "method": "deterministic_transformation",
                "model_value": matrix,
                "transformation": transformation
            }
        });
        assert!(probability_time_declaration_reasons(
            &plan,
            "strategies.intervention.transition_matrix",
            &mapping,
            mapping["derivation"].as_object().unwrap(),
        )
        .is_empty());

        let mut index = HashMap::new();
        index.insert(
            "event-probability".to_string(),
            crate::heor_synthesis::ExtractionLink {
                record_id: "source-1".into(),
                target: "strategies.intervention.transition_matrix".into(),
                extracted_value: r#"{"probability":0.36}"#.into(),
            },
        );
        assert!(probability_time_extraction_reasons(&mapping, &index).is_empty());
        index.get_mut("event-probability").unwrap().extracted_value =
            r#"{"probability":0.4}"#.into();
        assert!(probability_time_extraction_reasons(&mapping, &index)
            .join("; ")
            .contains("does not match the bound extraction"));
    }

    #[test]
    fn native_rate_derivation_rejects_non_string_source_pointer() {
        let plan = serde_json::json!({
            "states": ["alive", "dead"],
            "cycles": 1,
            "cycle_length_years": 1.0
        });
        let transformation = serde_json::json!({
            "operation": "constant_competing_rates",
            "cycle_length_years": 1.0,
            "phases": [{
                "start_cycle": 1,
                "rows": [
                    {"self_index": 0, "events": [{
                        "target_index": 1,
                        "rate_per_year": 0.2,
                        "source_extraction_id": "rate",
                        "source_pointer": 0
                    }]},
                    {"self_index": 1, "events": []}
                ]
            }]
        });

        assert!(derive_competing_rates(
            &plan,
            "strategies.intervention.transition_matrix",
            &transformation,
        )
        .unwrap_err()
        .contains("source_pointer must be a string"));
    }

    #[test]
    fn native_derivation_rejects_narrative_and_changed_monetary_source_values() {
        let plan = complete_plan();
        let direct = &plan["input_provenance"][0];
        let direct_id = direct["extraction_ids"][0].as_str().unwrap();
        let mut direct_index = HashMap::new();
        direct_index.insert(
            direct_id.to_string(),
            crate::heor_synthesis::ExtractionLink {
                record_id: "source-1".into(),
                target: "cycles".into(),
                extracted_value: "three cycles".into(),
            },
        );
        assert!(extraction_derivation_reasons(&plan, direct, &direct_index)
            .join("; ")
            .contains("must be strict JSON"));

        let monetary = plan["input_provenance"]
            .as_array()
            .unwrap()
            .iter()
            .find(|mapping| mapping["path"] == "strategies.intervention.state_costs")
            .unwrap();
        let monetary_id = monetary["extraction_ids"][0].as_str().unwrap();
        let mut monetary_index = HashMap::new();
        monetary_index.insert(
            monetary_id.to_string(),
            crate::heor_synthesis::ExtractionLink {
                record_id: "source-1".into(),
                target: "strategies.intervention.state_costs".into(),
                extracted_value: "[3999,3000,0]".into(),
            },
        );
        assert!(
            extraction_derivation_reasons(&plan, monetary, &monetary_index)
                .join("; ")
                .contains("source_value does not match the bound extraction")
        );
    }

    #[test]
    fn native_relative_effect_derivation_distinguishes_rr_and_or_and_fails_closed() {
        let plan = serde_json::json!({
            "schema_version": "0.10.0",
            "states": ["event-free", "event"],
            "cycles": 2,
            "cycle_length_years": 1.0
        });
        let mut transformation = serde_json::json!({
            "operation": "relative_effect_to_transition_schedule",
            "cycle_length_years": 1.0,
            "effect_interval_years": 1.0,
            "from_state_index": 0,
            "event_state_index": 1,
            "measure": "risk_ratio",
            "baseline_cycle_probabilities": [
                {"cycle": 1, "probability": {"value": 0.2, "assumption_id": "q1"}},
                {"cycle": 2, "probability": {"value": 0.0, "assumption_id": "q2"}}
            ],
            "relative_effect": {"value": 2.0, "assumption_id": "effect"},
            "review_bases": {
                "endpoint_alignment": {"assumption_id": "endpoint"},
                "population_transportability": {"assumption_id": "population"},
                "effect_constancy_over_cycles": {"assumption_id": "constancy"}
            }
        });
        let (rr, _, _) = derive_relative_effect_schedule(
            &plan,
            "strategies.intervention.transition_schedule",
            &transformation,
        )
        .unwrap();
        assert!((rr.pointer("/0/matrix/0/1").unwrap().as_f64().unwrap() - 0.4).abs() < 1e-12);
        assert_eq!(rr.pointer("/1/matrix/0/1").unwrap(), 0.0);

        transformation["measure"] = serde_json::json!("odds_ratio");
        let (or, _, _) = derive_relative_effect_schedule(
            &plan,
            "strategies.intervention.transition_schedule",
            &transformation,
        )
        .unwrap();
        assert!((or.pointer("/0/matrix/0/1").unwrap().as_f64().unwrap() - 1.0 / 3.0).abs() < 1e-12);

        transformation["measure"] = serde_json::json!("risk_ratio");
        transformation["relative_effect"]["value"] = serde_json::json!(5.0);
        assert!(derive_relative_effect_schedule(
            &plan,
            "strategies.intervention.transition_schedule",
            &transformation,
        )
        .unwrap_err()
        .contains("invalid event probability"));
        transformation["relative_effect"]["value"] = serde_json::json!(2.0);
        transformation["measure"] = serde_json::json!("hazard_ratio");
        assert!(derive_relative_effect_schedule(
            &plan,
            "strategies.intervention.transition_schedule",
            &transformation,
        )
        .unwrap_err()
        .contains("risk_ratio or odds_ratio"));
        transformation["measure"] = serde_json::json!("risk_ratio");
        transformation["relative_effect"]["value"] = serde_json::json!(2.0);
        transformation["baseline_cycle_probabilities"][0]["probability"]["value"] =
            serde_json::json!(0.0);
        assert!(derive_relative_effect_schedule(
            &plan,
            "strategies.intervention.transition_schedule",
            &transformation,
        )
        .unwrap_err()
        .contains("at least one positive"));
        transformation["unexpected"] = serde_json::json!(true);
        assert!(derive_relative_effect_schedule(
            &plan,
            "strategies.intervention.transition_schedule",
            &transformation,
        )
        .unwrap_err()
        .contains("exact supported contract"));
    }

    #[test]
    fn relative_effect_extraction_binding_rejects_changed_effect_value() {
        let mapping = serde_json::json!({
            "extraction_ids": ["effect-extraction"],
            "derivation": {"transformation": {
                "relative_effect": {
                    "value": 1.5,
                    "source_extraction_id": "effect-extraction",
                    "source_pointer": "/estimate"
                },
                "baseline_cycle_probabilities": [{
                    "cycle": 1,
                    "probability": {"value": 0.2, "assumption_id": "q"}
                }],
                "review_bases": {
                    "endpoint_alignment": {"assumption_id": "endpoint"},
                    "population_transportability": {"assumption_id": "population"},
                    "effect_constancy_over_cycles": {"assumption_id": "constancy"}
                }
            }}
        });
        let mut index = HashMap::new();
        index.insert(
            "effect-extraction".into(),
            crate::heor_synthesis::ExtractionLink {
                record_id: "source-1".into(),
                target: "relative_effect".into(),
                extracted_value: r#"{"estimate":1.5}"#.into(),
            },
        );
        assert!(relative_effect_extraction_reasons(&mapping, &index).is_empty());
        index.get_mut("effect-extraction").unwrap().extracted_value = r#"{"estimate":1.6}"#.into();
        assert!(relative_effect_extraction_reasons(&mapping, &index)
            .join("; ")
            .contains("does not match the bound extraction"));
    }
}
