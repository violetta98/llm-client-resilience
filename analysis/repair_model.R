# Experiment B, the registered comparison (protocol/REPAIR_ADDENDUM.md, Amendment 1): fixed with the test report (R0,
# "feedback") vs fixed after a review request without a report (R1, "review"), paired by solution.
#
#   docker run --rm --network none -v "$PWD/analysis:/a:ro" -v "$PWD/analysis/out/repair:/d" lcr-analysis-r:dev Rscript /a/repair_model.R /d
#
# Model: y ~ arm + (1 | task) + (1 | model) + (1 | solution), logistic, glmmTMB. Fallback in the order of protocol v1:
# drop (1 | solution), then (1 | model), then (1 | task); last resort a bootstrap over tasks of the difference in
# proportions (2,000 resamples, seed 20261106).
suppressPackageStartupMessages({ library(glmmTMB) })
args <- commandArgs(trailingOnly = TRUE)
dir <- if (length(args)) args[1] else "analysis/out/repair"
d <- read.csv(file.path(dir, "repair_test.csv"), stringsAsFactors = FALSE)
d$arm <- factor(d$arm, levels = c("review", "feedback"))
ok <- function(f) !inherits(f, "try-error") && isTRUE(f$sdr$pdHess) && f$fit$convergence == 0
forms <- list(
  full = y ~ arm + (1 | task) + (1 | model) + (1 | solution),
  no_solution = y ~ arm + (1 | task) + (1 | model),
  no_model = y ~ arm + (1 | task),
  fixed = y ~ arm)
res <- NULL
for (nm in names(forms)) {
  f <- try(glmmTMB(forms[[nm]], data = d, family = binomial), silent = TRUE)
  if (ok(f)) {
    f0 <- try(update(f, . ~ . - arm), silent = TRUE)
    lr <- if (ok(f0)) as.numeric(2 * (logLik(f) - logLik(f0))) else NA
    est <- fixef(f)$cond["armfeedback"]; se <- sqrt(vcov(f)$cond["armfeedback", "armfeedback"])
    res <- data.frame(fit = nm, or = exp(est), lo = exp(est - 1.96 * se), hi = exp(est + 1.96 * se),
                      lr_chisq = lr, p = if (is.na(lr)) 2 * pnorm(-abs(est / se)) else pchisq(lr, 1, lower.tail = FALSE),
                      test = if (is.na(lr)) "Wald" else "LR")
    break
  }
}
if (is.null(res)) {
  set.seed(20261106); tasks <- unique(d$task)
  diffs <- replicate(2000, { s <- do.call(rbind, lapply(sample(tasks, replace = TRUE), function(t) d[d$task == t, ]))
    mean(s$y[s$arm == "feedback"]) - mean(s$y[s$arm == "review"]) })
  obs <- mean(d$y[d$arm == "feedback"]) - mean(d$y[d$arm == "review"])
  res <- data.frame(fit = "bootstrap", or = NA, lo = quantile(diffs, 0.025), hi = quantile(diffs, 0.975),
                    lr_chisq = NA, p = 2 * min(mean(diffs <= 0), mean(diffs >= 0)), test = "bootstrap (difference)")
}
res$feedback_share <- mean(d$y[d$arm == "feedback"]); res$review_share <- mean(d$y[d$arm == "review"])
res$n_solutions <- length(unique(d$solution))
write.csv(res, file.path(dir, "repair_test_result.csv"), row.names = FALSE)
print(res)
