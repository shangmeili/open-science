//! Native audit for the optional isolated survHE MLE execution bundle.

use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::io::Read;
use std::path::{Component, Path, PathBuf};

const SCHEMA_VERSION: &str = "0.1.0";
const EVALUATOR: &str = "ai4heor-survival-crosscheck@0.2.0";
const JSON_CAP: u64 = 10 * 1024 * 1024;
const DATA_CAP: u64 = 256 * 1024 * 1024;
const MAX_ROWS: usize = 1_000_000;
const FAMILIES: &[&str] = &[
    "exponential",
    "weibull",
    "gompertz",
    "gamma",
    "generalized_gamma",
    "generalized_f",
    "lognormal",
    "loglogistic",
];

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SurvivalFitExecutionAudit {
    pub complete: bool,
    pub eligible_for_review: bool,
    pub status: String,
    pub execution_id: String,
    pub result_sha256: Option<String>,
    pub candidate_models: usize,
    pub converged_models: usize,
    pub cross_implementation_complete: bool,
    pub package_versions: HashMap<String, String>,
    pub errors: Vec<String>,
}

#[derive(Default)]
struct RequestFacts {
    execution_id: String,
    source_path: String,
    source_sha256: String,
    row_count: usize,
    event_count: usize,
    censor_count: usize,
    families: Vec<String>,
    times: Vec<f64>,
    tolerance: f64,
    output_directory: String,
    packages: HashMap<String, String>,
}

fn exact_fields(value: &serde_json::Value, fields: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == fields.len() && fields.iter().all(|field| object.contains_key(*field))
    })
}

fn text(value: Option<&serde_json::Value>) -> Option<&str> {
    value
        .and_then(serde_json::Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
}

fn finite(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite())
}

fn safe_id(value: &str) -> bool {
    let mut bytes = value.bytes();
    bytes.next().is_some_and(|byte| byte.is_ascii_lowercase())
        && value.len() <= 64
        && bytes.all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'_' | b'-')
        })
}

fn safe_column(value: &str) -> bool {
    let mut bytes = value.bytes();
    bytes.next().is_some_and(|byte| byte.is_ascii_alphabetic())
        && value.len() <= 64
        && bytes.all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn read_capped(path: &Path, cap: u64, label: &str) -> Result<Vec<u8>, String> {
    let metadata =
        std::fs::metadata(path).map_err(|error| format!("{label} unavailable: {error}"))?;
    if !metadata.is_file() || metadata.len() > cap {
        return Err(format!("{label} is not a bounded regular file"));
    }
    let mut file =
        std::fs::File::open(path).map_err(|error| format!("{label} unavailable: {error}"))?;
    let mut raw = Vec::with_capacity(metadata.len() as usize);
    file.read_to_end(&mut raw)
        .map_err(|error| format!("{label} unavailable: {error}"))?;
    Ok(raw)
}

fn resolve_file(workspace: &Path, relative: &str, label: &str) -> Result<PathBuf, String> {
    let path = Path::new(relative);
    if path.is_absolute()
        || path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(format!("{label} path must stay inside the workspace"));
    }
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let unresolved = root.join(path);
    if std::fs::symlink_metadata(&unresolved)
        .is_ok_and(|metadata| metadata.file_type().is_symlink())
    {
        return Err(format!("{label} must not be a symlink"));
    }
    let resolved = unresolved
        .canonicalize()
        .map_err(|error| format!("{label} unavailable: {error}"))?;
    if !resolved.starts_with(&root) || !resolved.is_file() {
        return Err(format!("{label} path must stay inside the workspace"));
    }
    Ok(resolved)
}

fn bound_file(
    workspace: &Path,
    path: Option<&serde_json::Value>,
    expected: Option<&serde_json::Value>,
    label: &str,
    cap: u64,
    errors: &mut Vec<String>,
) -> Option<(PathBuf, Vec<u8>)> {
    let Some(relative) = text(path) else {
        errors.push(format!("{label} requires a relative path"));
        return None;
    };
    let Some(expected) = expected
        .and_then(serde_json::Value::as_str)
        .filter(|value| is_sha256(value))
    else {
        errors.push(format!("{label} requires a lowercase SHA-256"));
        return None;
    };
    let resolved = match resolve_file(workspace, relative, label) {
        Ok(value) => value,
        Err(error) => {
            errors.push(error);
            return None;
        }
    };
    let raw = match read_capped(&resolved, cap, label) {
        Ok(value) => value,
        Err(error) => {
            errors.push(error);
            return None;
        }
    };
    if sha256(&raw) != expected {
        errors.push(format!("{label} SHA-256 does not match current bytes"));
        return None;
    }
    Some((resolved, raw))
}

fn json_object(raw: &[u8], label: &str, errors: &mut Vec<String>) -> Option<serde_json::Value> {
    match serde_json::from_slice::<serde_json::Value>(raw) {
        Ok(value) if value.is_object() => Some(value),
        Ok(_) => {
            errors.push(format!("{label} must contain a JSON object"));
            None
        }
        Err(error) => {
            errors.push(format!("{label} is invalid JSON: {error}"));
            None
        }
    }
}

fn string_map(value: Option<&serde_json::Value>) -> Option<HashMap<String, String>> {
    let object = value?.as_object()?;
    let mut result = HashMap::new();
    for (key, value) in object {
        let value = value.as_str()?.trim();
        if key.trim().is_empty() || value.is_empty() {
            return None;
        }
        result.insert(key.clone(), value.to_owned());
    }
    Some(result)
}

