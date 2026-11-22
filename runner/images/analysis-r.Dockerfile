# R analysis environment (stage A): R 4.6.1, CRAN snapshot 2026-10-28 (Posit Package Manager, set by the base image).
FROM rocker/r-ver:4.6.1@sha256:780bc87219250a6dfffef6c812999731986fd94d8d5f7e572d1157c923d1b4bb
RUN Rscript -e 'install.packages(c("glmmTMB", "jsonlite"), Ncpus = 2); stopifnot(requireNamespace("glmmTMB"), requireNamespace("jsonlite"))' \
 && Rscript -e 'ip <- installed.packages()[, c("Package", "Version")]; write.table(ip, "/etc/lcr-r-packages.tsv", sep = "\t", row.names = FALSE, quote = FALSE)'
USER 65534:65534
WORKDIR /tmp
