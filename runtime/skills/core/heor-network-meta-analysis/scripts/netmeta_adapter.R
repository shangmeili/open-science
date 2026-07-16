#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("usage: netmeta_adapter.R probe <library> | run <data> <measure> <model> <reference> <favorable> <ranking> <output> <library>")
}

library_dir <- normalizePath(args[[length(args)]], mustWork = TRUE)
.libPaths(c(library_dir, .Library))
required_packages <- c("netmeta", "meta", "metafor")
missing_packages <- required_packages[!vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_packages) > 0) {
  stop(paste("missing required packages in isolated library:", paste(missing_packages, collapse = ", ")))
}

if (args[[1]] == "probe") {
  cat(paste0("r_version\t", as.character(getRversion()), "\n"))
  for (name in required_packages) {
    cat(paste0("package\t", name, "\t", as.character(utils::packageVersion(name)), "\n"))
  }
  quit(save = "no", status = 0)
}

if (args[[1]] != "run" || length(args) != 9) {
  stop("run mode requires exactly eight arguments after 'run'")
}

data_path <- normalizePath(args[[2]], mustWork = TRUE)
measure <- args[[3]]
model_type <- args[[4]]
reference <- args[[5]]
favorable <- args[[6]]
ranking_method <- args[[7]]
output_dir <- normalizePath(args[[8]], mustWork = TRUE)

measure_map <- c(
  log_odds_ratio = "OR",
  log_risk_ratio = "RR",
  log_hazard_ratio = "HR",
  mean_difference = "MD",
  standardized_mean_difference = "SMD"
)
if (!measure %in% names(measure_map)) stop("unsupported effect measure")
if (!model_type %in% c("common", "random")) stop("unsupported model type")
if (!favorable %in% c("lower", "higher")) stop("unsupported favorable direction")
if (!ranking_method %in% c("none", "p_score")) stop("unsupported ranking method")

data <- utils::read.csv(data_path, check.names = FALSE, stringsAsFactors = FALSE)
expected_columns <- c("study_id", "treat1", "treat2", "effect", "se")
if (!identical(names(data), expected_columns)) stop("CSV columns changed after Python preflight")
if (anyDuplicated(data$study_id)) stop("multi-arm or duplicate studies are rejected")
if (any(data$treat1 == data$treat2)) stop("study contrast must contain distinct treatments")
if (any(!is.finite(data$effect)) || any(!is.finite(data$se)) || any(data$se <= 0)) stop("effect and se must be finite and se positive")
if (!reference %in% unique(c(data$treat1, data$treat2))) stop("reference treatment is absent")

warnings <- character()
clean_message <- function(value) trimws(gsub("[\t\r\n]+", " ", value))
nma <- withCallingHandlers(
  netmeta::netmeta(
    TE = as.numeric(data$effect),
    seTE = as.numeric(data$se),
    treat1 = data$treat1,
    treat2 = data$treat2,
    studlab = data$study_id,
    sm = unname(measure_map[[measure]]),
    common = model_type == "common",
    random = model_type == "random",
    prediction = model_type == "random",
    method.tau = if (model_type == "random") "REML" else "DL",
    reference.group = reference,
    baseline.reference = TRUE,
    small.values = if (favorable == "lower") "desirable" else "undesirable",
    backtransf = FALSE,
    warn = TRUE
  ),
  warning = function(warning) {
    warnings <<- c(warnings, clean_message(conditionMessage(warning)))
    invokeRestart("muffleWarning")
  }
)

select_matrix <- function(common_value, random_value) {
  if (model_type == "common") common_value else random_value
}
effect_matrix <- select_matrix(nma$TE.common, nma$TE.random)
se_matrix <- select_matrix(nma$seTE.common, nma$seTE.random)
lower_matrix <- select_matrix(nma$lower.common, nma$lower.random)
upper_matrix <- select_matrix(nma$upper.common, nma$upper.random)
prediction_lower <- if (model_type == "random") nma$lower.predict else NULL
prediction_upper <- if (model_type == "random") nma$upper.predict else NULL

