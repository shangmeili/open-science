//! Native fail-closed audit for the bounded HEOR reproducibility companion.
//! The companion is prepared under researcher direction with Agent assistance,
//! but only the existing app-owned release gate may bind it after deterministic replay.
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::Path;
use tauri::AppHandle;

pub const REPRODUCIBILITY_PACKAGE_PATH: &str = "heor/reproducibility-package.json";
const REPORT_PACKAGE_PATH: &str = crate::heor_reporting::REPORT_PACKAGE_PATH;
const REQUIRED_CLAIMS: [(&str, &str, &str); 7] = [
    ("CHEERS-2022", "23-summary-results", "cost_effectiveness"),
    ("CHEERS-2022", "24-uncertainty-effects", "uncertainty"),
    (
        "CHEERS-2022",
        "26-findings-limitations-generalisability",
        "cost_effectiveness",
    ),
    (
        "ISPOR-BIA-GP-II-2014",
        "bia-8-period-disaggregated-results",
        "budget_impact",
    ),
    (
        "ISPOR-BIA-GP-II-2014",
        "bia-9-cumulative-impact",
        "budget_impact",
    ),
    (
        "ISPOR-BIA-GP-II-2014",
        "bia-10-uncertainty-scenarios",
        "budget_impact",
    ),
    (
        "ISPOR-BIA-GP-II-2014",
        "bia-12-limitations-reproducibility",
        "budget_impact",
    ),
];

#[derive(Clone, Debug)]
pub struct RuntimeIdentity {
    pub ai4heor_version: String,
    pub platform: String,
    pub python_version: String,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReproducibilityAudit {
    pub complete: bool,
    pub release_companion_ready: bool,
    pub status: &'static str,
    pub package_id: String,
    pub analysis_id: String,
    pub package_sha256: String,
    pub report_package_sha256: String,
    pub runtime_matches: bool,
    pub artifact_count: usize,
    pub execution_count: usize,
    pub source_count: usize,
    pub availability_count: usize,
    pub exhibit_count: usize,
    pub claim_count: usize,
    pub required_claim_count: usize,
    pub covered_claim_count: usize,
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

fn safe_id(value: &str) -> bool {
    value.len() <= 64
        && value.bytes().enumerate().all(|(index, byte)| match index {
            0 => byte.is_ascii_lowercase(),
            _ => byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'_' | b'-'),
        })
}

fn safe_availability_id(value: &str) -> bool {
    value.len() <= 77
        && value.bytes().enumerate().all(|(index, byte)| match index {
            0 => byte.is_ascii_lowercase(),
            _ => byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'_' | b'-'),
        })
}

fn valid_date(value: Option<&serde_json::Value>) -> bool {
    text(value).is_some_and(|value| {
        value.len() == 10
            && value.as_bytes()[4] == b'-'
            && value.as_bytes()[7] == b'-'
            && value
                .bytes()
                .enumerate()
                .all(|(index, byte)| matches!(index, 4 | 7) || byte.is_ascii_digit())
    })
}

fn strings(value: Option<&serde_json::Value>) -> Option<Vec<&str>> {
    value?
        .as_array()?
        .iter()
        .map(|item| text(Some(item)))
        .collect()
}

fn read_json(workspace: &Path, relative: &str) -> Result<(serde_json::Value, Vec<u8>), String> {
    let raw = crate::heor_uncertainty::read_workspace_capped(workspace, relative)?;
    let value: serde_json::Value =
        serde_json::from_slice(&raw).map_err(|error| format!("{relative} is invalid: {error}"))?;
    if !value.is_object() {
        return Err(format!("{relative} must contain a JSON object"));
    }
    Ok((value, raw))
}

fn empty(error: String) -> ReproducibilityAudit {
    ReproducibilityAudit {
        complete: false,
        release_companion_ready: false,
        status: "incomplete",
        package_id: String::new(),
        analysis_id: String::new(),
        package_sha256: String::new(),
        report_package_sha256: String::new(),
        runtime_matches: false,
        artifact_count: 0,
        execution_count: 0,
        source_count: 0,
        availability_count: 0,
        exhibit_count: 0,
        claim_count: 0,
        required_claim_count: REQUIRED_CLAIMS.len(),
        covered_claim_count: 0,
        errors: vec![error],
    }
}

fn expected_role(key: &str) -> &'static str {
    if key == "report_package" {
        "release_manifest"
    } else if key == "report_document" {
        "report"
    } else if key == "evidence_synthesis" {
        "evidence"
    } else if key.ends_with("_result") {
        "result"
    } else if matches!(
        key,
        "survival_curve_materializations"
            | "treatment_effect_duration"
            | "cost_input_normalization"
            | "utility_inputs"
            | "event_disutilities"
    ) {
        "input"
    } else {
        "method"
    }
}

