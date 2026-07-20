#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("usage: paired_survival_bootstrap_adapter.R probe <library> | run <data> <plan> <curves> <times> <output> <library>")
}

library_dir <- normalizePath(args[[length(args)]], mustWork = TRUE)
.libPaths(c(library_dir, .Library))

required_packages <- c("survHE", "flexsurv", "survival")
missing_packages <- required_packages[!vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_packages) > 0) {
  stop(paste("missing required packages in isolated library:", paste(missing_packages, collapse = ", ")))
}

package_rows <- data.frame(
  package = required_packages,
  version = vapply(required_packages, function(name) as.character(utils::packageVersion(name)), character(1)),
  stringsAsFactors = FALSE
)

if (args[[1]] == "probe") {
  cat(paste0("r_version\t", R.version.string, "\n"))
  for (index in seq_len(nrow(package_rows))) {
    cat(paste0("package\t", package_rows$package[[index]], "\t", package_rows$version[[index]], "\n"))
  }
  quit(save = "no", status = 0)
}

if (args[[1]] != "run" || length(args) != 7) {
  stop("run mode requires exactly six arguments after 'run'")
}

data_path <- normalizePath(args[[2]], mustWork = TRUE)
plan_path <- normalizePath(args[[3]], mustWork = TRUE)
curve_specs_raw <- strsplit(args[[4]], ";", fixed = TRUE)[[1]]
prediction_times <- as.numeric(strsplit(args[[5]], ",", fixed = TRUE)[[1]])
output_dir <- normalizePath(args[[6]], mustWork = TRUE)

family_map <- c(
  exponential = "exponential",
  weibull = "weibull",
  gompertz = "gompertz",
  gamma = "gamma",
  generalized_gamma = "gengamma",
  generalized_f = "genf",
  lognormal = "lognormal",
  loglogistic = "loglogistic"
)
parameterization_map <- c(
  exponential = "exponential_rate",
  weibull = "weibull_shape_scale_aft",
  gompertz = "gompertz_shape_rate",
  gamma = "gamma_shape_rate",
  generalized_gamma = "generalized_gamma_prentice",
  generalized_f = "generalized_f_prentice",
  lognormal = "lognormal_meanlog_sdlog",
  loglogistic = "loglogistic_shape_scale"
)

curve_specs <- lapply(curve_specs_raw, function(value) strsplit(value, "|", fixed = TRUE)[[1]])
if (length(curve_specs) < 4 || any(vapply(curve_specs, length, integer(1)) != 3)) {
  stop("curve specifications must contain strategy, endpoint, and family")
}
if (any(!vapply(curve_specs, function(value) value[[2]] %in% c("pfs", "os"), logical(1))) ||
    any(!vapply(curve_specs, function(value) value[[3]] %in% names(family_map), logical(1)))) {
  stop("curve specification endpoint or family is invalid")
}
if (length(prediction_times) < 2 || any(!is.finite(prediction_times)) || prediction_times[[1]] != 0 || any(diff(prediction_times) <= 0)) {
  stop("prediction times must start at zero and strictly increase")
}

source <- utils::read.csv(data_path, check.names = FALSE, stringsAsFactors = FALSE)
expected_columns <- c("subject_id", "strategy_id", "pfs_time", "pfs_event", "os_time", "os_event")
if (!identical(names(source), expected_columns)) {
  stop("source CSV columns changed after Python preflight")
}
if (anyDuplicated(source$subject_id) || any(!nzchar(source$subject_id)) || any(!nzchar(source$strategy_id))) {
  stop("source subject or strategy identity is invalid")
}
for (endpoint in c("pfs", "os")) {
  time_column <- paste0(endpoint, "_time")
  event_column <- paste0(endpoint, "_event")
  if (!is.numeric(source[[time_column]]) || any(!is.finite(source[[time_column]])) || any(source[[time_column]] <= 0)) {
    stop(paste(endpoint, "time values must be finite and positive"))
  }
  if (!all(source[[event_column]] %in% c(0, 1))) {
    stop(paste(endpoint, "event values must be zero or one"))
  }
}
if (any(source$pfs_time > source$os_time + 1e-9)) {
  stop("source contains PFS time after OS time")
}

plan <- utils::read.csv(plan_path, check.names = FALSE, stringsAsFactors = FALSE)
expected_plan_columns <- c("replicate_index", paste0("row_", seq_len(nrow(source))))
if (!identical(names(plan), expected_plan_columns) || !identical(plan$replicate_index, seq_len(nrow(plan)))) {
  stop("bootstrap frequency plan identity or dimensions are invalid")
}
frequency_matrix <- as.matrix(plan[, -1, drop = FALSE])
storage.mode(frequency_matrix) <- "integer"
if (any(is.na(frequency_matrix)) || any(frequency_matrix < 0) || any(rowSums(frequency_matrix) != nrow(source))) {
  stop("bootstrap frequency rows must be non-negative and preserve total sample size")
}

suppressPackageStartupMessages(library(survival))
suppressPackageStartupMessages(library(survHE))

clean_message <- function(value) {
  trimws(gsub("[\t\r\n]+", " ", value))
}

summary_frame <- function(value) {
  if (is.data.frame(value)) return(value)
  if (is.list(value) && length(value) >= 1 && is.data.frame(value[[1]])) return(value[[1]])
  stop("unexpected flexsurv summary shape")
}

replicate_rows <- list()
model_rows <- list()
parameter_rows <- list()
prediction_rows <- list()

