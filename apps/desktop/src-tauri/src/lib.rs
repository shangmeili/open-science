// AI4HEOR — Tauri 2 entry. Hosts the React frontend and supervises the
// bundled OpenCode sidecar (isolated config/data + dedicated port; killed on exit).
mod artifact_file;
mod asset_admission;
mod compute;
mod debug_log;
mod examples;
mod git_snapshot;
mod harness;
mod heor_advanced_voi;
mod heor_approval;
mod heor_artifacts;
mod heor_budget_impact;
mod heor_cost_input_normalization;
mod heor_economic_inputs;
mod heor_engine;
mod heor_event_disutilities;
mod heor_evidence;
mod heor_evidence_review;
mod heor_joint_survival_uncertainty;
mod heor_library;
mod heor_methods_watchlist;
mod heor_microsimulation;
mod heor_model_calibration;
mod heor_network_meta_analysis;
mod heor_paired_survival_bootstrap;
mod heor_parametric_survival;
mod heor_partitioned_survival;
mod heor_population_adjusted_comparison;
mod heor_reference_case;
mod heor_reporting;
mod heor_reproducibility;
mod heor_rwe_causal_analysis;
mod heor_search;
mod heor_survival_execution;
mod heor_survival_materialization;
mod heor_survival_review;
mod heor_synthesis;
mod heor_treatment_effect_duration;
mod heor_uncertainty;
mod heor_utility_inputs;
mod heor_validation;
mod jupyter;
mod kernel;
mod large_file;
mod modal;
mod opencode_config;
mod preview_server;
mod project;
mod provenance;
mod runs;
mod runs_index;
mod runtime;
mod tools;
mod updates;
mod uv;

