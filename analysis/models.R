# Stage A, step 3: inference for the three primary outcomes (protocol/ANALYSIS_PLAN.md).
#
#   docker run --rm -v "$PWD":/w -w /w lcr-analysis-r:dev Rscript analysis/models.R analysis/out/main
#
# Input  <dir>/primary.csv (analysis/primary.py); complete solutions only.
# Output <dir>/primary_fits.csv       fit actually used per outcome (fallback step, convergence)
#        <dir>/primary_contrasts.csv  Family A (C2 vs C0 within each LLM, 8) and Family B (flagship vs others within
#                                     each condition, 2): OR, 95 % Wald CI, test, p, Holm-adjusted p
#        <dir>/primary_cells.csv      raw proportions per LLM x condition (and separation flags)
#
# Model: y ~ llm * condition + language + (1|task) + (1|task:language) + (1|llm:task)
#   unsafe_write: y ~ llm * condition + language + task  (fixed task effect, no random terms)
# Fallback order on failure (non-convergence or non-positive-definite Hessian): drop (1|llm:task), then
# (1|task:language), then (1|task) -> task as a fixed effect; last resort a bootstrap over solutions within tasks
# (2,000 resamples, seed 20261106). Family A uses likelihood-ratio tests: the model is written with one C2 indicator
# per LLM (equivalent to llm * condition) and each indicator is dropped in turn. Family B is a linear combination
# (mean log-odds of the flagships minus mean of the others) -> Wald. Cells with 0 % or 100 % (quasi-complete
# separation) are reported; contrasts touching them are tested by the bootstrap instead.

suppressPackageStartupMessages({ library(glmmTMB); library(jsonlite) })
args <- commandArgs(trailingOnly = TRUE)
dir <- if (length(args)) args[1] else "analysis/out/main"
SEED <- 20261106; B <- 2000
FLAG <- c("claude-opus-5.5", "gpt-6.1-sol", "gemini-4-argon")

d0 <- read.csv(file.path(dir, "primary.csv"), stringsAsFactors = FALSE)
d0 <- d0[d0$complete == 1 & !is.na(d0$y), ]

fit_ok <- function(f) {
  if (inherits(f, "try-error")) return(FALSE)
  conv <- isTRUE(f$fit$convergence == 0)
  pd <- isTRUE(f$sdr$pdHess)
  conv && pd
}

fit_try <- function(form, d) {
  w <- NULL
  f <- try(withCallingHandlers(glmmTMB(form, data = d, family = binomial),
                               warning = function(x) { w <<- c(w, conditionMessage(x)); invokeRestart("muffleWarning") }),
           silent = TRUE)
  list(fit = f, ok = fit_ok(f), warnings = w)
}

prep <- function(d) {
  d$llm <- factor(d$model); d$condition <- factor(d$cond, levels = c("C0", "C2"))
  d$language <- factor(d$lang); d$task <- factor(d$task)
  for (m in levels(d$llm)) d[[paste0("c2_", make.names(m))]] <- as.numeric(d$llm == m & d$condition == "C2")
  d
}

steps_for <- function(outcome) {
  fix <- "y ~ llm + language + %s"
  if (outcome == "unsafe_write")
    return(list(list(step = "task fixed (protocol)", re = "", fixed_task = TRUE)))
  list(list(step = "full", re = "(1|task) + (1|task:language) + (1|llm:task)", fixed_task = FALSE),
       list(step = "drop (1|llm:task)", re = "(1|task) + (1|task:language)", fixed_task = FALSE),
       list(step = "drop (1|task:language)", re = "(1|task)", fixed_task = FALSE),
       list(step = "drop (1|task): task fixed", re = "", fixed_task = TRUE))
}

formula_for <- function(st, cvars, drop = NULL) {
  terms <- c("llm", "language", setdiff(cvars, drop))
  if (st$fixed_task) terms <- c(terms, "task")
  if (nzchar(st$re)) terms <- c(terms, st$re)
  as.formula(paste("y ~", paste(terms, collapse = " + ")))
}

cells_of <- function(d) {
  a <- aggregate(y ~ model + cond, data = d, FUN = function(v) c(n = length(v), k = sum(v)))
  a <- data.frame(model = a$model, cond = a$cond, n = a$y[, "n"], events = a$y[, "k"])
  a$prop <- a$events / a$n
  a$separation <- a$events == 0 | a$events == a$n
  a
}

boot_contrast <- function(d, stat, seed = SEED) {
  set.seed(seed)
  idx <- split(seq_len(nrow(d)), d$task)
  obs <- stat(d)
  bs <- replicate(B, { i <- unlist(lapply(idx, function(v) v[sample.int(length(v), length(v), replace = TRUE)])); stat(d[i, ]) })
  bs <- bs[is.finite(bs)]
  p <- if (length(bs)) min(1, 2 * min(mean(bs <= 0), mean(bs >= 0))) else NA
  c(est = obs, lo = unname(quantile(bs, 0.025, na.rm = TRUE)), hi = unname(quantile(bs, 0.975, na.rm = TRUE)), p = p)
}
prop_diff <- function(m) function(d) mean(d$y[d$model == m & d$cond == "C2"]) - mean(d$y[d$model == m & d$cond == "C0"])
flag_diff <- function(cn) function(d) {
  e <- d[d$cond == cn, ]
  mean(tapply(e$y[e$model %in% FLAG], e$model[e$model %in% FLAG], mean)) -
    mean(tapply(e$y[!e$model %in% FLAG], e$model[!e$model %in% FLAG], mean))
}