fn expected_execution_manifest(
    report: &serde_json::Value,
    loaded: &HashMap<String, serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let bindings = report
        .get("bindings")
        .and_then(serde_json::Value::as_object)
        .ok_or("report package bindings must be an object")?;
    let path = |key: &str| -> Result<&str, String> {
        text(bindings.get(key).and_then(|value| value.get("path")))
            .ok_or_else(|| format!("report binding path is missing: {key}"))
    };
    let engine = |key: &str| -> Result<&str, String> {
        loaded
            .get(key)
            .and_then(|value| text(value.get("engine_version")))
            .ok_or_else(|| format!("bound result omitted engine_version: {key}"))
    };
    let partitioned = bindings.contains_key("partitioned_survival_result");
    let base_key = if partitioned {
        "partitioned_survival_result"
    } else {
        "base_case_result"
    };
    let mut base_command = vec![
        "python".to_string(),
        "-m".into(),
        "heor_core".into(),
        "heor/analysis-plan.json".into(),
    ];
    let mut base_inputs = vec!["analysis_plan".to_string()];
    if partitioned {
        for (flag, key) in [
            ("--partitioned-survival-plan", "partitioned_survival_plan"),
            (
                "--survival-curve-materializations",
                "survival_curve_materializations",
            ),
            ("--treatment-effect-duration", "treatment_effect_duration"),
            ("--cost-input-normalization", "cost_input_normalization"),
            ("--utility-inputs", "utility_inputs"),
            ("--event-disutilities", "event_disutilities"),
        ] {
            base_command.extend([flag.into(), path(key)?.into()]);
            base_inputs.push(key.into());
        }
    }
    let mut uncertainty_command = base_command.clone();
    uncertainty_command.extend([
        "--uncertainty-plan".into(),
        path("uncertainty_plan")?.into(),
    ]);
    let mut uncertainty_inputs = base_inputs.clone();
    uncertainty_inputs.push("uncertainty_plan".into());
    if loaded
        .get("uncertainty_plan")
        .and_then(|value| text(value.get("schema_version")))
        == Some("0.14.0")
    {
        uncertainty_command.extend([
            "--joint-survival-uncertainty-manifest".into(),
            crate::heor_joint_survival_uncertainty::MANIFEST_PATH.into(),
            "--joint-survival-draws".into(),
            crate::heor_joint_survival_uncertainty::DRAWS_PATH.into(),
        ]);
    }
    Ok(serde_json::json!([
        {
            "execution_id": "cost_effectiveness",
            "engine_version": engine(base_key)?,
            "command": base_command,
            "input_artifact_ids": base_inputs,
            "output_artifact_id": base_key,
            "determinism": "byte_replay_expected"
        },
        {
            "execution_id": "uncertainty",
            "engine_version": engine("uncertainty_result")?,
            "command": uncertainty_command,
            "input_artifact_ids": uncertainty_inputs,
            "output_artifact_id": "uncertainty_result",
            "determinism": "byte_replay_expected"
        },
        {
            "execution_id": "budget_impact",
            "engine_version": engine("budget_impact_result")?,
            "command": [
                "python", "-m", "heor_core", "heor/analysis-plan.json",
                "--budget-impact-plan", path("budget_impact_plan")?
            ],
            "input_artifact_ids": ["analysis_plan", "budget_impact_plan"],
            "output_artifact_id": "budget_impact_result",
            "determinism": "byte_replay_expected"
        }
    ]))
}

fn source_union(
    analysis: &serde_json::Value,
    budget: &serde_json::Value,
    errors: &mut Vec<String>,
) -> HashMap<String, serde_json::Value> {
    let mut result = HashMap::new();
    for (owner, plan) in [("analysis", analysis), ("budget impact", budget)] {
        let Some(sources) = plan
            .get("evidence_sources")
            .and_then(serde_json::Value::as_array)
        else {
            errors.push(format!("{owner} evidence_sources must be an array"));
            continue;
        };
        for source in sources {
            let Some(source_id) = text(source.get("id")) else {
                errors.push(format!("{owner} evidence source omitted id"));
                continue;
            };
            if !safe_id(source_id) {
                errors.push(format!("{owner} evidence source id is invalid"));
                continue;
            }
            if result
                .insert(source_id.into(), source.clone())
                .is_some_and(|existing| existing != *source)
            {
                errors.push(format!("evidence source {source_id} differs across plans"));
            }
        }
    }
    result
}