use jupyter::JupyterState;
use kernel::KernelState;
use preview_server::PreviewState;
use provenance::ProvenanceState;
use runtime::RuntimeState;
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Single instance MUST be the first plugin. A second launch (or a reinstall
        // while the app is still running) focuses the existing window instead of
        // starting a second OpenCode on the same data dir (which deadlocks the DB).
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .manage(RuntimeState::default())
        .manage(KernelState::default())
        .manage(JupyterState::default())
        .manage(PreviewState::default())
        .manage(ProvenanceState::default())
        .manage(heor_approval::HeorApprovalState::default())
        .manage(heor_advanced_voi::AdvancedVoiReviewState::default())
        .manage(heor_search::HeorSearchState::default())
        .manage(heor_synthesis::HeorSynthesisState::default())
        .manage(heor_library::HeorLibraryState::default())
        .manage(heor_methods_watchlist::MethodsWatchlistReviewState::default())
        .manage(heor_model_calibration::ModelCalibrationReviewState::default())
        .manage(heor_microsimulation::MicrosimulationReviewState::default())
        .manage(heor_paired_survival_bootstrap::PairedBootstrapReviewState::default())
        .manage(heor_network_meta_analysis::NetworkMetaAnalysisReviewState::default())
        .manage(
            heor_population_adjusted_comparison::PopulationAdjustedComparisonReviewState::default(),
        )
        .manage(heor_rwe_causal_analysis::RweCausalAnalysisReviewState::default())
        .manage(heor_evidence_review::HeorEvidenceReviewState::default())
        .manage(runs::RunState::default())
        .invoke_handler(tauri::generate_handler![
            runtime::start_runtime,
            runtime::runtime_password,
            runtime::stop_runtime,
            runtime::workspace_path,
            runtime::workspace_base,
            runtime::set_workspace_base,
            runtime::open_workspace_base,
            runtime::set_workspace,
            runtime::mark_session,
            runtime::new_dated_workspace,
            project::create_project,
            project::list_projects,
            project::rename_project,
            runtime::pick_folder,
            runtime::import_opencode_login,
            runtime::remove_config_entry,
            jupyter::jupyter_status,
            jupyter::setup_jupyter,
            jupyter::start_jupyter,
            runtime::configure_opencode,
            runtime::get_approval_mode,
            runtime::set_approval_mode,
            runtime::get_proxy_setting,
            runtime::set_proxy_setting,
            runtime::get_mirror_setting,
            runtime::set_mirror_setting,
            kernel::kernel_execute,
            kernel::kernel_reset,
            kernel::python_interpreter,
            kernel::set_python_path,
            artifact_file::read_artifact,
            artifact_file::open_path,
            artifact_file::reveal_path,
            artifact_file::absolute_path,
            artifact_file::resolve_artifact,
            artifact_file::save_text_file,
            artifact_file::open_url,
            artifact_file::add_files_to_workspace,
            artifact_file::add_text_to_workspace,
            artifact_file::list_notebooks,
            artifact_file::list_dir,
            artifact_file::write_workspace_file,
            asset_admission::audit_asset_admission,
            provenance::record_provenance,
            provenance::list_provenance,
            provenance::read_env_lockfile,
            heor_approval::append_heor_approval,
            heor_approval::list_heor_approvals,
            heor_advanced_voi::audit_heor_advanced_voi,
            heor_advanced_voi::run_heor_advanced_voi,
            heor_advanced_voi::append_heor_advanced_voi_review,
            heor_advanced_voi::list_heor_advanced_voi_reviews,
            heor_budget_impact::audit_heor_budget_impact,
            heor_budget_impact::run_heor_budget_impact,
            heor_partitioned_survival::audit_heor_partitioned_survival,
            heor_partitioned_survival::run_heor_partitioned_survival,
            heor_paired_survival_bootstrap::audit_heor_paired_survival_bootstrap,
            heor_paired_survival_bootstrap::append_heor_paired_bootstrap_review,
            heor_paired_survival_bootstrap::list_heor_paired_bootstrap_reviews,
            heor_network_meta_analysis::audit_heor_network_meta_analysis,
            heor_network_meta_analysis::append_heor_network_meta_analysis_review,
            heor_network_meta_analysis::list_heor_network_meta_analysis_reviews,
            heor_population_adjusted_comparison::audit_heor_population_adjusted_comparison,
            heor_population_adjusted_comparison::append_heor_population_adjusted_comparison_review,
            heor_population_adjusted_comparison::list_heor_population_adjusted_comparison_reviews,
            heor_rwe_causal_analysis::audit_heor_rwe_causal_analysis,
            heor_rwe_causal_analysis::append_heor_rwe_causal_analysis_review,
            heor_rwe_causal_analysis::list_heor_rwe_causal_analysis_reviews,
            heor_reference_case::audit_heor_reference_case,
            heor_reproducibility::audit_heor_reproducibility,
            heor_reporting::audit_heor_reporting,
            heor_search::audit_heor_evidence_search,
            heor_search::execute_heor_evidence_search,
            heor_search::list_heor_search_authorizations,
            heor_library::add_heor_library_directory,
            heor_library::add_heor_library_files,
            heor_library::audit_heor_evidence_library,
            heor_library::search_heor_evidence_library,
            heor_library::sync_heor_evidence_library,
            heor_methods_watchlist::audit_heor_methods_watchlist,
            heor_methods_watchlist::append_heor_methods_watchlist_review,
            heor_methods_watchlist::list_heor_methods_watchlist_reviews,
            heor_model_calibration::audit_heor_model_calibration,
            heor_model_calibration::append_heor_model_calibration_review,
            heor_model_calibration::list_heor_model_calibration_reviews,
            heor_microsimulation::audit_heor_microsimulation,
            heor_microsimulation::append_heor_microsimulation_review,
            heor_microsimulation::list_heor_microsimulation_reviews,
            heor_synthesis::audit_heor_evidence_synthesis,
            heor_synthesis::import_heor_search_candidates,
            heor_survival_execution::audit_heor_survival_fit_execution,
            heor_survival_review::audit_heor_survival_extrapolation,
            heor_evidence::audit_heor_evidence_selection,
            heor_evidence_review::list_heor_evidence_verifications,
            heor_evidence_review::verify_heor_evidence_extractions,
            heor_uncertainty::audit_heor_uncertainty,
            heor_uncertainty::run_heor_uncertainty,
            heor_validation::audit_heor_model_validation,
            heor_engine::run_heor_markov,
            runs::record_run,
            runs::list_runs,
            runs::read_run_log,
            runs_index::query_runs_cmd,
            examples::install_example,
            examples::run_heor_teaching_example,
            git_snapshot::commit_workspace_snapshot,
            compute::list_ssh_hosts,
            compute::compute_machines,
            compute::add_compute_machine,
            compute::remove_compute_machine,
            compute::compute_probe,
            compute::compute_jobs,
            compute::compute_cancel,
            modal::modal_status,
            preview_server::preview_url,
            large_file::probe_large_file,
            tools::detect_tools,
            updates::latest_release,
            debug_log::log_debug
        ])
        .build(tauri::generate_context!())
        .expect("error while building AI4HEOR")
        .run(|app, event| {
            // Clean up on exit. macOS Cmd+Q / Quit terminates via RunEvent::Exit
            // (ExitRequested is not always delivered), so handle BOTH — otherwise
            // the OpenCode sidecar / kernel / Jupyter orphan on every quit. The
            // cleanup is idempotent, so running on both is safe.
            if matches!(
                event,
                tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
            ) {
                runtime::kill_child(&app.state::<RuntimeState>());
                kernel::kill_kernel(&app.state::<KernelState>());
                jupyter::kill_jupyter(&app.state::<JupyterState>());
            }
        });
}
