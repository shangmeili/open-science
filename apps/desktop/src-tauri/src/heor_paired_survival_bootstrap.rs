//! Native audit and app-owned Human method review for paired survival bootstrap runs.
//!
//! The R adapter performs the repeated fits. This module independently re-reads
//! every bound input, regenerates the PCG32 resampling plan, evaluates every
//! natural-parameter survival curve, checks PFS <= OS, and compares candidate
//! rows with the retained replicate rows. It never fits or selects a model.

use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const REQUEST_SCHEMA: &str = "0.1.0";
const RESULT_SCHEMA: &str = "0.1.0";
const REVIEW_SCHEMA: &str = "0.1.0";
const REVIEW_EVENT_SCHEMA: u32 = 1;
const REVIEW_ASSURANCE: &str = "app_owned_local_human_assertion";
const PLAN_FORMAT: &str = "ai4heor-stratified-patient-bootstrap-frequencies-csv@0.1.0";
const REPLICATE_FORMAT: &str = "ai4heor-paired-survival-bootstrap-replicates-jsonl@0.1.0";
const DRAW_FORMAT: &str = "ai4heor-joint-survival-draws-jsonl@0.1.0";
const RNG: &str = "pcg32-xsh-rr";
const RNG_VERSION: &str = "1";
const EVALUATOR: &str = "ai4heor-parametric-survival@0.2.0";
const MAX_JSON_BYTES: u64 = 16 * 1024 * 1024;
const MAX_SOURCE_BYTES: u64 = 256 * 1024 * 1024;
const MAX_RESULT_BYTES: u64 = 128 * 1024 * 1024;
const MAX_LINE_BYTES: usize = 2 * 1024 * 1024;
const MAX_SOURCE_ROWS: usize = 100_000;
const MAX_BOOTSTRAP_SELECTIONS: usize = 5_000_000;
const MAX_DRAW_CELLS: usize = 5_000_000;
const TOLERANCE: f64 = 1e-9;
const ADAPTER_BYTES: &[u8] = include_bytes!(
    "../../../../runtime/skills/core/heor-paired-survival-bootstrap/scripts/paired_survival_bootstrap_adapter.R"
);
const EVALUATOR_BYTES: &[u8] = include_bytes!(
    "../../../../runtime/skills/core/heor-survival-fit-execution/scripts/parametric_survival.py"
);

#[derive(Default)]
pub struct PairedBootstrapReviewState(pub Mutex<()>);

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PairedBootstrapAudit {
    pub complete: bool,
    pub reviewable: bool,
    pub status: String,
    pub execution_id: String,
    pub result_path: String,
    pub result_sha256: Option<String>,
    pub request_path: String,
    pub request_sha256: Option<String>,
    pub candidate_path: Option<String>,
    pub candidate_sha256: Option<String>,
    pub iterations: usize,
    pub completed_replicates: usize,
    pub failed_replicates: usize,
    pub curve_count: usize,
    pub strategy_counts: BTreeMap<String, usize>,
    pub package_versions: BTreeMap<String, String>,
    pub cross_implementation_complete: bool,
    pub curve_coherence_complete: bool,
    pub dependence_preserved: bool,
    pub between_strategy_assumption: String,
    pub limitations: Vec<String>,
    pub errors: Vec<String>,
}

impl Default for PairedBootstrapAudit {
    fn default() -> Self {
        Self {
            complete: false,
            reviewable: false,
            status: "unavailable".into(),
            execution_id: String::new(),
            result_path: String::new(),
            result_sha256: None,
            request_path: String::new(),
            request_sha256: None,
            candidate_path: None,
            candidate_sha256: None,
            iterations: 0,
            completed_replicates: 0,
            failed_replicates: 0,
            curve_count: 0,
            strategy_counts: BTreeMap::new(),
            package_versions: BTreeMap::new(),
            cross_implementation_complete: false,
            curve_coherence_complete: false,
            dependence_preserved: false,
            between_strategy_assumption: String::new(),
            limitations: Vec::new(),
            errors: Vec::new(),
        }
    }
}

#[derive(Clone, Debug)]
struct CurveSpec {
    target_path: String,
    strategy_id: String,
    endpoint: String,
    family: String,
}

#[derive(Default)]
struct RequestFacts {
    execution_id: String,
    strategies: Vec<String>,
    strategy_positions: Vec<Vec<usize>>,
    strategy_counts: BTreeMap<String, usize>,
    curves: Vec<CurveSpec>,
    grid: Vec<f64>,
    iterations: usize,
    seed: u64,
    tolerance: f64,
    output_directory: String,
}

fn exact(value: &serde_json::Value, fields: &[&str]) -> bool {
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

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn safe_id(value: &str) -> bool {
    value.len() <= 64
        && value
            .bytes()
            .next()
            .is_some_and(|byte| byte.is_ascii_lowercase())
        && value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'-' | b'_')
        })
}

fn safe_subject(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .next()
            .is_some_and(|byte| byte.is_ascii_alphanumeric())
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'-' | b'_'))
}

fn read_capped(path: &Path, cap: u64, label: &str) -> Result<Vec<u8>, String> {
    let metadata =
        std::fs::metadata(path).map_err(|error| format!("{label} unavailable: {error}"))?;
    if !metadata.is_file() || metadata.len() > cap {
        return Err(format!("{label} is not a bounded regular file"));
    }
    let mut raw = Vec::with_capacity(metadata.len() as usize);
    std::fs::File::open(path)
        .and_then(|mut file| file.read_to_end(&mut raw))
        .map_err(|error| format!("{label} unavailable: {error}"))?;
    Ok(raw)
}

fn resolve_file(workspace: &Path, relative: &str, label: &str) -> Result<PathBuf, String> {
    let relative_path = Path::new(relative);
    if relative_path.is_absolute()
        || relative_path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(format!("{label} path must stay inside the workspace"));
    }
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let mut unresolved = root.clone();
    for component in relative_path.components() {
        let Component::Normal(component) = component else {
            return Err(format!("{label} path must stay inside the workspace"));
        };
        unresolved.push(component);
        if std::fs::symlink_metadata(&unresolved)
            .is_ok_and(|metadata| metadata.file_type().is_symlink())
        {
            return Err(format!("{label} path must not traverse a symlink"));
        }
    }
    let resolved = unresolved
        .canonicalize()
        .map_err(|error| format!("{label} unavailable: {error}"))?;
    if !resolved.starts_with(&root) || !resolved.is_file() {
        return Err(format!("{label} path must stay inside the workspace"));
    }
    Ok(resolved)
}

fn bound_bytes(
    workspace: &Path,
    binding: &serde_json::Value,
    expected_path: Option<&str>,
    label: &str,
    cap: u64,
    errors: &mut Vec<String>,
) -> Option<(String, Vec<u8>)> {
    let Some(path) = text(binding.get("path")) else {
        errors.push(format!("{label} path is invalid"));
        return None;
    };
    if expected_path.is_some_and(|expected| path != expected) {
        errors.push(format!("{label} path must be {}", expected_path.unwrap()));
        return None;
    }
    let Some(expected_sha) = text(binding.get("sha256")).filter(|value| is_sha256(value)) else {
        errors.push(format!("{label} SHA-256 is invalid"));
        return None;
    };
    let resolved = match resolve_file(workspace, path, label) {
        Ok(path) => path,
        Err(error) => {
            errors.push(error);
            return None;
        }
    };
    let raw = match read_capped(&resolved, cap, label) {
        Ok(raw) => raw,
        Err(error) => {
            errors.push(error);
            return None;
        }
    };
    if sha256(&raw) != expected_sha {
        errors.push(format!("{label} SHA-256 does not match current bytes"));
        return None;
    }
    Some((path.to_owned(), raw))
}