pub fn audit_reproducibility_package_for_identity(
    workspace: &Path,
    identity: &RuntimeIdentity,
) -> Result<ReproducibilityAudit, String> {
    let (package, package_raw) = match read_json(workspace, REPRODUCIBILITY_PACKAGE_PATH) {
        Ok(value) => value,
        Err(error) => return Ok(empty(error)),
    };
    let mut audit = empty(String::new());
    audit.errors.clear();
    audit.package_id = text(package.get("package_id")).unwrap_or_default().into();
    audit.analysis_id = text(package.get("analysis_id")).unwrap_or_default().into();
    audit.package_sha256 = sha256(&package_raw);
    if text(package.get("schema_version")) != Some("0.1.0") {
        audit.errors.push("schema_version must be 0.1.0".into());
    }
    for (field, value) in [
        ("package_id", audit.package_id.as_str()),
        ("analysis_id", audit.analysis_id.as_str()),
    ] {
        if !safe_id(value) {
            audit.errors.push(format!("{field} must be a safe id"));
        }
    }
    if text(package.get("status")) != Some("ready_for_reproducibility_review") {
        audit
            .errors
            .push("status must be ready_for_reproducibility_review".into());
    }
    if !valid_date(package.get("prepared_on")) {
        audit.errors.push("prepared_on must be YYYY-MM-DD".into());
    }

    let (report, report_raw) = read_json(workspace, REPORT_PACKAGE_PATH)?;
    audit.report_package_sha256 = sha256(&report_raw);
    let report_audit = crate::heor_reporting::audit_report_package(workspace)?;
    if !report_audit.releasable {
        audit
            .errors
            .push("current report package is not release-reviewable".into());
    }
    if audit.analysis_id != report_audit.analysis_id {
        audit
            .errors
            .push("analysis_id does not match the report package".into());
    }
    if package.get("report_package")
        != Some(&serde_json::json!({
            "path": REPORT_PACKAGE_PATH,
            "content_sha256": audit.report_package_sha256
        }))
    {
        audit
            .errors
            .push("report_package binding does not match current bytes".into());
    }

    let mut expected = HashMap::<String, (String, String, String)>::new();
    expected.insert(
        "report_package".into(),
        (
            REPORT_PACKAGE_PATH.into(),
            audit.report_package_sha256.clone(),
            "release_manifest".into(),
        ),
    );
    for (key, path) in &report_audit.binding_paths {
        let Some(hash) = report_audit.binding_hashes.get(key) else {
            audit
                .errors
                .push(format!("report binding hash is missing: {key}"));
            continue;
        };
        expected.insert(
            key.clone(),
            (path.clone(), hash.clone(), expected_role(key).into()),
        );
    }
    let (analysis, _) = read_json(workspace, "heor/analysis-plan.json")?;
    if let Some(evidence) = analysis
        .get("evidence_synthesis")
        .and_then(serde_json::Value::as_object)
    {
        if text(evidence.get("path")) != Some(crate::heor_synthesis::EVIDENCE_SYNTHESIS_PATH)
            || text(evidence.get("content_sha256")).is_none()
        {
            audit
                .errors
                .push("analysis evidence_synthesis binding is invalid".into());
        } else {
            expected.insert(
                "evidence_synthesis".into(),
                (
                    crate::heor_synthesis::EVIDENCE_SYNTHESIS_PATH.into(),
                    text(evidence.get("content_sha256"))
                        .unwrap_or_default()
                        .into(),
                    "evidence".into(),
                ),
            );
        }
    }

    let inventory = package
        .get("artifact_inventory")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    audit.artifact_count = inventory.len();
    let mut inventory_ids = HashSet::new();
    for (index, item) in inventory.iter().enumerate() {
        let Some(key) = text(item.get("artifact_id")) else {
            audit.errors.push(format!(
                "artifact_inventory[{index}].artifact_id is required"
            ));
            continue;
        };
        if !safe_id(key) || !inventory_ids.insert(key.to_string()) {
            audit.errors.push(format!(
                "artifact_inventory[{index}].artifact_id is invalid or duplicated"
            ));
            continue;
        }
        let Some((path, hash, role)) = expected.get(key) else {
            audit.errors.push(format!(
                "artifact_inventory contains unknown artifact: {key}"
            ));
            continue;
        };
        if item
            != &serde_json::json!({
                "artifact_id": key,
                "path": path,
                "content_sha256": hash,
                "role": role
            })
        {
            audit.errors.push(format!(
                "artifact_inventory entry does not match current binding: {key}"
            ));
            continue;
        }
        match crate::heor_uncertainty::read_workspace_capped(workspace, path) {
            Ok(raw) if sha256(&raw) == *hash => {}
            Ok(_) => audit
                .errors
                .push(format!("artifact_inventory current bytes differ: {key}")),
            Err(error) => audit.errors.push(error),
        }
    }
    if inventory_ids != expected.keys().cloned().collect::<HashSet<_>>() {
        audit.errors.push(
            "artifact_inventory must contain exactly the report graph and declared evidence synthesis"
                .into(),
        );
    }

    let mut loaded = HashMap::new();
    for key in [
        "uncertainty_plan",
        "base_case_result",
        "partitioned_survival_result",
        "uncertainty_result",
        "budget_impact_result",
    ] {
        if let Some((path, _, _)) = expected.get(key) {
            if let Ok((value, _)) = read_json(workspace, path) {
                loaded.insert(key.into(), value);
            }
        }
    }
    let expected_execution = match expected_execution_manifest(&report, &loaded) {
        Ok(value) => value,
        Err(error) => {
            audit.errors.push(error);
            serde_json::json!([])
        }
    };
    audit.execution_count = package
        .get("execution_manifest")
        .and_then(serde_json::Value::as_array)
        .map_or(0, Vec::len);
    if package.get("execution_manifest") != Some(&expected_execution) {
        audit
            .errors
            .push("execution_manifest does not match the exact current replay recipes".into());
    }

    let environment = package.get("environment");
    let mut engine_versions = expected_execution
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|value| text(value.get("engine_version")))
        .map(str::to_string)
        .collect::<Vec<_>>();
    engine_versions.sort();
    engine_versions.dedup();
    let expected_lock = serde_json::json!({
        "status": "not_applicable_standard_library_only",
        "package_count": 0,
        "path": null,
        "content_sha256": null
    });
    let runtime_matches = text(environment.and_then(|value| value.get("ai4heor_version")))
        == Some(identity.ai4heor_version.as_str())
        && text(environment.and_then(|value| value.get("platform")))
            == Some(identity.platform.as_str())
        && text(environment.and_then(|value| value.get("python_version")))
            == Some(identity.python_version.as_str())
        && environment.and_then(|value| value.get("result_engine_versions"))
            == Some(&serde_json::json!(engine_versions))
        && environment.and_then(|value| value.get("core_dependency_lock")) == Some(&expected_lock);
    audit.runtime_matches = runtime_matches;
    if !runtime_matches {
        audit
            .errors
            .push("environment does not match the current replay runtime".into());
    }

    let (budget, _) = read_json(workspace, "heor/budget-impact-plan.json")?;
    let sources = source_union(&analysis, &budget, &mut audit.errors);
    let source_register = package
        .get("source_register")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    audit.source_count = source_register.len();
    let mut registered = HashMap::<String, serde_json::Value>::new();
    for (index, item) in source_register.iter().enumerate() {
        let Some(source_id) = text(item.get("source_id")) else {
            audit
                .errors
                .push(format!("source_register[{index}].source_id is required"));
            continue;
        };
        if registered.insert(source_id.into(), item.clone()).is_some() {
            audit
                .errors
                .push(format!("source_register duplicates {source_id}"));
        }
    }
    if registered.keys().collect::<HashSet<_>>() != sources.keys().collect::<HashSet<_>>() {
        audit
            .errors
            .push("source_register must equal the unique evidence-source union".into());
    }
    for (source_id, source) in &sources {
        let locator = text(source.get("url")).or_else(|| text(source.get("local_path")));
        let content_hash = if text(source.get("local_path")).is_some() {
            source
                .get("content_sha256")
                .cloned()
                .unwrap_or(serde_json::Value::Null)
        } else {
            serde_json::Value::Null
        };
        let expected_source = serde_json::json!({
            "source_id": source_id,
            "title": source.get("title").cloned().unwrap_or(serde_json::Value::Null),
            "source_type": source.get("source_type").cloned().unwrap_or(serde_json::Value::Null),
            "locator": locator,
            "content_sha256": content_hash,
            "data_availability_id": format!("availability-{source_id}")
        });
        if registered.get(source_id) != Some(&expected_source) {
            audit.errors.push(format!(
                "source_register does not reproduce source metadata: {source_id}"
            ));
        }
    }

    let availability = package
        .get("data_availability")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    audit.availability_count = availability.len();
    let mut availability_ids = HashSet::new();
    let mut covered_sources = Vec::new();
    for (index, item) in availability.iter().enumerate() {
        let id = text(item.get("availability_id")).unwrap_or_default();
        if !safe_availability_id(id) || !availability_ids.insert(id.to_string()) {
            audit.errors.push(format!(
                "data_availability[{index}].availability_id is invalid or duplicated"
            ));
        }
        if !matches!(
            text(item.get("status")),
            Some(
                "included_workspace"
                    | "public_locator"
                    | "available_on_request"
                    | "restricted_not_shared"
                    | "unavailable"
            )
        ) || !matches!(
            text(item.get("license_status")),
            Some("open" | "permission_required" | "restricted" | "unknown" | "not_applicable")
        ) {
            audit.errors.push(format!(
                "data_availability[{index}] status or license_status is invalid"
            ));
        }
        if text(item.get("access_conditions")).is_none() || text(item.get("rationale")).is_none() {
            audit.errors.push(format!(
                "data_availability[{index}] requires access_conditions and rationale"
            ));
        }
        let source_ids = strings(item.get("source_ids")).unwrap_or_default();
        if source_ids.is_empty() || source_ids.iter().any(|id| !sources.contains_key(*id)) {
            audit
                .errors
                .push(format!("data_availability[{index}].source_ids are invalid"));
        }
        covered_sources.extend(source_ids.into_iter().map(str::to_string));
    }
    covered_sources.sort();
    let mut expected_sources = sources.keys().cloned().collect::<Vec<_>>();
    expected_sources.sort();
    if covered_sources != expected_sources
        || covered_sources.iter().collect::<HashSet<_>>().len() != covered_sources.len()
    {
        audit
            .errors
            .push("data_availability must cover every registered source exactly once".into());
    }
    for (source_id, item) in &registered {
        if text(item.get("data_availability_id")).is_none_or(|id| !availability_ids.contains(id)) {
            audit.errors.push(format!(
                "source_register availability link is missing: {source_id}"
            ));
        }
    }

    let claims = package
        .get("claim_evidence_ledger")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    audit.claim_count = claims.len();
    let mut claim_ids = HashSet::new();
    let mut covered_claims = HashSet::new();
    let base_result = if expected.contains_key("partitioned_survival_result") {
        "partitioned_survival_result"
    } else {
        "base_case_result"
    };
    let result_for = |scope: &str| match scope {
        "cost_effectiveness" => base_result,
        "uncertainty" => "uncertainty_result",
        _ => "budget_impact_result",
    };
    for (index, claim) in claims.iter().enumerate() {
        let claim_id = text(claim.get("claim_id")).unwrap_or_default();
        if !safe_id(claim_id) || !claim_ids.insert(claim_id.to_string()) {
            audit.errors.push(format!(
                "claim_evidence_ledger[{index}].claim_id is invalid or duplicated"
            ));
        }
        let profile = text(claim.get("profile_id")).unwrap_or_default();
        let item = text(claim.get("item_id")).unwrap_or_default();
        let required = REQUIRED_CLAIMS
            .iter()
            .find(|(required_profile, required_item, _)| {
                *required_profile == profile && *required_item == item
            });
        let artifacts = strings(claim.get("artifact_ids")).unwrap_or_default();
        if let Some((_, _, scope)) = required {
            covered_claims.insert((profile.to_string(), item.to_string()));
            if !artifacts.contains(&result_for(scope)) {
                audit.errors.push(format!(
                    "claim_evidence_ledger[{index}] omits its deterministic result"
                ));
            }
        } else {
            audit.errors.push(format!(
                "claim_evidence_ledger[{index}] reporting item is outside the required ledger"
            ));
        }
        if !matches!(
            text(claim.get("claim_type")),
            Some("numerical" | "interpretation" | "limitation")
        ) || !matches!(text(claim.get("status")), Some("supported" | "qualified"))
        {
            audit.errors.push(format!(
                "claim_evidence_ledger[{index}] type or status is invalid"
            ));
        }
        if text(claim.get("status")) == Some("qualified")
            && text(claim.get("qualification")).is_none()
        {
            audit.errors.push(format!(
                "claim_evidence_ledger[{index}] qualified claim needs qualification"
            ));
        }
        if text(claim.get("statement")).is_none() || artifacts.is_empty() {
            audit.errors.push(format!(
                "claim_evidence_ledger[{index}] requires statement and artifact_ids"
            ));
        }
        let source_ids_value = claim.get("source_ids");
        let source_ids = strings(source_ids_value).unwrap_or_default();
        if source_ids_value
            .and_then(serde_json::Value::as_array)
            .is_none()
            || source_ids_value
                .and_then(serde_json::Value::as_array)
                .is_some_and(|values| values.len() != source_ids.len())
        {
            audit.errors.push(format!(
                "claim_evidence_ledger[{index}].source_ids must be an explicit string array"
            ));
        }
        if artifacts.iter().any(|id| !expected.contains_key(*id))
            || source_ids.iter().any(|id| !sources.contains_key(*id))
        {
            audit.errors.push(format!(
                "claim_evidence_ledger[{index}] links unknown artifacts or sources"
            ));
        }
    }
    audit.covered_claim_count = covered_claims.len();
    if claims.len() != REQUIRED_CLAIMS.len() || covered_claims.len() != REQUIRED_CLAIMS.len() {
        audit.errors.push(
            "claim_evidence_ledger must contain exactly the seven required reporting items".into(),
        );
    }

    let exhibits = package
        .get("exhibit_register")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    audit.exhibit_count = exhibits.len();
    let exhibits_by_id = exhibits
        .iter()
        .filter_map(|item| text(item.get("exhibit_id")).map(|id| (id, item)))
        .collect::<HashMap<_, _>>();
    if exhibits.len() != 3
        || exhibits_by_id.keys().copied().collect::<HashSet<_>>()
            != HashSet::from(["cost_effectiveness", "uncertainty", "budget_impact"])
    {
        audit
            .errors
            .push("exhibit_register must contain exactly the three deterministic exhibits".into());
    }
    for (exhibit_id, result_id) in [
        ("cost_effectiveness", base_result),
        ("uncertainty", "uncertainty_result"),
        ("budget_impact", "budget_impact_result"),
    ] {
        let item = exhibits_by_id.get(exhibit_id).copied();
        let artifacts =
            strings(item.and_then(|value| value.get("artifact_ids"))).unwrap_or_default();
        let exhibit_claims =
            strings(item.and_then(|value| value.get("claim_ids"))).unwrap_or_default();
        if item.and_then(|value| text(value.get("label"))).is_none()
            || !artifacts.contains(&result_id)
            || exhibit_claims.is_empty()
        {
            audit
                .errors
                .push(format!("exhibit_register is incomplete: {exhibit_id}"));
        }
        if artifacts.iter().any(|id| !expected.contains_key(*id))
            || exhibit_claims.iter().any(|id| !claim_ids.contains(*id))
        {
            audit.errors.push(format!(
                "exhibit_register links unknown artifacts or claims: {exhibit_id}"
            ));
        }
    }

    let limitations = strings(package.get("limitations")).unwrap_or_default();
    if limitations.is_empty()
        || limitations.iter().copied().collect::<HashSet<_>>().len() != limitations.len()
    {
        audit
            .errors
            .push("limitations must contain unique non-empty statements".into());
    }

    audit.complete = audit.errors.is_empty();
    audit.release_companion_ready = audit.complete;
    audit.status = if audit.complete {
        "complete"
    } else {
        "incomplete"
    };
    Ok(audit)
}

