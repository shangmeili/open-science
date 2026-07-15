//! Independent app-owned audit for selected parametric survival materialization.
use sha2::{Digest, Sha256};
use std::path::Path;

pub const SURVIVAL_MATERIALIZATION_PATH: &str = "heor/survival-curve-materializations.json";
const ANALYSIS_PLAN_PATH: &str = "heor/analysis-plan.json";
const EVALUATOR_ID: &str = "ai4heor-parametric-survival";
const EVALUATOR_VERSION: &str = "0.1.0";
const TOLERANCE: f64 = 1e-12;

#[derive(Clone, Debug)]
pub struct SurvivalMaterializationAudit {
    pub complete: bool,
    pub sha256: String,
    pub curve_count: usize,
    pub artifact_bindings: Vec<crate::heor_approval::ArtifactBinding>,
    pub errors: Vec<String>,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn finite_positive(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
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

fn safe_relative_path(value: &str) -> bool {
    !value.is_empty()
        && !Path::new(value).is_absolute()
        && Path::new(value)
            .components()
            .all(|component| matches!(component, std::path::Component::Normal(_)))
}

fn exact_fields(value: &serde_json::Value, fields: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == fields.len() && fields.iter().all(|field| object.contains_key(*field))
    })
}

fn read_bound_json(
    workspace: &Path,
    path: Option<&serde_json::Value>,
    digest: Option<&serde_json::Value>,
    label: &str,
    errors: &mut Vec<String>,
) -> Option<(String, String, Vec<u8>, serde_json::Value)> {
    let Some(path) = path
        .and_then(serde_json::Value::as_str)
        .filter(|value| safe_relative_path(value))
    else {
        errors.push(format!("{label} path must stay inside the workspace"));
        return None;
    };
    let Some(digest) = digest
        .and_then(serde_json::Value::as_str)
        .filter(|_| valid_sha(digest))
    else {
        errors.push(format!("{label} requires a lowercase SHA-256"));
        return None;
    };
    let raw = match crate::heor_uncertainty::read_workspace_capped(workspace, path) {
        Ok(raw) => raw,
        Err(error) => {
            errors.push(format!("{label}: {error}"));
            return None;
        }
    };
    if sha256(&raw) != digest {
        errors.push(format!("{label} hash does not match current bytes"));
        return None;
    }
    let value = match serde_json::from_slice(&raw) {
        Ok(value) => value,
        Err(error) => {
            errors.push(format!("{label} is invalid JSON: {error}"));
            return None;
        }
    };
    Some((path.to_owned(), digest.to_owned(), raw, value))
}

fn evaluate(family: &str, parameters: &serde_json::Value, time: f64) -> Option<f64> {
    let cumulative_hazard = match family {
        "exponential" => finite_positive(parameters.get("rate_per_year"))? * time,
        "weibull" => {
            let shape = finite_positive(parameters.get("shape"))?;
            let scale = finite_positive(parameters.get("scale_years"))?;
            (time / scale).powf(shape)
        }
        _ => return None,
    };
    let survival = (-cumulative_hazard).exp();
    survival.is_finite().then_some(survival)
}

