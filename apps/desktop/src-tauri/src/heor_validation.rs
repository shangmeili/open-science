//! Native, fail-closed audit for the independent HEOR model-validation gate.
//! The report documents validation evidence; only the app-owned human approval
//! event can advance the gate.
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::{Component, Path};
use tauri::AppHandle;

pub const MODEL_VALIDATION_PATH: &str = "heor/model-validation.json";
const ANALYSIS_PLAN_PATH: &str = "heor/analysis-plan.json";
const CONCEPTUAL_MODEL_PATH: &str = "heor/conceptual-model.json";
const UNCERTAINTY_PLAN_PATH: &str = "heor/uncertainty-plan.json";
const BUDGET_IMPACT_PLAN_PATH: &str = "heor/budget-impact-plan.json";
const MAX_EVIDENCE: usize = 128;
const MAX_CHECKS: usize = 256;
const MAX_ISSUES: usize = 128;

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ModelValidationAudit {
    pub complete: bool,
    pub approvable: bool,
    pub status: &'static str,
    pub validation_id: String,
    pub analysis_id: String,
    pub validation_sha256: String,
    pub analysis_plan_sha256: String,
    pub conceptual_model_sha256: String,
    pub uncertainty_plan_sha256: String,
    pub budget_impact_plan_sha256: String,
    pub reviewer_label: String,
    pub recommendation: String,
    pub evidence_count: usize,
    pub check_count: usize,
    pub required_coverage_count: usize,
    pub covered_requirement_count: usize,
    pub issue_count: usize,
    pub open_blocking_issue_count: usize,
    pub open_minor_issue_count: usize,
    pub invalid_evidence: Vec<String>,
    pub missing_coverage: Vec<String>,
    pub errors: Vec<String>,
}

#[derive(Clone, Copy)]
struct Requirement {
    label: &'static str,
    scope: &'static str,
    domain: &'static str,
    component: Option<&'static str>,
    allow_not_feasible: bool,
}

const REQUIREMENTS: [Requirement; 18] = [
    Requirement {
        label: "cost-effectiveness face validity",
        scope: "cost_effectiveness",
        domain: "face_validity",
        component: None,
        allow_not_feasible: false,
    },
    Requirement {
        label: "cost-effectiveness input validation",
        scope: "cost_effectiveness",
        domain: "input_data",
        component: None,
        allow_not_feasible: false,
    },
    Requirement {
        label: "cost-effectiveness external validity",
        scope: "cost_effectiveness",
        domain: "external_validity",
        component: None,
        allow_not_feasible: false,
    },
    Requirement {
        label: "budget-impact face validity",
        scope: "budget_impact",
        domain: "face_validity",
        component: None,
        allow_not_feasible: false,
    },
    Requirement {
        label: "budget-impact input validation",
        scope: "budget_impact",
        domain: "input_data",
        component: None,
        allow_not_feasible: false,
    },
    Requirement {
        label: "budget-impact external validity",
        scope: "budget_impact",
        domain: "external_validity",
        component: None,
        allow_not_feasible: false,
    },
    Requirement {
        label: "cost-effectiveness technical input_calculations",
        scope: "cost_effectiveness",
        domain: "technical_verification",
        component: Some("input_calculations"),
        allow_not_feasible: false,
    },
    Requirement {
        label: "cost-effectiveness technical event_state_calculations",
        scope: "cost_effectiveness",
        domain: "technical_verification",
        component: Some("event_state_calculations"),
        allow_not_feasible: false,
    },
    Requirement {
        label: "cost-effectiveness technical result_calculations",
        scope: "cost_effectiveness",
        domain: "technical_verification",
        component: Some("result_calculations"),
        allow_not_feasible: false,
    },
    Requirement {
        label: "cost-effectiveness technical uncertainty_calculations",
        scope: "cost_effectiveness",
        domain: "technical_verification",
        component: Some("uncertainty_calculations"),
        allow_not_feasible: false,
    },
    Requirement {
        label: "cost-effectiveness technical overall_checks",
        scope: "cost_effectiveness",
        domain: "technical_verification",
        component: Some("overall_checks"),
        allow_not_feasible: false,
    },
    Requirement {
        label: "budget-impact technical input_calculations",
        scope: "budget_impact",
        domain: "technical_verification",
        component: Some("input_calculations"),
        allow_not_feasible: false,
    },
    Requirement {
        label: "budget-impact technical result_calculations",
        scope: "budget_impact",
        domain: "technical_verification",
        component: Some("result_calculations"),
        allow_not_feasible: false,
    },
    Requirement {
        label: "budget-impact technical uncertainty_calculations",
        scope: "budget_impact",
        domain: "technical_verification",
        component: Some("uncertainty_calculations"),
        allow_not_feasible: false,
    },
    Requirement {
        label: "budget-impact technical overall_checks",
        scope: "budget_impact",
        domain: "technical_verification",
        component: Some("overall_checks"),
        allow_not_feasible: false,
    },
    Requirement {
        label: "cost-effectiveness cross validity",
        scope: "cost_effectiveness",
        domain: "cross_validity",
        component: None,
        allow_not_feasible: true,
    },
    Requirement {
        label: "cost-effectiveness predictive validity",
        scope: "cost_effectiveness",
        domain: "predictive_validity",
        component: None,
        allow_not_feasible: true,
    },
    Requirement {
        label: "budget-impact predictive validity",
        scope: "budget_impact",
        domain: "predictive_validity",
        component: None,
        allow_not_feasible: true,
    },
];

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn text(value: Option<&serde_json::Value>) -> Option<&str> {
    value
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.trim().is_empty())
}