fn audit_csv(
    raw: &[u8],
    time_column: &str,
    event_column: &str,
    errors: &mut Vec<String>,
) -> (usize, usize, usize, f64) {
    let Ok(content) = std::str::from_utf8(raw) else {
        errors.push("source_data CSV must be UTF-8".into());
        return (0, 0, 0, 0.0);
    };
    let mut lines = content.lines();
    if lines.next() != Some(&format!("{time_column},{event_column}")) {
        errors.push("source_data CSV must contain exactly the declared columns in order".into());
        return (0, 0, 0, 0.0);
    }
    let mut rows = 0;
    let mut events = 0;
    let mut censors = 0;
    let mut maximum_time: f64 = 0.0;
    for (index, line) in lines.enumerate() {
        if rows >= MAX_ROWS {
            errors.push("source_data CSV exceeds 1,000,000 rows".into());
            break;
        }
        let parts: Vec<_> = line.split(',').collect();
        if parts.len() != 2
            || parts
                .iter()
                .any(|part| part.is_empty() || *part != part.trim())
        {
            errors.push(format!(
                "source_data row {} must contain exactly two unquoted values",
                index + 2
            ));
            continue;
        }
        rows += 1;
        match parts[0].parse::<f64>() {
            Ok(value) if value.is_finite() && value > 0.0 => maximum_time = maximum_time.max(value),
            _ => errors.push(format!(
                "source_data row {} time must be finite and positive",
                index + 2
            )),
        }
        match parts[1] {
            "1" => events += 1,
            "0" => censors += 1,
            _ => errors.push(format!(
                "source_data row {} event must be exactly 0 or 1",
                index + 2
            )),
        }
    }
    if rows < 2 || events == 0 {
        errors.push("source_data CSV requires at least two rows and one event".into());
    }
    (rows, events, censors, maximum_time)
}

fn audit_request(
    workspace: &Path,
    request: &serde_json::Value,
    errors: &mut Vec<String>,
) -> RequestFacts {
    let mut facts = RequestFacts::default();
    if !exact_fields(
        request,
        &[
            "schema_version",
            "execution_id",
            "status",
            "analysis_target",
            "source_data",
            "fit",
            "runtime",
            "output",
            "limitations",
            "human_gate",
        ],
    ) {
        errors.push("execution request fields are not the exact contract".into());
        return facts;
    }
    if request
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some(SCHEMA_VERSION)
        || request.get("status").and_then(serde_json::Value::as_str) != Some("ready_for_execution")
    {
        errors.push("execution request schema or status is invalid".into());
    }
    facts.execution_id = text(request.get("execution_id"))
        .unwrap_or_default()
        .to_owned();
    if !safe_id(&facts.execution_id) {
        errors.push("execution_id must be a safe lowercase identifier".into());
    }
    let target = request
        .get("analysis_target")
        .unwrap_or(&serde_json::Value::Null);
    if !exact_fields(target, &["analysis_id", "path"])
        || text(target.get("analysis_id")).is_none()
        || text(target.get("path")).is_none()
    {
        errors.push("analysis_target is invalid".into());
    }

    let source = request
        .get("source_data")
        .unwrap_or(&serde_json::Value::Null);
    if !exact_fields(
        source,
        &[
            "classification",
            "execution_boundary",
            "format",
            "path",
            "sha256",
            "columns",
            "row_count",
            "event_count",
            "censor_count",
            "contains_direct_identifiers",
            "missing_policy",
            "additional_columns",
        ],
    ) {
        errors.push("source_data fields are invalid".into());
    } else {
        if !matches!(
            source
                .get("classification")
                .and_then(serde_json::Value::as_str),
            Some("public" | "non_sensitive" | "restricted")
        ) || source
            .get("execution_boundary")
            .and_then(serde_json::Value::as_str)
            != Some("local_only")
            || source.get("format").and_then(serde_json::Value::as_str) != Some("csv")
            || source
                .get("contains_direct_identifiers")
                .and_then(serde_json::Value::as_bool)
                != Some(false)
            || source
                .get("missing_policy")
                .and_then(serde_json::Value::as_str)
                != Some("reject")
            || source
                .get("additional_columns")
                .and_then(serde_json::Value::as_str)
                != Some("reject")
        {
            errors.push("source_data boundary is not admitted".into());
        }
        let columns = source.get("columns").unwrap_or(&serde_json::Value::Null);
        let time_column = text(columns.get("time")).unwrap_or_default();
        let event_column = text(columns.get("event")).unwrap_or_default();
        if !exact_fields(columns, &["time", "event"])
            || !safe_column(time_column)
            || !safe_column(event_column)
            || time_column == event_column
        {
            errors.push("source_data.columns are invalid".into());
        }
        facts.source_path = text(source.get("path")).unwrap_or_default().to_owned();
        facts.source_sha256 = text(source.get("sha256")).unwrap_or_default().to_owned();
        if let Some((_, raw)) = bound_file(
            workspace,
            source.get("path"),
            source.get("sha256"),
            "source_data",
            DATA_CAP,
            errors,
        ) {
            let (rows, events, censors, maximum_time) =
                audit_csv(&raw, time_column, event_column, errors);
            facts.row_count = rows;
            facts.event_count = events;
            facts.censor_count = censors;
            for (field, actual) in [
                ("row_count", rows),
                ("event_count", events),
                ("censor_count", censors),
            ] {
                if source.get(field).and_then(serde_json::Value::as_u64) != Some(actual as u64) {
                    errors.push(format!("source_data.{field} does not match current CSV"));
                }
            }
            let observed = finite(request.pointer("/fit/observed_follow_up"));
            if !observed.is_some_and(|value| (value - maximum_time).abs() <= 1e-12) {
                errors.push("observed_follow_up must equal maximum source time".into());
            }
        }
    }

    let fit = request.get("fit").unwrap_or(&serde_json::Value::Null);
    if !exact_fields(
        fit,
        &[
            "method",
            "formula",
            "candidate_models",
            "prediction_times",
            "observed_follow_up",
            "model_horizon",
            "cross_implementation_tolerance",
        ],
    ) || fit.get("method").and_then(serde_json::Value::as_str) != Some("maximum_likelihood")
        || fit.get("formula").and_then(serde_json::Value::as_str) != Some("intercept_only")
    {
        errors.push("fit fields or admitted method are invalid".into());
    } else {
        if let Some(candidates) = fit
            .get("candidate_models")
            .and_then(serde_json::Value::as_array)
        {
            if !(2..=8).contains(&candidates.len()) {
                errors.push("candidate_models must contain 2-8 entries".into());
            }
            for (index, candidate) in candidates.iter().enumerate() {
                let family = text(candidate.get("family"));
                if !exact_fields(candidate, &["family", "rationale"])
                    || !family.is_some_and(|value| FAMILIES.contains(&value))
                    || text(candidate.get("rationale")).is_none()
                {
                    errors.push(format!("candidate_models[{index}] is invalid"));
                } else {
                    facts.families.push(family.unwrap().to_owned());
                }
            }
            if facts.families.iter().collect::<HashSet<_>>().len() != facts.families.len()
                || !["exponential", "weibull"]
                    .iter()
                    .all(|family| facts.families.iter().any(|value| value == family))
            {
                errors.push(
                    "candidate_models must be unique and include exponential and weibull".into(),
                );
            }
        } else {
            errors.push("candidate_models must be a list".into());
        }
        if let Some(times) = fit
            .get("prediction_times")
            .and_then(serde_json::Value::as_array)
        {
            facts.times = times
                .iter()
                .filter_map(|value| finite(Some(value)))
                .collect();
            if !(3..=256).contains(&times.len())
                || facts.times.len() != times.len()
                || facts.times.first() != Some(&0.0)
                || facts.times.windows(2).any(|pair| pair[1] <= pair[0])
            {
                errors.push("prediction_times must start at zero and strictly increase".into());
            }
        }
        let observed = finite(fit.get("observed_follow_up"));
        let horizon = finite(fit.get("model_horizon"));
        if !matches!((observed, horizon), (Some(observed), Some(horizon)) if observed > 0.0 && horizon > observed)
        {
            errors.push("model_horizon must exceed positive observed_follow_up".into());
        } else if facts.times.last() != horizon.as_ref() {
            errors.push("prediction_times must end at model_horizon".into());
        }
        facts.tolerance = finite(fit.get("cross_implementation_tolerance")).unwrap_or(f64::NAN);
        if !facts.tolerance.is_finite() || !(1e-12..=1e-6).contains(&facts.tolerance) {
            errors.push("cross_implementation_tolerance is outside the admitted range".into());
        }
    }

    let runtime = request.get("runtime").unwrap_or(&serde_json::Value::Null);
    facts.packages = string_map(runtime.get("expected_packages")).unwrap_or_default();
    if !exact_fields(runtime, &["expected_packages"])
        || facts.packages.len() != 3
        || !["survHE", "flexsurv", "survival"]
            .iter()
            .all(|name| facts.packages.contains_key(*name))
    {
        errors.push(
            "runtime.expected_packages must contain exactly the three required packages".into(),
        );
    }
    let output = request.get("output").unwrap_or(&serde_json::Value::Null);
    facts.output_directory = text(output.get("directory")).unwrap_or_default().to_owned();
    if !exact_fields(output, &["directory", "overwrite_policy"])
        || facts.output_directory != format!("heor/survival-fit-executions/{}", facts.execution_id)
        || output
            .get("overwrite_policy")
            .and_then(serde_json::Value::as_str)
            != Some("fail_if_exists")
    {
        errors.push("output contract is invalid".into());
    }
    if !request
        .get("limitations")
        .and_then(serde_json::Value::as_array)
        .is_some_and(|items| {
            !items.is_empty() && items.iter().all(|item| text(Some(item)).is_some())
        })
    {
        errors.push("request limitations must be non-empty".into());
    }
    if request.get("human_gate")
        != Some(&serde_json::json!({
            "state": "awaiting_execution_authorization",
            "required_action": "approve_local_survival_fit_command"
        }))
    {
        errors.push("request Human gate is invalid".into());
    }
    facts
}

