//! Native fail-closed audit for evidence-linked annual state-cost normalization.
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::Path;

pub const COST_INPUT_NORMALIZATION_PATH: &str = "heor/cost-input-normalization.json";
const ANALYSIS_PATH: &str = "heor/analysis-plan.json";
const TOLERANCE: f64 = 1e-9;

#[derive(Clone, Debug)]
pub struct CostInputNormalizationAudit {
    pub complete: bool,
    pub sha256: String,
    pub item_count: usize,
    pub artifact_bindings: Vec<crate::heor_approval::ArtifactBinding>,
    pub errors: Vec<String>,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn finite(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite())
}

fn exact_fields(value: &serde_json::Value, fields: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == fields.len() && fields.iter().all(|field| object.contains_key(*field))
    })
}

fn safe_id(value: &str) -> bool {
    let mut bytes = value.bytes();
    matches!(bytes.next(), Some(b'a'..=b'z'))
        && value.len() <= 64
        && bytes.all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'-' | b'_')
        })
}

fn strings(value: Option<&serde_json::Value>) -> Option<Vec<String>> {
    let values = value?.as_array()?;
    let mut seen = HashSet::new();
    let mut result = Vec::with_capacity(values.len());
    for value in values {
        let value = value.as_str()?.trim();
        if value.is_empty() || !seen.insert(value.to_owned()) {
            return None;
        }
        result.push(value.to_owned());
    }
    Some(result)
}

fn linked_ids(value: Option<&serde_json::Value>, valid: &HashSet<String>) -> bool {
    strings(value).is_some_and(|values| {
        !values.is_empty() && values.iter().all(|identifier| valid.contains(identifier))
    })
}

fn close(left: f64, right: f64) -> bool {
    (left - right).abs() <= (left.abs().max(right.abs()) * TOLERANCE).max(1e-6)
}