fn parse_object(raw: &[u8], label: &str, errors: &mut Vec<String>) -> Option<serde_json::Value> {
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

fn json_binding(
    workspace: &Path,
    binding: &serde_json::Value,
    expected_path: &str,
    label: &str,
    errors: &mut Vec<String>,
) -> Option<(serde_json::Value, Vec<u8>)> {
    if !exact(binding, &["path", "sha256", "id"]) {
        errors.push(format!("{label} binding fields are invalid"));
        return None;
    }
    let (_, raw) = bound_bytes(
        workspace,
        binding,
        Some(expected_path),
        label,
        MAX_JSON_BYTES,
        errors,
    )?;
    let value = parse_object(&raw, label, errors)?;
    Some((value, raw))
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

#[derive(Clone)]
struct Pcg32 {
    state: u64,
    increment: u64,
}

impl Pcg32 {
    fn new(seed: u64) -> Self {
        let mut rng = Self {
            state: 0,
            increment: (54_u64 << 1) | 1,
        };
        rng.next_u32();
        rng.state = rng.state.wrapping_add(seed);
        rng.next_u32();
        rng
    }

    fn next_u32(&mut self) -> u32 {
        let old = self.state;
        self.state = old
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(self.increment);
        let shifted = (((old >> 18) ^ old) >> 27) as u32;
        shifted.rotate_right((old >> 59) as u32)
    }

    fn bounded(&mut self, upper: u32) -> u32 {
        let threshold = upper.wrapping_neg() % upper;
        loop {
            let value = self.next_u32();
            if value >= threshold {
                return value % upper;
            }
        }
    }
}

fn dedup_errors(errors: &mut Vec<String>) {
    let mut seen = HashSet::new();
    errors.retain(|error| seen.insert(error.clone()));
}

fn inspect_source(
    raw: &[u8],
    strategies: &[String],
    errors: &mut Vec<String>,
) -> (Vec<Vec<usize>>, BTreeMap<String, usize>) {
    let Ok(content) = std::str::from_utf8(raw) else {
        errors.push("source_data CSV must be UTF-8".into());
        return (Vec::new(), BTreeMap::new());
    };
    let mut lines = content.lines();
    if lines.next() != Some("subject_id,strategy_id,pfs_time,pfs_event,os_time,os_event") {
        errors.push("source_data CSV must contain exactly the six fixed columns in order".into());
        return (Vec::new(), BTreeMap::new());
    }
    let index_by_strategy: HashMap<&str, usize> = strategies
        .iter()
        .enumerate()
        .map(|(index, strategy)| (strategy.as_str(), index))
        .collect();
    let mut positions = vec![Vec::new(); strategies.len()];
    let mut counts = strategies
        .iter()
        .map(|strategy| (strategy.clone(), 0_usize))
        .collect::<BTreeMap<_, _>>();
    let mut events = vec![[0_usize; 2]; strategies.len()];
    let mut subjects = HashSet::new();
    for (row_index, line) in lines.enumerate() {
        let line_number = row_index + 2;
        if row_index >= MAX_SOURCE_ROWS {
            errors.push("source_data exceeds 100,000 rows".into());
            break;
        }
        let fields = line.split(',').collect::<Vec<_>>();
        if fields.len() != 6
            || fields
                .iter()
                .any(|field| field.is_empty() || *field != field.trim())
        {
            errors.push(format!(
                "source_data row {line_number} must contain six non-empty unpadded values"
            ));
            continue;
        }
        if !safe_subject(fields[0]) {
            errors.push(format!(
                "source_data row {line_number} subject_id is not a safe pseudonymous identifier"
            ));
        } else if !subjects.insert(fields[0].to_owned()) {
            errors.push(format!("source_data row {line_number} repeats subject_id"));
        }
        let Some(&strategy_index) = index_by_strategy.get(fields[1]) else {
            errors.push(format!(
                "source_data row {line_number} strategy_id is outside strategy_order"
            ));
            continue;
        };
        let Ok(pfs_time) = fields[2].parse::<f64>() else {
            errors.push(format!(
                "source_data row {line_number} times must be numeric"
            ));
            continue;
        };
        let Ok(os_time) = fields[4].parse::<f64>() else {
            errors.push(format!(
                "source_data row {line_number} times must be numeric"
            ));
            continue;
        };
        if !pfs_time.is_finite() || !os_time.is_finite() || pfs_time <= 0.0 || os_time <= 0.0 {
            errors.push(format!(
                "source_data row {line_number} times must be finite and positive"
            ));
        }
        if pfs_time > os_time + TOLERANCE {
            errors.push(format!(
                "source_data row {line_number} has PFS time after OS time"
            ));
        }
        if !matches!(fields[3], "0" | "1") || !matches!(fields[5], "0" | "1") {
            errors.push(format!(
                "source_data row {line_number} event indicators must be exactly 0 or 1"
            ));
            continue;
        }
        positions[strategy_index].push(row_index);
        *counts.get_mut(fields[1]).unwrap() += 1;
        events[strategy_index][0] += usize::from(fields[3] == "1");
        events[strategy_index][1] += usize::from(fields[5] == "1");
    }
    let row_count = positions.iter().map(Vec::len).sum::<usize>();
    if row_count < 2 {
        errors.push("source_data must contain at least two subjects".into());
    }
    for (index, strategy) in strategies.iter().enumerate() {
        if positions[index].len() < 2 {
            errors.push(format!(
                "source_data strategy {strategy} must contain at least two subjects"
            ));
        }
        if events[index][0] == 0 {
            errors.push(format!(
                "source_data strategy {strategy} pfs must contain at least one event"
            ));
        }
        if events[index][1] == 0 {
            errors.push(format!(
                "source_data strategy {strategy} os must contain at least one event"
            ));
        }
    }
    (positions, counts)
}

fn selected_curves(
    materializations: &serde_json::Value,
    strategies: &[String],
    errors: &mut Vec<String>,
) -> Vec<CurveSpec> {
    let Some(curves) = materializations
        .get("curves")
        .and_then(serde_json::Value::as_array)
    else {
        errors.push("curve materializations must contain a curves array".into());
        return Vec::new();
    };
    let mut by_target = HashMap::new();
    for curve in curves {
        let Some(target) = text(curve.get("target_path")) else {
            errors.push("curve materializations contain an invalid target".into());
            continue;
        };
        if by_target.insert(target.to_owned(), curve).is_some() {
            errors.push("curve materializations contain a repeated target".into());
        }
    }
    let mut result = Vec::new();
    for strategy in strategies {
        for endpoint in ["pfs", "os"] {
            let target = format!("partitioned_survival.strategies.{strategy}.{endpoint}");
            let Some(curve) = by_target.get(&target) else {
                errors.push(format!(
                    "curve materializations do not contain a selected curve for {target}"
                ));
                continue;
            };
            let family = text(curve.get("family")).unwrap_or_default();
            if text(curve.get("strategy_id")) != Some(strategy)
                || text(curve.get("endpoint")) != Some(endpoint)
                || expected_parameterization(family).is_none()
            {
                errors.push(format!(
                    "curve materializations do not contain a valid selected family for {target}"
                ));
                continue;
            }
            result.push(CurveSpec {
                target_path: target,
                strategy_id: strategy.clone(),
                endpoint: endpoint.into(),
                family: family.into(),
            });
        }
    }
    if by_target.len() != result.len() {
        errors.push(
            "curve materializations contain targets outside the exact strategy PFS/OS order".into(),
        );
    }
    result
}

fn validate_request(
    request: &serde_json::Value,
    workspace: &Path,
    errors: &mut Vec<String>,
) -> RequestFacts {
    let mut facts = RequestFacts::default();
    if !exact(
        request,
        &[
            "schema_version",
            "execution_id",
            "status",
            "analysis",
            "partitioned_survival",
            "curve_materializations",
            "source_data",
            "bootstrap",
            "runtime",
            "output",
            "limitations",
            "human_gate",
        ],
    ) {
        errors.push("bootstrap request fields are not the exact supported contract".into());
        return facts;
    }
    if text(request.get("schema_version")) != Some(REQUEST_SCHEMA) {
        errors.push(format!("request schema_version must be {REQUEST_SCHEMA}"));
    }
    let execution_id = text(request.get("execution_id")).unwrap_or_default();
    if !safe_id(execution_id) {
        errors.push("request execution_id must be a safe lowercase identifier".into());
    }
    facts.execution_id = execution_id.into();
    if text(request.get("status")) != Some("ready_for_execution") {
        errors.push("request status must be ready_for_execution".into());
    }

    let analysis_binding = request.get("analysis").unwrap_or(&serde_json::Value::Null);
    let psm_binding = request
        .get("partitioned_survival")
        .unwrap_or(&serde_json::Value::Null);
    let material_binding = request
        .get("curve_materializations")
        .unwrap_or(&serde_json::Value::Null);
    let analysis = json_binding(
        workspace,
        analysis_binding,
        "heor/analysis-plan.json",
        "analysis",
        errors,
    )
    .map(|(value, _)| value);
    let psm = json_binding(
        workspace,
        psm_binding,
        "heor/partitioned-survival-plan.json",
        "partitioned_survival",
        errors,
    )
    .map(|(value, _)| value);
    let materializations = json_binding(
        workspace,
        material_binding,
        "heor/survival-curve-materializations.json",
        "curve_materializations",
        errors,
    )
    .map(|(value, _)| value);

    if let Some(analysis) = &analysis {
        let strategies = analysis
            .get("strategy_order")
            .and_then(serde_json::Value::as_array)
            .map(|values| {
                values
                    .iter()
                    .filter_map(|value| text(Some(value)).map(str::to_owned))
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        if text(analysis.get("schema_version")) != Some("0.15.0")
            || strategies.len() < 2
            || strategies.iter().any(|value| !safe_id(value))
            || strategies.iter().collect::<HashSet<_>>().len() != strategies.len()
        {
            errors.push(
                "analysis must be current schema 0.15.0 with a valid unique strategy_order".into(),
            );
        }
        if text(analysis_binding.get("id")) != text(analysis.get("analysis_id")) {
            errors.push("analysis.id does not match current analysis_id".into());
        }
        facts.strategies = strategies;
        let cycles = analysis.get("cycles").and_then(serde_json::Value::as_u64);
        let cycle_length = finite(analysis.get("cycle_length_years"));
        match (cycles, cycle_length) {
            (Some(cycles), Some(length)) if cycles > 0 && length > 0.0 => {
                facts.grid = (0..=cycles).map(|index| index as f64 * length).collect();
            }
            _ => errors.push("analysis cycle grid is invalid".into()),
        }
    }
    if let Some(psm) = &psm {
        if text(psm.get("schema_version")) != Some("0.7.0")
            || text(psm_binding.get("id")) != text(psm.get("psm_id"))
        {
            errors.push(
                "partitioned survival must be current schema 0.7.0 with a matching psm_id".into(),
            );
        }
        if analysis
            .as_ref()
            .and_then(|value| text(value.get("analysis_id")))
            != text(psm.get("analysis_id"))
        {
            errors.push(
                "partitioned survival analysis_id does not match the current analysis".into(),
            );
        }
    }
    if let Some(materializations) = &materializations {
        if text(materializations.get("schema_version")) != Some("0.2.0")
            || text(material_binding.get("id")) != text(materializations.get("materialization_id"))
        {
            errors.push(
                "curve materializations must be schema 0.2.0 with a matching materialization_id"
                    .into(),
            );
        }
        facts.curves = selected_curves(materializations, &facts.strategies, errors);
    }

    let source = request
        .get("source_data")
        .unwrap_or(&serde_json::Value::Null);
    if !exact(
        source,
        &[
            "classification",
            "execution_boundary",
            "format",
            "path",
            "sha256",
            "columns",
            "row_count",
            "strategy_counts",
            "contains_direct_identifiers",
            "subject_identifier",
            "time_unit",
            "missing_policy",
            "additional_columns",
        ],
    ) {
        errors.push("source_data fields are invalid".into());
    } else {
        if !matches!(
            text(source.get("classification")),
            Some("public" | "non_sensitive" | "restricted")
        ) || text(source.get("execution_boundary")) != Some("local_only")
            || text(source.get("format")) != Some("csv")
            || source
                .get("contains_direct_identifiers")
                .and_then(serde_json::Value::as_bool)
                != Some(false)
            || text(source.get("subject_identifier")) != Some("pseudonymous_unique")
            || text(source.get("time_unit")) != Some("years")
            || text(source.get("missing_policy")) != Some("reject")
            || text(source.get("additional_columns")) != Some("reject")
        {
            errors.push(
                "source_data privacy, local-only, format, or missing-value contract is invalid"
                    .into(),
            );
        }
        let expected_columns = [
            "subject_id",
            "strategy_id",
            "pfs_time",
            "pfs_event",
            "os_time",
            "os_event",
        ];
        if source
            .get("columns")
            .and_then(serde_json::Value::as_array)
            .map(|values| {
                values
                    .iter()
                    .filter_map(|value| text(Some(value)))
                    .collect::<Vec<_>>()
            })
            != Some(expected_columns.to_vec())
        {
            errors.push("source_data.columns must contain the six fixed columns in order".into());
        }
        if let Some((_, raw)) = bound_bytes(
            workspace,
            source,
            None,
            "source_data",
            MAX_SOURCE_BYTES,
            errors,
        ) {
            let (positions, counts) = inspect_source(&raw, &facts.strategies, errors);
            let row_count = positions.iter().map(Vec::len).sum::<usize>();
            if source.get("row_count").and_then(serde_json::Value::as_u64) != Some(row_count as u64)
            {
                errors.push("source_data.row_count does not match current CSV".into());
            }
            let declared_counts = source
                .get("strategy_counts")
                .and_then(serde_json::Value::as_object)
                .map(|object| {
                    object
                        .iter()
                        .filter_map(|(key, value)| {
                            value.as_u64().map(|count| (key.clone(), count as usize))
                        })
                        .collect::<BTreeMap<_, _>>()
                });
            if declared_counts.as_ref() != Some(&counts) {
                errors.push("source_data.strategy_counts do not match current CSV".into());
            }
            facts.strategy_positions = positions;
            facts.strategy_counts = counts;
        }
    }

    let bootstrap = request.get("bootstrap").unwrap_or(&serde_json::Value::Null);
    if !exact(
        bootstrap,
        &[
            "method",
            "iterations",
            "seed",
            "rng",
            "rng_version",
            "resampling_unit",
            "strategy_resampling_design",
            "preserve_strategy_sample_sizes",
            "endpoint_sampling",
            "between_strategy_assumption",
            "curves",
            "time_grid_years",
            "cross_implementation_tolerance",
        ],
    ) {
        errors.push("bootstrap fields are invalid".into());
    } else {
        if text(bootstrap.get("method")) != Some("ordinary_nonparametric_case_resampling")
            || text(bootstrap.get("rng")) != Some(RNG)
            || text(bootstrap.get("rng_version")) != Some(RNG_VERSION)
            || text(bootstrap.get("resampling_unit")) != Some("whole_subject_row")
            || text(bootstrap.get("strategy_resampling_design"))
                != Some("stratified_independent_parallel_arms")
            || bootstrap
                .get("preserve_strategy_sample_sizes")
                .and_then(serde_json::Value::as_bool)
                != Some(true)
            || text(bootstrap.get("endpoint_sampling"))
                != Some("same_subject_indices_for_pfs_and_os")
            || text(bootstrap.get("between_strategy_assumption"))
                != Some("conditional_independence_given_parallel_arm_design")
        {
            errors.push("bootstrap design, RNG, or dependence contract is invalid".into());
        }
        facts.iterations = bootstrap
            .get("iterations")
            .and_then(serde_json::Value::as_u64)
            .unwrap_or_default() as usize;
        if !(1_000..=10_000).contains(&facts.iterations) {
            errors.push("bootstrap.iterations must be from 1000 to 10000".into());
        }
        facts.seed = bootstrap
            .get("seed")
            .and_then(serde_json::Value::as_u64)
            .unwrap_or_default();
        facts.tolerance =
            finite(bootstrap.get("cross_implementation_tolerance")).unwrap_or_default();
        if !(1e-12..=1e-6).contains(&facts.tolerance) {
            errors.push("cross_implementation_tolerance must be between 1e-12 and 1e-6".into());
        }
        let observed_grid = bootstrap
            .get("time_grid_years")
            .and_then(serde_json::Value::as_array);
        if observed_grid.is_none_or(|values| {
            values.len() != facts.grid.len()
                || values.iter().zip(&facts.grid).any(|(observed, expected)| {
                    finite(Some(observed)).is_none_or(|value| (value - expected).abs() > 1e-12)
                })
        }) {
            errors.push(
                "bootstrap.time_grid_years must exactly reproduce the analysis cycle grid".into(),
            );
        }
        let observed_curves = bootstrap
            .get("curves")
            .and_then(serde_json::Value::as_array);
        if observed_curves.is_none_or(|values| {
            values.len() != facts.curves.len()
                || values
                    .iter()
                    .zip(&facts.curves)
                    .any(|(observed, expected)| {
                        !exact(
                            observed,
                            &["target_path", "strategy_id", "endpoint", "family"],
                        ) || text(observed.get("target_path")) != Some(&expected.target_path)
                            || text(observed.get("strategy_id")) != Some(&expected.strategy_id)
                            || text(observed.get("endpoint")) != Some(&expected.endpoint)
                            || text(observed.get("family")) != Some(&expected.family)
                    })
        }) {
            errors.push(
                "bootstrap.curves must exactly reproduce selected strategy PFS/OS families".into(),
            );
        }
        let rows = facts.strategy_positions.iter().map(Vec::len).sum::<usize>();
        if facts.iterations.saturating_mul(rows) > MAX_BOOTSTRAP_SELECTIONS {
            errors.push("bootstrap plan exceeds the patient-selection limit".into());
        }
        if facts
            .iterations
            .saturating_mul(facts.curves.len())
            .saturating_mul(facts.grid.len())
            > MAX_DRAW_CELLS
        {
            errors.push("bootstrap output exceeds the survival-value limit".into());
        }
    }

    let runtime = request.get("runtime").unwrap_or(&serde_json::Value::Null);
    let packages = runtime.get("expected_packages");
    if !exact(runtime, &["expected_packages"])
        || packages
            .and_then(serde_json::Value::as_object)
            .is_none_or(|object| {
                object.len() != 3
                    || ["survHE", "flexsurv", "survival"]
                        .iter()
                        .any(|name| text(object.get(*name)).is_none())
            })
    {
        errors.push(
            "runtime.expected_packages must contain exactly survHE, flexsurv, and survival".into(),
        );
    }

    let output = request.get("output").unwrap_or(&serde_json::Value::Null);
    facts.output_directory = format!(
        "heor/paired-survival-bootstrap-executions/{}",
        facts.execution_id
    );
    if !exact(output, &["directory", "overwrite_policy"])
        || text(output.get("directory")) != Some(&facts.output_directory)
        || text(output.get("overwrite_policy")) != Some("fail_if_exists")
    {
        errors.push("request output directory or overwrite policy is invalid".into());
    }
    if request
        .get("limitations")
        .and_then(serde_json::Value::as_array)
        .is_none_or(|values| {
            values.is_empty() || values.iter().any(|value| text(Some(value)).is_none())
        })
    {
        errors.push("request limitations must contain non-empty strings".into());
    }
    if request.get("human_gate")
        != Some(&serde_json::json!({
            "state": "awaiting_execution_authorization",
            "required_action": "approve_local_paired_survival_bootstrap_command"
        }))
    {
        errors.push("request Human gate is invalid".into());
    }
    facts
}

fn output_binding(
    workspace: &Path,
    binding: &serde_json::Value,
    label: &str,
    errors: &mut Vec<String>,
) -> Option<(String, Vec<u8>)> {
    if !exact(binding, &["path", "sha256", "format", "row_count"])
        || binding
            .get("row_count")
            .and_then(serde_json::Value::as_u64)
            .is_none()
    {
        errors.push(format!("{label} binding fields are invalid"));
        return None;
    }
    bound_bytes(workspace, binding, None, label, MAX_RESULT_BYTES, errors)
}

fn audit_plan(raw: &[u8], facts: &RequestFacts, errors: &mut Vec<String>) {
    let row_count = facts.strategy_positions.iter().map(Vec::len).sum::<usize>();
    let mut expected = String::from("replicate_index");
    for index in 1..=row_count {
        expected.push_str(&format!(",row_{index}"));
    }
    expected.push('\n');
    let mut rng = Pcg32::new(facts.seed);
    for replicate in 1..=facts.iterations {
        let mut frequencies = vec![0_u32; row_count];
        for positions in &facts.strategy_positions {
            for _ in positions {
                let selected = positions[rng.bounded(positions.len() as u32) as usize];
                frequencies[selected] += 1;
            }
        }
        expected.push_str(&replicate.to_string());
        for frequency in frequencies {
            expected.push(',');
            expected.push_str(&frequency.to_string());
        }
        expected.push('\n');
    }
    if raw != expected.as_bytes() {
        errors.push(
            "resampling_plan bytes do not reproduce the declared PCG32 stratified design".into(),
        );
    }
}

fn parse_parameters(value: &serde_json::Value) -> Option<HashMap<String, f64>> {
    let parameters = value.as_array()?;
    let mut result = HashMap::new();
    for parameter in parameters {
        if !exact(parameter, &["name", "estimate"]) {
            return None;
        }
        let name = text(parameter.get("name"))?.to_owned();
        let estimate = finite(parameter.get("estimate"))?;
        if result.insert(name, estimate).is_some() {
            return None;
        }
    }
    Some(result)
}

fn read_jsonl(
    raw: &[u8],
    expected_rows: usize,
    label: &str,
    errors: &mut Vec<String>,
) -> Vec<serde_json::Value> {
    let mut rows = Vec::new();
    for (index, line) in raw.split(|byte| *byte == b'\n').enumerate() {
        if line.is_empty() {
            continue;
        }
        if line.len() > MAX_LINE_BYTES {
            errors.push(format!("{label} row {} exceeds 2 MB", index + 1));
            continue;
        }
        match serde_json::from_slice::<serde_json::Value>(line) {
            Ok(value) if value.is_object() => rows.push(value),
            _ => errors.push(format!("{label} row {} is invalid JSON", index + 1)),
        }
        if rows.len() > expected_rows {
            errors.push(format!("{label} exceeds the requested row count"));
            break;
        }
    }
    if rows.len() != expected_rows {
        errors.push(format!(
            "{label} must contain exactly {expected_rows} non-empty rows"
        ));
    }
    rows
}

fn audit_replicates(
    rows: &[serde_json::Value],
    facts: &RequestFacts,
    errors: &mut Vec<String>,
) -> (usize, bool, bool, Vec<Vec<Vec<f64>>>) {
    let mut failed = 0;
    let mut cross_complete = true;
    let mut coherence_complete = true;
    let mut completed_curves = Vec::new();
    for (row_index, row) in rows.iter().enumerate() {
        let replicate_index = row_index + 1;
        if !exact(
            row,
            &["replicate_index", "status", "curves", "failure_reasons"],
        ) || row
            .get("replicate_index")
            .and_then(serde_json::Value::as_u64)
            != Some(replicate_index as u64)
        {
            errors.push(format!(
                "replicate {replicate_index} fields or index are invalid"
            ));
            failed += 1;
            cross_complete = false;
            coherence_complete = false;
            continue;
        }
        let reasons = row
            .get("failure_reasons")
            .and_then(serde_json::Value::as_array);
        if reasons.is_none_or(|values| values.iter().any(|value| text(Some(value)).is_none())) {
            errors.push(format!(
                "replicate {replicate_index} failure_reasons are invalid"
            ));
        }
        let Some(curves) = row.get("curves").and_then(serde_json::Value::as_array) else {
            errors.push(format!(
                "replicate {replicate_index} does not cover every selected curve"
            ));
            failed += 1;
            cross_complete = false;
            coherence_complete = false;
            continue;
        };
        if curves.len() != facts.curves.len() {
            errors.push(format!(
                "replicate {replicate_index} does not cover every selected curve"
            ));
            failed += 1;
            cross_complete = false;
            coherence_complete = false;
            continue;
        }
        let mut row_ok = true;
        let mut row_curves = Vec::new();
        for (curve_index, (curve, expected)) in curves.iter().zip(&facts.curves).enumerate() {
            if !exact(
                curve,
                &[
                    "target_path",
                    "strategy_id",
                    "endpoint",
                    "family",
                    "status",
                    "parameterization",
                    "parameters",
                    "survival",
                    "warnings",
                    "crosscheck",
                ],
            ) || text(curve.get("target_path")) != Some(&expected.target_path)
                || text(curve.get("strategy_id")) != Some(&expected.strategy_id)
                || text(curve.get("endpoint")) != Some(&expected.endpoint)
                || text(curve.get("family")) != Some(&expected.family)
            {
                errors.push(format!(
                    "replicate {replicate_index} curve {curve_index} identity or fields are invalid"
                ));
                row_ok = false;
                cross_complete = false;
                row_curves.push(Vec::new());
                continue;
            }
            let warnings_valid = curve
                .get("warnings")
                .and_then(serde_json::Value::as_array)
                .is_some_and(|values| values.iter().all(|value| text(Some(value)).is_some()));
            if !warnings_valid {
                errors.push(format!(
                    "replicate {replicate_index} curve {curve_index} warnings are invalid"
                ));
                row_ok = false;
            }
            if text(curve.get("status")) == Some("failed") {
                let crosscheck = curve.get("crosscheck");
                if text(curve.get("parameterization")) != Some("")
                    || curve
                        .get("parameters")
                        .and_then(serde_json::Value::as_array)
                        != Some(&Vec::new())
                    || curve.get("survival").and_then(serde_json::Value::as_array)
                        != Some(&Vec::new())
                    || crosscheck
                        != Some(&serde_json::json!({
                            "status": "fit_failed",
                            "max_abs_survival_error": null
                        }))
                {
                    errors.push(format!(
                        "replicate {replicate_index} failed curve payload is invalid"
                    ));
                }
                row_ok = false;
                cross_complete = false;
                row_curves.push(Vec::new());
                continue;
            }
            if text(curve.get("status")) != Some("converged")
                || text(curve.get("parameterization"))
                    != expected_parameterization(&expected.family)
            {
                errors.push(format!(
                    "replicate {replicate_index} curve {curve_index} status or parameterization is invalid"
                ));
                row_ok = false;
                cross_complete = false;
                row_curves.push(Vec::new());
                continue;
            }
            let Some(parameters) =
                parse_parameters(curve.get("parameters").unwrap_or(&serde_json::Value::Null))
            else {
                errors.push(format!(
                    "replicate {replicate_index} curve {curve_index} parameters are invalid"
                ));
                row_ok = false;
                cross_complete = false;
                row_curves.push(Vec::new());
                continue;
            };
            let Some(survival) = curve
                .get("survival")
                .and_then(serde_json::Value::as_array)
                .map(|values| {
                    values
                        .iter()
                        .filter_map(|value| finite(Some(value)))
                        .collect::<Vec<_>>()
                })
                .filter(|values| values.len() == facts.grid.len())
            else {
                errors.push(format!(
                    "replicate {replicate_index} curve {curve_index} survival grid is invalid"
                ));
                row_ok = false;
                cross_complete = false;
                row_curves.push(Vec::new());
                continue;
            };
            let expected_values = facts
                .grid
                .iter()
                .map(|time| {
                    crate::heor_parametric_survival::curve(&expected.family, &parameters, *time)
                        .map(|value| value.0)
                })
                .collect::<Result<Vec<_>, _>>();
            let Ok(expected_values) = expected_values else {
                errors.push(format!(
                    "replicate {replicate_index} curve {curve_index} native evaluator failed"
                ));
                row_ok = false;
                cross_complete = false;
                row_curves.push(survival);
                continue;
            };
            let max_error = survival
                .iter()
                .zip(&expected_values)
                .map(|(observed, expected)| (observed - expected).abs())
                .fold(0.0_f64, f64::max);
            let check = curve.get("crosscheck").unwrap_or(&serde_json::Value::Null);
            let observed_error = finite(check.get("max_abs_survival_error"));
            let expected_status = if max_error <= facts.tolerance {
                "passed"
            } else {
                "failed"
            };
            if !exact(check, &["status", "max_abs_survival_error"])
                || text(check.get("status")) != Some(expected_status)
                || observed_error.is_none_or(|value| {
                    (value - max_error).abs() > (1e-15_f64).max(max_error.abs() * 1e-12)
                })
            {
                errors.push(format!(
                    "replicate {replicate_index} curve {curve_index} crosscheck is invalid"
                ));
                row_ok = false;
                cross_complete = false;
            }
            if max_error > facts.tolerance {
                row_ok = false;
                cross_complete = false;
            }
            if survival
                .first()
                .is_none_or(|value| (*value - 1.0).abs() > TOLERANCE)
                || survival.iter().any(|value| !(0.0..=1.0).contains(value))
                || survival
                    .windows(2)
                    .any(|pair| pair[1] > pair[0] + TOLERANCE)
            {
                errors.push(format!(
                    "replicate {replicate_index} curve {curve_index} is not a valid survival curve"
                ));
                row_ok = false;
                coherence_complete = false;
            }
            row_curves.push(survival);
        }
        for strategy_index in 0..facts.strategies.len() {
            let pfs = row_curves.get(strategy_index * 2);
            let overall = row_curves.get(strategy_index * 2 + 1);
            if pfs.zip(overall).is_some_and(|(pfs, overall)| {
                !pfs.is_empty()
                    && !overall.is_empty()
                    && pfs
                        .iter()
                        .zip(overall)
                        .any(|(pfs, overall)| pfs > &(overall + TOLERANCE))
            }) {
                errors.push(format!("replicate {replicate_index} has PFS above OS"));
                row_ok = false;
                coherence_complete = false;
            }
        }
        let expected_status = if row_ok { "complete" } else { "failed" };
        let reason_count = reasons.map_or(0, Vec::len);
        if text(row.get("status")) != Some(expected_status)
            || (row_ok && reason_count != 0)
            || (!row_ok && reason_count == 0)
        {
            errors.push(format!(
                "replicate {replicate_index} status or failure reasons do not match audited curves"
            ));
        }
        if row_ok {
            completed_curves.push(row_curves);
        } else {
            failed += 1;
        }
    }
    (failed, cross_complete, coherence_complete, completed_curves)
}

fn audit_candidate(
    rows: &[serde_json::Value],
    completed_curves: &[Vec<Vec<f64>>],
    errors: &mut Vec<String>,
) {
    if rows.len() != completed_curves.len() {
        errors.push("candidate draws do not cover every complete replicate".into());
        return;
    }
    for (index, (row, expected_curves)) in rows.iter().zip(completed_curves).enumerate() {
        if !exact(row, &["draw_index", "curves"])
            || row.get("draw_index").and_then(serde_json::Value::as_u64) != Some((index + 1) as u64)
        {
            errors.push(format!("candidate draw {} identity is invalid", index + 1));
            continue;
        }
        let observed = row.get("curves").and_then(serde_json::Value::as_array);
        if observed.is_none_or(|curves| {
            curves.len() != expected_curves.len()
                || curves.iter().zip(expected_curves).any(|(curve, expected)| {
                    curve.as_array().is_none_or(|values| {
                        values.len() != expected.len()
                            || values
                                .iter()
                                .zip(expected)
                                .any(|(value, expected)| finite(Some(value)) != Some(*expected))
                    })
                })
        }) {
            errors.push(format!(
                "candidate draw {} does not exactly reproduce its audited replicate curves",
                index + 1
            ));
        }
    }
}

pub(crate) fn audit_paired_bootstrap_path(
    workspace: &Path,
    result_relative: &str,
) -> PairedBootstrapAudit {
    let mut audit = PairedBootstrapAudit {
        result_path: result_relative.to_owned(),
        ..PairedBootstrapAudit::default()
    };
    let result_path = match resolve_file(workspace, result_relative, "paired bootstrap result") {
        Ok(path) => path,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let result_raw = match read_capped(&result_path, MAX_JSON_BYTES, "paired bootstrap result") {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    audit.result_sha256 = Some(sha256(&result_raw));
    let Some(manifest) = parse_object(&result_raw, "paired bootstrap result", &mut audit.errors)
    else {
        return audit;
    };
    if !exact(
        &manifest,
        &[
            "schema_version",
            "execution_id",
            "status",
            "request",
            "analysis",
            "partitioned_survival",
            "curve_materializations",
            "source_data",
            "runtime",
            "bootstrap",
            "limitations",
            "human_gate",
        ],
    ) {
        audit
            .errors
            .push("result manifest fields are invalid".into());
        return audit;
    }
    if text(manifest.get("schema_version")) != Some(RESULT_SCHEMA) {
        audit
            .errors
            .push(format!("result schema_version must be {RESULT_SCHEMA}"));
    }
    audit.execution_id = text(manifest.get("execution_id"))
        .unwrap_or_default()
        .to_owned();
    if !safe_id(&audit.execution_id) {
        audit.errors.push("result execution_id is invalid".into());
    }
    audit.status = text(manifest.get("status")).unwrap_or("invalid").to_owned();

    let request_binding = manifest.get("request").unwrap_or(&serde_json::Value::Null);
    if !exact(request_binding, &["path", "sha256"]) {
        audit
            .errors
            .push("result request binding fields are invalid".into());
        return audit;
    }
    let Some((request_path, request_raw)) = bound_bytes(
        workspace,
        request_binding,
        Some("heor/paired-survival-bootstrap-request.json"),
        "paired bootstrap request",
        MAX_JSON_BYTES,
        &mut audit.errors,
    ) else {
        return audit;
    };
    audit.request_path = request_path;
    audit.request_sha256 = Some(sha256(&request_raw));
    let Some(request) = parse_object(&request_raw, "paired bootstrap request", &mut audit.errors)
    else {
        return audit;
    };
    let facts = validate_request(&request, workspace, &mut audit.errors);
    if facts.execution_id != audit.execution_id {
        audit
            .errors
            .push("result execution_id does not match request".into());
    }
    let expected_result_path = format!("{}/result-manifest.json", facts.output_directory);
    if result_relative != expected_result_path {
        audit
            .errors
            .push("result manifest path does not match request output directory".into());
    }
    for field in ["analysis", "partitioned_survival", "curve_materializations"] {
        if manifest.get(field) != request.get(field) {
            audit.errors.push(format!(
                "result {field} does not exactly copy request binding"
            ));
        }
    }
    let expected_source = serde_json::json!({
        "path": request.pointer("/source_data/path").cloned().unwrap_or(serde_json::Value::Null),
        "sha256": request.pointer("/source_data/sha256").cloned().unwrap_or(serde_json::Value::Null),
        "row_count": request.pointer("/source_data/row_count").cloned().unwrap_or(serde_json::Value::Null),
        "strategy_counts": request.pointer("/source_data/strategy_counts").cloned().unwrap_or(serde_json::Value::Null)
    });
    if manifest.get("source_data") != Some(&expected_source) {
        audit
            .errors
            .push("result source_data does not exactly copy request binding and counts".into());
    }
    audit.strategy_counts = facts.strategy_counts.clone();
    audit.curve_count = facts.curves.len();
    audit.iterations = facts.iterations;

    let runtime = manifest.get("runtime").unwrap_or(&serde_json::Value::Null);
    if !exact(
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
    ) || text(runtime.get("backend")) != Some("survHE")
        || text(runtime.get("method")) != Some("paired_patient_bootstrap")
        || runtime.get("package_versions") != request.pointer("/runtime/expected_packages")
    {
        audit
            .errors
            .push("result runtime fields, backend, method, or package versions are invalid".into());
    } else {
        if let Some(packages) = runtime
            .get("package_versions")
            .and_then(serde_json::Value::as_object)
        {
            audit.package_versions = packages
                .iter()
                .filter_map(|(name, version)| {
                    text(Some(version)).map(|version| (name.clone(), version.to_owned()))
                })
                .collect();
        }
        for prefix in ["adapter", "session_info", "execution_log"] {
            let binding = serde_json::json!({
                "path": runtime.get(format!("{prefix}_path")).cloned().unwrap_or(serde_json::Value::Null),
                "sha256": runtime.get(format!("{prefix}_sha256")).cloned().unwrap_or(serde_json::Value::Null)
            });
            let result = bound_bytes(
                workspace,
                &binding,
                None,
                &format!("runtime {prefix}"),
                MAX_RESULT_BYTES,
                &mut audit.errors,
            );
            if prefix == "adapter"
                && result
                    .as_ref()
                    .is_some_and(|(_, raw)| raw.as_slice() != ADAPTER_BYTES)
            {
                audit.errors.push(
                    "result runtime adapter does not match the fixed packaged adapter".into(),
                );
            }
        }
        if text(runtime.get("adapter_sha256")) != Some(&sha256(ADAPTER_BYTES)) {
            audit
                .errors
                .push("result adapter SHA-256 does not match the packaged adapter".into());
        }
    }

    let bootstrap = manifest
        .get("bootstrap")
        .unwrap_or(&serde_json::Value::Null);
    if !exact(
        bootstrap,
        &[
            "method",
            "rng",
            "rng_version",
            "seed",
            "iterations",
            "resampling_unit",
            "strategy_resampling_design",
            "endpoint_sampling",
            "between_strategy_assumption",
            "evaluator",
            "curve_order",
            "time_grid_years",
            "resampling_plan",
            "replicate_results",
            "candidate_draws",
            "completed_replicates",
            "failed_replicates",
            "cross_implementation_complete",
            "curve_coherence_complete",
            "eligible_for_joint_packaging",
        ],
    ) {
        audit
            .errors
            .push("result bootstrap fields are invalid".into());
        return audit;
    }
    for field in [
        "method",
        "rng",
        "rng_version",
        "seed",
        "iterations",
        "resampling_unit",
        "strategy_resampling_design",
        "endpoint_sampling",
        "between_strategy_assumption",
        "time_grid_years",
    ] {
        if bootstrap.get(field) != request.pointer(&format!("/bootstrap/{field}")) {
            audit
                .errors
                .push(format!("result bootstrap.{field} does not match request"));
        }
    }
    audit.between_strategy_assumption = text(bootstrap.get("between_strategy_assumption"))
        .unwrap_or_default()
        .to_owned();
    audit.dependence_preserved = text(bootstrap.get("resampling_unit"))
        == Some("whole_subject_row")
        && text(bootstrap.get("endpoint_sampling")) == Some("same_subject_indices_for_pfs_and_os")
        && text(bootstrap.get("strategy_resampling_design"))
            == Some("stratified_independent_parallel_arms")
        && audit.between_strategy_assumption
            == "conditional_independence_given_parallel_arm_design";
    let expected_evaluator = serde_json::json!({
        "id": EVALUATOR,
        "sha256": sha256(EVALUATOR_BYTES)
    });
    if bootstrap.get("evaluator") != Some(&expected_evaluator) {
        audit.errors.push(
            "result bootstrap.evaluator does not bind the packaged native-equivalent evaluator"
                .into(),
        );
    }
    let expected_order = facts
        .curves
        .iter()
        .map(|curve| curve.target_path.as_str())
        .collect::<Vec<_>>();
    if bootstrap
        .get("curve_order")
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(|value| text(Some(value)))
                .collect::<Vec<_>>()
        })
        != Some(expected_order)
    {
        audit
            .errors
            .push("result bootstrap.curve_order does not match selected curves".into());
    }

    let plan = bootstrap
        .get("resampling_plan")
        .unwrap_or(&serde_json::Value::Null);
    if text(plan.get("format")) != Some(PLAN_FORMAT)
        || plan.get("row_count").and_then(serde_json::Value::as_u64)
            != Some(facts.iterations as u64)
    {
        audit
            .errors
            .push("resampling_plan format or row_count is invalid".into());
    }
    if let Some((_, raw)) = output_binding(workspace, plan, "resampling_plan", &mut audit.errors) {
        audit_plan(&raw, &facts, &mut audit.errors);
    }

    let replicates = bootstrap
        .get("replicate_results")
        .unwrap_or(&serde_json::Value::Null);
    if text(replicates.get("format")) != Some(REPLICATE_FORMAT)
        || replicates
            .get("row_count")
            .and_then(serde_json::Value::as_u64)
            != Some(facts.iterations as u64)
    {
        audit
            .errors
            .push("replicate_results format or row_count is invalid".into());
    }
    let replicate_rows = output_binding(
        workspace,
        replicates,
        "replicate_results",
        &mut audit.errors,
    )
    .map(|(_, raw)| {
        read_jsonl(
            &raw,
            facts.iterations,
            "replicate_results",
            &mut audit.errors,
        )
    })
    .unwrap_or_default();
    let (failed, cross_complete, coherence_complete, completed_curves) =
        audit_replicates(&replicate_rows, &facts, &mut audit.errors);
    audit.failed_replicates = failed;
    audit.completed_replicates = facts.iterations.saturating_sub(failed);
    audit.cross_implementation_complete = cross_complete;
    audit.curve_coherence_complete = coherence_complete;
    if bootstrap
        .get("completed_replicates")
        .and_then(serde_json::Value::as_u64)
        != Some(audit.completed_replicates as u64)
        || bootstrap
            .get("failed_replicates")
            .and_then(serde_json::Value::as_u64)
            != Some(failed as u64)
    {
        audit
            .errors
            .push("result replicate counts do not match native audit".into());
    }
    if bootstrap
        .get("cross_implementation_complete")
        .and_then(serde_json::Value::as_bool)
        != Some(cross_complete)
        || bootstrap
            .get("curve_coherence_complete")
            .and_then(serde_json::Value::as_bool)
            != Some(coherence_complete)
    {
        audit
            .errors
            .push("result completion flags do not match native audit".into());
    }
    let eligible = failed == 0
        && cross_complete
        && coherence_complete
        && completed_curves.len() == facts.iterations;
    if bootstrap
        .get("eligible_for_joint_packaging")
        .and_then(serde_json::Value::as_bool)
        != Some(eligible)
    {
        audit
            .errors
            .push("eligible_for_joint_packaging does not match native audit".into());
    }

    let candidate = bootstrap.get("candidate_draws");
    if eligible {
        let Some(candidate) = candidate.filter(|value| !value.is_null()) else {
            audit
                .errors
                .push("candidate_draws is required for a complete execution".into());
            dedup_errors(&mut audit.errors);
            return audit;
        };
        if text(candidate.get("format")) != Some(DRAW_FORMAT)
            || candidate
                .get("row_count")
                .and_then(serde_json::Value::as_u64)
                != Some(facts.iterations as u64)
        {
            audit
                .errors
                .push("candidate_draws format or row_count is invalid".into());
        }
        if let Some((path, raw)) =
            output_binding(workspace, candidate, "candidate_draws", &mut audit.errors)
        {
            audit.candidate_path = Some(path);
            audit.candidate_sha256 = Some(sha256(&raw));
            let rows = read_jsonl(&raw, facts.iterations, "candidate_draws", &mut audit.errors);
            audit_candidate(&rows, &completed_curves, &mut audit.errors);
        }
    } else if candidate.is_some_and(|value| !value.is_null()) {
        audit
            .errors
            .push("candidate_draws must be null when any replicate is ineligible".into());
    }
    let expected_status = if eligible { "complete" } else { "incomplete" };
    if audit.status != expected_status {
        audit
            .errors
            .push("result status does not match native bootstrap eligibility".into());
    }
    audit.limitations = manifest
        .get("limitations")
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(|value| text(Some(value)).map(str::to_owned))
                .collect()
        })
        .unwrap_or_default();
    if audit.limitations.is_empty() {
        audit
            .errors
            .push("result limitations must contain non-empty strings".into());
    }
    if manifest.get("human_gate")
        != Some(&serde_json::json!({
            "state": "awaiting_bootstrap_method_review",
            "required_action": "review_paired_bootstrap_before_joint_packaging"
        }))
    {
        audit
            .errors
            .push("result Human gate must remain awaiting method review".into());
    }
    dedup_errors(&mut audit.errors);
    audit.complete = audit.errors.is_empty();
    audit.reviewable = audit.complete && eligible;
    audit
}

fn result_path_from_request(workspace: &Path) -> Result<String, String> {
    let request_path = resolve_file(
        workspace,
        "heor/paired-survival-bootstrap-request.json",
        "paired bootstrap request",
    )?;
    let raw = read_capped(&request_path, MAX_JSON_BYTES, "paired bootstrap request")?;
    let value: serde_json::Value = serde_json::from_slice(&raw)
        .map_err(|error| format!("request is invalid JSON: {error}"))?;
    let output = text(value.pointer("/output/directory"))
        .ok_or_else(|| "request output.directory is invalid".to_string())?;
    Ok(format!("{output}/result-manifest.json"))
}

#[tauri::command]
pub fn audit_heor_paired_survival_bootstrap(
    app: AppHandle,
) -> Result<PairedBootstrapAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    match result_path_from_request(&workspace) {
        Ok(path) => Ok(audit_paired_bootstrap_path(&workspace, &path)),
        Err(error) => Ok(PairedBootstrapAudit {
            errors: vec![error],
            ..PairedBootstrapAudit::default()
        }),
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PairedBootstrapReviewAction {
    Accept,
    Reject,
}

#[derive(Clone, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct PairedBootstrapChecklist {
    pub resampling_design_reviewed: bool,
    pub endpoints_and_censoring_reviewed: bool,
    pub selected_families_reviewed: bool,
    pub failures_and_convergence_reviewed: bool,
    pub follow_up_and_extrapolation_reviewed: bool,
    pub parallel_arm_assumption_reviewed: bool,
    pub clinical_plausibility_reviewed: bool,
}

impl PairedBootstrapChecklist {
    fn all_confirmed(&self) -> bool {
        self.resampling_design_reviewed
            && self.endpoints_and_censoring_reviewed
            && self.selected_families_reviewed
            && self.failures_and_convergence_reviewed
            && self.follow_up_and_extrapolation_reviewed
            && self.parallel_arm_assumption_reviewed
            && self.clinical_plausibility_reviewed
    }
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct PairedBootstrapReviewRequest {
    pub project_id: String,
    pub result_path: String,
    pub result_sha256: String,
    pub action: PairedBootstrapReviewAction,
    pub checklist: PairedBootstrapChecklist,
    pub actor_label: String,
    pub rationale: String,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct PairedBootstrapReviewEvent {
    pub schema_version: u32,
    pub sequence: u64,
    pub review_id: String,
    pub project_id: String,
    pub execution_id: String,
    pub action: PairedBootstrapReviewAction,
    pub result_path: String,
    pub result_sha256: String,
    pub related_artifacts: Vec<crate::heor_approval::ArtifactBinding>,
    pub checklist: PairedBootstrapChecklist,
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
pub struct PairedBootstrapReviewLog {
    pub events: Vec<PairedBootstrapReviewEvent>,
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
    execution_id: &'a str,
    action: PairedBootstrapReviewAction,
    status: &'static str,
    result_path: &'a str,
    result_sha256: &'a str,
    related_artifacts: &'a [crate::heor_approval::ArtifactBinding],
    checklist: &'a PairedBootstrapChecklist,
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
    execution_id: &'a str,
    action: PairedBootstrapReviewAction,
    result_path: &'a str,
    result_sha256: &'a str,
    related_artifacts: &'a [crate::heor_approval::ArtifactBinding],
    checklist: &'a PairedBootstrapChecklist,
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
        .join("paired-bootstrap-method-reviews"))
}

fn review_log_path(root: &Path, project_id: &str) -> Result<PathBuf, String> {
    if !validate_project_id(project_id) {
        return Err("projectId must be a safe identifier".into());
    }
    Ok(root.join(format!("{project_id}.jsonl")))
}

fn hash_review_event(event: &PairedBootstrapReviewEvent) -> Result<String, String> {
    let raw = serde_json::to_vec(&ReviewHashPayload {
        schema_version: event.schema_version,
        sequence: event.sequence,
        review_id: &event.review_id,
        project_id: &event.project_id,
        execution_id: &event.execution_id,
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

fn snapshot_bytes(event: &PairedBootstrapReviewEvent) -> Result<Vec<u8>, String> {
    let snapshot = ReviewSnapshot {
        schema_version: REVIEW_SCHEMA,
        review_id: &event.review_id,
        project_id: &event.project_id,
        execution_id: &event.execution_id,
        action: event.action,
        status: if event.action == PairedBootstrapReviewAction::Accept {
            "accepted_for_joint_packaging"
        } else {
            "rejected_for_joint_packaging"
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
    audit: &PairedBootstrapAudit,
) -> Result<Vec<crate::heor_approval::ArtifactBinding>, String> {
    let result_path = resolve_file(workspace, &audit.result_path, "paired bootstrap result")?;
    let result_raw = read_capped(&result_path, MAX_JSON_BYTES, "paired bootstrap result")?;
    let manifest: serde_json::Value =
        serde_json::from_slice(&result_raw).map_err(|error| error.to_string())?;
    let mut bindings = vec![crate::heor_approval::ArtifactBinding {
        path: audit.result_path.clone(),
        sha256: audit.result_sha256.clone().unwrap_or_default(),
    }];
    let add = |bindings: &mut Vec<crate::heor_approval::ArtifactBinding>,
               path: Option<&serde_json::Value>,
               hash: Option<&serde_json::Value>| {
        if let (Some(path), Some(hash)) = (text(path), text(hash)) {
            bindings.push(crate::heor_approval::ArtifactBinding {
                path: path.into(),
                sha256: hash.into(),
            });
        }
    };
    add(
        &mut bindings,
        manifest.pointer("/request/path"),
        manifest.pointer("/request/sha256"),
    );
    for field in ["analysis", "partitioned_survival", "curve_materializations"] {
        add(
            &mut bindings,
            manifest.pointer(&format!("/{field}/path")),
            manifest.pointer(&format!("/{field}/sha256")),
        );
    }
    for field in ["resampling_plan", "replicate_results", "candidate_draws"] {
        add(
            &mut bindings,
            manifest.pointer(&format!("/bootstrap/{field}/path")),
            manifest.pointer(&format!("/bootstrap/{field}/sha256")),
        );
    }
    add(
        &mut bindings,
        manifest.pointer("/runtime/adapter_path"),
        manifest.pointer("/runtime/adapter_sha256"),
    );
    let mut seen = HashSet::new();
    bindings.retain(|binding| seen.insert(binding.path.clone()));
    if bindings.len() != 9 || bindings.iter().any(|binding| !is_sha256(&binding.sha256)) {
        return Err("paired bootstrap review could not bind the complete execution graph".into());
    }
    for binding in &bindings {
        let path = resolve_file(workspace, &binding.path, "review artifact")?;
        let raw = read_capped(&path, MAX_RESULT_BYTES, "review artifact")?;
        if sha256(&raw) != binding.sha256 {
            return Err("paired bootstrap review artifact changed during submission".into());
        }
    }
    Ok(bindings)
}

fn read_review_events(
    root: &Path,
    workspace: &Path,
    project_id: &str,
) -> Result<Vec<PairedBootstrapReviewEvent>, String> {
    let path = review_log_path(root, project_id)?;
    let raw = match std::fs::read(&path) {
        Ok(raw) => raw,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("paired bootstrap review log unavailable: {error}")),
    };
    if raw.len() > 4 * 1024 * 1024 {
        return Err("paired bootstrap review log exceeds 4 MB".into());
    }
    let mut events = Vec::new();
    let mut previous_hash = None;
    for (index, line) in raw
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
        .enumerate()
    {
        if events.len() >= 2_000 {
            return Err("paired bootstrap review log exceeds 2,000 events".into());
        }
        let event: PairedBootstrapReviewEvent = serde_json::from_slice(line)
            .map_err(|error| format!("review log line {} is invalid: {error}", index + 1))?;
        if event.schema_version != REVIEW_EVENT_SCHEMA
            || event.sequence != index as u64 + 1
            || event.project_id != project_id
            || !safe_id(&event.execution_id)
            || event.review_id.len() != 32
            || !event.review_id.bytes().all(|byte| byte.is_ascii_hexdigit())
            || !is_sha256(&event.result_sha256)
            || !is_sha256(&event.record_sha256)
            || !is_sha256(&event.event_hash)
            || event.assurance != REVIEW_ASSURANCE
            || event.previous_hash != previous_hash
            || !validate_review_text(&event.actor_label, 120)
            || !validate_review_text(&event.rationale, 2_000)
        {
            return Err(format!(
                "review log line {} violates the event contract",
                index + 1
            ));
        }
        if hash_review_event(&event)? != event.event_hash {
            return Err(format!("review log line {} hash is invalid", index + 1));
        }
        let record = resolve_file(workspace, &event.record_path, "method review record")?;
        let record_raw = read_capped(&record, MAX_JSON_BYTES, "method review record")?;
        if sha256(&record_raw) != event.record_sha256 || record_raw != snapshot_bytes(&event)? {
            return Err(format!(
                "review log line {} record binding is invalid",
                index + 1
            ));
        }
        previous_hash = Some(event.event_hash.clone());
        events.push(event);
    }
    Ok(events)
}

fn review_log(events: Vec<PairedBootstrapReviewEvent>) -> PairedBootstrapReviewLog {
    PairedBootstrapReviewLog {
        chain_head: events.last().map(|event| event.event_hash.clone()),
        events,
        integrity: "verified_unanchored_sha256_chain",
        identity_assurance: REVIEW_ASSURANCE,
    }
}

fn latest_review_for_execution<'a>(
    events: &'a [PairedBootstrapReviewEvent],
    execution_id: &str,
) -> Option<&'a PairedBootstrapReviewEvent> {
    events
        .iter()
        .rev()
        .find(|event| event.execution_id == execution_id)
}

fn write_review_record(workspace: &Path, event: &PairedBootstrapReviewEvent) -> Result<(), String> {
    let relative = Path::new(&event.record_path);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err("method review record path is unsafe".into());
    }
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let target = root.join(relative);
    let parent = target
        .parent()
        .ok_or_else(|| "method review record parent is invalid".to_string())?;
    let heor = root.join("heor");
    if std::fs::symlink_metadata(&heor).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err("heor directory must not be a symlink".into());
    }
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("method review directory failed: {error}"))?;
    if std::fs::symlink_metadata(parent).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err("method review directory must not be a symlink".into());
    }
    let raw = snapshot_bytes(event)?;
    if sha256(&raw) != event.record_sha256 {
        return Err("method review record hash changed before write".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&target)
        .map_err(|error| format!("method review record write failed: {error}"))?;
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("method review record write failed: {error}"))
}

fn append_review_event(root: &Path, event: &PairedBootstrapReviewEvent) -> Result<(), String> {
    let path = review_log_path(root, &event.project_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("review log directory failed: {error}"))?;
        crate::runtime::tighten_private(parent);
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|error| format!("review log open failed: {error}"))?;
    crate::runtime::tighten_private(&path);
    let line = serde_json::to_string(event).map_err(|error| error.to_string())?;
    writeln!(file, "{line}")
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("review log append failed: {error}"))
}