fn parameter_map(model: &serde_json::Value) -> Option<HashMap<String, f64>> {
    let parameters = model.get("parameters")?.as_array()?;
    let mut result = HashMap::new();
    for parameter in parameters {
        if !exact_fields(parameter, &["name", "estimate"]) {
            return None;
        }
        let name = text(parameter.get("name"))?;
        let estimate = finite(parameter.get("estimate"))?;
        if result.insert(name.to_owned(), estimate).is_some() {
            return None;
        }
    }
    Some(result)
}

fn expected_curve(
    family: &str,
    parameters: &HashMap<String, f64>,
    time: f64,
) -> Result<(f64, Option<f64>), String> {
    crate::heor_parametric_survival::curve(family, parameters, time)
}

fn expected_parameterization(family: &str) -> Option<&'static str> {
    match family {
        "exponential" => Some("exponential_rate"),
        "weibull" => Some("weibull_shape_scale_aft"),
        "gompertz" => Some("gompertz_shape_rate"),
        "gamma" => Some("gamma_shape_rate"),
        "generalized_gamma" => Some("generalized_gamma_prentice"),
        "generalized_f" => Some("generalized_f_prentice"),
        "lognormal" => Some("lognormal_meanlog_sdlog"),
        "loglogistic" => Some("loglogistic_shape_scale"),
        _ => None,
    }
}