fn python_version(app: &AppHandle) -> Result<String, String> {
    let (python, _) = crate::kernel::python_bin(app)?;
    let output = crate::runtime::quiet_command(python)
        .arg("--version")
        .output()
        .map_err(|error| format!("Python version probe failed: {error}"))?;
    if !output.status.success() {
        return Err("Python version probe failed".into());
    }
    let value = String::from_utf8_lossy(if output.stdout.is_empty() {
        &output.stderr
    } else {
        &output.stdout
    })
    .trim()
    .to_string();
    if value.is_empty() {
        return Err("Python version probe returned no version".into());
    }
    Ok(value)
}

pub fn runtime_identity(app: &AppHandle) -> Result<RuntimeIdentity, String> {
    Ok(RuntimeIdentity {
        ai4heor_version: env!("CARGO_PKG_VERSION").into(),
        platform: format!("{}-{}", std::env::consts::OS, std::env::consts::ARCH),
        python_version: python_version(app)?,
    })
}

pub fn audit_reproducibility_package(
    app: &AppHandle,
    workspace: &Path,
) -> Result<ReproducibilityAudit, String> {
    match runtime_identity(app) {
        Ok(identity) => audit_reproducibility_package_for_identity(workspace, &identity),
        Err(error) => Ok(empty(format!(
            "current replay runtime is unavailable: {error}"
        ))),
    }
}