treatments <- rownames(effect_matrix)
matrix_rows <- list()
for (row_name in treatments) {
  for (column_name in colnames(effect_matrix)) {
    if (row_name == column_name) next
    matrix_rows[[length(matrix_rows) + 1]] <- data.frame(
      row_treatment = row_name,
      column_treatment = column_name,
      effect = as.numeric(effect_matrix[row_name, column_name]),
      se = as.numeric(se_matrix[row_name, column_name]),
      lower = as.numeric(lower_matrix[row_name, column_name]),
      upper = as.numeric(upper_matrix[row_name, column_name]),
      prediction_lower = if (is.null(prediction_lower)) NA_real_ else as.numeric(prediction_lower[row_name, column_name]),
      prediction_upper = if (is.null(prediction_upper)) NA_real_ else as.numeric(prediction_upper[row_name, column_name]),
      stringsAsFactors = FALSE
    )
  }
}
matrix_table <- do.call(rbind, matrix_rows)

direct_effect <- select_matrix(nma$TE.direct.common, nma$TE.direct.random)
direct_se <- select_matrix(nma$seTE.direct.common, nma$seTE.direct.random)
indirect_effect <- select_matrix(nma$TE.indirect.common, nma$TE.indirect.random)
indirect_se <- select_matrix(nma$seTE.indirect.common, nma$seTE.indirect.random)
local_rows <- list()
for (i in seq_along(treatments)) {
  if (i == length(treatments)) next
  for (j in seq.int(i + 1, length(treatments))) {
    left <- treatments[[i]]
    right <- treatments[[j]]
    values <- c(
      direct_effect[left, right], direct_se[left, right],
      indirect_effect[left, right], indirect_se[left, right]
    )
    if (any(!is.finite(values)) || values[[2]] <= 0 || values[[4]] <= 0) next
    difference <- values[[1]] - values[[3]]
    se_difference <- sqrt(values[[2]]^2 + values[[4]]^2)
    local_rows[[length(local_rows) + 1]] <- data.frame(
      row_treatment = left,
      column_treatment = right,
      network_effect = as.numeric(effect_matrix[left, right]),
      direct_effect = values[[1]],
      indirect_effect = values[[3]],
      difference = difference,
      se_difference = se_difference,
      p_value = 2 * stats::pnorm(-abs(difference / se_difference)),
      stringsAsFactors = FALSE
    )
  }
}
local_table <- if (length(local_rows)) do.call(rbind, local_rows) else data.frame(
  row_treatment = character(), column_treatment = character(), network_effect = numeric(),
  direct_effect = numeric(), indirect_effect = numeric(), difference = numeric(),
  se_difference = numeric(), p_value = numeric(), stringsAsFactors = FALSE
)

ranking_table <- data.frame(treatment = character(), p_score = numeric(), stringsAsFactors = FALSE)
if (ranking_method == "p_score") {
  rank_object <- netmeta::netrank(nma, method = "P-score")
  scores <- if (model_type == "common") rank_object$ranking.common else rank_object$ranking.random
  ranking_table <- data.frame(treatment = names(scores), p_score = as.numeric(scores), stringsAsFactors = FALSE)
}

diagnostics_table <- data.frame(
  tau = if (model_type == "common") 0 else as.numeric(nma$tau),
  q_total = as.numeric(nma$Q),
  df_total = as.integer(nma$df.Q),
  p_total = as.numeric(nma$pval.Q),
  q_heterogeneity = as.numeric(nma$Q.heterogeneity),
  df_heterogeneity = as.integer(nma$df.Q.heterogeneity),
  p_heterogeneity = as.numeric(nma$pval.Q.heterogeneity),
  q_inconsistency = as.numeric(nma$Q.inconsistency),
  df_inconsistency = as.integer(nma$df.Q.inconsistency),
  p_inconsistency = as.numeric(nma$pval.Q.inconsistency),
  stringsAsFactors = FALSE
)

write_tsv <- function(value, name) {
  utils::write.table(value, file.path(output_dir, name), sep = "\t", row.names = FALSE, quote = FALSE, na = "")
}
write_tsv(matrix_table, "matrix.tsv")
write_tsv(diagnostics_table, "diagnostics.tsv")
write_tsv(local_table, "local-inconsistency.tsv")
write_tsv(ranking_table, "ranking.tsv")
writeLines(unique(warnings[nzchar(warnings)]), file.path(output_dir, "warnings.txt"), useBytes = TRUE)
