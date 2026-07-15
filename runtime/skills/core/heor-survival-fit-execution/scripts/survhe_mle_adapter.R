#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("usage: survhe_mle_adapter.R probe <library> | run <data> <time> <event> <families> <times> <output> <library>")
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

if (args[[1]] != "run" || length(args) != 8) {
  stop("run mode requires exactly seven arguments after 'run'")
}

data_path <- normalizePath(args[[2]], mustWork = TRUE)
time_column <- args[[3]]
event_column <- args[[4]]
families <- strsplit(args[[5]], ",", fixed = TRUE)[[1]]
prediction_times <- as.numeric(strsplit(args[[6]], ",", fixed = TRUE)[[1]])
output_dir <- normalizePath(args[[7]], mustWork = TRUE)

safe_column <- function(value) grepl("^[A-Za-z][A-Za-z0-9_]{0,63}$", value)
if (!safe_column(time_column) || !safe_column(event_column) || time_column == event_column) {
  stop("time and event columns must be distinct safe names")
}

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
if (length(families) < 2 || any(!families %in% names(family_map)) || anyDuplicated(families)) {
  stop("candidate model list is invalid")
}
if (length(prediction_times) < 3 || any(!is.finite(prediction_times)) || prediction_times[[1]] != 0 || any(diff(prediction_times) <= 0)) {
  stop("prediction times must start at zero and strictly increase")
}

data <- utils::read.csv(data_path, check.names = FALSE, stringsAsFactors = FALSE)
if (!identical(names(data), c(time_column, event_column))) {
  stop("CSV columns changed after Python preflight")
}
if (!is.numeric(data[[time_column]]) || any(!is.finite(data[[time_column]])) || any(data[[time_column]] <= 0)) {
  stop("time column must be finite and positive")
}
if (!all(data[[event_column]] %in% c(0, 1))) {
  stop("event column must contain only 0 and 1")
}

fit_data <- data.frame(
  ai4heor_time = as.numeric(data[[time_column]]),
  ai4heor_event = as.numeric(data[[event_column]])
)
rm(data)

suppressPackageStartupMessages(library(survival))
suppressPackageStartupMessages(library(survHE))
formula <- Surv(ai4heor_time, ai4heor_event) ~ 1
positive_times <- prediction_times[prediction_times > 0]

models_rows <- list()
parameters_rows <- list()
predictions_rows <- list()
uncertainty_rows <- list()
estimation_parameters_rows <- list()
covariance_rows <- list()
fitted_models <- list()

clean_message <- function(value) {
  value <- gsub("[\t\r\n]+", " ", value)
  trimws(value)
}

summary_frame <- function(value) {
  if (is.data.frame(value)) return(value)
  if (is.list(value) && length(value) >= 1 && is.data.frame(value[[1]])) return(value[[1]])
  stop("unexpected flexsurv summary shape")
}