pub(crate) fn audit_survival_fit_execution_path(
    workspace: &Path,
    manifest_relative: &str,
) -> SurvivalFitExecutionAudit {
    let mut audit = SurvivalFitExecutionAudit {
        complete: false,
        eligible_for_review: false,
        status: "incomplete".into(),
        execution_id: String::new(),
        result_sha256: None,
        candidate_models: 0,
        converged_models: 0,
        cross_implementation_complete: false,
        package_versions: HashMap::new(),
        errors: Vec::new(),
    };
    let manifest_path = match resolve_file(workspace, manifest_relative, "result manifest") {
        Ok(value) => value,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let manifest_raw = match read_capped(&manifest_path, JSON_CAP, "result manifest") {
        Ok(value) => value,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    audit.result_sha256 = Some(sha256(&manifest_raw));
    let Some(manifest) = json_object(&manifest_raw, "result manifest", &mut audit.errors) else {
        return audit;
    };
    if !exact_fields(
        &manifest,
        &[
            "schema_version",
            "execution_id",
            "status",
            "request",
            "source_data",
            "runtime",
            "model_order",
            "models",
            "diagnostics",
            "cross_implementation",
            "limitations",
            "human_gate",
        ],
    ) {
        audit
            .errors
            .push("result fields are not the exact contract".into());
        return audit;
    }
    if manifest
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some(SCHEMA_VERSION)
    {
        audit
            .errors
            .push("result schema_version is unsupported".into());
    }
    audit.execution_id = text(manifest.get("execution_id"))
        .unwrap_or_default()
        .to_owned();
    audit.status = text(manifest.get("status"))
        .unwrap_or("incomplete")
        .to_owned();
    if !safe_id(&audit.execution_id)
        || !matches!(
            audit.status.as_str(),
            "execution_complete"
                | "execution_complete_with_model_failures"
                | "cross_implementation_failed"
        )
    {
        audit
            .errors
            .push("result identity or status is invalid".into());
    }

    let request_binding = manifest.get("request").unwrap_or(&serde_json::Value::Null);
    let mut request_facts = RequestFacts::default();
    if !exact_fields(request_binding, &["path", "sha256"]) {
        audit
            .errors
            .push("request binding fields are invalid".into());
    } else if let Some((_, request_raw)) = bound_file(
        workspace,
        request_binding.get("path"),
        request_binding.get("sha256"),
        "request",
        JSON_CAP,
        &mut audit.errors,
    ) {
        if let Some(request) = json_object(&request_raw, "request", &mut audit.errors) {
            request_facts = audit_request(workspace, &request, &mut audit.errors);
        }
    }
    if audit.execution_id != request_facts.execution_id {
        audit
            .errors
            .push("result execution_id does not match request".into());
    }

    let source = manifest
        .get("source_data")
        .unwrap_or(&serde_json::Value::Null);
    if !exact_fields(
        source,
        &["path", "sha256", "row_count", "event_count", "censor_count"],
    ) || text(source.get("path")) != Some(&request_facts.source_path)
        || text(source.get("sha256")) != Some(&request_facts.source_sha256)
        || source.get("row_count").and_then(serde_json::Value::as_u64)
            != Some(request_facts.row_count as u64)
        || source
            .get("event_count")
            .and_then(serde_json::Value::as_u64)
            != Some(request_facts.event_count as u64)
        || source
            .get("censor_count")
            .and_then(serde_json::Value::as_u64)
            != Some(request_facts.censor_count as u64)
    {
        audit
            .errors
            .push("result source_data does not exactly copy request facts".into());
    }

    let runtime = manifest.get("runtime").unwrap_or(&serde_json::Value::Null);
    if !exact_fields(
        runtime,
        &[
            "backend",
            "method",
            "r_version",
            "rscript_sha256",
            "package_versions",
            "adapter_path",
            "adapter_sha256",
            "session_info_path",
            "session_info_sha256",
            "execution_log_path",
            "execution_log_sha256",
        ],
    ) || runtime.get("backend").and_then(serde_json::Value::as_str) != Some("survHE")
        || runtime.get("method").and_then(serde_json::Value::as_str) != Some("maximum_likelihood")
        || text(runtime.get("r_version")).is_none()
        || !text(runtime.get("rscript_sha256")).is_some_and(is_sha256)
    {
        audit
            .errors
            .push("runtime fields or backend identity are invalid".into());
    } else {
        audit.package_versions = string_map(runtime.get("package_versions")).unwrap_or_default();
        if audit.package_versions != request_facts.packages {
            audit
                .errors
                .push("runtime package versions do not match request".into());
        }
        for (path, hash, label) in [
            ("adapter_path", "adapter_sha256", "adapter"),
            ("session_info_path", "session_info_sha256", "session info"),
            (
                "execution_log_path",
                "execution_log_sha256",
                "execution log",
            ),
        ] {
            bound_file(
                workspace,
                runtime.get(path),
                runtime.get(hash),
                label,
                DATA_CAP,
                &mut audit.errors,
            );
        }
    }

    let model_order: Vec<String> = manifest
        .get("model_order")
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(|value| value.as_str().map(str::to_owned))
                .collect()
        })
        .unwrap_or_default();
    if model_order != request_facts.families {
        audit
            .errors
            .push("model_order does not match request".into());
    }
    audit.candidate_models = model_order.len();
    let mut models = HashMap::<String, serde_json::Value>::new();
    let bindings = manifest.get("models").and_then(serde_json::Value::as_array);
    if !bindings.is_some_and(|values| values.len() == model_order.len()) {
        audit
            .errors
            .push("models must bind every requested family".into());
    } else {
        for (index, binding) in bindings.unwrap().iter().enumerate() {
            let family = text(binding.get("family")).unwrap_or_default();
            if !exact_fields(binding, &["family", "status", "path", "sha256"])
                || model_order.get(index).map(String::as_str) != Some(family)
            {
                audit
                    .errors
                    .push(format!("models[{index}] binding is invalid"));
                continue;
            }
            let Some((_, raw)) = bound_file(
                workspace,
                binding.get("path"),
                binding.get("sha256"),
                &format!("models[{index}]"),
                JSON_CAP,
                &mut audit.errors,
            ) else {
                continue;
            };
            let Some(model) = json_object(&raw, &format!("models[{index}]"), &mut audit.errors)
            else {
                continue;
            };
            if !exact_fields(
                &model,
                &[
                    "schema_version",
                    "family",
                    "status",
                    "fit_statistics",
                    "parameterization",
                    "parameters",
                    "landmarks",
                    "warnings",
                ],
            ) || model
                .get("schema_version")
                .and_then(serde_json::Value::as_str)
                != Some(SCHEMA_VERSION)
                || text(model.get("family")) != Some(family)
                || model.get("status") != binding.get("status")
            {
                audit
                    .errors
                    .push(format!("models[{index}] contents are invalid"));
                continue;
            }
            let status = text(model.get("status")).unwrap_or_default();
            if status == "failed" {
                if model.get("fit_statistics")
                    != Some(&serde_json::json!({"aic": null, "bic": null, "log_likelihood": null}))
                    || !model
                        .get("parameters")
                        .and_then(serde_json::Value::as_array)
                        .is_some_and(Vec::is_empty)
                    || !model
                        .get("landmarks")
                        .and_then(serde_json::Value::as_array)
                        .is_some_and(Vec::is_empty)
                {
                    audit
                        .errors
                        .push(format!("models[{index}] failed output is invalid"));
                }
                models.insert(family.to_owned(), model);
                continue;
            }
            if status != "converged" {
                audit
                    .errors
                    .push(format!("models[{index}] status is invalid"));
                continue;
            }
            audit.converged_models += 1;
            let statistics = model
                .get("fit_statistics")
                .unwrap_or(&serde_json::Value::Null);
            if !exact_fields(statistics, &["aic", "bic", "log_likelihood"])
                || ["aic", "bic", "log_likelihood"]
                    .iter()
                    .any(|field| finite(statistics.get(*field)).is_none())
                || text(model.get("parameterization")) != expected_parameterization(family)
            {
                audit
                    .errors
                    .push(format!("models[{index}] fit output is invalid"));
            }
            let parameters = parameter_map(&model);
            if parameters.is_none() {
                audit
                    .errors
                    .push(format!("models[{index}] parameters are invalid"));
            }
            let landmarks = model.get("landmarks").and_then(serde_json::Value::as_array);
            if !landmarks.is_some_and(|values| values.len() == request_facts.times.len()) {
                audit
                    .errors
                    .push(format!("models[{index}] landmarks do not cover request"));
            } else {
                let mut previous_survival = 1.0;
                for (landmark_index, (landmark, expected_time)) in landmarks
                    .unwrap()
                    .iter()
                    .zip(request_facts.times.iter())
                    .enumerate()
                {
                    let time = finite(landmark.get("time"));
                    let survival = finite(landmark.get("survival"));
                    let hazard = finite(landmark.get("hazard"));
                    if !exact_fields(landmark, &["time", "survival", "hazard"])
                        || !time.is_some_and(|value| (value - expected_time).abs() <= 1e-12)
                        || !survival.is_some_and(|value| {
                            (0.0..=1.0).contains(&value) && value <= previous_survival + 1e-12
                        })
                        || (*expected_time == 0.0
                            && !landmark
                                .get("hazard")
                                .is_some_and(serde_json::Value::is_null))
                        || (*expected_time > 0.0 && !hazard.is_some_and(|value| value >= 0.0))
                    {
                        audit.errors.push(format!(
                            "models[{index}].landmarks[{landmark_index}] is invalid"
                        ));
                    }
                    if let Some(value) = survival {
                        previous_survival = value;
                    }
                }
                if let Some(parameters) = parameters {
                    for landmark in landmarks.unwrap() {
                        let time = finite(landmark.get("time")).unwrap_or(f64::NAN);
                        let survival = finite(landmark.get("survival")).unwrap_or(f64::NAN);
                        let hazard = finite(landmark.get("hazard"));
                        match expected_curve(family, &parameters, time) {
                            Ok((expected_survival, expected_hazard))
                                if (survival - expected_survival).abs()
                                    <= request_facts.tolerance
                                    && expected_hazard.is_none_or(|expected| {
                                        hazard.is_some_and(|actual| {
                                            (actual - expected).abs() <= request_facts.tolerance
                                        })
                                    }) => {}
                            Ok(_) => audit.errors.push(format!(
                                "models[{index}] exceeds independent cross-check tolerance"
                            )),
                            Err(error) => audit.errors.push(format!(
                                "models[{index}] cannot be independently evaluated: {error}"
                            )),
                        }
                    }
                }
            }
            models.insert(family.to_owned(), model);
        }
    }

    let diagnostics = manifest
        .get("diagnostics")
        .unwrap_or(&serde_json::Value::Null);
    if !exact_fields(
        diagnostics,
        &[
            "km_overlay_path",
            "km_overlay_sha256",
            "log_cumulative_hazard_path",
            "log_cumulative_hazard_sha256",
            "hazard_plot_path",
            "hazard_plot_sha256",
        ],
    ) {
        audit.errors.push("diagnostics fields are invalid".into());
    } else {
        for (path, hash, label) in [
            ("km_overlay_path", "km_overlay_sha256", "KM overlay"),
            (
                "log_cumulative_hazard_path",
                "log_cumulative_hazard_sha256",
                "log-cumulative-hazard plot",
            ),
            ("hazard_plot_path", "hazard_plot_sha256", "hazard plot"),
        ] {
            bound_file(
                workspace,
                diagnostics.get(path),
                diagnostics.get(hash),
                label,
                DATA_CAP,
                &mut audit.errors,
            );
        }
    }

    let cross = manifest
        .get("cross_implementation")
        .unwrap_or(&serde_json::Value::Null);
    let mut required_passed = HashSet::new();
    if !exact_fields(cross, &["evaluator", "tolerance", "checks", "complete"])
        || cross.get("evaluator").and_then(serde_json::Value::as_str) != Some(EVALUATOR)
        || !finite(cross.get("tolerance")).is_some_and(|value| value == request_facts.tolerance)
    {
        audit
            .errors
            .push("cross_implementation fields are invalid".into());
    } else if let Some(checks) = cross.get("checks").and_then(serde_json::Value::as_array) {
        if checks.len() != model_order.len() {
            audit
                .errors
                .push("cross_implementation checks are incomplete".into());
        }
        for (index, (check, family)) in checks.iter().zip(model_order.iter()).enumerate() {
            let model_status = models
                .get(family)
                .and_then(|model| text(model.get("status")))
                .unwrap_or_default();
            let expected_status = if model_status == "failed" {
                "fit_failed"
            } else {
                "passed"
            };
            let observed_status = text(check.get("status")).unwrap_or_default();
            let admitted_status = observed_status == expected_status
                || (expected_status == "passed" && observed_status == "failed");
            if !exact_fields(
                check,
                &[
                    "family",
                    "status",
                    "max_abs_survival_error",
                    "max_abs_hazard_error",
                ],
            ) || text(check.get("family")) != Some(family)
                || !admitted_status
            {
                audit
                    .errors
                    .push(format!("cross_implementation.checks[{index}] is invalid"));
                continue;
            }
            if observed_status == "passed" {
                let survival_error = finite(check.get("max_abs_survival_error"));
                let hazard_error = finite(check.get("max_abs_hazard_error"));
                if !survival_error.is_some_and(|value| value <= request_facts.tolerance)
                    || !hazard_error.is_some_and(|value| value <= request_facts.tolerance)
                {
                    audit.errors.push(format!(
                        "cross_implementation.checks[{index}] exceeds tolerance"
                    ));
                } else {
                    required_passed.insert(family.clone());
                }
            } else {
                let survival_error = check.get("max_abs_survival_error");
                let hazard_error = check.get("max_abs_hazard_error");
                let both_null = survival_error.is_some_and(serde_json::Value::is_null)
                    && hazard_error.is_some_and(serde_json::Value::is_null);
                let both_finite =
                    finite(survival_error).is_some() && finite(hazard_error).is_some();
                if (observed_status == "fit_failed" && !both_null)
                    || (observed_status == "failed" && !both_null && !both_finite)
                {
                    audit.errors.push(format!(
                        "cross_implementation.checks[{index}] failed errors are invalid"
                    ));
                }
            }
        }
    } else {
        audit
            .errors
            .push("cross_implementation checks must be a list".into());
    }
    audit.cross_implementation_complete = ["exponential", "weibull"]
        .iter()
        .all(|family| required_passed.contains(*family))
        && model_order.iter().all(|family| {
            models
                .get(family)
                .and_then(|model| text(model.get("status")))
                == Some("failed")
                || required_passed.contains(family)
        });
    if cross.get("complete").and_then(serde_json::Value::as_bool)
        != Some(audit.cross_implementation_complete)
    {
        audit
            .errors
            .push("cross_implementation.complete is incorrect".into());
    }
    let failed_models = model_order.len().saturating_sub(audit.converged_models);
    let expected_status = if !audit.cross_implementation_complete {
        "cross_implementation_failed"
    } else if failed_models == 0 {
        "execution_complete"
    } else {
        "execution_complete_with_model_failures"
    };
    if audit.status != expected_status {
        audit
            .errors
            .push("result status does not match model convergence".into());
    }
    if !manifest
        .get("limitations")
        .and_then(serde_json::Value::as_array)
        .is_some_and(|items| {
            !items.is_empty() && items.iter().all(|item| text(Some(item)).is_some())
        })
        || manifest.get("human_gate")
            != Some(&serde_json::json!({
                "state": "awaiting_human_review",
                "required_action": "review_survival_extrapolation"
            }))
    {
        audit
            .errors
            .push("result limitations or Human gate are invalid".into());
    }
    audit.complete = audit.errors.is_empty();
    audit.eligible_for_review =
        audit.complete && audit.cross_implementation_complete && audit.converged_models >= 2;
    audit
}