pub fn audit_survival_materializations(
    workspace: &Path,
    plan: &serde_json::Value,
    plan_raw: &[u8],
    psm: &serde_json::Value,
) -> SurvivalMaterializationAudit {
    let mut audit = SurvivalMaterializationAudit {
        complete: false,
        sha256: String::new(),
        curve_count: 0,
        artifact_bindings: Vec::new(),
        errors: Vec::new(),
    };
    let link = psm
        .get("curve_materializations")
        .unwrap_or(&serde_json::Value::Null);
    if !exact_fields(link, &["path", "content_sha256"])
        || link.get("path").and_then(serde_json::Value::as_str)
            != Some(SURVIVAL_MATERIALIZATION_PATH)
        || !valid_sha(link.get("content_sha256"))
    {
        audit.errors.push(format!(
            "curve_materializations must bind {SURVIVAL_MATERIALIZATION_PATH}"
        ));
        return audit;
    }
    let Some((manifest_path, manifest_sha, manifest_raw, manifest)) = read_bound_json(
        workspace,
        link.get("path"),
        link.get("content_sha256"),
        "survival materialization manifest",
        &mut audit.errors,
    ) else {
        return audit;
    };
    audit.sha256 = manifest_sha.clone();
    audit
        .artifact_bindings
        .push(crate::heor_approval::ArtifactBinding {
            path: manifest_path,
            sha256: manifest_sha,
        });
    if !exact_fields(
        &manifest,
        &[
            "schema_version",
            "materialization_id",
            "analysis_id",
            "psm_id",
            "status",
            "base_analysis",
            "time_origin",
            "time_unit",
            "evaluator",
            "curves",
            "limitations",
        ],
    ) {
        audit
            .errors
            .push("survival materialization fields are not the exact contract".into());
    }
    if manifest
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
    {
        audit
            .errors
            .push("survival materialization schema_version must be 0.1.0".into());
    }
    if manifest.get("status").and_then(serde_json::Value::as_str) != Some("ready_for_human_review")
    {
        audit
            .errors
            .push("survival materialization must be ready_for_human_review".into());
    }
    for field in ["materialization_id", "analysis_id", "psm_id", "time_origin"] {
        if !manifest
            .get(field)
            .and_then(serde_json::Value::as_str)
            .is_some_and(|value| !value.trim().is_empty())
        {
            audit
                .errors
                .push(format!("materialization {field} is required"));
        }
    }
    if manifest.get("analysis_id") != plan.get("analysis_id")
        || manifest.get("psm_id") != psm.get("psm_id")
        || manifest.get("time_origin") != psm.get("time_origin")
        || manifest
            .get("time_unit")
            .and_then(serde_json::Value::as_str)
            != Some("years")
    {
        audit
            .errors
            .push("survival materialization analysis, PSM, or time basis does not match".into());
    }
    if manifest
        .pointer("/base_analysis/path")
        .and_then(serde_json::Value::as_str)
        != Some(ANALYSIS_PLAN_PATH)
        || manifest
            .pointer("/base_analysis/content_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(sha256(plan_raw).as_str())
    {
        audit
            .errors
            .push("survival materialization base_analysis does not match analysis bytes".into());
    }
    if manifest
        .pointer("/evaluator/id")
        .and_then(serde_json::Value::as_str)
        != Some(EVALUATOR_ID)
        || manifest
            .pointer("/evaluator/version")
            .and_then(serde_json::Value::as_str)
            != Some(EVALUATOR_VERSION)
        || !exact_fields(
            manifest
                .get("evaluator")
                .unwrap_or(&serde_json::Value::Null),
            &["id", "version"],
        )
    {
        audit
            .errors
            .push("survival materialization evaluator is unsupported".into());
    }

    let cycles = plan.get("cycles").and_then(serde_json::Value::as_u64);
    let cycle_length = finite_positive(plan.get("cycle_length_years"));
    if !cycles.is_some_and(|value| (1..=10_000).contains(&value)) || cycle_length.is_none() {
        audit.errors.push("analysis cycle grid is invalid".into());
    }
    let strategy_order = plan
        .get("strategy_order")
        .and_then(serde_json::Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(serde_json::Value::as_str)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let expected_targets = strategy_order
        .iter()
        .flat_map(|strategy| [(*strategy, "pfs"), (*strategy, "os")])
        .collect::<Vec<_>>();
    let curves = manifest.get("curves").and_then(serde_json::Value::as_array);
    audit.curve_count = curves.map_or(0, Vec::len);
    if curves.map_or(0, Vec::len) != expected_targets.len() {
        audit.errors.push(
            "survival materialization must contain every strategy PFS/OS curve in order".into(),
        );
    }

    for (index, (strategy_id, endpoint)) in expected_targets.iter().enumerate() {
        let Some(curve) = curves.and_then(|items| items.get(index)) else {
            continue;
        };
        let target = format!("partitioned_survival.strategies.{strategy_id}.{endpoint}");
        if !exact_fields(
            curve,
            &[
                "target_path",
                "strategy_id",
                "endpoint",
                "review_binding",
                "fit_output_binding",
                "family",
                "parameterization",
                "parameters",
                "basis_ids",
                "values",
            ],
        ) {
            audit
                .errors
                .push(format!("{target} materialization fields are invalid"));
        }
        if curve.get("target_path").and_then(serde_json::Value::as_str) != Some(target.as_str())
            || curve.get("strategy_id").and_then(serde_json::Value::as_str) != Some(*strategy_id)
            || curve.get("endpoint").and_then(serde_json::Value::as_str) != Some(*endpoint)
        {
            audit.errors.push(format!(
                "materialization curve {index} target order is invalid"
            ));
        }
        let expected_review = psm.pointer(&format!(
            "/strategies/{strategy_id}/curve_review_bindings/{endpoint}"
        ));
        let review_binding = curve.get("review_binding");
        if review_binding != expected_review {
            audit.errors.push(format!(
                "{target} review binding does not match partitioned plan"
            ));
        }
        let family = curve
            .get("family")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let parameterization = curve
            .get("parameterization")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let expected_parameterization = match family {
            "exponential" => "exponential_rate",
            "weibull" => "weibull_shape_scale_aft",
            _ => {
                audit.errors.push(format!("{target} family is unsupported"));
                ""
            }
        };
        if parameterization != expected_parameterization {
            audit
                .errors
                .push(format!("{target} parameterization is unsupported"));
        }
        if review_binding
            .and_then(|value| value.get("selected_family"))
            .and_then(serde_json::Value::as_str)
            != Some(family)
        {
            audit
                .errors
                .push(format!("{target} family does not match Human selection"));
        }
        let fit_binding = curve.get("fit_output_binding");
        if !fit_binding.is_some_and(|value| exact_fields(value, &["path", "content_sha256"])) {
            audit
                .errors
                .push(format!("{target} fit-output binding is invalid"));
        }

        let review_loaded = read_bound_json(
            workspace,
            review_binding.and_then(|value| value.get("path")),
            review_binding.and_then(|value| value.get("content_sha256")),
            &format!("{target} review"),
            &mut audit.errors,
        );
        if let Some((path, digest, _, review)) = review_loaded {
            let review_audit = crate::heor_survival_review::audit_survival_review_value(
                workspace,
                plan,
                &review,
                digest.clone(),
                &target,
                family,
            );
            if !review_audit.complete {
                audit.errors.extend(
                    review_audit
                        .errors
                        .into_iter()
                        .map(|error| format!("{target} review: {error}")),
                );
            }
            let expected_endpoint = endpoint.to_ascii_uppercase();
            if review
                .pointer("/context/endpoint")
                .and_then(serde_json::Value::as_str)
                != Some(expected_endpoint.as_str())
                || review
                    .pointer("/context/time_origin")
                    .and_then(serde_json::Value::as_str)
                    != psm.get("time_origin").and_then(serde_json::Value::as_str)
                || review
                    .pointer("/context/time_unit")
                    .and_then(serde_json::Value::as_str)
                    != Some("years")
            {
                audit.errors.push(format!(
                    "{target} review endpoint or time basis does not match"
                ));
            }
            let matches = review
                .get("models")
                .and_then(serde_json::Value::as_array)
                .map(|models| {
                    models
                        .iter()
                        .filter(|model| {
                            model.get("family").and_then(serde_json::Value::as_str) == Some(family)
                        })
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            if matches.len() != 1 {
                audit.errors.push(format!(
                    "{target} review must contain exactly one selected-family model"
                ));
            } else {
                let model = matches[0];
                if model.get("status").and_then(serde_json::Value::as_str) != Some("converged")
                    || model
                        .get("parameterization")
                        .and_then(serde_json::Value::as_str)
                        != Some(parameterization)
                    || model.get("fit_output_path")
                        != fit_binding.and_then(|value| value.get("path"))
                    || model.get("fit_output_sha256")
                        != fit_binding.and_then(|value| value.get("content_sha256"))
                {
                    audit.errors.push(format!(
                        "{target} selected review model does not bind the materialized fit"
                    ));
                }
            }
            audit
                .artifact_bindings
                .push(crate::heor_approval::ArtifactBinding {
                    path,
                    sha256: digest,
                });
        }

        let fit_loaded = read_bound_json(
            workspace,
            fit_binding.and_then(|value| value.get("path")),
            fit_binding.and_then(|value| value.get("content_sha256")),
            &format!("{target} fit output"),
            &mut audit.errors,
        );
        if let Some((path, digest, _, fit)) = fit_loaded {
            if !exact_fields(
                &fit,
                &[
                    "schema_version",
                    "family",
                    "parameterization",
                    "time_unit",
                    "parameters",
                ],
            ) || fit
                .get("schema_version")
                .and_then(serde_json::Value::as_str)
                != Some("0.1.0")
                || fit.get("family").and_then(serde_json::Value::as_str) != Some(family)
                || fit
                    .get("parameterization")
                    .and_then(serde_json::Value::as_str)
                    != Some(parameterization)
                || fit.get("time_unit").and_then(serde_json::Value::as_str) != Some("years")
                || fit.get("parameters") != curve.get("parameters")
            {
                audit
                    .errors
                    .push(format!("{target} typed fit output does not match manifest"));
            }
            audit
                .artifact_bindings
                .push(crate::heor_approval::ArtifactBinding {
                    path,
                    sha256: digest,
                });
        }

        let parameters = curve.get("parameters").unwrap_or(&serde_json::Value::Null);
        let parameter_fields_valid = match family {
            "exponential" => {
                exact_fields(parameters, &["rate_per_year"])
                    && finite_positive(parameters.get("rate_per_year")).is_some()
            }
            "weibull" => {
                exact_fields(parameters, &["shape", "scale_years"])
                    && finite_positive(parameters.get("shape")).is_some()
                    && finite_positive(parameters.get("scale_years")).is_some()
            }
            _ => false,
        };
        if !parameter_fields_valid {
            audit
                .errors
                .push(format!("{target} parameters are invalid"));
        }
        let review_sha = review_binding
            .and_then(|value| value.get("content_sha256"))
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let fit_sha = fit_binding
            .and_then(|value| value.get("content_sha256"))
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let expected_basis = vec![
            format!("review-sha256:{review_sha}"),
            format!("fit-output-sha256:{fit_sha}"),
            format!("evaluator:{EVALUATOR_ID}@{EVALUATOR_VERSION}"),
        ];
        let basis = curve
            .get("basis_ids")
            .and_then(serde_json::Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(serde_json::Value::as_str)
                    .collect::<Vec<_>>()
            });
        if basis != Some(expected_basis.iter().map(String::as_str).collect()) {
            audit
                .errors
                .push(format!("{target} basis IDs do not match exact inputs"));
        }
        let manifest_values = curve.get("values").and_then(serde_json::Value::as_array);
        let psm_values = psm
            .pointer(&format!("/strategies/{strategy_id}/{endpoint}"))
            .and_then(serde_json::Value::as_array);
        let expected_count = cycles.map_or(0, |value| value as usize + 1);
        let duration_derived = matches!(
            psm.get("schema_version")
                .and_then(serde_json::Value::as_str),
            Some("0.4.0" | "0.5.0" | "0.6.0" | "0.7.0")
        );
        if manifest_values.map_or(0, Vec::len) != expected_count
            || (!duration_derived && psm_values.map_or(0, Vec::len) != expected_count)
        {
            audit
                .errors
                .push(format!("{target} must contain every cycle boundary"));
            continue;
        }
        if parameter_fields_valid {
            for value_index in 0..expected_count {
                let time = value_index as f64 * cycle_length.unwrap_or_default();
                let Some(expected) = evaluate(family, parameters, time) else {
                    audit
                        .errors
                        .push(format!("{target} deterministic evaluation failed"));
                    break;
                };
                let mut rows = vec![("manifest", &manifest_values.unwrap()[value_index], false)];
                if !duration_derived {
                    rows.push(("PSM", &psm_values.unwrap()[value_index], true));
                }
                for (label, row, require_basis) in rows {
                    let observed_time = row.get("time_years").and_then(serde_json::Value::as_f64);
                    let observed = row.get("survival").and_then(serde_json::Value::as_f64);
                    if !observed_time
                        .is_some_and(|value| value.is_finite() && (value - time).abs() <= TOLERANCE)
                        || !observed.is_some_and(|value| {
                            value.is_finite() && (value - expected).abs() <= TOLERANCE
                        })
                    {
                        audit.errors.push(format!(
                            "{target} {label}[{value_index}] does not match deterministic evaluation"
                        ));
                    }
                    if require_basis {
                        let row_basis = row
                            .get("basis_ids")
                            .and_then(serde_json::Value::as_array)
                            .map(|items| {
                                items
                                    .iter()
                                    .filter_map(serde_json::Value::as_str)
                                    .collect::<Vec<_>>()
                            });
                        if row_basis != Some(expected_basis.iter().map(String::as_str).collect()) {
                            audit.errors.push(format!(
                                "{target} PSM[{value_index}] basis IDs do not match"
                            ));
                        }
                    }
                }
            }
        }
    }
    if !manifest
        .get("limitations")
        .and_then(serde_json::Value::as_array)
        .is_some_and(|items| {
            !items.is_empty()
                && items
                    .iter()
                    .all(|item| item.as_str().is_some_and(|value| !value.trim().is_empty()))
        })
    {
        audit
            .errors
            .push("survival materialization limitations are required".into());
    }
    let authority = String::from_utf8_lossy(&manifest_raw).to_ascii_lowercase();
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
            .push("survival materialization contains a forbidden authority field".into());
    }
    audit
        .artifact_bindings
        .sort_by(|left, right| left.path.cmp(&right.path));
    audit
        .artifact_bindings
        .dedup_by(|left, right| left.path == right.path && left.sha256 == right.sha256);
    audit.complete = audit.errors.is_empty();
    audit
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_materialization_link_fails_closed() {
        let audit = audit_survival_materializations(
            &std::env::temp_dir(),
            &serde_json::json!({"analysis_id": "a"}),
            br#"{}"#,
            &serde_json::json!({}),
        );
        assert!(!audit.complete);
        assert_eq!(audit.errors.len(), 1);
    }

    #[test]
    fn evaluator_distinguishes_exponential_and_weibull_aft() {
        let exponential = serde_json::json!({"rate_per_year": 0.5});
        let weibull = serde_json::json!({"shape": 2.0, "scale_years": 4.0});
        assert!(
            (evaluate("exponential", &exponential, 2.0).unwrap() - (-1.0_f64).exp()).abs()
                < TOLERANCE
        );
        assert!(
            (evaluate("weibull", &weibull, 2.0).unwrap() - (-0.25_f64).exp()).abs() < TOLERANCE
        );
        assert_eq!(evaluate("gompertz", &exponential, 2.0), None);
        assert_eq!(
            evaluate(
                "weibull",
                &serde_json::json!({"shape": 0.0, "scale_years": 4.0}),
                2.0
            ),
            None
        );
    }
}
