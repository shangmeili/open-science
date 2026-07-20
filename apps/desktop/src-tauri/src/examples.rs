// Built-in AI4HEOR example projects: bounded, explicitly synthetic teaching
// inputs copied into the workspace on demand. They demonstrate researcher-led
// HEOR workflows and must never be presented as clinical or economic evidence.
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{path::BaseDirectory, AppHandle, Manager};

use crate::runtime::workspace_dir;

/// Bundled example projects; the command rejects anything else.
const EXAMPLES: &[&str] = &["heor-cost-effectiveness"];
const TEACHING_EXAMPLE: &str = "heor-cost-effectiveness";
const EXECUTION_INPUTS: &[&str] = &[
    "run_analysis.py",
    "inputs/analysis-spec.json",
    "inputs/model-inputs.csv",
    "expected/base-case-result.json",
];
const RESULT_CAP_BYTES: u64 = 10 * 1024 * 1024;
static NEXT_TEMP_ID: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TeachingExampleOutput {
    path: String,
    sha256: String,
    scenario: String,
    scenario_value: Option<f64>,
    incremental_cost_per_person: f64,
    incremental_qalys_per_person: f64,
    icer_per_qaly: Option<f64>,
    incremental_net_monetary_benefit_per_person: f64,
}

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TeachingExampleRunResult {
    schema: &'static str,
    run_id: String,
    interpreter_source: &'static str,
    expected_result_sha256: String,
    base_case: TeachingExampleOutput,
    sensitivity_low: TeachingExampleOutput,
    sensitivity_high: TeachingExampleOutput,
    limitations: Vec<String>,
}

struct TeachingExecution {
    interpreter_source: &'static str,
    expected_result_sha256: String,
    base_case: TeachingExampleOutput,
    sensitivity_low: TeachingExampleOutput,
    sensitivity_high: TeachingExampleOutput,
    log: String,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

fn read_regular_file(path: &Path, label: &str) -> Result<Vec<u8>, String> {
    let metadata = std::fs::symlink_metadata(path)
        .map_err(|error| format!("{label} is unavailable: {error}"))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(format!("{label} must be a regular file"));
    }
    if metadata.len() > RESULT_CAP_BYTES {
        return Err(format!("{label} exceeds the 10 MB limit"));
    }
    std::fs::read(path).map_err(|error| format!("{label} could not be read: {error}"))
}

fn verify_installed_inputs(resource: &Path, installed: &Path) -> Result<(), String> {
    for relative in EXECUTION_INPUTS {
        let source = read_regular_file(&resource.join(relative), relative)?;
        let target = read_regular_file(&installed.join(relative), relative)?;
        if source != target {
            return Err(format!(
                "{relative} differs from the bundled teaching example; keep the edited copy, then install a fresh example in another project before using the fixed local run"
            ));
        }
    }
    Ok(())
}

fn prepare_output_directory(example: &Path) -> Result<PathBuf, String> {
    let output = example.join("outputs");
    match std::fs::symlink_metadata(&output) {
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_dir() => {
            return Err("teaching example outputs must be a regular local directory".into())
        }
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            std::fs::create_dir(&output)
                .map_err(|error| format!("teaching example output directory failed: {error}"))?;
        }
        Err(error) => return Err(format!("teaching example output directory failed: {error}")),
    }
    let example = example
        .canonicalize()
        .map_err(|error| format!("teaching example is unavailable: {error}"))?;
    let output = output
        .canonicalize()
        .map_err(|error| format!("teaching example output directory failed: {error}"))?;
    if !output.starts_with(&example) {
        return Err("teaching example output directory escapes the example".into());
    }
    Ok(output)
}

fn temporary_output(output: &Path, label: &str) -> PathBuf {
    output.join(format!(
        ".ai4heor-{label}-{}-{}.tmp",
        std::process::id(),
        NEXT_TEMP_ID.fetch_add(1, Ordering::Relaxed)
    ))
}

fn run_step(
    python: &str,
    example: &Path,
    arguments: &[String],
    label: &str,
) -> Result<String, String> {
    let output = crate::runtime::quiet_command(python)
        .args(arguments)
        .current_dir(example)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONNOUSERSITE", "1")
        .output()
        .map_err(|error| format!("{label} failed to start: {error}"))?;
    if output.stdout.len() > 200_000 || output.stderr.len() > 200_000 {
        return Err(format!("{label} output exceeds the audit-log limit"));
    }
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if !output.status.success() {
        return Err(if stderr.is_empty() {
            format!("{label} exited with {}", output.status)
        } else {
            stderr
        });
    }
    Ok(if stderr.is_empty() {
        stdout
    } else {
        format!("{stdout}\n{stderr}")
    })
}