fn basis_ids(plan: &serde_json::Value) -> HashSet<String> {
    let mut result = HashSet::new();
    for source in plan
        .get("evidence_sources")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
    {
        if let Some(identifier) = source.get("id").and_then(serde_json::Value::as_str) {
            result.insert(identifier.to_owned());
        }
    }
    for assumption in plan
        .get("assumptions")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
    {
        if assumption.get("status").and_then(serde_json::Value::as_str) == Some("proposed") {
            if let Some(identifier) = assumption.get("id").and_then(serde_json::Value::as_str) {
                result.insert(identifier.to_owned());
            }
        }
    }
    for mapping in plan
        .get("input_provenance")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
    {
        for field in ["source_ids", "extraction_ids", "assumption_ids"] {
            for identifier in mapping
                .get(field)
                .and_then(serde_json::Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(serde_json::Value::as_str)
            {
                result.insert(identifier.to_owned());
            }
        }
    }
    result
}

pub fn audit_cost_input_normalization(
    workspace: &Path,
    plan: &serde_json::Value,
    plan_raw: &[u8],
    psm: &serde_json::Value,
) -> CostInputNormalizationAudit {
    let mut audit = CostInputNormalizationAudit {
        complete: false,
        sha256: String::new(),
        item_count: 0,
        artifact_bindings: Vec::new(),
        errors: Vec::new(),
    };
    let link = psm
        .get("cost_input_normalization")
        .unwrap_or(&serde_json::Value::Null);
    if !exact_fields(link, &["path", "content_sha256"])
        || link.get("path").and_then(serde_json::Value::as_str)
            != Some(COST_INPUT_NORMALIZATION_PATH)
    {
        audit.errors.push(format!(
            "cost_input_normalization must bind {COST_INPUT_NORMALIZATION_PATH}"
        ));
        return audit;
    }
    let expected_sha = link
        .get("content_sha256")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let raw = match crate::heor_uncertainty::read_workspace_capped(
        workspace,
        COST_INPUT_NORMALIZATION_PATH,
    ) {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    audit.sha256 = sha256(&raw);
    if audit.sha256 != expected_sha {
        audit
            .errors
            .push("cost-input normalization hash does not match current bytes".into());
    }
    audit
        .artifact_bindings
        .push(crate::heor_approval::ArtifactBinding {
            path: COST_INPUT_NORMALIZATION_PATH.into(),
            sha256: audit.sha256.clone(),
        });
    let value: serde_json::Value = match serde_json::from_slice(&raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("cost-input normalization is invalid JSON: {error}"));
            return audit;
        }
    };
    if !exact_fields(
        &value,
        &[
            "schema_version",
            "normalization_id",
            "analysis_id",
            "status",
            "base_analysis",
            "target_basis",
            "item_order",
            "items",
            "annual_state_costs",
            "limitations",
        ],
    ) {
        audit
            .errors
            .push("cost-input normalization fields are not the exact contract".into());
    }
    if value
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
        || value.get("status").and_then(serde_json::Value::as_str) != Some("ready_for_human_review")
        || value.get("analysis_id") != plan.get("analysis_id")
        || !value
            .get("normalization_id")
            .and_then(serde_json::Value::as_str)
            .is_some_and(safe_id)
    {
        audit
            .errors
            .push("cost-input normalization identity or status is invalid".into());
    }
    if !exact_fields(
        value
            .get("base_analysis")
            .unwrap_or(&serde_json::Value::Null),
        &["path", "content_sha256"],
    ) || value
        .pointer("/base_analysis/path")
        .and_then(serde_json::Value::as_str)
        != Some(ANALYSIS_PATH)
        || value
            .pointer("/base_analysis/content_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(sha256(plan_raw).as_str())
    {
        audit
            .errors
            .push("cost-input normalization base_analysis is stale".into());
    }
    let target = value
        .get("target_basis")
        .unwrap_or(&serde_json::Value::Null);
    if !exact_fields(
        target,
        &["currency", "price_year", "jurisdiction", "perspective"],
    ) || target.get("currency") != plan.pointer("/economic_basis/currency")
        || target.get("price_year") != plan.pointer("/economic_basis/price_year")
        || target.get("jurisdiction") != plan.pointer("/decision_problem/jurisdiction")
        || target.get("perspective") != plan.pointer("/decision_problem/perspective")
    {
        audit
            .errors
            .push("cost-input normalization target basis does not match analysis".into());
    }

    let strategy_order = strings(plan.get("strategy_order")).unwrap_or_default();
    let states = strings(plan.get("states")).unwrap_or_default();
    let item_order = strings(value.get("item_order")).unwrap_or_default();
    audit.item_count = item_order.len();
    if !(1..=1_000).contains(&audit.item_count)
        || item_order.iter().any(|identifier| !safe_id(identifier))
    {
        audit
            .errors
            .push("cost-input normalization item_order is invalid".into());
    }
    let items = value.get("items").and_then(serde_json::Value::as_object);
    if items.map(|items| items.keys().cloned().collect::<HashSet<_>>())
        != Some(item_order.iter().cloned().collect())
    {
        audit
            .errors
            .push("cost-input normalization items do not match item_order".into());
    }
    let valid_basis = basis_ids(plan);
    let mut totals: HashMap<String, Vec<f64>> = strategy_order
        .iter()
        .map(|strategy| (strategy.clone(), vec![0.0; states.len()]))
        .collect();
    for item_id in &item_order {
        let Some(item) = items.and_then(|items| items.get(item_id)) else {
            continue;
        };
        let label = format!("items.{item_id}");
        if !exact_fields(
            item,
            &[
                "item_id",
                "strategy_id",
                "state_id",
                "category",
                "description",
                "scope_basis_ids",
                "annual_quantity",
                "unit_price",
                "adjustments",
                "normalized_unit_price",
                "normalized_annual_cost",
            ],
        ) || item.get("item_id").and_then(serde_json::Value::as_str) != Some(item_id)
        {
            audit
                .errors
                .push(format!("{label} fields or id are invalid"));
            continue;
        }
        let strategy = item
            .get("strategy_id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let state = item
            .get("state_id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let Some(state_index) = states.iter().position(|candidate| candidate == state) else {
            audit
                .errors
                .push(format!("{label}.state_id is not admitted"));
            continue;
        };
        if !strategy_order.iter().any(|candidate| candidate == strategy)
            || !item
                .get("category")
                .and_then(serde_json::Value::as_str)
                .is_some_and(safe_id)
            || !item
                .get("description")
                .and_then(serde_json::Value::as_str)
                .is_some_and(|value| !value.trim().is_empty())
            || !linked_ids(item.get("scope_basis_ids"), &valid_basis)
        {
            audit.errors.push(format!("{label} scope is invalid"));
        }
        let quantity = item
            .get("annual_quantity")
            .unwrap_or(&serde_json::Value::Null);
        let price = item.get("unit_price").unwrap_or(&serde_json::Value::Null);
        let quantity_value = finite(quantity.get("value")).filter(|value| *value > 0.0);
        let unit = quantity.get("unit").and_then(serde_json::Value::as_str);
        let source_amount = finite(price.get("amount")).filter(|value| *value >= 0.0);
        if !exact_fields(quantity, &["value", "unit", "basis_ids"])
            || !exact_fields(
                price,
                &[
                    "amount",
                    "per_unit",
                    "currency",
                    "price_year",
                    "jurisdiction",
                    "price_basis",
                    "tax_status",
                    "basis_ids",
                ],
            )
            || quantity_value.is_none()
            || source_amount.is_none()
            || unit.is_none_or(|value| value.trim().is_empty())
            || price.get("per_unit").and_then(serde_json::Value::as_str) != unit
            || !linked_ids(quantity.get("basis_ids"), &valid_basis)
            || !linked_ids(price.get("basis_ids"), &valid_basis)
        {
            audit
                .errors
                .push(format!("{label} quantity or unit price is invalid"));
            continue;
        }
        let price_basis = price.get("price_basis").and_then(serde_json::Value::as_str);
        let tax_status = price.get("tax_status").and_then(serde_json::Value::as_str);
        if !matches!(
            price_basis,
            Some(
                "list_price"
                    | "net_price"
                    | "tariff"
                    | "paid_price"
                    | "negotiated_price"
                    | "microcost"
                    | "opportunity_cost"
                    | "other"
            )
        ) || !matches!(tax_status, Some("included" | "excluded" | "not_applicable"))
        {
            audit
                .errors
                .push(format!("{label} price basis or tax status is unsupported"));
        }
        let adjustments = item
            .get("adjustments")
            .and_then(serde_json::Value::as_array);
        let mut seen = HashSet::new();
        let mut factor = 1.0;
        if adjustments.is_none_or(|values| values.len() > 3) {
            audit.errors.push(format!("{label}.adjustments is invalid"));
            continue;
        }
        for adjustment in adjustments.into_iter().flatten() {
            let kind = adjustment.get("kind").and_then(serde_json::Value::as_str);
            let adjustment_factor = finite(adjustment.get("factor")).filter(|value| *value > 0.0);
            if !exact_fields(adjustment, &["kind", "factor", "method", "basis_ids"])
                || !matches!(
                    kind,
                    Some("inflation" | "currency_conversion" | "price_adjustment")
                )
                || !kind.is_some_and(|kind| seen.insert(kind))
                || adjustment_factor.is_none()
                || !adjustment
                    .get("method")
                    .and_then(serde_json::Value::as_str)
                    .is_some_and(|value| !value.trim().is_empty())
                || !linked_ids(adjustment.get("basis_ids"), &valid_basis)
            {
                audit
                    .errors
                    .push(format!("{label} adjustment is invalid or duplicated"));
                continue;
            }
            factor *= adjustment_factor.unwrap_or(1.0);
        }
        let source_year = price.get("price_year");
        let target_year = plan.pointer("/economic_basis/price_year");
        let source_currency = price.get("currency");
        let target_currency = plan.pointer("/economic_basis/currency");
        if (source_year != target_year) != seen.contains("inflation") {
            audit.errors.push(format!(
                "{label} must use inflation exactly when price years differ"
            ));
        }
        if (source_currency != target_currency) != seen.contains("currency_conversion") {
            audit.errors.push(format!(
                "{label} must use currency_conversion exactly when currencies differ"
            ));
        }
        let normalized_unit =
            finite(item.get("normalized_unit_price")).filter(|value| *value >= 0.0);
        let normalized_annual =
            finite(item.get("normalized_annual_cost")).filter(|value| *value >= 0.0);
        let expected_unit = source_amount.unwrap_or_default() * factor;
        let expected_annual =
            quantity_value.unwrap_or_default() * normalized_unit.unwrap_or_default();
        if normalized_unit.is_none_or(|value| !close(value, expected_unit))
            || normalized_annual.is_none_or(|value| !close(value, expected_annual))
        {
            audit
                .errors
                .push(format!("{label} normalized arithmetic is stale"));
            continue;
        }
        if let Some(strategy_totals) = totals.get_mut(strategy) {
            strategy_totals[state_index] += normalized_annual.unwrap_or_default();
        }
    }
    let declared = value
        .get("annual_state_costs")
        .and_then(serde_json::Value::as_object);
    if declared.map(|values| values.keys().cloned().collect::<HashSet<_>>())
        != Some(strategy_order.iter().cloned().collect())
    {
        audit
            .errors
            .push("annual_state_costs do not match strategy_order".into());
    } else {
        for strategy in &strategy_order {
            let values = declared
                .and_then(|values| values.get(strategy))
                .and_then(serde_json::Value::as_array);
            let model = plan
                .pointer(&format!("/strategies/{strategy}/state_costs"))
                .and_then(serde_json::Value::as_array);
            if values.map(Vec::len) != Some(states.len())
                || model.map(Vec::len) != Some(states.len())
            {
                audit.errors.push(format!(
                    "annual_state_costs.{strategy} does not match state order"
                ));
                continue;
            }
            for index in 0..states.len() {
                let declared_value = values.and_then(|values| finite(values.get(index)));
                let model_value = model.and_then(|values| finite(values.get(index)));
                let calculated = totals
                    .get(strategy)
                    .and_then(|values| values.get(index))
                    .copied()
                    .unwrap_or_default();
                if declared_value.is_none_or(|value| value < 0.0 || !close(value, calculated))
                    || model_value.is_none_or(|value| value < 0.0)
                    || !close(
                        declared_value.unwrap_or_default(),
                        model_value.unwrap_or_default(),
                    )
                {
                    audit.errors.push(format!(
                        "annual_state_costs.{strategy}[{index}] does not reproduce items and analysis"
                    ));
                }
            }
        }
    }
    if strings(value.get("limitations")).is_none_or(|values| values.is_empty()) {
        audit
            .errors
            .push("cost-input limitations are required".into());
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
            .push("cost-input normalization contains a forbidden authority field".into());
    }
    audit.complete = audit.errors.is_empty();
    audit
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> (serde_json::Value, Vec<u8>, serde_json::Value) {
        let plan = serde_json::json!({
            "schema_version": "0.13.0",
            "analysis_id": "cost-test",
            "economic_basis": {"currency": "GBP", "price_year": 2026},
            "decision_problem": {"jurisdiction": "England", "perspective": "NHS and PSS"},
            "states": ["progression_free", "progressed", "dead"],
            "strategy_order": ["usual_care", "new_treatment"],
            "strategies": {
                "usual_care": {"state_costs": [120.0, 0.0, 0.0]},
                "new_treatment": {"state_costs": [240.0, 0.0, 0.0]}
            },
            "evidence_sources": [{"id": "scope"}, {"id": "quantity"}, {"id": "price"}],
            "assumptions": [],
            "input_provenance": []
        });
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let mut items = serde_json::Map::new();
        for (item_id, strategy, amount) in [
            ("usual-care-drug", "usual_care", 10.0),
            ("new-treatment-drug", "new_treatment", 20.0),
        ] {
            items.insert(
                item_id.into(),
                serde_json::json!({
                    "item_id": item_id,
                    "strategy_id": strategy,
                    "state_id": "progression_free",
                    "category": "drug_acquisition",
                    "description": "One monthly dose represented as an annual rate.",
                    "scope_basis_ids": ["scope"],
                    "annual_quantity": {"value": 12.0, "unit": "dose", "basis_ids": ["quantity"]},
                    "unit_price": {
                        "amount": amount, "per_unit": "dose", "currency": "GBP",
                        "price_year": 2026, "jurisdiction": "England",
                        "price_basis": "paid_price", "tax_status": "excluded",
                        "basis_ids": ["price"]
                    },
                    "adjustments": [],
                    "normalized_unit_price": amount,
                    "normalized_annual_cost": amount * 12.0
                }),
            );
        }
        let artifact = serde_json::json!({
            "schema_version": "0.1.0",
            "normalization_id": "cost-inputs",
            "analysis_id": "cost-test",
            "status": "ready_for_human_review",
            "base_analysis": {"path": ANALYSIS_PATH, "content_sha256": sha256(&plan_raw)},
            "target_basis": {"currency": "GBP", "price_year": 2026, "jurisdiction": "England", "perspective": "NHS and PSS"},
            "item_order": ["usual-care-drug", "new-treatment-drug"],
            "items": items,
            "annual_state_costs": {"usual_care": [120.0, 0.0, 0.0], "new_treatment": [240.0, 0.0, 0.0]},
            "limitations": ["Event costs are outside the annual-rate contract."]
        });
        (plan, plan_raw, artifact)
    }

    fn workspace() -> std::path::PathBuf {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("ai4heor-cost-{unique}"))
    }

    #[test]
    fn arithmetic_tolerance_is_bounded() {
        assert!(close(120.0, 120.0 + 1e-8));
        assert!(!close(120.0, 120.01));
    }

    #[test]
    fn safe_ids_reject_paths_and_uppercase() {
        assert!(safe_id("drug-cost-1"));
        assert!(!safe_id("../drug"));
        assert!(!safe_id("Drug"));
    }

    #[test]
    fn native_audit_recalculates_and_rejects_drift() {
        let (plan, plan_raw, mut artifact) = fixture();
        let root = workspace();
        std::fs::create_dir_all(root.join("heor")).unwrap();
        let artifact_raw = serde_json::to_vec(&artifact).unwrap();
        std::fs::write(root.join(COST_INPUT_NORMALIZATION_PATH), &artifact_raw).unwrap();
        let psm = serde_json::json!({
            "cost_input_normalization": {
                "path": COST_INPUT_NORMALIZATION_PATH,
                "content_sha256": sha256(&artifact_raw)
            }
        });
        let valid = audit_cost_input_normalization(&root, &plan, &plan_raw, &psm);
        assert!(valid.complete, "{:?}", valid.errors);
        assert_eq!(valid.item_count, 2);

        artifact["items"]["new-treatment-drug"]["normalized_annual_cost"] =
            serde_json::json!(239.0);
        let stale_raw = serde_json::to_vec(&artifact).unwrap();
        std::fs::write(root.join(COST_INPUT_NORMALIZATION_PATH), &stale_raw).unwrap();
        let stale_psm = serde_json::json!({
            "cost_input_normalization": {
                "path": COST_INPUT_NORMALIZATION_PATH,
                "content_sha256": sha256(&stale_raw)
            }
        });
        let stale = audit_cost_input_normalization(&root, &plan, &plan_raw, &stale_psm);
        assert!(!stale.complete);
        assert!(stale
            .errors
            .iter()
            .any(|error| error.contains("arithmetic")));
        std::fs::remove_dir_all(root).unwrap();
    }
}