#[tauri::command(async)]
pub fn append_heor_paired_bootstrap_review(
    app: AppHandle,
    state: tauri::State<PairedBootstrapReviewState>,
    request: PairedBootstrapReviewRequest,
) -> Result<PairedBootstrapReviewEvent, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "paired bootstrap review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != request.project_id {
        return Err("review projectId does not match the current project".into());
    }
    if !validate_review_text(&request.actor_label, 120)
        || !validate_review_text(&request.rationale, 2_000)
        || !is_sha256(&request.result_sha256)
    {
        return Err("review actor, rationale, or result hash is invalid".into());
    }
    let audit = audit_paired_bootstrap_path(&workspace, &request.result_path);
    if audit.result_sha256.as_deref() != Some(&request.result_sha256) {
        return Err("review must target the exact current result manifest".into());
    }
    if request.action == PairedBootstrapReviewAction::Accept
        && (!audit.reviewable || !request.checklist.all_confirmed())
    {
        return Err(
            "acceptance requires a complete native audit and every Human method checklist item"
                .into(),
        );
    }
    if audit.execution_id.is_empty() {
        return Err("review result has no valid execution identity".into());
    }
    let root = review_root(&app)?;
    let events = read_review_events(&root, &workspace, &request.project_id)?;
    if latest_review_for_execution(&events, &audit.execution_id).is_some_and(|event| {
        event.result_sha256 == request.result_sha256 && event.action == request.action
    }) {
        return Err(
            "the latest method review already records this action for the exact result".into(),
        );
    }
    let related_artifacts = collect_related_artifacts(&workspace, &audit)?;
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_secs();
    let review_id = crate::runtime::random_hex(16);
    let record_path = format!(
        "heor/paired-survival-bootstrap-reviews/{}-{review_id}.json",
        audit.execution_id
    );
    let mut event = PairedBootstrapReviewEvent {
        schema_version: REVIEW_EVENT_SCHEMA,
        sequence: events.len() as u64 + 1,
        review_id,
        project_id: request.project_id,
        execution_id: audit.execution_id,
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
    if let Err(error) = append_review_event(&root, &event) {
        let _ = std::fs::remove_file(workspace.join(&event.record_path));
        return Err(error);
    }
    crate::git_snapshot::commit_best_effort(&workspace, "Record paired bootstrap method review");
    Ok(event)
}