fn number_at(value: &serde_json::Value, pointer: &str, label: &str) -> Result<f64, String> {
    value
        .pointer(pointer)
        .and_then(serde_json::Value::as_f64)
        .filter(|number| number.is_finite())
        .ok_or_else(|| format!("teaching result omitted {label}"))
}

fn summarize_result(
    raw: &[u8],
    path: &str,
    expected_scenario: &str,
    expected_value: Option<f64>,
) -> Result<TeachingExampleOutput, String> {
    let value: serde_json::Value = serde_json::from_slice(raw)
        .map_err(|error| format!("teaching result is invalid JSON: {error}"))?;
    if value.get("schema").and_then(serde_json::Value::as_str)
        != Some("ai4heor-teaching-cea-result/v1")
    {
        return Err("teaching result has an unsupported schema".into());
    }
    let scenario = value
        .pointer("/scenario/type")
        .and_then(serde_json::Value::as_str)
        .ok_or("teaching result omitted its scenario")?;
    if scenario != expected_scenario {
        return Err("teaching result scenario does not match the requested run".into());
    }
    let scenario_value = value
        .pointer("/scenario/value")
        .and_then(serde_json::Value::as_f64);
    if scenario_value != expected_value {
        return Err(
            "teaching result sensitivity value does not match the declared scenario".into(),
        );
    }
    if !value
        .pointer("/incremental_vs_comparator/cost_effectiveness_claim")
        .is_some_and(serde_json::Value::is_null)
    {
        return Err("teaching result must not contain a cost-effectiveness claim".into());
    }
    Ok(TeachingExampleOutput {
        path: path.to_string(),
        sha256: sha256(raw),
        scenario: scenario.to_string(),
        scenario_value,
        incremental_cost_per_person: number_at(
            &value,
            "/incremental_vs_comparator/discounted_incremental_cost_per_person",
            "incremental cost",
        )?,
        incremental_qalys_per_person: number_at(
            &value,
            "/incremental_vs_comparator/discounted_incremental_qalys_per_person",
            "incremental QALYs",
        )?,
        icer_per_qaly: value
            .pointer("/incremental_vs_comparator/icer_per_qaly")
            .and_then(serde_json::Value::as_f64),
        incremental_net_monetary_benefit_per_person: number_at(
            &value,
            "/incremental_vs_comparator/incremental_net_monetary_benefit_per_person",
            "incremental net monetary benefit",
        )?,
    })
}

fn commit_output(temp: &Path, final_path: &Path) -> Result<Vec<u8>, String> {
    let raw = read_regular_file(temp, "temporary teaching result")?;
    match std::fs::symlink_metadata(final_path) {
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_file() => {
            let _ = std::fs::remove_file(temp);
            Err("an existing teaching result is not a regular file".into())
        }
        Ok(_) => {
            let existing = match read_regular_file(final_path, "existing teaching result") {
                Ok(existing) => existing,
                Err(error) => {
                    let _ = std::fs::remove_file(temp);
                    return Err(error);
                }
            };
            let _ = std::fs::remove_file(temp);
            if existing == raw {
                Ok(existing)
            } else {
                Err(format!(
                    "{} already exists with different bytes; AI4HEOR did not overwrite it",
                    final_path.display()
                ))
            }
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            std::fs::rename(temp, final_path)
                .map_err(|error| format!("teaching result commit failed: {error}"))?;
            Ok(raw)
        }
        Err(error) => {
            let _ = std::fs::remove_file(temp);
            Err(format!("teaching result inspection failed: {error}"))
        }
    }
}

