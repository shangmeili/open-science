//! Native fail-closed audit for model-structure-neutral economic inputs.
use std::collections::HashSet;

const PSM_PLAN_PATH: &str = "heor/partitioned-survival-plan.json";

fn finite(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite())
}

fn safe_id(value: &str) -> bool {
    let mut bytes = value.bytes();
    matches!(bytes.next(), Some(b'a'..=b'z'))
        && value.len() <= 64
        && bytes.all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_' || byte == b'-'
        })
}

pub fn audit_economic_inputs(plan: &serde_json::Value) -> Vec<String> {
    let mut errors = Vec::new();
    if plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        .is_none_or(|value| !matches!(value, "0.12.0" | "0.13.0" | "0.14.0"))
    {
        errors.push(
            "structure-neutral economic inputs require analysis schema 0.12.0 through 0.14.0"
                .into(),
        );
    }
    if plan.get("approvals").is_some() {
        errors.push("analysis plan approvals are app-owned and forbidden".into());
    }
    let cost_link = plan.get("cost_input_normalization");
    if plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        .is_some_and(|schema| matches!(schema, "0.13.0" | "0.14.0"))
    {
        if cost_link
            != Some(&serde_json::json!({
                "path": crate::heor_cost_input_normalization::COST_INPUT_NORMALIZATION_PATH
            }))
        {
            errors.push(
                "analysis schema 0.13.0 or 0.14.0 must link only heor/cost-input-normalization.json".into(),
            );
        }
    } else if cost_link.is_some() {
        errors.push(
            "cost_input_normalization is admitted only by analysis schema 0.13.0 or 0.14.0".into(),
        );
    }
    let utility_link = plan.get("utility_inputs");
    if plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        == Some("0.14.0")
    {
        if utility_link
            != Some(&serde_json::json!({"path": crate::heor_utility_inputs::UTILITY_INPUTS_PATH}))
        {
            errors.push("analysis schema 0.14.0 must link only heor/utility-inputs.json".into());
        }
    } else if utility_link.is_some() {
        errors.push("utility_inputs is admitted only by analysis schema 0.14.0".into());
    }
    if plan
        .pointer("/partitioned_survival_analysis/path")
        .and_then(serde_json::Value::as_str)
        != Some(PSM_PLAN_PATH)
        || plan
            .get("partitioned_survival_analysis")
            .and_then(serde_json::Value::as_object)
            .map(serde_json::Map::len)
            != Some(1)
    {
        errors.push(format!(
            "partitioned_survival_analysis must link only {PSM_PLAN_PATH}"
        ));
    }
    if !plan
        .get("analysis_id")
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| !value.trim().is_empty())
    {
        errors.push("analysis_id is required".into());
    }
    let basis = plan
        .get("economic_basis")
        .and_then(serde_json::Value::as_object);
    if basis.map(|value| value.keys().map(String::as_str).collect::<HashSet<_>>())
        != Some(HashSet::from(["currency", "price_year"]))
    {
        errors.push("economic_basis fields must be exactly currency and price_year".into());
    } else {
        let currency = plan
            .pointer("/economic_basis/currency")
            .and_then(serde_json::Value::as_str);
        if !currency.is_some_and(|value| {
            value.len() == 3 && value.bytes().all(|byte| byte.is_ascii_uppercase())
        }) {
            errors.push("economic_basis.currency must be a three-letter uppercase code".into());
        }
        if !plan
            .pointer("/economic_basis/price_year")
            .and_then(serde_json::Value::as_u64)
            .is_some_and(|value| (1900..=2100).contains(&value))
        {
            errors.push("economic_basis.price_year must be from 1900 to 2100".into());
        }
    }
    let states = plan.get("states").and_then(serde_json::Value::as_array);
    if states.map(|values| {
        values
            .iter()
            .filter_map(serde_json::Value::as_str)
            .collect::<Vec<_>>()
    }) != Some(vec!["progression_free", "progressed", "dead"])
    {
        errors.push("states must be progression_free, progressed, dead in order".into());
    }
    if !plan
        .get("cycles")
        .and_then(serde_json::Value::as_u64)
        .is_some_and(|value| (1..=10_000).contains(&value))
    {
        errors.push("cycles must be from 1 to 10000".into());
    }
    if !finite(plan.get("cycle_length_years")).is_some_and(|value| value > 0.0) {
        errors.push("cycle_length_years must be positive and finite".into());
    }
    let discounts = plan
        .get("discount_rates")
        .and_then(serde_json::Value::as_object);
    if discounts.map(|value| value.keys().map(String::as_str).collect::<HashSet<_>>())
        != Some(HashSet::from(["costs", "outcomes"]))
        || !finite(plan.pointer("/discount_rates/costs")).is_some_and(|value| value >= 0.0)
        || !finite(plan.pointer("/discount_rates/outcomes")).is_some_and(|value| value >= 0.0)
    {
        errors.push("discount_rates must contain finite non-negative costs and outcomes".into());
    }
    if plan
        .get("half_cycle_correction")
        .and_then(serde_json::Value::as_bool)
        .is_none()
    {
        errors.push("half_cycle_correction must be a boolean".into());
    }
    if plan
        .get("willingness_to_pay")
        .is_some_and(|value| !value.is_null())
        && !finite(plan.get("willingness_to_pay")).is_some_and(|value| value >= 0.0)
    {
        errors.push("willingness_to_pay must be finite and non-negative when present".into());
    }
    let order = plan
        .get("strategy_order")
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(serde_json::Value::as_str)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    if !(2..=16).contains(&order.len())
        || order.iter().any(|value| !safe_id(value))
        || order.iter().copied().collect::<HashSet<_>>().len() != order.len()
    {
        errors.push("strategy_order must contain 2-16 unique safe strategy ids".into());
    }
    if order.first().copied()
        != plan
            .get("baseline_strategy_id")
            .and_then(serde_json::Value::as_str)
    {
        errors.push("baseline_strategy_id must be first in strategy_order".into());
    }
    let strategies = plan
        .get("strategies")
        .and_then(serde_json::Value::as_object);
    if strategies.map(|values| values.keys().map(String::as_str).collect::<HashSet<_>>())
        != Some(order.iter().copied().collect::<HashSet<_>>())
    {
        errors.push("strategies must contain exactly the strategy_order ids".into());
    }
    let mut names = HashSet::new();
    for strategy_id in &order {
        let Some(strategy) = strategies
            .and_then(|values| values.get(*strategy_id))
            .and_then(serde_json::Value::as_object)
        else {
            continue;
        };
        if strategy.keys().map(String::as_str).collect::<HashSet<_>>()
            != HashSet::from(["name", "state_costs", "state_utilities"])
        {
            errors.push(format!("strategies.{strategy_id} must contain only name, state_costs, and state_utilities; transition structure is forbidden"));
            continue;
        }
        let name = strategy.get("name").and_then(serde_json::Value::as_str);
        if !name.is_some_and(|value| !value.trim().is_empty() && names.insert(value)) {
            errors.push(format!(
                "strategies.{strategy_id}.name must be non-empty and unique"
            ));
        }
        let costs = strategy
            .get("state_costs")
            .and_then(serde_json::Value::as_array);
        if costs.map(Vec::len) != Some(3)
            || costs
                .into_iter()
                .flatten()
                .any(|value| !finite(Some(value)).is_some_and(|number| number >= 0.0))
        {
            errors.push(format!("strategies.{strategy_id}.state_costs must contain three finite non-negative values"));
        }
        let utilities = strategy
            .get("state_utilities")
            .and_then(serde_json::Value::as_array);
        if utilities.map(Vec::len) != Some(3)
            || utilities.into_iter().flatten().any(|value| {
                !finite(Some(value)).is_some_and(|number| (-1.0..=1.0).contains(&number))
            })
        {
            errors.push(format!("strategies.{strategy_id}.state_utilities must contain three finite values from -1 to 1"));
        }
    }
    errors
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_plan() -> serde_json::Value {
        serde_json::json!({
            "schema_version": "0.12.0", "analysis_id": "a", "economic_basis": {"currency": "GBP", "price_year": 2026},
            "partitioned_survival_analysis": {"path": PSM_PLAN_PATH}, "states": ["progression_free", "progressed", "dead"],
            "cycles": 12, "cycle_length_years": 1.0 / 12.0, "discount_rates": {"costs": 0.035, "outcomes": 0.035},
            "half_cycle_correction": true, "willingness_to_pay": null, "strategy_order": ["usual_care", "new_treatment"],
            "baseline_strategy_id": "usual_care", "strategies": {
                "usual_care": {"name": "Usual care", "state_costs": [10, 20, 0], "state_utilities": [0.8, 0.5, 0]},
                "new_treatment": {"name": "New treatment", "state_costs": [30, 20, 0], "state_utilities": [0.82, 0.5, 0]}
            }
        })
    }

    #[test]
    fn accepts_structure_neutral_inputs() {
        assert!(audit_economic_inputs(&valid_plan()).is_empty());
    }

    #[test]
    fn rejects_transition_structure() {
        let mut plan = valid_plan();
        plan.pointer_mut("/strategies/usual_care")
            .unwrap()
            .as_object_mut()
            .unwrap()
            .insert(
                "transition_matrix".into(),
                serde_json::json!([[1, 0, 0], [0, 1, 0], [0, 0, 1]]),
            );
        assert!(audit_economic_inputs(&plan)
            .iter()
            .any(|error| error.contains("transition structure")));
    }
}