#[tauri::command(async)]
pub fn list_heor_paired_bootstrap_reviews(
    app: AppHandle,
    state: tauri::State<PairedBootstrapReviewState>,
    project_id: String,
) -> Result<PairedBootstrapReviewLog, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "paired bootstrap review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("review projectId does not match the current project".into());
    }
    Ok(review_log(read_review_events(
        &review_root(&app)?,
        &workspace,
        &project_id,
    )?))
}

struct ReviewExpectation<'a> {
    review_id: &'a str,
    record_path: &'a str,
    record_sha256: &'a str,
    result_path: &'a str,
    result_sha256: &'a str,
}

fn current_accepted_review(
    app: &AppHandle,
    workspace: &Path,
    project_id: &str,
    expected: &ReviewExpectation<'_>,
) -> Result<crate::heor_approval::ArtifactBinding, String> {
    let events = read_review_events(&review_root(app)?, workspace, project_id)?;
    let Some(target) = events
        .iter()
        .find(|event| event.review_id == expected.review_id)
    else {
        return Err(
            "paired bootstrap joint packaging requires an app-owned Human method review".into(),
        );
    };
    let Some(event) = latest_review_for_execution(&events, &target.execution_id) else {
        return Err(
            "paired bootstrap joint packaging requires an app-owned Human method review".into(),
        );
    };
    if event.action != PairedBootstrapReviewAction::Accept
        || event.review_id != expected.review_id
        || event.record_path != expected.record_path
        || event.record_sha256 != expected.record_sha256
        || event.result_path != expected.result_path
        || event.result_sha256 != expected.result_sha256
        || !event.checklist.all_confirmed()
    {
        return Err(
            "paired bootstrap method review is missing, rejected, stale, or does not bind the canonical joint manifest"
                .into(),
        );
    }
    Ok(crate::heor_approval::ArtifactBinding {
        path: event.record_path.clone(),
        sha256: event.record_sha256.clone(),
    })
}