fn execute_teaching_example(app: &AppHandle) -> Result<TeachingExecution, String> {
    let resource = app
        .path()
        .resolve(
            format!("examples/{TEACHING_EXAMPLE}"),
            BaseDirectory::Resource,
        )
        .map_err(|error| format!("teaching example resource missing: {error}"))?;
    let workspace = workspace_dir(app)?
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let installed = workspace.join(TEACHING_EXAMPLE);
    let metadata = std::fs::symlink_metadata(&installed)
        .map_err(|error| format!("teaching example is not installed: {error}"))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err("installed teaching example must be a regular local directory".into());
    }
    let installed = installed
        .canonicalize()
        .map_err(|error| format!("teaching example is unavailable: {error}"))?;
    if !installed.starts_with(&workspace) {
        return Err("installed teaching example escapes the current workspace".into());
    }
    verify_installed_inputs(&resource, &installed)?;
    let output = prepare_output_directory(&installed)?;
    let (python, interpreter_source) = crate::kernel::python_bin(app)?;
    let mut log = Vec::new();
    log.push(run_step(
        &python,
        &installed,
        &[
            "run_analysis.py".into(),
            "--check".into(),
            "expected/base-case-result.json".into(),
        ],
        "fixed-result verification",
    )?);

    let scenarios = [
        (
            "base-case",
            "base-case-result.json",
            None,
            "base_case",
            None,
        ),
        (
            "stable-cost-low",
            "stable-cost-low-result.json",
            Some("14400"),
            "one_way_sensitivity",
            Some(14_400.0),
        ),
        (
            "stable-cost-high",
            "stable-cost-high-result.json",
            Some("21600"),
            "one_way_sensitivity",
            Some(21_600.0),
        ),
    ];
    let mut summaries = Vec::new();
    for (label, filename, stable_cost, scenario, scenario_value) in scenarios {
        let temp = temporary_output(&output, label);
        let relative_temp = format!(
            "outputs/{}",
            temp.file_name()
                .ok_or("temporary teaching result has no filename")?
                .to_string_lossy()
        );
        let mut arguments = vec!["run_analysis.py".into(), "--output".into(), relative_temp];
        if let Some(stable_cost) = stable_cost {
            arguments.extend(["--intervention-stable-cost".into(), stable_cost.into()]);
        }
        let stdout = match run_step(&python, &installed, &arguments, label) {
            Ok(stdout) => stdout,
            Err(error) => {
                let _ = std::fs::remove_file(&temp);
                return Err(error);
            }
        };
        log.push(stdout);
        let final_path = output.join(filename);
        let raw = commit_output(&temp, &final_path)?;
        let relative = format!("{TEACHING_EXAMPLE}/outputs/{filename}");
        summaries.push(summarize_result(&raw, &relative, scenario, scenario_value)?);
    }
    let expected = read_regular_file(
        &installed.join("expected/base-case-result.json"),
        "expected teaching result",
    )?;
    if summaries[0].sha256 != sha256(&expected) {
        return Err("base-case output no longer matches the expected result".into());
    }
    let mut summaries = summaries.into_iter();
    Ok(TeachingExecution {
        interpreter_source,
        expected_result_sha256: sha256(&expected),
        base_case: summaries.next().ok_or("base-case result is missing")?,
        sensitivity_low: summaries
            .next()
            .ok_or("low sensitivity result is missing")?,
        sensitivity_high: summaries
            .next()
            .ok_or("high sensitivity result is missing")?,
        log: log.join("\n"),
    })
}

/// Copy `src` into `dst` recursively WITHOUT overwriting existing files — a
/// re-installed example must never clobber the user's edited copy.
pub(crate) fn copy_missing(src: &Path, dst: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(dst)?;
    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let to = dst.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_missing(&entry.path(), &to)?;
        } else if !to.exists() {
            std::fs::copy(entry.path(), &to)?;
        }
    }
    Ok(())
}

/// Copy a bundled example project into the workspace (idempotent, never
/// overwrites) and return its workspace-relative directory name.
#[tauri::command(async)]
pub fn install_example(app: AppHandle, name: String) -> Result<String, String> {
    if !EXAMPLES.contains(&name.as_str()) {
        return Err(format!("unknown example: {name}"));
    }
    let src = app
        .path()
        .resolve(format!("examples/{name}"), BaseDirectory::Resource)
        .map_err(|e| format!("example resource missing: {e}"))?;
    if !src.is_dir() {
        return Err("example not bundled in this build".into());
    }
    let dst = workspace_dir(&app)?.join(&name);
    copy_missing(&src, &dst).map_err(|e| format!("example install failed: {e}"))?;
    Ok(name)
}

