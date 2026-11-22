# Prompt ablation P1-P3 (protocol/ABLATION_ADDENDUM.md). Input: ablation_p.csv from analysis/ablation_analysis.py.
# y ~ c + lang + (1|model) + (1|task), glmmTMB, one-sided Wald p for c (all three predict OR < 1); fallback: drop
# (1|task), then (1|model), then a plain logistic model, then a one-sided Fisher exact test. Holm over P1-P3.
suppressPackageStartupMessages({ library(glmmTMB) })
args <- commandArgs(trailingOnly = TRUE); dir <- if (length(args)) args[1] else "analysis/out/ablation"
d <- read.csv(file.path(dir, "ablation_p.csv"), stringsAsFactors = FALSE)
ok <- function(f) !inherits(f, "try-error") && isTRUE(f$sdr$pdHess) && f$fit$convergence == 0
out <- NULL
for (h in c("P1", "P2", "P3")) {
  dh <- d[d$hyp == h, ]
  forms <- c(full = "y ~ c + lang + (1 | model) + (1 | task)", no_task = "y ~ c + lang + (1 | model)",
             no_model = "y ~ c + lang + (1 | task)", fixed = "y ~ c + lang")
  res <- NULL
  for (nm in names(forms)) {
    f <- try(glmmTMB(as.formula(forms[[nm]]), data = dh, family = binomial), silent = TRUE)
    if (ok(f)) {
      est <- fixef(f)$cond["c"]; se <- sqrt(vcov(f)$cond["c", "c"]); z <- est / se
      res <- data.frame(hyp = h, fit = nm, n = nrow(dh), share_c0 = mean(dh$y[dh$c == 0]), share_c1 = mean(dh$y[dh$c == 1]),
                        or = exp(est), lo = exp(est - 1.96 * se), hi = exp(est + 1.96 * se), z = z, p_one_sided = pnorm(z))
      break
    }
  }
  if (is.null(res)) {
    ft <- fisher.test(table(factor(dh$c, levels = 1:0), factor(dh$y, levels = 1:0)), alternative = "less")
    res <- data.frame(hyp = h, fit = "fisher", n = nrow(dh), share_c0 = mean(dh$y[dh$c == 0]), share_c1 = mean(dh$y[dh$c == 1]),
                      or = unname(ft$estimate), lo = NA, hi = NA, z = NA, p_one_sided = ft$p.value)
  }
  out <- rbind(out, res)
}
out$p_holm <- p.adjust(out$p_one_sided, method = "holm")
out$supported <- out$p_holm < 0.05
write.csv(out, file.path(dir, "ablation_tests.csv"), row.names = FALSE)
print(out)