fn strings(value: Option<&serde_json::Value>, nonempty: bool) -> Option<HashSet<String>> {
    let values = value?.as_array()?;
    if nonempty && values.is_empty() {
        return None;
    }
    let mut result = HashSet::new();
    for value in values {
        let item = text(Some(value))?;
        if !result.insert(item.to_string()) {
            return None;
        }
    }
    Some(result)
}

fn objects(value: Option<&serde_json::Value>) -> Option<&Vec<serde_json::Value>> {
    value?
        .as_array()
        .filter(|values| values.iter().all(serde_json::Value::is_object))
}

fn valid_date(value: Option<&serde_json::Value>) -> bool {
    let Some(value) = text(value) else {
        return false;
    };
    value.len() == 10
        && value.as_bytes()[4] == b'-'
        && value.as_bytes()[7] == b'-'
        && value
            .bytes()
            .enumerate()
            .all(|(index, byte)| matches!(index, 4 | 7) || byte.is_ascii_digit())
}

fn safe_evidence_path(path: &str) -> bool {
    path.starts_with("heor/validation-evidence/")
        && !path.contains('\\')
        && !Path::new(path).is_absolute()
        && Path::new(path)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn method_matches(domain: &str, method: &str) -> bool {
    match domain {
        "face_validity" => method == "expert_review",
        "input_data" => matches!(method, "source_reconciliation" | "replication"),
        "technical_verification" => matches!(method, "black_box" | "white_box" | "replication"),
        "cross_validity" => method == "cross_model_comparison",
        "external_validity" => method == "external_data_comparison",
        "predictive_validity" => method == "prospective_comparison",
        _ => false,
    }
}

fn check_covers(check: &serde_json::Value, requirement: Requirement) -> bool {
    let status = text(check.get("status"));
    let status_is_acceptable = status == Some("passed")
        || (requirement.allow_not_feasible && status == Some("not_feasible"));
    text(check.get("performed_by")) == Some("independent_reviewer")
        && matches!(text(check.get("scope")), Some(scope) if scope == requirement.scope || scope == "shared")
        && text(check.get("domain")) == Some(requirement.domain)
        && requirement
            .component
            .is_none_or(|component| text(check.get("component")) == Some(component))
        && status_is_acceptable
}

fn empty_audit(plan_raw: &[u8]) -> ModelValidationAudit {
    ModelValidationAudit {
        complete: false,
        approvable: false,
        status: "incomplete",
        validation_id: String::new(),
        analysis_id: String::new(),
        validation_sha256: String::new(),
        analysis_plan_sha256: sha256(plan_raw),
        conceptual_model_sha256: String::new(),
        uncertainty_plan_sha256: String::new(),
        budget_impact_plan_sha256: String::new(),
        reviewer_label: String::new(),
        recommendation: "pending".into(),
        evidence_count: 0,
        check_count: 0,
        required_coverage_count: REQUIREMENTS.len(),
        covered_requirement_count: 0,
        issue_count: 0,
        open_blocking_issue_count: 0,
        open_minor_issue_count: 0,
        invalid_evidence: Vec::new(),
        missing_coverage: Vec::new(),
        errors: Vec::new(),
    }
}

fn audit_values(
    workspace: &Path,
    plan_raw: &[u8],
    report: &serde_json::Value,
    report_raw: &[u8],
) -> ModelValidationAudit {
    let mut audit = empty_audit(plan_raw);
    audit.validation_sha256 = sha256(report_raw);
    audit.validation_id = text(report.get("validation_id"))
        .unwrap_or_default()
        .to_string();
    audit.analysis_id = text(report.get("analysis_id"))
        .unwrap_or_default()
        .to_string();
    if report
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
    {
        audit.errors.push("schema_version must be 0.1.0".into());
    }
    for field in [
        "validation_id",
        "analysis_id",
        "intended_use",
        "developer_label",
    ] {
        if text(report.get(field)).is_none() {
            audit.errors.push(format!("{field} is required"));
        }
    }
    if text(report.get("status")) != Some("ready_for_independent_review") {
        audit
            .errors
            .push("status must be ready_for_independent_review".into());
    }

    let plan: serde_json::Value =
        serde_json::from_slice(plan_raw).unwrap_or(serde_json::Value::Null);
    let bindings = report.get("model_bindings");
    for (key, path, provided_raw) in [
        ("analysis_plan", ANALYSIS_PLAN_PATH, Some(plan_raw.to_vec())),
        ("conceptual_model", CONCEPTUAL_MODEL_PATH, None),
        ("uncertainty_plan", UNCERTAINTY_PLAN_PATH, None),
        ("budget_impact_plan", BUDGET_IMPACT_PLAN_PATH, None),
    ] {
        let binding = bindings.and_then(|value| value.get(key));
        if text(binding.and_then(|value| value.get("path"))) != Some(path) {
            audit
                .errors
                .push(format!("model_bindings.{key}.path must be {path}"));
            continue;
        }
        let raw = match provided_raw {
            Some(raw) => raw,
            None => match crate::heor_uncertainty::read_workspace_capped(workspace, path) {
                Ok(raw) => raw,
                Err(error) => {
                    audit.errors.push(error);
                    continue;
                }
            },
        };
        let current_hash = sha256(&raw);
        match key {
            "analysis_plan" => audit.analysis_plan_sha256 = current_hash.clone(),
            "conceptual_model" => audit.conceptual_model_sha256 = current_hash.clone(),
            "uncertainty_plan" => audit.uncertainty_plan_sha256 = current_hash.clone(),
            "budget_impact_plan" => audit.budget_impact_plan_sha256 = current_hash.clone(),
            _ => unreachable!(),
        }
        if text(binding.and_then(|value| value.get("content_sha256"))) != Some(&current_hash) {
            audit.errors.push(format!(
                "model_bindings.{key}.content_sha256 does not match current bytes"
            ));
        }
        let value: serde_json::Value =
            serde_json::from_slice(&raw).unwrap_or(serde_json::Value::Null);
        if text(value.get("analysis_id")) != Some(audit.analysis_id.as_str()) {
            audit.errors.push(format!(
                "{path} analysis_id does not match the validation report"
            ));
        }
    }
    if text(plan.get("analysis_id")) != Some(audit.analysis_id.as_str()) {
        audit
            .errors
            .push("analysis plan analysis_id does not match the validation report".into());
    }

    let reviewer = report.get("reviewer");
    audit.reviewer_label = text(reviewer.and_then(|value| value.get("label")))
        .unwrap_or_default()
        .to_string();
    for field in [
        "label",
        "organization",
        "independence_statement",
        "conflict_statement",
    ] {
        if text(reviewer.and_then(|value| value.get(field))).is_none() {
            audit.errors.push(format!("reviewer.{field} is required"));
        }
    }
    if text(reviewer.and_then(|value| value.get("role"))) != Some("independent_reviewer") {
        audit
            .errors
            .push("reviewer.role must be independent_reviewer".into());
    }
    if reviewer
        .and_then(|value| value.get("declared_independent"))
        .and_then(serde_json::Value::as_bool)
        != Some(true)
    {
        audit
            .errors
            .push("reviewer.declared_independent must be true".into());
    }
    if !valid_date(reviewer.and_then(|value| value.get("reviewed_on"))) {
        audit
            .errors
            .push("reviewer.reviewed_on must be YYYY-MM-DD".into());
    }
    if let (Some(developer), Some(reviewer_label)) = (
        text(report.get("developer_label")),
        text(reviewer.and_then(|value| value.get("label"))),
    ) {
        if developer.trim().eq_ignore_ascii_case(reviewer_label.trim()) {
            audit
                .errors
                .push("independent reviewer must differ from the developer".into());
        }
    }

    let mut evidence_ids = HashSet::new();
    let evidence = objects(report.get("evidence_artifacts"));
    audit.evidence_count = evidence.map_or(0, Vec::len);
    if !matches!(evidence, Some(values) if (1..=MAX_EVIDENCE).contains(&values.len())) {
        audit.errors.push(format!(
            "evidence_artifacts must contain 1-{MAX_EVIDENCE} entries"
        ));
    }
    for (index, item) in evidence.into_iter().flatten().enumerate() {
        let Some(id) = text(item.get("id")) else {
            audit
                .invalid_evidence
                .push(format!("evidence_artifacts[{index}].id is required"));
            continue;
        };
        if !evidence_ids.insert(id.to_string()) {
            audit
                .invalid_evidence
                .push(format!("evidence_artifacts[{index}].id is duplicated"));
        }
        if text(item.get("description")).is_none()
            || !matches!(
                text(item.get("evidence_type")),
                Some(
                    "expert_review_minutes"
                        | "test_log"
                        | "replication_output"
                        | "cross_model_output"
                        | "external_dataset_extract"
                        | "search_record"
                        | "other"
                )
            )
        {
            audit
                .invalid_evidence
                .push(format!("evidence_artifacts[{index}] metadata is invalid"));
        }
        let Some(path) = text(item.get("path")) else {
            audit
                .invalid_evidence
                .push(format!("evidence_artifacts[{index}].path is required"));
            continue;
        };
        if !safe_evidence_path(path) {
            audit.invalid_evidence.push(format!(
                "evidence_artifacts[{index}].path must stay under heor/validation-evidence/"
            ));
            continue;
        }
        match crate::heor_uncertainty::read_workspace_capped(workspace, path) {
            Ok(raw) => {
                let current_hash = sha256(&raw);
                if text(item.get("content_sha256")) != Some(current_hash.as_str()) {
                    audit.invalid_evidence.push(format!(
                        "evidence_artifacts[{index}].content_sha256 does not match current bytes"
                    ));
                }
            }
            Err(error) => audit.invalid_evidence.push(error),
        }
    }

    let issues = objects(report.get("issues"));
    audit.issue_count = issues.map_or(0, Vec::len);
    if !matches!(issues, Some(values) if values.len() <= MAX_ISSUES) {
        audit
            .errors
            .push(format!("issues must contain at most {MAX_ISSUES} entries"));
    }
    let mut issue_status = HashMap::<String, String>::new();
    let mut issue_severity = HashMap::<String, String>::new();
    for (index, issue) in issues.into_iter().flatten().enumerate() {
        let Some(id) = text(issue.get("id")) else {
            audit.errors.push(format!("issues[{index}].id is required"));
            continue;
        };
        if issue_status.contains_key(id) {
            audit
                .errors
                .push(format!("issues[{index}].id is duplicated"));
        }
        let severity = text(issue.get("severity")).unwrap_or_default();
        let status = text(issue.get("status")).unwrap_or_default();
        if text(issue.get("description")).is_none()
            || !matches!(severity, "blocker" | "major" | "minor")
            || !matches!(status, "open" | "resolved")
        {
            audit
                .errors
                .push(format!("issues[{index}] metadata is invalid"));
        }
        if strings(issue.get("evidence_ids"), true).is_none_or(|ids| !ids.is_subset(&evidence_ids))
        {
            audit
                .errors
                .push(format!("issues[{index}].evidence_ids are invalid"));
        }
        if status == "resolved"
            && (text(issue.get("root_cause")).is_none() || text(issue.get("resolution")).is_none())
        {
            audit.errors.push(format!(
                "issues[{index}] resolved issue requires root_cause and resolution"
            ));
        }
        issue_status.insert(id.to_string(), status.to_string());
        issue_severity.insert(id.to_string(), severity.to_string());
    }

    let checks = objects(report.get("checks"));
    audit.check_count = checks.map_or(0, Vec::len);
    if !matches!(checks, Some(values) if (1..=MAX_CHECKS).contains(&values.len())) {
        audit
            .errors
            .push(format!("checks must contain 1-{MAX_CHECKS} entries"));
    }
    let mut check_ids = HashSet::new();
    for (index, check) in checks.into_iter().flatten().enumerate() {
        let Some(id) = text(check.get("id")) else {
            audit.errors.push(format!("checks[{index}].id is required"));
            continue;
        };
        if !check_ids.insert(id) {
            audit
                .errors
                .push(format!("checks[{index}].id is duplicated"));
        }
        for field in ["description", "expected", "observed", "rationale"] {
            if text(check.get(field)).is_none() {
                audit
                    .errors
                    .push(format!("checks[{index}].{field} is required"));
            }
        }
        let scope = text(check.get("scope")).unwrap_or_default();
        let domain = text(check.get("domain")).unwrap_or_default();
        let component = text(check.get("component")).unwrap_or_default();
        let method = text(check.get("method")).unwrap_or_default();
        let status = text(check.get("status")).unwrap_or_default();
        if !matches!(scope, "cost_effectiveness" | "budget_impact" | "shared")
            || !matches!(
                domain,
                "face_validity"
                    | "input_data"
                    | "technical_verification"
                    | "cross_validity"
                    | "external_validity"
                    | "predictive_validity"
            )
            || !matches!(
                component,
                "conceptual_model"
                    | "input_calculations"
                    | "event_state_calculations"
                    | "result_calculations"
                    | "uncertainty_calculations"
                    | "overall_checks"
                    | "model_outcomes"
            )
        {
            audit.errors.push(format!(
                "checks[{index}] scope, domain, or component is invalid"
            ));
        }
        if !method_matches(domain, method) {
            audit.errors.push(format!(
                "checks[{index}].method is inconsistent with its domain"
            ));
        }
        if !matches!(
            status,
            "passed" | "failed" | "inconclusive" | "not_feasible"
        ) {
            audit
                .errors
                .push(format!("checks[{index}].status is invalid"));
        }
        if !matches!(
            text(check.get("performed_by")),
            Some("independent_reviewer" | "developer" | "automated_test")
        ) {
            audit
                .errors
                .push(format!("checks[{index}].performed_by is invalid"));
        }
        if strings(check.get("evidence_ids"), true).is_none_or(|ids| !ids.is_subset(&evidence_ids))
        {
            audit
                .errors
                .push(format!("checks[{index}].evidence_ids are invalid"));
        }
        let linked_issues = strings(check.get("issue_ids"), false);
        if linked_issues
            .as_ref()
            .is_none_or(|ids| ids.iter().any(|id| !issue_status.contains_key(id)))
        {
            audit
                .errors
                .push(format!("checks[{index}].issue_ids are invalid"));
        }
        if matches!(status, "failed" | "inconclusive")
            && linked_issues.as_ref().is_none_or(HashSet::is_empty)
        {
            audit.errors.push(format!(
                "checks[{index}] failed or inconclusive check must link an issue"
            ));
        }
        if status == "not_feasible" && !matches!(domain, "cross_validity" | "predictive_validity") {
            audit.errors.push(format!(
                "checks[{index}] not_feasible is allowed only for cross or predictive validity"
            ));
        }
    }

    let check_values = checks.map_or(&[][..], Vec::as_slice);
    audit.missing_coverage = REQUIREMENTS
        .iter()
        .filter(|requirement| {
            !check_values
                .iter()
                .any(|check| check_covers(check, **requirement))
        })
        .map(|requirement| requirement.label.to_string())
        .collect();
    audit.covered_requirement_count = REQUIREMENTS.len() - audit.missing_coverage.len();

    if strings(report.get("limitations"), true).is_none() {
        audit
            .errors
            .push("limitations must be a non-empty unique string array".into());
    }
    let conclusion = report.get("conclusion");
    audit.recommendation = text(conclusion.and_then(|value| value.get("recommendation")))
        .unwrap_or("pending")
        .to_string();
    if !matches!(
        audit.recommendation.as_str(),
        "approve_for_intended_use" | "approve_with_limitations" | "do_not_approve"
    ) {
        audit
            .errors
            .push("conclusion.recommendation must be a final reviewer recommendation".into());
    }
    if text(conclusion.and_then(|value| value.get("rationale"))).is_none()
        || strings(
            conclusion.and_then(|value| value.get("residual_uncertainty")),
            true,
        )
        .is_none()
    {
        audit
            .errors
            .push("conclusion requires rationale and residual_uncertainty".into());
    }

    audit.open_blocking_issue_count = issue_status
        .iter()
        .filter(|(id, status)| {
            status.as_str() == "open"
                && matches!(
                    issue_severity.get(*id).map(String::as_str),
                    Some("blocker" | "major")
                )
        })
        .count();
    audit.open_minor_issue_count = issue_status
        .iter()
        .filter(|(id, status)| {
            status.as_str() == "open"
                && issue_severity.get(*id).map(String::as_str) == Some("minor")
        })
        .count();
    if audit.recommendation == "approve_for_intended_use"
        && audit.open_blocking_issue_count + audit.open_minor_issue_count > 0
    {
        audit
            .errors
            .push("approve_for_intended_use cannot retain open issues".into());
    }
    if audit.recommendation == "approve_with_limitations" && audit.open_blocking_issue_count > 0 {
        audit
            .errors
            .push("approve_with_limitations cannot retain open blocker or major issues".into());
    }

    audit.errors.extend(audit.invalid_evidence.iter().cloned());
    if !audit.missing_coverage.is_empty() {
        audit.errors.push(format!(
            "missing independent validation coverage: {}",
            audit.missing_coverage.join(", ")
        ));
    }
    audit.complete = audit.errors.is_empty();
    audit.approvable = audit.complete
        && matches!(
            audit.recommendation.as_str(),
            "approve_for_intended_use" | "approve_with_limitations"
        );
    audit.status = if audit.complete {
        "complete"
    } else {
        "incomplete"
    };
    audit
}

pub fn audit_model_validation_for_plan(
    workspace: &Path,
    plan_raw: &[u8],
) -> Result<ModelValidationAudit, String> {
    let report_raw =
        match crate::heor_uncertainty::read_workspace_capped(workspace, MODEL_VALIDATION_PATH) {
            Ok(raw) => raw,
            Err(error) => {
                let mut audit = empty_audit(plan_raw);
                audit.errors.push(error);
                return Ok(audit);
            }
        };
    let report: serde_json::Value = serde_json::from_slice(&report_raw)
        .map_err(|error| format!("model validation report is invalid: {error}"))?;
    Ok(audit_values(workspace, plan_raw, &report, &report_raw))
}

pub fn require_model_validation_approvable(
    workspace: &Path,
    expected_hash: &str,
    actor_label: &str,
) -> Result<ModelValidationAudit, String> {
    let plan_raw = crate::heor_uncertainty::read_workspace_capped(workspace, ANALYSIS_PLAN_PATH)?;
    let audit = audit_model_validation_for_plan(workspace, &plan_raw)?;
    if audit.validation_sha256 != expected_hash {
        return Err(
            "independent-validation approval must target the current heor/model-validation.json"
                .into(),
        );
    }
    if !audit.complete || !audit.approvable {
        return Err(format!(
            "model validation is not approvable: {}/{} requirements covered, {} open blocker/major issues, {} errors",
            audit.covered_requirement_count,
            audit.required_coverage_count,
            audit.open_blocking_issue_count,
            audit.errors.len()
        ));
    }
    if actor_label != audit.reviewer_label {
        return Err(
            "approval actorLabel must exactly match the independent reviewer label in the report"
                .into(),
        );
    }
    Ok(audit)
}

pub fn analysis_plan_approval_is_current(
    log: &crate::heor_approval::ApprovalLog,
    audit: &ModelValidationAudit,
) -> bool {
    if !log
        .effective_approved_gates
        .contains(&crate::heor_approval::ApprovalGate::AnalysisPlan)
    {
        return false;
    }
    let conceptual = log
        .events
        .iter()
        .rev()
        .find(|event| event.gate == crate::heor_approval::ApprovalGate::ConceptualModel);
    let analysis = log
        .events
        .iter()
        .rev()
        .find(|event| event.gate == crate::heor_approval::ApprovalGate::AnalysisPlan);
    conceptual.is_some_and(|event| {
        event.action == crate::heor_approval::ApprovalAction::Approve
            && event.artifact_sha256 == audit.conceptual_model_sha256
    }) && analysis.is_some_and(|event| {
        event.action == crate::heor_approval::ApprovalAction::Approve
            && event.artifact_sha256 == audit.analysis_plan_sha256
            && crate::heor_approval::event_binds_artifact(
                event,
                UNCERTAINTY_PLAN_PATH,
                &audit.uncertainty_plan_sha256,
            )
            && crate::heor_approval::event_binds_artifact(
                event,
                BUDGET_IMPACT_PLAN_PATH,
                &audit.budget_impact_plan_sha256,
            )
    })
}

pub fn approval_bindings(
    audit: &ModelValidationAudit,
) -> Vec<crate::heor_approval::ArtifactBinding> {
    vec![
        crate::heor_approval::ArtifactBinding {
            path: ANALYSIS_PLAN_PATH.into(),
            sha256: audit.analysis_plan_sha256.clone(),
        },
        crate::heor_approval::ArtifactBinding {
            path: CONCEPTUAL_MODEL_PATH.into(),
            sha256: audit.conceptual_model_sha256.clone(),
        },
        crate::heor_approval::ArtifactBinding {
            path: UNCERTAINTY_PLAN_PATH.into(),
            sha256: audit.uncertainty_plan_sha256.clone(),
        },
        crate::heor_approval::ArtifactBinding {
            path: BUDGET_IMPACT_PLAN_PATH.into(),
            sha256: audit.budget_impact_plan_sha256.clone(),
        },
    ]
}

#[tauri::command(async)]
pub fn audit_heor_model_validation(app: AppHandle) -> Result<ModelValidationAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    let plan_raw = crate::heor_uncertainty::read_workspace_capped(&workspace, ANALYSIS_PLAN_PATH)?;
    audit_model_validation_for_plan(&workspace, &plan_raw)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::path::PathBuf;

    fn temp_root(tag: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "heor-model-validation-{tag}-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor/validation-evidence")).unwrap();
        root
    }

    fn method(domain: &str) -> &'static str {
        match domain {
            "face_validity" => "expert_review",
            "input_data" => "source_reconciliation",
            "technical_verification" => "black_box",
            "cross_validity" => "cross_model_comparison",
            "external_validity" => "external_data_comparison",
            "predictive_validity" => "prospective_comparison",
            _ => unreachable!(),
        }
    }

    fn fixture(root: &Path) -> (Vec<u8>, serde_json::Value) {
        let analysis_id = "analysis-1";
        let mut bindings = serde_json::Map::new();
        let mut plan_raw = Vec::new();
        for (key, path) in [
            ("analysis_plan", ANALYSIS_PLAN_PATH),
            ("conceptual_model", CONCEPTUAL_MODEL_PATH),
            ("uncertainty_plan", UNCERTAINTY_PLAN_PATH),
            ("budget_impact_plan", BUDGET_IMPACT_PLAN_PATH),
        ] {
            let raw =
                serde_json::to_vec(&json!({"analysis_id": analysis_id, "kind": key})).unwrap();
            std::fs::write(root.join(path), &raw).unwrap();
            if key == "analysis_plan" {
                plan_raw = raw.clone();
            }
            bindings.insert(
                key.into(),
                json!({"path": path, "content_sha256": sha256(&raw)}),
            );
        }
        let evidence_raw = b"independent validation evidence\n";
        std::fs::write(
            root.join("heor/validation-evidence/review.txt"),
            evidence_raw,
        )
        .unwrap();
        let checks = REQUIREMENTS
            .iter()
            .enumerate()
            .map(|(index, requirement)| {
                json!({
                    "id": format!("check-{index}"),
                    "scope": requirement.scope,
                    "domain": requirement.domain,
                    "component": requirement.component.unwrap_or("model_outcomes"),
                    "method": method(requirement.domain),
                    "status": "passed",
                    "performed_by": "independent_reviewer",
                    "description": requirement.label,
                    "expected": "Independent criterion is met",
                    "observed": "Evidence supports the criterion",
                    "rationale": "Reviewed for the intended use",
                    "evidence_ids": ["review-evidence"],
                    "issue_ids": []
                })
            })
            .collect::<Vec<_>>();
        let report = json!({
            "schema_version": "0.1.0",
            "validation_id": "validation-1",
            "analysis_id": analysis_id,
            "status": "ready_for_independent_review",
            "intended_use": "Local reimbursement research",
            "model_bindings": bindings,
            "developer_label": "Model developer",
            "reviewer": {
                "label": "Independent reviewer",
                "organization": "Independent methods unit",
                "role": "independent_reviewer",
                "reviewed_on": "2026-07-14",
                "declared_independent": true,
                "independence_statement": "No role in model development",
                "conflict_statement": "No conflicts declared"
            },
            "evidence_artifacts": [{
                "id": "review-evidence",
                "path": "heor/validation-evidence/review.txt",
                "content_sha256": sha256(evidence_raw),
                "evidence_type": "test_log",
                "description": "Independent review evidence"
            }],
            "checks": checks,
            "issues": [],
            "limitations": ["Predictive observations remain time-limited"],
            "conclusion": {
                "recommendation": "approve_for_intended_use",
                "rationale": "All required checks passed",
                "residual_uncertainty": ["Future data may change external comparisons"]
            }
        });
        std::fs::write(
            root.join(MODEL_VALIDATION_PATH),
            serde_json::to_vec(&report).unwrap(),
        )
        .unwrap();
        (plan_raw, report)
    }

    #[test]
    fn complete_report_is_approvable() {
        let root = temp_root("complete");
        let (plan_raw, _) = fixture(&root);
        let audit = audit_model_validation_for_plan(&root, &plan_raw).unwrap();
        assert!(audit.complete);
        assert!(audit.approvable);
        assert_eq!(audit.covered_requirement_count, REQUIREMENTS.len());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn stale_binding_and_missing_external_check_fail_closed() {
        let root = temp_root("stale");
        let (plan_raw, mut report) = fixture(&root);
        report["model_bindings"]["conceptual_model"]["content_sha256"] = json!("0".repeat(64));
        report["checks"].as_array_mut().unwrap().retain(|check| {
            !(check["scope"] == "budget_impact" && check["domain"] == "external_validity")
        });
        let raw = serde_json::to_vec(&report).unwrap();
        let audit = audit_values(&root, &plan_raw, &report, &raw);
        assert!(!audit.complete);
        assert!(audit
            .missing_coverage
            .contains(&"budget-impact external validity".into()));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn approval_actor_must_match_independent_reviewer() {
        let root = temp_root("actor");
        let (_, report) = fixture(&root);
        let hash = sha256(&serde_json::to_vec(&report).unwrap());
        let error =
            require_model_validation_approvable(&root, &hash, "Model developer").unwrap_err();
        assert!(error.contains("actorLabel"));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn open_major_issue_cannot_be_approved_with_limitations() {
        let root = temp_root("major");
        let (plan_raw, mut report) = fixture(&root);
        report["issues"] = json!([{
            "id": "issue-1", "severity": "major", "status": "open",
            "description": "External mismatch", "evidence_ids": ["review-evidence"]
        }]);
        report["conclusion"]["recommendation"] = json!("approve_with_limitations");
        let raw = serde_json::to_vec(&report).unwrap();
        let audit = audit_values(&root, &plan_raw, &report, &raw);
        assert!(!audit.complete);
        assert!(!audit.approvable);
        assert_eq!(audit.open_blocking_issue_count, 1);
        let _ = std::fs::remove_dir_all(root);
    }
}