for (replicate_index in seq_len(nrow(plan))) {
  selected_indices <- rep(seq_len(nrow(source)), times = frequency_matrix[replicate_index, ])
  sampled <- source[selected_indices, , drop = FALSE]
  failed_curves <- character()

  for (curve_position in seq_along(curve_specs)) {
    specification <- curve_specs[[curve_position]]
    strategy_id <- specification[[1]]
    endpoint <- specification[[2]]
    family <- specification[[3]]
    strategy_data <- sampled[sampled$strategy_id == strategy_id, , drop = FALSE]
    fit_data <- data.frame(
      ai4heor_time = strategy_data[[paste0(endpoint, "_time")]],
      ai4heor_event = strategy_data[[paste0(endpoint, "_event")]]
    )
    warnings <- character()
    fitted <- withCallingHandlers(
      tryCatch(
        survHE::fit.models(
          formula = Surv(ai4heor_time, ai4heor_event) ~ 1,
          data = fit_data,
          distr = unname(family_map[[family]]),
          method = "mle"
        ),
        error = function(error) error
      ),
      warning = function(warning) {
        warnings <<- c(warnings, clean_message(conditionMessage(warning)))
        invokeRestart("muffleWarning")
      }
    )
    if (inherits(fitted, "error")) {
      failure <- clean_message(conditionMessage(fitted))
      failed_curves <- c(failed_curves, paste(strategy_id, endpoint, failure, sep = ":"))
      model_rows[[length(model_rows) + 1]] <- data.frame(
        replicate_index = replicate_index,
        curve_position = curve_position,
        strategy_id = strategy_id,
        endpoint = endpoint,
        family = family,
        status = "failed",
        parameterization = "",
        warnings = failure,
        stringsAsFactors = FALSE
      )
      next
    }

    model <- fitted$models[[1]]
    convergence <- model$opt$convergence
    if (!is.null(convergence) && convergence != 0) {
      warnings <- c(warnings, paste("optimizer convergence code", convergence))
    }
    natural_parameters <- model$res
    if (is.null(natural_parameters) || is.null(rownames(natural_parameters)) || !"est" %in% colnames(natural_parameters)) {
      failure <- "backend did not expose natural-scale parameter estimates"
      failed_curves <- c(failed_curves, paste(strategy_id, endpoint, failure, sep = ":"))
      model_rows[[length(model_rows) + 1]] <- data.frame(
        replicate_index = replicate_index,
        curve_position = curve_position,
        strategy_id = strategy_id,
        endpoint = endpoint,
        family = family,
        status = "failed",
        parameterization = "",
        warnings = failure,
        stringsAsFactors = FALSE
      )
      next
    }
    positive_times <- prediction_times[prediction_times > 0]
    predicted <- tryCatch(
      summary_frame(summary(model, t = positive_times, type = "survival", ci = FALSE)),
      error = function(error) error
    )
    if (inherits(predicted, "error") || nrow(predicted) != length(positive_times)) {
      failure <- if (inherits(predicted, "error")) clean_message(conditionMessage(predicted)) else "backend omitted prediction times"
      failed_curves <- c(failed_curves, paste(strategy_id, endpoint, failure, sep = ":"))
      model_rows[[length(model_rows) + 1]] <- data.frame(
        replicate_index = replicate_index,
        curve_position = curve_position,
        strategy_id = strategy_id,
        endpoint = endpoint,
        family = family,
        status = "failed",
        parameterization = "",
        warnings = failure,
        stringsAsFactors = FALSE
      )
      next
    }

    model_rows[[length(model_rows) + 1]] <- data.frame(
      replicate_index = replicate_index,
      curve_position = curve_position,
      strategy_id = strategy_id,
      endpoint = endpoint,
      family = family,
      status = "converged",
      parameterization = unname(parameterization_map[[family]]),
      warnings = paste(unique(warnings[nzchar(warnings)]), collapse = " | "),
      stringsAsFactors = FALSE
    )
    parameter_rows[[length(parameter_rows) + 1]] <- data.frame(
      replicate_index = replicate_index,
      curve_position = curve_position,
      name = rownames(natural_parameters),
      estimate = as.numeric(natural_parameters[, "est"]),
      stringsAsFactors = FALSE
    )
    prediction_rows[[length(prediction_rows) + 1]] <- data.frame(
      replicate_index = replicate_index,
      curve_position = curve_position,
      time = prediction_times,
      survival = c(1, as.numeric(predicted$est)),
      stringsAsFactors = FALSE
    )
  }
  replicate_rows[[length(replicate_rows) + 1]] <- data.frame(
    replicate_index = replicate_index,
    status = if (length(failed_curves)) "failed" else "complete",
    failure_reasons = paste(failed_curves, collapse = " | "),
    stringsAsFactors = FALSE
  )
}

replicate_table <- do.call(rbind, replicate_rows)
model_table <- do.call(rbind, model_rows)
parameter_table <- if (length(parameter_rows)) do.call(rbind, parameter_rows) else data.frame(replicate_index = integer(), curve_position = integer(), name = character(), estimate = numeric())
prediction_table <- if (length(prediction_rows)) do.call(rbind, prediction_rows) else data.frame(replicate_index = integer(), curve_position = integer(), time = numeric(), survival = numeric())

utils::write.table(replicate_table, file.path(output_dir, "replicates.tsv"), sep = "\t", quote = TRUE, row.names = FALSE, na = "")
utils::write.table(model_table, file.path(output_dir, "models.tsv"), sep = "\t", quote = TRUE, row.names = FALSE, na = "")
utils::write.table(parameter_table, file.path(output_dir, "parameters.tsv"), sep = "\t", quote = TRUE, row.names = FALSE, na = "")
utils::write.table(prediction_table, file.path(output_dir, "predictions.tsv"), sep = "\t", quote = TRUE, row.names = FALSE, na = "")
utils::write.table(package_rows, file.path(output_dir, "runtime.tsv"), sep = "\t", quote = TRUE, row.names = FALSE)
capture.output(sessionInfo(), file = file.path(output_dir, "session-info.txt"))