pub(crate) fn audit_survival_fit_execution_for_review(
    workspace: &Path,
    manifest_relative: &str,
    review: &serde_json::Value,
) -> (SurvivalFitExecutionAudit, Vec<String>) {
    let audit = audit_survival_fit_execution_path(workspace, manifest_relative);
    let mut errors = Vec::new();
    if !audit.complete || !audit.eligible_for_review {
        errors.extend(
            audit
                .errors
                .iter()
                .map(|error| format!("local execution: {error}")),
        );
        if audit.complete && !audit.eligible_for_review {
            errors.push("local execution is not eligible for survival review".into());
        }
        return (audit, errors);
    }
    let manifest = resolve_file(workspace, manifest_relative, "result manifest")
        .and_then(|path| read_capped(&path, JSON_CAP, "result manifest"))
        .ok()
        .and_then(|raw| serde_json::from_slice::<serde_json::Value>(&raw).ok());
    let Some(manifest) = manifest else {
        errors.push("local execution manifest cannot be compared with review".into());
        return (audit, errors);
    };
    let request_relative = text(manifest.pointer("/request/path")).unwrap_or_default();
    let request = resolve_file(workspace, request_relative, "request")
        .and_then(|path| read_capped(&path, JSON_CAP, "request"))
        .ok()
        .and_then(|raw| serde_json::from_slice::<serde_json::Value>(&raw).ok());
    let Some(request) = request else {
        errors.push("local execution request cannot be compared with review".into());
        return (audit, errors);
    };

    if review.get("analysis_target") != request.get("analysis_target") {
        errors.push("review analysis_target does not match local execution request".into());
    }
    for field in ["observed_follow_up", "model_horizon"] {
        if review.pointer(&format!("/context/{field}")) != request.pointer(&format!("/fit/{field}"))
        {
            errors.push(format!(
                "review context.{field} does not match local execution request"
            ));
        }
    }
    if review.pointer("/source_data/classification")
        != request.pointer("/source_data/classification")
        || review.pointer("/source_data/time_variable")
            != request.pointer("/source_data/columns/time")
    {
        errors.push("review source facts do not match local execution request".into());
    }
    let requested_families = request
        .pointer("/fit/candidate_models")
        .and_then(serde_json::Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.get("family").cloned())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let reviewed_families = review
        .pointer("/pre_specification/candidate_models")
        .and_then(serde_json::Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.get("family").cloned())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    if requested_families != reviewed_families {
        errors.push("review candidate order does not match local execution request".into());
    }

    let runtime = manifest.get("runtime").unwrap_or(&serde_json::Value::Null);
    let expected_execution = serde_json::json!({
        "backend": "survHE",
        "environment": "ai4heor_isolated_local_mle",
        "r_version": runtime.get("r_version").cloned().unwrap_or(serde_json::Value::Null),
        "package_versions": runtime.get("package_versions").cloned().unwrap_or(serde_json::Value::Null),
        "command_path": runtime.get("adapter_path").cloned().unwrap_or(serde_json::Value::Null),
        "command_sha256": runtime.get("adapter_sha256").cloned().unwrap_or(serde_json::Value::Null),
        "session_info_path": runtime.get("session_info_path").cloned().unwrap_or(serde_json::Value::Null),
        "session_info_sha256": runtime.get("session_info_sha256").cloned().unwrap_or(serde_json::Value::Null)
    });
    if review.get("execution") != Some(&expected_execution) {
        errors.push("review execution fields do not exactly match local execution bundle".into());
    }

    let mut expected_models = Vec::new();
    if let Some(bindings) = manifest.get("models").and_then(serde_json::Value::as_array) {
        for binding in bindings {
            let relative = text(binding.get("path")).unwrap_or_default();
            let model = resolve_file(workspace, relative, "model")
                .and_then(|path| read_capped(&path, JSON_CAP, "model"))
                .ok()
                .and_then(|raw| serde_json::from_slice::<serde_json::Value>(&raw).ok());
            let Some(model) = model else {
                errors.push("local execution model cannot be compared with review".into());
                continue;
            };
            let statistics = model
                .get("fit_statistics")
                .unwrap_or(&serde_json::Value::Null);
            expected_models.push(serde_json::json!({
                "family": binding.get("family").cloned().unwrap_or(serde_json::Value::Null),
                "status": binding.get("status").cloned().unwrap_or(serde_json::Value::Null),
                "aic": statistics.get("aic").cloned().unwrap_or(serde_json::Value::Null),
                "bic": statistics.get("bic").cloned().unwrap_or(serde_json::Value::Null),
                "log_likelihood": statistics.get("log_likelihood").cloned().unwrap_or(serde_json::Value::Null),
                "parameterization": model.get("parameterization").cloned().unwrap_or(serde_json::Value::Null),
                "fit_output_path": binding.get("path").cloned().unwrap_or(serde_json::Value::Null),
                "fit_output_sha256": binding.get("sha256").cloned().unwrap_or(serde_json::Value::Null),
                "landmarks": model.get("landmarks").cloned().unwrap_or(serde_json::Value::Null),
                "warnings": model.get("warnings").cloned().unwrap_or(serde_json::Value::Null)
            }));
        }
    }
    if review.get("models") != Some(&serde_json::Value::Array(expected_models)) {
        errors.push("review models do not exactly reproduce local execution outputs".into());
    }
    for field in [
        "km_overlay_path",
        "km_overlay_sha256",
        "log_cumulative_hazard_path",
        "log_cumulative_hazard_sha256",
        "hazard_plot_path",
        "hazard_plot_sha256",
    ] {
        if review.pointer(&format!("/diagnostics/{field}"))
            != manifest.pointer(&format!("/diagnostics/{field}"))
        {
            errors.push(format!(
                "review diagnostics.{field} does not match local execution bundle"
            ));
        }
    }
    (audit, errors)
}