pub(crate) fn require_current_review_for_joint_manifest(
    app: &AppHandle,
    workspace: &Path,
    project_id: &str,
) -> Result<Option<crate::heor_approval::ArtifactBinding>, String> {
    let relative = crate::heor_joint_survival_uncertainty::MANIFEST_PATH;
    if !workspace.join(relative).exists() {
        return Ok(None);
    }
    let path = resolve_file(workspace, relative, "joint survival manifest")?;
    let raw = read_capped(&path, MAX_JSON_BYTES, "joint survival manifest")?;
    let manifest: serde_json::Value = serde_json::from_slice(&raw)
        .map_err(|error| format!("joint survival manifest is invalid JSON: {error}"))?;
    if text(manifest.pointer("/generation/method")) != Some("paired_patient_bootstrap") {
        return Ok(None);
    }
    if text(manifest.get("schema_version")) != Some("0.5.0") {
        return Err(
            "paired bootstrap joint packaging requires manifest schema 0.5.0 and an app-owned Human method review"
                .into(),
        );
    }
    let review = manifest
        .pointer("/generation/method_review")
        .ok_or_else(|| "paired bootstrap joint manifest omits method_review".to_string())?;
    let review_id = text(review.get("review_id"))
        .ok_or_else(|| "paired bootstrap method_review.review_id is invalid".to_string())?;
    let record_path = text(review.get("record_path"))
        .ok_or_else(|| "paired bootstrap method_review.record_path is invalid".to_string())?;
    let record_sha = text(review.get("record_sha256"))
        .ok_or_else(|| "paired bootstrap method_review.record_sha256 is invalid".to_string())?;
    let result_path = text(review.get("result_path"))
        .ok_or_else(|| "paired bootstrap method_review.result_path is invalid".to_string())?;
    let result_sha = text(review.get("result_sha256"))
        .ok_or_else(|| "paired bootstrap method_review.result_sha256 is invalid".to_string())?;
    let expected = ReviewExpectation {
        review_id,
        record_path,
        record_sha256: record_sha,
        result_path,
        result_sha256: result_sha,
    };
    current_accepted_review(app, workspace, project_id, &expected).map(Some)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static SEQUENCE: AtomicU64 = AtomicU64::new(0);

    fn workspace(tag: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "ai4heor-paired-native-{tag}-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        root
    }

    fn write(root: &Path, relative: &str, raw: &[u8]) -> String {
        let path = root.join(relative);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, raw).unwrap();
        sha256(raw)
    }

    fn write_json(root: &Path, relative: &str, value: &serde_json::Value) -> String {
        let mut raw = serde_json::to_vec_pretty(value).unwrap();
        raw.push(b'\n');
        write(root, relative, &raw)
    }

    fn fixture(root: &Path) -> String {
        let analysis = serde_json::json!({
            "schema_version": "0.15.0",
            "analysis_id": "analysis-native",
            "strategy_order": ["standard", "new_treatment"],
            "cycles": 1,
            "cycle_length_years": 1.0
        });
        let analysis_sha = write_json(root, "heor/analysis-plan.json", &analysis);
        let psm = serde_json::json!({
            "schema_version": "0.7.0",
            "psm_id": "psm-native",
            "analysis_id": "analysis-native"
        });
        let psm_sha = write_json(root, "heor/partitioned-survival-plan.json", &psm);
        let curves = [
            ("standard", "pfs", "exponential"),
            ("standard", "os", "exponential"),
            ("new_treatment", "pfs", "exponential"),
            ("new_treatment", "os", "exponential"),
        ];
        let materializations = serde_json::json!({
            "schema_version": "0.2.0",
            "materialization_id": "material-native",
            "curves": curves.iter().map(|(strategy, endpoint, family)| serde_json::json!({
                "target_path": format!("partitioned_survival.strategies.{strategy}.{endpoint}"),
                "strategy_id": strategy,
                "endpoint": endpoint,
                "family": family
            })).collect::<Vec<_>>()
        });
        let material_sha = write_json(
            root,
            "heor/survival-curve-materializations.json",
            &materializations,
        );
        let source = b"subject_id,strategy_id,pfs_time,pfs_event,os_time,os_event\ns1,standard,1,1,2,1\ns2,standard,1.5,1,2.5,1\nn1,new_treatment,1,1,2,1\nn2,new_treatment,1.5,1,2.5,1\n";
        let source_sha = write(root, "heor/data/paired.csv", source);
        let curve_requests = curves
            .iter()
            .map(|(strategy, endpoint, family)| {
                serde_json::json!({
                    "target_path": format!("partitioned_survival.strategies.{strategy}.{endpoint}"),
                    "strategy_id": strategy,
                    "endpoint": endpoint,
                    "family": family
                })
            })
            .collect::<Vec<_>>();
        let request = serde_json::json!({
            "schema_version": "0.1.0",
            "execution_id": "native-smoke",
            "status": "ready_for_execution",
            "analysis": {"path": "heor/analysis-plan.json", "sha256": analysis_sha, "id": "analysis-native"},
            "partitioned_survival": {"path": "heor/partitioned-survival-plan.json", "sha256": psm_sha, "id": "psm-native"},
            "curve_materializations": {"path": "heor/survival-curve-materializations.json", "sha256": material_sha, "id": "material-native"},
            "source_data": {
                "classification": "restricted",
                "execution_boundary": "local_only",
                "format": "csv",
                "path": "heor/data/paired.csv",
                "sha256": source_sha,
                "columns": ["subject_id", "strategy_id", "pfs_time", "pfs_event", "os_time", "os_event"],
                "row_count": 4,
                "strategy_counts": {"standard": 2, "new_treatment": 2},
                "contains_direct_identifiers": false,
                "subject_identifier": "pseudonymous_unique",
                "time_unit": "years",
                "missing_policy": "reject",
                "additional_columns": "reject"
            },
            "bootstrap": {
                "method": "ordinary_nonparametric_case_resampling",
                "iterations": 1000,
                "seed": 42,
                "rng": RNG,
                "rng_version": RNG_VERSION,
                "resampling_unit": "whole_subject_row",
                "strategy_resampling_design": "stratified_independent_parallel_arms",
                "preserve_strategy_sample_sizes": true,
                "endpoint_sampling": "same_subject_indices_for_pfs_and_os",
                "between_strategy_assumption": "conditional_independence_given_parallel_arm_design",
                "curves": curve_requests,
                "time_grid_years": [0.0, 1.0],
                "cross_implementation_tolerance": 1e-8
            },
            "runtime": {"expected_packages": {"survHE": "2.0.51", "flexsurv": "2.3.2", "survival": "3.8.6"}},
            "output": {"directory": "heor/paired-survival-bootstrap-executions/native-smoke", "overwrite_policy": "fail_if_exists"},
            "limitations": ["Synthetic unit fixture only."],
            "human_gate": {"state": "awaiting_execution_authorization", "required_action": "approve_local_paired_survival_bootstrap_command"}
        });
        let request_sha = write_json(
            root,
            "heor/paired-survival-bootstrap-request.json",
            &request,
        );
        let output = "heor/paired-survival-bootstrap-executions/native-smoke";
        let adapter_sha = write(
            root,
            &format!("{output}/paired_survival_bootstrap_adapter.R"),
            ADAPTER_BYTES,
        );
        let session_sha = write(root, &format!("{output}/session-info.txt"), b"R session\n");
        let log_sha = write(root, &format!("{output}/execution.log"), b"complete\n");
        let mut plan = String::from("replicate_index,row_1,row_2,row_3,row_4\n");
        let positions = [vec![0, 1], vec![2, 3]];
        let mut rng = Pcg32::new(42);
        for replicate in 1..=1000 {
            let mut frequency = [0_u32; 4];
            for arm in &positions {
                for _ in arm {
                    frequency[arm[rng.bounded(arm.len() as u32) as usize]] += 1;
                }
            }
            plan.push_str(&format!(
                "{replicate},{},{},{},{}\n",
                frequency[0], frequency[1], frequency[2], frequency[3]
            ));
        }
        let plan_sha = write(
            root,
            &format!("{output}/bootstrap-plan.csv"),
            plan.as_bytes(),
        );
        let rates = [0.2_f64, 0.1, 0.18, 0.09];
        let mut replicate_raw = Vec::new();
        let mut candidate_raw = Vec::new();
        for replicate in 1..=1000 {
            let row_curves = curves
                .iter()
                .zip(rates)
                .map(|((strategy, endpoint, family), rate)| {
                    serde_json::json!({
                        "target_path": format!("partitioned_survival.strategies.{strategy}.{endpoint}"),
                        "strategy_id": strategy,
                        "endpoint": endpoint,
                        "family": family,
                        "status": "converged",
                        "parameterization": "exponential_rate",
                        "parameters": [{"name": "rate", "estimate": rate}],
                        "survival": [1.0, (-rate).exp()],
                        "warnings": [],
                        "crosscheck": {"status": "passed", "max_abs_survival_error": 0.0}
                    })
                })
                .collect::<Vec<_>>();
            let replicate_row = serde_json::json!({
                "replicate_index": replicate,
                "status": "complete",
                "curves": row_curves,
                "failure_reasons": []
            });
            serde_json::to_writer(&mut replicate_raw, &replicate_row).unwrap();
            replicate_raw.push(b'\n');
            let candidate = serde_json::json!({
                "draw_index": replicate,
                "curves": replicate_row["curves"].as_array().unwrap().iter().map(|curve| curve["survival"].clone()).collect::<Vec<_>>()
            });
            serde_json::to_writer(&mut candidate_raw, &candidate).unwrap();
            candidate_raw.push(b'\n');
        }
        let replicate_sha = write(
            root,
            &format!("{output}/replicate-results.jsonl"),
            &replicate_raw,
        );
        let candidate_sha = write(
            root,
            &format!("{output}/joint-survival-draws.candidate.jsonl"),
            &candidate_raw,
        );
        let manifest = serde_json::json!({
            "schema_version": "0.1.0",
            "execution_id": "native-smoke",
            "status": "complete",
            "request": {"path": "heor/paired-survival-bootstrap-request.json", "sha256": request_sha},
            "analysis": request["analysis"],
            "partitioned_survival": request["partitioned_survival"],
            "curve_materializations": request["curve_materializations"],
            "source_data": {"path": "heor/data/paired.csv", "sha256": source_sha, "row_count": 4, "strategy_counts": {"standard": 2, "new_treatment": 2}},
            "runtime": {
                "backend": "survHE", "method": "paired_patient_bootstrap", "r_version": "4.6.1",
                "rscript_sha256": "a".repeat(64),
                "package_versions": request["runtime"]["expected_packages"],
                "adapter_path": format!("{output}/paired_survival_bootstrap_adapter.R"), "adapter_sha256": adapter_sha,
                "session_info_path": format!("{output}/session-info.txt"), "session_info_sha256": session_sha,
                "execution_log_path": format!("{output}/execution.log"), "execution_log_sha256": log_sha
            },
            "bootstrap": {
                "method": request["bootstrap"]["method"], "rng": RNG, "rng_version": RNG_VERSION, "seed": 42, "iterations": 1000,
                "resampling_unit": "whole_subject_row", "strategy_resampling_design": "stratified_independent_parallel_arms",
                "endpoint_sampling": "same_subject_indices_for_pfs_and_os", "between_strategy_assumption": "conditional_independence_given_parallel_arm_design",
                "evaluator": {"id": EVALUATOR, "sha256": sha256(EVALUATOR_BYTES)},
                "curve_order": curves.iter().map(|(strategy, endpoint, _)| format!("partitioned_survival.strategies.{strategy}.{endpoint}")).collect::<Vec<_>>(),
                "time_grid_years": [0.0, 1.0],
                "resampling_plan": {"path": format!("{output}/bootstrap-plan.csv"), "sha256": plan_sha, "format": PLAN_FORMAT, "row_count": 1000},
                "replicate_results": {"path": format!("{output}/replicate-results.jsonl"), "sha256": replicate_sha, "format": REPLICATE_FORMAT, "row_count": 1000},
                "candidate_draws": {"path": format!("{output}/joint-survival-draws.candidate.jsonl"), "sha256": candidate_sha, "format": DRAW_FORMAT, "row_count": 1000},
                "completed_replicates": 1000, "failed_replicates": 0,
                "cross_implementation_complete": true, "curve_coherence_complete": true, "eligible_for_joint_packaging": true
            },
            "limitations": ["Synthetic unit fixture only.", "Human review required."],
            "human_gate": {"state": "awaiting_bootstrap_method_review", "required_action": "review_paired_bootstrap_before_joint_packaging"}
        });
        let result = format!("{output}/result-manifest.json");
        write_json(root, &result, &manifest);
        result
    }

    #[test]
    fn native_audit_replays_complete_paired_execution() {
        let root = workspace("complete");
        let result = fixture(&root);
        let audit = audit_paired_bootstrap_path(&root, &result);
        assert!(audit.reviewable, "{:?}", audit.errors);
        assert_eq!(audit.completed_replicates, 1000);
        assert_eq!(audit.failed_replicates, 0);
        assert!(audit.dependence_preserved);
        assert_eq!(audit.strategy_counts["standard"], 2);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn native_audit_rejects_candidate_drift_and_symlinked_output() {
        let root = workspace("drift");
        let result = fixture(&root);
        let manifest_path = root.join(&result);
        let mut manifest: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&manifest_path).unwrap()).unwrap();
        let candidate_path = root.join(
            manifest
                .pointer("/bootstrap/candidate_draws/path")
                .unwrap()
                .as_str()
                .unwrap(),
        );
        let mut lines = std::fs::read_to_string(&candidate_path).unwrap();
        lines = lines.replacen("0.8187307530779818", "0.7", 1);
        std::fs::write(&candidate_path, &lines).unwrap();
        manifest["bootstrap"]["candidate_draws"]["sha256"] =
            serde_json::json!(sha256(lines.as_bytes()));
        write_json(&root, &result, &manifest);
        let drift = audit_paired_bootstrap_path(&root, &result);
        assert!(!drift.reviewable);
        assert!(drift
            .errors
            .iter()
            .any(|error| error.contains("candidate draw")));

        #[cfg(unix)]
        {
            use std::os::unix::fs::symlink;
            let symlink_root = workspace("symlink");
            let external = workspace("external");
            std::fs::create_dir_all(symlink_root.join("heor")).unwrap();
            symlink(
                &external,
                symlink_root.join("heor/paired-survival-bootstrap-executions"),
            )
            .unwrap();
            let audit = audit_paired_bootstrap_path(
                &symlink_root,
                "heor/paired-survival-bootstrap-executions/native-smoke/result-manifest.json",
            );
            assert!(audit.errors.iter().any(|error| error.contains("symlink")));
            std::fs::remove_dir_all(symlink_root).unwrap();
            std::fs::remove_dir_all(external).unwrap();
        }
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn review_event_hash_and_snapshot_bind_the_exact_execution() {
        let root = workspace("review");
        let result = fixture(&root);
        let audit = audit_paired_bootstrap_path(&root, &result);
        let checklist = PairedBootstrapChecklist {
            resampling_design_reviewed: true,
            endpoints_and_censoring_reviewed: true,
            selected_families_reviewed: true,
            failures_and_convergence_reviewed: true,
            follow_up_and_extrapolation_reviewed: true,
            parallel_arm_assumption_reviewed: true,
            clinical_plausibility_reviewed: true,
        };
        let mut event = PairedBootstrapReviewEvent {
            schema_version: 1,
            sequence: 1,
            review_id: "a".repeat(32),
            project_id: "project-1".into(),
            execution_id: audit.execution_id.clone(),
            action: PairedBootstrapReviewAction::Accept,
            result_path: result,
            result_sha256: audit.result_sha256.clone().unwrap(),
            related_artifacts: collect_related_artifacts(&root, &audit).unwrap(),
            checklist,
            actor_label: "Qualified reviewer".into(),
            rationale: "Reviewed design, endpoints, models, convergence, and plausibility.".into(),
            timestamp: 1_700_000_000,
            record_path: "heor/paired-survival-bootstrap-reviews/native-smoke-a.json".into(),
            record_sha256: String::new(),
            assurance: REVIEW_ASSURANCE.into(),
            previous_hash: None,
            event_hash: String::new(),
        };
        event.record_sha256 = sha256(&snapshot_bytes(&event).unwrap());
        event.event_hash = hash_review_event(&event).unwrap();
        write_review_record(&root, &event).unwrap();
        let log_root = root.join("app-data");
        append_review_event(&log_root, &event).unwrap();
        let events = read_review_events(&log_root, &root, "project-1").unwrap();
        assert_eq!(events, vec![event.clone()]);
        let mut unrelated = event.clone();
        unrelated.execution_id = "other-execution".into();
        unrelated.action = PairedBootstrapReviewAction::Reject;
        let unrelated_events = vec![event.clone(), unrelated];
        assert_eq!(
            latest_review_for_execution(&unrelated_events, &event.execution_id)
                .unwrap()
                .action,
            PairedBootstrapReviewAction::Accept
        );
        let mut rejection = event.clone();
        rejection.review_id = "b".repeat(32);
        rejection.action = PairedBootstrapReviewAction::Reject;
        let superseded_events = vec![event.clone(), rejection];
        assert_eq!(
            latest_review_for_execution(&superseded_events, &event.execution_id)
                .unwrap()
                .action,
            PairedBootstrapReviewAction::Reject
        );
        let mut record = std::fs::read(root.join(&event.record_path)).unwrap();
        record.push(b' ');
        std::fs::write(root.join(&event.record_path), record).unwrap();
        assert!(read_review_events(&log_root, &root, "project-1").is_err());
        std::fs::remove_dir_all(root).unwrap();
    }
}