for (family in families) {
  warnings <- character()
  fitted <- withCallingHandlers(
    tryCatch(
      survHE::fit.models(
        formula = formula,
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
    models_rows[[length(models_rows) + 1]] <- data.frame(
      family = family,
      status = "failed",
      aic = NA_real_,
      bic = NA_real_,
      log_likelihood = NA_real_,
      parameterization = "",
      warnings = clean_message(conditionMessage(fitted)),
      stringsAsFactors = FALSE
    )
    next
  }

  model <- fitted$models[[1]]
  convergence <- model$opt$convergence
  if (!is.null(convergence) && convergence != 0) {
    warnings <- c(warnings, paste("optimizer convergence code", convergence))
  }
  parameterization <- switch(
    family,
    exponential = "exponential_rate",
    weibull = "weibull_shape_scale_aft",
    gompertz = "gompertz_shape_rate",
    gamma = "gamma_shape_rate",
    generalized_gamma = "generalized_gamma_prentice",
    generalized_f = "generalized_f_prentice",
    lognormal = "lognormal_meanlog_sdlog",
    loglogistic = "loglogistic_shape_scale"
  )
  models_rows[[length(models_rows) + 1]] <- data.frame(
    family = family,
    status = "converged",
    aic = as.numeric(fitted$model.fitting$aic[[1]]),
    bic = as.numeric(fitted$model.fitting$bic[[1]]),
    log_likelihood = as.numeric(model$loglik),
    parameterization = parameterization,
    warnings = paste(unique(warnings[nzchar(warnings)]), collapse = " | "),
    stringsAsFactors = FALSE
  )

  natural_parameters <- model$res
  if (is.null(natural_parameters) || is.null(rownames(natural_parameters)) || !"est" %in% colnames(natural_parameters)) {
    stop(paste("model", family, "does not expose natural-scale parameter estimates"))
  }
  parameters_rows[[length(parameters_rows) + 1]] <- data.frame(
    family = family,
    name = rownames(natural_parameters),
    estimate = as.numeric(natural_parameters[, "est"]),
    stringsAsFactors = FALSE
  )

  expected_transforms <- switch(
    family,
    exponential = c(rate = "exp"),
    weibull = c(shape = "exp", scale = "exp"),
    gompertz = c(shape = "identity", rate = "exp"),
    gamma = c(shape = "exp", rate = "exp"),
    generalized_gamma = c(mu = "identity", sigma = "exp", Q = "identity"),
    generalized_f = c(mu = "identity", sigma = "exp", Q = "identity", P = "exp"),
    lognormal = c(meanlog = "identity", sdlog = "exp"),
    loglogistic = c(shape = "exp", scale = "exp")
  )
  transformed_parameters <- model$res.t
  covariance <- model$cov
  uncertainty_reason <- ""
  if (
    is.null(transformed_parameters) || is.null(rownames(transformed_parameters)) ||
    !"est" %in% colnames(transformed_parameters) ||
    !identical(rownames(transformed_parameters), names(expected_transforms))
  ) {
    uncertainty_reason <- "transformed parameter order does not match the admitted family contract"
  } else if (
    is.null(covariance) || !is.matrix(covariance) ||
    !identical(dim(covariance), c(length(expected_transforms), length(expected_transforms))) ||
    any(!is.finite(covariance))
  ) {
    uncertainty_reason <- "finite full-dimension covariance matrix is unavailable"
  } else if (max(abs(covariance - t(covariance))) > 1e-10) {
    uncertainty_reason <- "covariance matrix is not symmetric within tolerance"
  } else if (inherits(tryCatch(chol(covariance), error = function(error) error), "error")) {
    uncertainty_reason <- "covariance matrix is not positive definite"
  } else {
    transformed_estimates <- as.numeric(transformed_parameters[, "est"])
    recovered_natural <- vapply(
      seq_along(transformed_estimates),
      function(index) if (expected_transforms[[index]] == "exp") exp(transformed_estimates[[index]]) else transformed_estimates[[index]],
      numeric(1)
    )
    natural_estimates <- as.numeric(natural_parameters[, "est"])
    if (any(abs(recovered_natural - natural_estimates) > 1e-10 * pmax(1, abs(natural_estimates)))) {
      uncertainty_reason <- "inverse transforms do not reproduce natural-scale estimates"
    } else {
      estimation_parameters_rows[[length(estimation_parameters_rows) + 1]] <- data.frame(
        family = family,
        position = seq_along(transformed_estimates),
        name = names(expected_transforms),
        estimate = transformed_estimates,
        inverse_transform = unname(expected_transforms),
        stringsAsFactors = FALSE
      )
      covariance_rows[[length(covariance_rows) + 1]] <- data.frame(
        family = family,
        row_position = rep(seq_along(transformed_estimates), each = length(transformed_estimates)),
        column_position = rep(seq_along(transformed_estimates), times = length(transformed_estimates)),
        value = as.numeric(t(covariance)),
        stringsAsFactors = FALSE
      )
    }
  }
  uncertainty_rows[[length(uncertainty_rows) + 1]] <- data.frame(
    family = family,
    status = if (nzchar(uncertainty_reason)) "unavailable" else "available",
    reason = uncertainty_reason,
    stringsAsFactors = FALSE
  )

  survival <- summary_frame(summary(model, t = positive_times, type = "survival", ci = FALSE))
  hazard <- summary_frame(summary(model, t = positive_times, type = "hazard", ci = FALSE))
  if (nrow(survival) != length(positive_times) || nrow(hazard) != length(positive_times)) {
    stop(paste("model", family, "did not return every requested prediction time"))
  }
  predictions_rows[[length(predictions_rows) + 1]] <- data.frame(
    family = family,
    time = prediction_times,
    survival = c(1, as.numeric(survival$est)),
    hazard = c(NA_real_, as.numeric(hazard$est)),
    stringsAsFactors = FALSE
  )
  fitted_models[[family]] <- model
}

models_table <- do.call(rbind, models_rows)
parameters_table <- if (length(parameters_rows)) do.call(rbind, parameters_rows) else data.frame(family = character(), name = character(), estimate = numeric())
predictions_table <- if (length(predictions_rows)) do.call(rbind, predictions_rows) else data.frame(family = character(), time = numeric(), survival = numeric(), hazard = numeric())
uncertainty_table <- if (length(uncertainty_rows)) do.call(rbind, uncertainty_rows) else data.frame(family = character(), status = character(), reason = character())
estimation_parameters_table <- if (length(estimation_parameters_rows)) do.call(rbind, estimation_parameters_rows) else data.frame(family = character(), position = integer(), name = character(), estimate = numeric(), inverse_transform = character())
covariance_table <- if (length(covariance_rows)) do.call(rbind, covariance_rows) else data.frame(family = character(), row_position = integer(), column_position = integer(), value = numeric())

utils::write.table(models_table, file.path(output_dir, "models.tsv"), sep = "\t", quote = TRUE, row.names = FALSE, na = "")
utils::write.table(parameters_table, file.path(output_dir, "parameters.tsv"), sep = "\t", quote = TRUE, row.names = FALSE, na = "")
utils::write.table(predictions_table, file.path(output_dir, "predictions.tsv"), sep = "\t", quote = TRUE, row.names = FALSE, na = "")
utils::write.table(uncertainty_table, file.path(output_dir, "uncertainty-status.tsv"), sep = "\t", quote = TRUE, row.names = FALSE, na = "")
utils::write.table(estimation_parameters_table, file.path(output_dir, "estimation-parameters.tsv"), sep = "\t", quote = TRUE, row.names = FALSE, na = "")
utils::write.table(covariance_table, file.path(output_dir, "covariance.tsv"), sep = "\t", quote = TRUE, row.names = FALSE, na = "")
utils::write.table(package_rows, file.path(output_dir, "runtime.tsv"), sep = "\t", quote = TRUE, row.names = FALSE)
capture.output(sessionInfo(), file = file.path(output_dir, "session-info.txt"))

if (length(fitted_models) == 0) {
  stop("all candidate models failed")
}

km <- survival::survfit(formula, data = fit_data)
colors <- grDevices::hcl.colors(length(fitted_models), "Dark 3")

grDevices::png(file.path(output_dir, "km-overlay.png"), width = 1200, height = 800, res = 120)
plot(km, xlab = "Time", ylab = "Survival", conf.int = FALSE, mark.time = TRUE)
for (index in seq_along(fitted_models)) {
  family <- names(fitted_models)[[index]]
  values <- predictions_table[predictions_table$family == family, ]
  lines(values$time, values$survival, col = colors[[index]], lwd = 2)
}
legend("topright", legend = c("Kaplan-Meier", names(fitted_models)), col = c("black", colors), lty = 1, bty = "n")
grDevices::dev.off()

grDevices::png(file.path(output_dir, "log-cumulative-hazard.png"), width = 1200, height = 800, res = 120)
plot(km, fun = "cloglog", xlab = "Time", ylab = "log(-log(Survival))", conf.int = FALSE, mark.time = TRUE)
grDevices::dev.off()

grDevices::png(file.path(output_dir, "hazard.png"), width = 1200, height = 800, res = 120)
first_family <- names(fitted_models)[[1]]
first_values <- predictions_table[predictions_table$family == first_family & predictions_table$time > 0, ]
plot(first_values$time, first_values$hazard, type = "l", col = colors[[1]], lwd = 2, xlab = "Time", ylab = "Hazard", ylim = range(predictions_table$hazard, na.rm = TRUE))
if (length(fitted_models) > 1) {
  for (index in 2:length(fitted_models)) {
    family <- names(fitted_models)[[index]]
    values <- predictions_table[predictions_table$family == family & predictions_table$time > 0, ]
    lines(values$time, values$hazard, col = colors[[index]], lwd = 2)
  }
}
legend("topright", legend = names(fitted_models), col = colors, lty = 1, bty = "n")
grDevices::dev.off()