#[tauri::command]
pub fn audit_heor_survival_fit_execution(
    app: tauri::AppHandle,
    result_path: String,
) -> Result<SurvivalFitExecutionAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    Ok(audit_survival_fit_execution_path(&workspace, &result_path))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn workspace() -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("ai4heor-survhe-{suffix}"));
        fs::create_dir_all(&root).unwrap();
        root
    }

    fn write(root: &Path, relative: &str, raw: &[u8]) -> String {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, raw).unwrap();
        sha256(raw)
    }

    fn write_json(root: &Path, relative: &str, value: &serde_json::Value) -> String {
        let mut raw = serde_json::to_vec_pretty(value).unwrap();
        raw.push(b'\n');
        write(root, relative, &raw)
    }

    fn model(family: &str, parameters: serde_json::Value) -> serde_json::Value {
        let values = parameters
            .as_array()
            .unwrap()
            .iter()
            .map(|value| {
                (
                    value["name"].as_str().unwrap().to_owned(),
                    value["estimate"].as_f64().unwrap(),
                )
            })
            .collect::<HashMap<_, _>>();
        let landmarks = [0.0, 1.0, 3.0, 5.0]
            .into_iter()
            .map(|time| {
                let (survival, hazard) = expected_curve(family, &values, time).unwrap();
                serde_json::json!({"time": time, "survival": survival, "hazard": hazard})
            })
            .collect::<Vec<_>>();
        serde_json::json!({
            "schema_version": "0.1.0",
            "family": family,
            "status": "converged",
            "fit_statistics": {"aic": 10.0, "bic": 12.0, "log_likelihood": -4.0},
            "parameterization": expected_parameterization(family).unwrap(),
            "parameters": parameters,
            "landmarks": landmarks,
            "warnings": []
        })
    }

    fn fixture(root: &Path) -> (String, serde_json::Value) {
        let source_raw = b"time,event\n0.5,1\n1,0\n2,1\n3,0\n";
        let source_hash = write(root, "data/survival.csv", source_raw);
        let request_path = "heor/survival-fit-requests/os-control.json";
        let request = serde_json::json!({
            "schema_version": "0.1.0",
            "execution_id": "os-control",
            "status": "ready_for_execution",
            "analysis_target": {"analysis_id": "survival-analysis", "path": "strategies.comparator.transition_schedule"},
            "source_data": {
                "classification": "restricted", "execution_boundary": "local_only", "format": "csv",
                "path": "data/survival.csv", "sha256": source_hash,
                "columns": {"time": "time", "event": "event"},
                "row_count": 4, "event_count": 2, "censor_count": 2,
                "contains_direct_identifiers": false, "missing_policy": "reject", "additional_columns": "reject"
            },
            "fit": {
                "method": "maximum_likelihood", "formula": "intercept_only",
                "candidate_models": [
                    {"family": "exponential", "rationale": "Constant hazard reference."},
                    {"family": "weibull", "rationale": "Monotone hazard alternative."}
                ],
                "prediction_times": [0.0, 1.0, 3.0, 5.0], "observed_follow_up": 3.0,
                "model_horizon": 5.0, "cross_implementation_tolerance": 1e-8
            },
            "runtime": {"expected_packages": {"survHE": "2.0.51", "flexsurv": "2.3.2", "survival": "3.8-3"}},
            "output": {"directory": "heor/survival-fit-executions/os-control", "overwrite_policy": "fail_if_exists"},
            "limitations": ["Clinical validity remains a Human-review question."],
            "human_gate": {"state": "awaiting_execution_authorization", "required_action": "approve_local_survival_fit_command"}
        });
        let request_hash = write_json(root, request_path, &request);
        let base = "heor/survival-fit-executions/os-control";
        let exp_path = format!("{base}/models/exponential.json");
        let wei_path = format!("{base}/models/weibull.json");
        let exp_hash = write_json(
            root,
            &exp_path,
            &model(
                "exponential",
                serde_json::json!([
                    {"name": "rate", "estimate": 0.2}
                ]),
            ),
        );
        let wei_hash = write_json(
            root,
            &wei_path,
            &model(
                "weibull",
                serde_json::json!([
                    {"name": "shape", "estimate": 1.5}, {"name": "scale", "estimate": 4.0}
                ]),
            ),
        );
        let adapter_hash = write(
            root,
            &format!("{base}/survhe_mle_adapter.R"),
            b"fixed adapter\n",
        );
        let session_hash = write(root, &format!("{base}/session-info.txt"), b"R session\n");
        let log_hash = write(root, &format!("{base}/execution.log"), b"exit_code: 0\n");
        let km_hash = write(root, &format!("{base}/km-overlay.png"), b"km");
        let lch_hash = write(root, &format!("{base}/log-cumulative-hazard.png"), b"lch");
        let hazard_hash = write(root, &format!("{base}/hazard.png"), b"hazard");
        let manifest = serde_json::json!({
            "schema_version": "0.1.0", "execution_id": "os-control", "status": "execution_complete",
            "request": {"path": request_path, "sha256": request_hash},
            "source_data": {"path": "data/survival.csv", "sha256": source_hash, "row_count": 4, "event_count": 2, "censor_count": 2},
            "runtime": {
                "backend": "survHE", "method": "maximum_likelihood", "r_version": "R version 4.5.2",
                "rscript_sha256": "a".repeat(64),
                "package_versions": {"survHE": "2.0.51", "flexsurv": "2.3.2", "survival": "3.8-3"},
                "adapter_path": format!("{base}/survhe_mle_adapter.R"), "adapter_sha256": adapter_hash,
                "session_info_path": format!("{base}/session-info.txt"), "session_info_sha256": session_hash,
                "execution_log_path": format!("{base}/execution.log"), "execution_log_sha256": log_hash
            },
            "model_order": ["exponential", "weibull"],
            "models": [
                {"family": "exponential", "status": "converged", "path": exp_path, "sha256": exp_hash},
                {"family": "weibull", "status": "converged", "path": wei_path, "sha256": wei_hash}
            ],
            "diagnostics": {
                "km_overlay_path": format!("{base}/km-overlay.png"), "km_overlay_sha256": km_hash,
                "log_cumulative_hazard_path": format!("{base}/log-cumulative-hazard.png"), "log_cumulative_hazard_sha256": lch_hash,
                "hazard_plot_path": format!("{base}/hazard.png"), "hazard_plot_sha256": hazard_hash
            },
            "cross_implementation": {"evaluator": EVALUATOR, "tolerance": 1e-8, "checks": [
                {"family": "exponential", "status": "passed", "max_abs_survival_error": 0.0, "max_abs_hazard_error": 0.0},
                {"family": "weibull", "status": "passed", "max_abs_survival_error": 0.0, "max_abs_hazard_error": 0.0}
            ], "complete": true},
            "limitations": ["Numerical agreement is not scientific validity."],
            "human_gate": {"state": "awaiting_human_review", "required_action": "review_survival_extrapolation"}
        });
        let manifest_path = format!("{base}/result-manifest.json");
        write_json(root, &manifest_path, &manifest);
        (manifest_path, manifest)
    }

    fn review_binding(root: &Path, manifest: &serde_json::Value) -> serde_json::Value {
        let request: serde_json::Value = serde_json::from_slice(
            &fs::read(root.join(manifest["request"]["path"].as_str().unwrap())).unwrap(),
        )
        .unwrap();
        let models = manifest["models"]
            .as_array()
            .unwrap()
            .iter()
            .map(|binding| {
                let model: serde_json::Value = serde_json::from_slice(
                    &fs::read(root.join(binding["path"].as_str().unwrap())).unwrap(),
                )
                .unwrap();
                serde_json::json!({
                    "family": binding["family"], "status": binding["status"],
                    "aic": model["fit_statistics"]["aic"], "bic": model["fit_statistics"]["bic"],
                    "log_likelihood": model["fit_statistics"]["log_likelihood"],
                    "parameterization": model["parameterization"],
                    "fit_output_path": binding["path"], "fit_output_sha256": binding["sha256"],
                    "landmarks": model["landmarks"], "warnings": model["warnings"]
                })
            })
            .collect::<Vec<_>>();
        let runtime = &manifest["runtime"];
        serde_json::json!({
            "analysis_target": request["analysis_target"],
            "context": {"observed_follow_up": request["fit"]["observed_follow_up"], "model_horizon": request["fit"]["model_horizon"]},
            "source_data": {"classification": request["source_data"]["classification"], "time_variable": request["source_data"]["columns"]["time"]},
            "pre_specification": {"candidate_models": request["fit"]["candidate_models"]},
            "execution": {
                "backend": "survHE", "environment": "ai4heor_isolated_local_mle",
                "r_version": runtime["r_version"], "package_versions": runtime["package_versions"],
                "command_path": runtime["adapter_path"], "command_sha256": runtime["adapter_sha256"],
                "session_info_path": runtime["session_info_path"], "session_info_sha256": runtime["session_info_sha256"]
            },
            "models": models,
            "diagnostics": manifest["diagnostics"]
        })
    }

    #[test]
    fn complete_bundle_is_independently_audited() {
        let root = workspace();
        let (manifest_path, _) = fixture(&root);
        let audit = audit_survival_fit_execution_path(&root, &manifest_path);
        assert!(audit.complete, "{:?}", audit.errors);
        assert!(audit.eligible_for_review);
        assert!(audit.cross_implementation_complete);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn parameter_drift_fails_after_model_hash_is_updated() {
        let root = workspace();
        let (manifest_path, mut manifest) = fixture(&root);
        let model_path = manifest["models"][1]["path"].as_str().unwrap().to_owned();
        let mut value: serde_json::Value =
            serde_json::from_slice(&fs::read(root.join(&model_path)).unwrap()).unwrap();
        value["landmarks"][2]["survival"] = serde_json::json!(0.9);
        manifest["models"][1]["sha256"] = serde_json::json!(write_json(&root, &model_path, &value));
        write_json(&root, &manifest_path, &manifest);
        let audit = audit_survival_fit_execution_path(&root, &manifest_path);
        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("cross-check tolerance")));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn review_binding_must_exactly_reproduce_normalized_outputs() {
        let root = workspace();
        let (manifest_path, manifest) = fixture(&root);
        let mut review = review_binding(&root, &manifest);
        let (audit, errors) =
            audit_survival_fit_execution_for_review(&root, &manifest_path, &review);
        assert!(audit.eligible_for_review);
        assert!(errors.is_empty(), "{errors:?}");
        review["models"][0]["aic"] = serde_json::json!(11.0);
        let (_, errors) = audit_survival_fit_execution_for_review(&root, &manifest_path, &review);
        assert!(errors
            .iter()
            .any(|error| error.contains("exactly reproduce")));
        fs::remove_dir_all(root).unwrap();
    }
}