fits <- list(); contrasts <- list(); cells <- list()
for (oc in unique(d0$outcome)) {
  d <- prep(d0[d0$outcome == oc, ])
  if (oc == "unsafe_write") d$task <- factor(d$task)
  ce <- cells_of(d); ce$outcome <- oc; cells[[oc]] <- ce
  cvars <- grep("^c2_", names(d), value = TRUE)
  used <- NULL
  if (sum(d$y) > 0 && sum(d$y) < nrow(d)) {
    for (st in steps_for(oc)) {
      r <- fit_try(formula_for(st, cvars), d)
      fits[[length(fits) + 1]] <- data.frame(outcome = oc, step = st$step, ok = r$ok, n = nrow(d), events = sum(d$y),
                                             warnings = paste(unique(r$warnings), collapse = " | "))
      if (r$ok) { used <- list(st = st, fit = r$fit); break }
    }
  } else {
    fits[[length(fits) + 1]] <- data.frame(outcome = oc, step = "no variation", ok = FALSE, n = nrow(d), events = sum(d$y), warnings = "")
  }
  sep_models <- ce$model[ce$separation]
  # Family A: C2 vs C0 within each LLM
  for (m in levels(d$llm)) {
    v <- paste0("c2_", make.names(m))
    row <- data.frame(outcome = oc, family = "A", contrast = paste0(m, ": C2 vs C0"), estimate = NA, lo = NA, hi = NA,
                      scale = "OR", test = NA, p = NA)
    if (!is.null(used) && !(m %in% sep_models)) {
      cf <- fixef(used$fit)$cond; se <- sqrt(diag(vcov(used$fit)$cond))
      r0 <- fit_try(formula_for(used$st, cvars, drop = v), d)
      if (r0$ok) {
        lr <- 2 * (as.numeric(logLik(used$fit)) - as.numeric(logLik(r0$fit)))
        row$test <- "LR"; row$p <- pchisq(max(lr, 0), 1, lower.tail = FALSE)
      } else {
        row$test <- "Wald"; row$p <- 2 * pnorm(-abs(cf[v] / se[v]))
      }
      row$estimate <- exp(cf[v]); row$lo <- exp(cf[v] - 1.96 * se[v]); row$hi <- exp(cf[v] + 1.96 * se[v])
    } else {
      b <- boot_contrast(d, prop_diff(m))
      row$estimate <- b["est"]; row$lo <- b["lo"]; row$hi <- b["hi"]; row$scale <- "difference in proportions"
      row$test <- if (m %in% sep_models) "bootstrap (separation)" else "bootstrap (no model)"; row$p <- b["p"]
    }
    contrasts[[length(contrasts) + 1]] <- row
  }
  # Family B: flagship vs others within each condition
  for (cn in c("C0", "C2")) {
    row <- data.frame(outcome = oc, family = "B", contrast = paste0("flagship vs others, ", cn), estimate = NA, lo = NA,
                      hi = NA, scale = "OR", test = NA, p = NA)
    sep_here <- any(ce$separation[ce$cond == cn])
    if (!is.null(used) && !sep_here) {
      cf <- fixef(used$fit)$cond; V <- vcov(used$fit)$cond
      L <- setNames(numeric(length(cf)), names(cf))
      lv <- levels(d$llm); fl <- lv %in% FLAG
      # log-odds of llm k (reference language, task effects averaged out): intercept + llm_k (+ c2_k in C2)
      for (k in seq_along(lv)) {
        wk <- if (fl[k]) 1 / sum(fl) else -1 / sum(!fl)
        nm <- paste0("llm", lv[k]); if (nm %in% names(L)) L[nm] <- L[nm] + wk
        if (cn == "C2") { v <- paste0("c2_", make.names(lv[k])); if (v %in% names(L)) L[v] <- L[v] + wk }
      }
      est <- sum(L * cf); se <- sqrt(as.numeric(t(L) %*% V %*% L))
      row$estimate <- exp(est); row$lo <- exp(est - 1.96 * se); row$hi <- exp(est + 1.96 * se)
      row$test <- "Wald"; row$p <- 2 * pnorm(-abs(est / se))
    } else {
      b <- boot_contrast(d, flag_diff(cn))
      row$estimate <- b["est"]; row$lo <- b["lo"]; row$hi <- b["hi"]; row$scale <- "difference in proportions"
      row$test <- if (sep_here) "bootstrap (separation)" else "bootstrap (no model)"; row$p <- b["p"]
    }
    contrasts[[length(contrasts) + 1]] <- row
  }
}
ct <- do.call(rbind, contrasts)
ct$p_holm <- NA
for (g in unique(paste(ct$outcome, ct$family))) {
  i <- paste(ct$outcome, ct$family) == g
  ct$p_holm[i] <- p.adjust(ct$p[i], method = "holm")
}
write.csv(do.call(rbind, fits), file.path(dir, "primary_fits.csv"), row.names = FALSE)
write.csv(ct, file.path(dir, "primary_contrasts.csv"), row.names = FALSE)
write.csv(do.call(rbind, cells), file.path(dir, "primary_cells.csv"), row.names = FALSE)
cat("fits:\n"); print(do.call(rbind, fits)[, 1:5])
cat("contrasts:", nrow(ct), "rows ->", file.path(dir, "primary_contrasts.csv"), "\n")