/// Run only the exact installed deterministic teaching example after an
/// explicit auxiliary Human confirmation. The model provider is deliberately
/// absent from this boundary; all outputs remain synthetic teaching artifacts.
#[tauri::command(async)]
pub fn run_heor_teaching_example(
    app: AppHandle,
    run_state: tauri::State<crate::runs::RunState>,
    provenance_state: tauri::State<crate::provenance::ProvenanceState>,
    confirmed_teaching_assumptions: bool,
) -> Result<TeachingExampleRunResult, String> {
    if !confirmed_teaching_assumptions {
        return Err(
            "explicit confirmation of the synthetic teaching assumptions is required".into(),
        );
    }
    let started_at = now_ms();
    let execution = execute_teaching_example(&app);
    let ended_at = now_ms();
    let command = "python heor-cost-effectiveness/run_analysis.py --check expected/base-case-result.json && python heor-cost-effectiveness/run_analysis.py --output outputs/base-case-result.json && python heor-cost-effectiveness/run_analysis.py --intervention-stable-cost 14400 --output outputs/stable-cost-low-result.json && python heor-cost-effectiveness/run_analysis.py --intervention-stable-cost 21600 --output outputs/stable-cost-high-result.json";
    match execution {
        Ok(execution) => {
            let record = crate::runs::record_run(
                app,
                run_state,
                provenance_state,
                command.into(),
                Some(execution.log),
                Some(started_at),
                Some(ended_at),
                "ok".into(),
                Some("local".into()),
                None,
                None,
            )?;
            Ok(TeachingExampleRunResult {
                schema: "ai4heor-teaching-cea-desktop-run/v1",
                run_id: record.run_id,
                interpreter_source: execution.interpreter_source,
                expected_result_sha256: execution.expected_result_sha256,
                base_case: execution.base_case,
                sensitivity_low: execution.sensitivity_low,
                sensitivity_high: execution.sensitivity_high,
                limitations: vec![
                    "All inputs are synthetic teaching assumptions, not evidence.".into(),
                    "The illustrative threshold is not an official Chinese threshold.".into(),
                    "Reproducible calculation does not establish model validity.".into(),
                    "No cost-effectiveness, reimbursement, pricing, or policy conclusion is produced.".into(),
                ],
            })
        }
        Err(error) => {
            let _ = crate::runs::record_run(
                app,
                run_state,
                provenance_state,
                command.into(),
                Some(error.clone()),
                Some(started_at),
                Some(ended_at),
                "failed".into(),
                Some("local".into()),
                None,
                None,
            );
            Err(error)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{copy_missing, summarize_result, verify_installed_inputs, EXAMPLES};

    #[test]
    fn bundled_examples_are_heor_specific() {
        assert_eq!(EXAMPLES, &["heor-cost-effectiveness"]);
    }

    #[test]
    fn copies_recursively_but_never_overwrites() {
        let base = std::env::temp_dir().join(format!("ai4s-example-{}", std::process::id()));
        let src = base.join("src");
        let dst = base.join("dst");
        std::fs::create_dir_all(src.join("data")).unwrap();
        std::fs::write(src.join("README.md"), "bundled readme").unwrap();
        std::fs::write(src.join("data/x.csv"), "a,b\n1,2\n").unwrap();

        copy_missing(&src, &dst).unwrap();
        assert_eq!(
            std::fs::read_to_string(dst.join("data/x.csv")).unwrap(),
            "a,b\n1,2\n"
        );

        // The user edits a file; re-installing must keep the edit.
        std::fs::write(dst.join("README.md"), "user edited").unwrap();
        copy_missing(&src, &dst).unwrap();
        assert_eq!(
            std::fs::read_to_string(dst.join("README.md")).unwrap(),
            "user edited"
        );

        let _ = std::fs::remove_dir_all(base);
    }

    #[test]
    fn fixed_execution_rejects_changed_installed_inputs() {
        let base = std::env::temp_dir().join(format!(
            "ai4s-example-execution-{}-{}",
            std::process::id(),
            super::NEXT_TEMP_ID.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
        ));
        let resource = base.join("resource");
        let installed = base.join("installed");
        for relative in super::EXECUTION_INPUTS {
            let source = resource.join(relative);
            let target = installed.join(relative);
            std::fs::create_dir_all(source.parent().unwrap()).unwrap();
            std::fs::create_dir_all(target.parent().unwrap()).unwrap();
            std::fs::write(source, relative.as_bytes()).unwrap();
            std::fs::write(target, relative.as_bytes()).unwrap();
        }
        verify_installed_inputs(&resource, &installed).unwrap();
        std::fs::write(installed.join("inputs/model-inputs.csv"), b"changed").unwrap();
        let error = verify_installed_inputs(&resource, &installed).unwrap_err();
        assert!(error.contains("model-inputs.csv differs"));
        let _ = std::fs::remove_dir_all(base);
    }

    #[test]
    fn result_summary_requires_the_no_claim_boundary() {
        let mut value = serde_json::json!({
            "schema": "ai4heor-teaching-cea-result/v1",
            "scenario": {"type": "base_case"},
            "incremental_vs_comparator": {
                "discounted_incremental_cost_per_person": 10.0,
                "discounted_incremental_qalys_per_person": 0.5,
                "icer_per_qaly": 20.0,
                "incremental_net_monetary_benefit_per_person": 5.0,
                "cost_effectiveness_claim": null
            }
        });
        let raw = serde_json::to_vec(&value).unwrap();
        let summary = summarize_result(&raw, "result.json", "base_case", None).unwrap();
        assert_eq!(summary.icer_per_qaly, Some(20.0));
        value["incremental_vs_comparator"]["cost_effectiveness_claim"] =
            serde_json::json!("cost effective");
        let raw = serde_json::to_vec(&value).unwrap();
        assert!(summarize_result(&raw, "result.json", "base_case", None).is_err());
    }
}
