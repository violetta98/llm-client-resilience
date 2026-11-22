# Confirmatory tests H1-H3 (protocol/CONFIRM_ADDENDUM.md). Input: confirm_h.csv from analysis/confirm_analysis.py.
# y ~ x + language (+ condition for H1) + (1|model) + (1|task), glmmTMB, one-sided Wald p for x (OR > 1 for H1, H3;
# OR < 1 for H2); fallback: drop (1|task), then (1|model), then a plain logistic model. Holm over H1-H3.
suppressPackageStartupMessages({ library(glmmTMB) })
args <- commandArgs(trailingOnly = TRUE); dir <- if (length(args)) args[1] else "analysis/out/confirm"
d <- read.csv(file.path(dir, "confirm_h.csv"), stringsAsFactors = FALSE)
ok <- function(f) !inherits(f, "try-error") && isTRUE(f$sdr$pdHess) && f$fit$convergence == 0
out <- NULL
for (h in c("H1", "H2", "H3")) {
  dh <- d[d$hyp == h, ]
  fx <- if (h == "H1") "y ~ x + lang + c2" else "y ~ x + lang"
  forms <- c(full = paste(fx, "+ (1 | model) + (1 | task)"), no_task = paste(fx, "+ (1 | model)"),
             no_model = paste(fx, "+ (1 | task)"), fixed = fx)
  res <- NULL
  for (nm in names(forms)) {
    f <- try(glmmTMB(as.formula(forms[[nm]]), data = dh, family = binomial), silent = TRUE)
    if (ok(f)) {
      est <- fixef(f)$cond["x"]; se <- sqrt(vcov(f)$cond["x", "x"]); z <- est / se
      p <- if (h == "H2") pnorm(z) else pnorm(z, lower.tail = FALSE)
      res <- data.frame(hyp = h, fit = nm, n = nrow(dh), or = exp(est), lo = exp(est - 1.96 * se),
                        hi = exp(est + 1.96 * se), z = z, p_one_sided = p)
      break
    }
  }
  if (is.null(res)) res <- data.frame(hyp = h, fit = "none", n = nrow(dh), or = NA, lo = NA, hi = NA, z = NA, p_one_sided = NA)
  out <- rbind(out, res)
}
out$p_holm <- p.adjust(out$p_one_sided, method = "holm")
out$supported <- out$p_holm < 0.05
write.csv(out, file.path(dir, "confirm_tests.csv"), row.names = FALSE)
print(out)
