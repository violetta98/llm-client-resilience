# Post-hoc sensitivity of the confirmatory tests (D48; not part of the frozen addendum).
# Input: confirm_h.csv (analysis/confirm_analysis.py). For H1-H3:
#   cell   - the frozen model plus a random intercept for the (model, task, language) cell of three samples;
#   firth  - bias-reduced (Firth) logistic regression with the same fixed effects, which stays finite under the
#            near-separation of H1 (brglm2 if installed, otherwise skipped);
#   fisher - one-sided Fisher exact test of the 2x2 table (ignores clustering);
#   noclaude - the frozen model without the two Claude models.
suppressPackageStartupMessages({ library(glmmTMB) })
args <- commandArgs(trailingOnly = TRUE); dir <- if (length(args)) args[1] else "analysis/out/confirm"
d <- read.csv(file.path(dir, "confirm_h.csv"), stringsAsFactors = FALSE)
d$cell <- paste(d$model, d$task, d$lang)
has_br <- requireNamespace("brglm2", quietly = TRUE)
ok <- function(f) !inherits(f, "try-error") && isTRUE(f$sdr$pdHess) && f$fit$convergence == 0
one <- function(h, z) if (h == "H2") pnorm(z) else pnorm(z, lower.tail = FALSE)
row <- function(h, what, n, est, se) data.frame(hyp = h, analysis = what, n = n, or = exp(est), lo = exp(est - 1.96 * se),
                                                hi = exp(est + 1.96 * se), p_one_sided = one(h, est / se))
out <- NULL
for (h in c("H1", "H2", "H3")) {
  dh <- d[d$hyp == h, ]
  fx <- if (h == "H1") "y ~ x + lang + c2" else "y ~ x + lang"
  for (spec in list(c("cell", paste(fx, "+ (1 | model) + (1 | task) + (1 | cell)"), "all"),
                    c("cell_no_task", paste(fx, "+ (1 | model) + (1 | cell)"), "all"),
                    c("noclaude", paste(fx, "+ (1 | model) + (1 | task)"), "noclaude"),
                    c("noclaude_no_task", paste(fx, "+ (1 | model)"), "noclaude"))) {
    dd <- if (spec[3] == "noclaude") dh[!grepl("^claude", dh$model), ] else dh
    f <- try(glmmTMB(as.formula(spec[2]), data = dd, family = binomial), silent = TRUE)
    if (ok(f)) out <- rbind(out, row(h, spec[1], nrow(dd), fixef(f)$cond["x"], sqrt(vcov(f)$cond["x", "x"])))
    else out <- rbind(out, data.frame(hyp = h, analysis = paste(spec[1], "(no convergence)"), n = nrow(dd), or = NA, lo = NA, hi = NA, p_one_sided = NA))
  }
  if (has_br) {
    f <- glm(as.formula(fx), data = dh, family = binomial, method = brglm2::brglmFit)
    s <- summary(f)$coefficients
    out <- rbind(out, row(h, "firth (fixed effects only)", nrow(dh), s["x", 1], s["x", 2]))
  }
  t <- table(factor(dh$x, levels = c(1, 0)), factor(dh$y, levels = c(1, 0)))
  ft <- fisher.test(t, alternative = if (h == "H2") "less" else "greater")
  out <- rbind(out, data.frame(hyp = h, analysis = "fisher (2x2, no clustering)", n = nrow(dh), or = unname(ft$estimate),
                               lo = ft$conf.int[1], hi = ft$conf.int[2], p_one_sided = ft$p.value))
}
write.csv(out, file.path(dir, "confirm_sensitivity.csv"), row.names = FALSE)
print(out, digits = 3)