pub fn approval_binding(audit: &ReproducibilityAudit) -> crate::heor_approval::ArtifactBinding {
    crate::heor_approval::ArtifactBinding {
        path: REPRODUCIBILITY_PACKAGE_PATH.into(),
        sha256: audit.package_sha256.clone(),
    }
}

#[tauri::command(async)]
pub fn audit_heor_reproducibility(app: AppHandle) -> Result<ReproducibilityAudit, String> {
    audit_reproducibility_package(&app, &crate::runtime::workspace_dir(&app)?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn fixture(tag: &str) -> (PathBuf, RuntimeIdentity) {
        let root =
            std::env::temp_dir().join(format!("heor-reproducibility-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor/results")).unwrap();

        let analysis = serde_json::json!({
            "schema_version": "0.8.0",
            "analysis_id": "analysis-1",
            "evidence_sources": []
        });
        let analysis_raw = serde_json::to_vec(&analysis).unwrap();
        let analysis_hash = sha256(&analysis_raw);
        let uncertainty_plan = serde_json::json!({
            "schema_version": "0.7.0",
            "analysis_id": "analysis-1"
        });
        let uncertainty_raw = serde_json::to_vec(&uncertainty_plan).unwrap();
        let uncertainty_hash = sha256(&uncertainty_raw);
        let budget_plan = serde_json::json!({
            "schema_version": "0.1.0",
            "analysis_id": "analysis-1",
            "evidence_sources": []
        });
        let budget_raw = serde_json::to_vec(&budget_plan).unwrap();
        let budget_hash = sha256(&budget_raw);
        let base = serde_json::json!({
            "analysis_id": "analysis-1",
            "engine_version": "0.15.0",
            "input_sha256": analysis_hash,
            "economic_basis": {"currency": "CNY", "price_year": 2026},
            "incremental": {
                "delta_cost": 10,
                "delta_qaly": 0.1,
                "icer": 100,
                "incremental_net_monetary_benefit": 9990
            }
        });
        let uncertainty = serde_json::json!({
            "analysis_id": "analysis-1",
            "engine_version": "0.15.0",
            "base_analysis_sha256": analysis_hash,
            "uncertainty_plan_sha256": uncertainty_hash,
            "probabilistic_analysis": {
                "iterations": 1000,
                "cost_effective_probability": 0.75,
                "mean_incremental_net_monetary_benefit": 9000
            }
        });
        let budget = serde_json::json!({
            "analysis_id": "analysis-1",
            "engine_version": "0.15.0",
            "analysis_plan_sha256": analysis_hash,
            "budget_impact_plan_sha256": budget_hash,
            "base_case": {
                "annual_net_budget_impact": [1, 2, 3],
                "cumulative_net_budget_impact": 6
            }
        });
        let mut report_template: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../runtime/skills/core/heor-reporting/assets/report-package.template.json"
        ))
        .unwrap();
        let items = report_template["items"].as_array_mut().unwrap();
        let report_document = items
            .iter_mut()
            .enumerate()
            .map(|(index, item)| {
                item["rationale"] = serde_json::json!("Reported from bound artifacts.");
                item["section_id"] = serde_json::json!(format!("section-{index}"));
                item["artifact_paths"] = serde_json::json!(["heor/report.md"]);
                format!("<!-- report-section:section-{index} -->\nSection {index}\n")
            })
            .collect::<String>();

        let artifacts = HashMap::from([
            (
                "report_document",
                ("heor/report.md", report_document.into_bytes()),
            ),
            ("analysis_plan", ("heor/analysis-plan.json", analysis_raw)),
            (
                "conceptual_model",
                (
                    "heor/conceptual-model.json",
                    serde_json::to_vec(&serde_json::json!({"analysis_id": "analysis-1"})).unwrap(),
                ),
            ),
            (
                "uncertainty_plan",
                ("heor/uncertainty-plan.json", uncertainty_raw),
            ),
            (
                "budget_impact_plan",
                ("heor/budget-impact-plan.json", budget_raw),
            ),
            (
                "model_validation",
                (
                    "heor/model-validation.json",
                    serde_json::to_vec(&serde_json::json!({"analysis_id": "analysis-1"})).unwrap(),
                ),
            ),
            (
                "base_case_result",
                (
                    crate::heor_reporting::BASE_CASE_RESULT_PATH,
                    serde_json::to_vec(&base).unwrap(),
                ),
            ),
            (
                "uncertainty_result",
                (
                    crate::heor_reporting::UNCERTAINTY_RESULT_PATH,
                    serde_json::to_vec(&uncertainty).unwrap(),
                ),
            ),
            (
                "budget_impact_result",
                (
                    crate::heor_reporting::BUDGET_IMPACT_RESULT_PATH,
                    serde_json::to_vec(&budget).unwrap(),
                ),
            ),
        ]);
        for (relative, raw) in artifacts.values() {
            let target = root.join(relative);
            std::fs::create_dir_all(target.parent().unwrap()).unwrap();
            std::fs::write(target, raw).unwrap();
        }
        let bindings = artifacts
            .iter()
            .map(|(key, (path, raw))| {
                (
                    (*key).to_string(),
                    serde_json::json!({"path": path, "content_sha256": sha256(raw)}),
                )
            })
            .collect::<serde_json::Map<_, _>>();
        report_template["package_id"] = serde_json::json!("report-1");
        report_template["analysis_id"] = serde_json::json!("analysis-1");
        report_template["status"] = serde_json::json!("ready_for_release_review");
        report_template["version"] = serde_json::json!("1.0");
        report_template["prepared_on"] = serde_json::json!("2026-07-16");
        report_template["intended_audience"] = serde_json::json!("HTA reviewers");
        report_template["release_owner_label"] = serde_json::json!("Release owner");
        report_template["bindings"] = serde_json::Value::Object(bindings);
        report_template["result_summary"] = serde_json::json!({
            "cost_effectiveness": {
                "economic_basis": {"currency": "CNY", "price_year": 2026},
                "delta_cost": 10,
                "delta_qaly": 0.1,
                "icer": 100,
                "incremental_net_monetary_benefit": 9990
            },
            "uncertainty": {
                "iterations": 1000,
                "cost_effective_probability": 0.75,
                "mean_incremental_net_monetary_benefit": 9000
            },
            "budget_impact": {
                "annual_net_budget_impact": [1, 2, 3],
                "cumulative_net_budget_impact": 6
            }
        });
        report_template["disclosures"] = serde_json::json!({
            "funding": "None",
            "conflicts_of_interest": "None",
            "agent_contributions": "Documented",
            "model_providers": "Documented",
            "data_and_model_availability": "Documented in the companion.",
            "patient_and_public_involvement": "Not involved"
        });
        report_template["limitations"] = serde_json::json!(["Illustrative fixture"]);
        report_template["release_notes"] = serde_json::json!(["Initial release"]);
        let report_raw = serde_json::to_vec(&report_template).unwrap();
        std::fs::write(root.join(REPORT_PACKAGE_PATH), &report_raw).unwrap();

        let report_audit = crate::heor_reporting::audit_report_package(&root).unwrap();
        assert!(report_audit.releasable, "{:?}", report_audit.errors);
        let expected_inventory = std::iter::once((
            "report_package".to_string(),
            (
                REPORT_PACKAGE_PATH.to_string(),
                sha256(&report_raw),
                "release_manifest".to_string(),
            ),
        ))
        .chain(report_audit.binding_paths.iter().map(|(key, path)| {
            (
                key.clone(),
                (
                    path.clone(),
                    report_audit.binding_hashes[key].clone(),
                    expected_role(key).to_string(),
                ),
            )
        }))
        .collect::<HashMap<_, _>>();
        let mut inventory = expected_inventory
            .iter()
            .map(|(key, (path, hash, role))| {
                serde_json::json!({
                    "artifact_id": key,
                    "path": path,
                    "content_sha256": hash,
                    "role": role
                })
            })
            .collect::<Vec<_>>();
        inventory.sort_by(|left, right| {
            text(left.get("artifact_id")).cmp(&text(right.get("artifact_id")))
        });
        let mut loaded = HashMap::new();
        loaded.insert("uncertainty_plan".into(), uncertainty_plan);
        loaded.insert("base_case_result".into(), base);
        loaded.insert("uncertainty_result".into(), uncertainty);
        loaded.insert("budget_impact_result".into(), budget);
        let execution = expected_execution_manifest(&report_template, &loaded).unwrap();
        let claims = REQUIRED_CLAIMS
            .iter()
            .enumerate()
            .map(|(index, (profile, item, scope))| {
                let result = match *scope {
                    "cost_effectiveness" => "base_case_result",
                    "uncertainty" => "uncertainty_result",
                    _ => "budget_impact_result",
                };
                serde_json::json!({
                    "claim_id": format!("claim-{}", index + 1),
                    "profile_id": profile,
                    "item_id": item,
                    "claim_type": if item.contains("limitation") || item.starts_with("26-") {"limitation"} else {"numerical"},
                    "statement": "Traceable fixture claim.",
                    "status": "qualified",
                    "artifact_ids": [result],
                    "source_ids": [],
                    "qualification": "Structural fixture only."
                })
            })
            .collect::<Vec<_>>();
        let identity = RuntimeIdentity {
            ai4heor_version: "0.1.16".into(),
            platform: "test-x86_64".into(),
            python_version: "Python 3.12.0".into(),
        };
        let package = serde_json::json!({
            "schema_version": "0.1.0",
            "package_id": "repro-1",
            "analysis_id": "analysis-1",
            "status": "ready_for_reproducibility_review",
            "prepared_on": "2026-07-16",
            "report_package": {"path": REPORT_PACKAGE_PATH, "content_sha256": sha256(&report_raw)},
            "artifact_inventory": inventory,
            "execution_manifest": execution,
            "environment": {
                "ai4heor_version": identity.ai4heor_version,
                "platform": identity.platform,
                "python_version": identity.python_version,
                "result_engine_versions": ["0.15.0"],
                "core_dependency_lock": {
                    "status": "not_applicable_standard_library_only",
                    "package_count": 0,
                    "path": null,
                    "content_sha256": null
                }
            },
            "source_register": [],
            "data_availability": [],
            "exhibit_register": [
                {"exhibit_id": "cost_effectiveness", "label": "Cost effectiveness", "artifact_ids": ["base_case_result"], "claim_ids": ["claim-1", "claim-3"]},
                {"exhibit_id": "uncertainty", "label": "Uncertainty", "artifact_ids": ["uncertainty_result"], "claim_ids": ["claim-2"]},
                {"exhibit_id": "budget_impact", "label": "Budget impact", "artifact_ids": ["budget_impact_result"], "claim_ids": ["claim-4", "claim-5", "claim-6", "claim-7"]}
            ],
            "claim_evidence_ledger": claims,
            "limitations": ["This package proves structural traceability only."]
        });
        std::fs::write(
            root.join(REPRODUCIBILITY_PACKAGE_PATH),
            serde_json::to_vec(&package).unwrap(),
        )
        .unwrap();
        (root, identity)
    }

    #[test]
    fn complete_companion_is_natively_auditable() {
        let (root, identity) = fixture("complete");
        let audit = audit_reproducibility_package_for_identity(&root, &identity).unwrap();
        assert!(audit.complete, "{:?}", audit.errors);
        assert!(audit.release_companion_ready);
        assert_eq!(audit.artifact_count, 10);
        assert_eq!(audit.execution_count, 3);
        assert_eq!(audit.covered_claim_count, 7);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn current_runtime_and_bound_bytes_fail_closed() {
        let (root, mut identity) = fixture("drift");
        identity.python_version = "Python 9.9.9".into();
        let audit = audit_reproducibility_package_for_identity(&root, &identity).unwrap();
        assert!(!audit.complete);
        assert!(!audit.runtime_matches);

        std::fs::write(root.join("heor/results/base-case.json"), b"{}\n").unwrap();
        let audit = audit_reproducibility_package_for_identity(
            &root,
            &RuntimeIdentity {
                ai4heor_version: "0.1.16".into(),
                platform: "test-x86_64".into(),
                python_version: "Python 3.12.0".into(),
            },
        )
        .unwrap();
        assert!(!audit.complete);
        assert!(audit.errors.iter().any(|error| error.contains("report")));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn psm_replay_recipe_binds_all_method_inputs_and_joint_draws() {
        let binding_keys = [
            ("analysis_plan", "heor/analysis-plan.json"),
            (
                "partitioned_survival_plan",
                "heor/partitioned-survival-plan.json",
            ),
            (
                "survival_curve_materializations",
                "heor/survival-curve-materializations.json",
            ),
            (
                "treatment_effect_duration",
                "heor/treatment-effect-duration.json",
            ),
            (
                "cost_input_normalization",
                "heor/cost-input-normalization.json",
            ),
            ("utility_inputs", "heor/utility-inputs.json"),
            ("event_disutilities", "heor/event-disutilities.json"),
            ("uncertainty_plan", "heor/uncertainty-plan.json"),
            ("budget_impact_plan", "heor/budget-impact-plan.json"),
            (
                "partitioned_survival_result",
                "heor/results/partitioned-survival.json",
            ),
            ("uncertainty_result", "heor/results/uncertainty.json"),
            ("budget_impact_result", "heor/results/budget-impact.json"),
        ];
        let bindings = binding_keys
            .iter()
            .map(|(key, path)| {
                (
                    (*key).to_string(),
                    serde_json::json!({"path": path, "content_sha256": "a".repeat(64)}),
                )
            })
            .collect::<serde_json::Map<_, _>>();
        let report = serde_json::json!({"bindings": bindings});
        let loaded = HashMap::from([
            (
                "uncertainty_plan".into(),
                serde_json::json!({"schema_version": "0.14.0"}),
            ),
            (
                "partitioned_survival_result".into(),
                serde_json::json!({"engine_version": "0.15.0"}),
            ),
            (
                "uncertainty_result".into(),
                serde_json::json!({"engine_version": "0.15.0"}),
            ),
            (
                "budget_impact_result".into(),
                serde_json::json!({"engine_version": "0.15.0"}),
            ),
        ]);

        let recipes = expected_execution_manifest(&report, &loaded).unwrap();
        let base = recipes[0]["command"].as_array().unwrap();
        let uncertainty = recipes[1]["command"].as_array().unwrap();
        assert_eq!(
            recipes[0]["output_artifact_id"],
            "partitioned_survival_result"
        );
        assert!(base
            .iter()
            .any(|value| value == "--partitioned-survival-plan"));
        assert!(base.iter().any(|value| value == "--event-disutilities"));
        assert!(uncertainty
            .iter()
            .any(|value| value == "--joint-survival-uncertainty-manifest"));
        assert!(uncertainty
            .iter()
            .any(|value| value == "--joint-survival-draws"));
    }
}
