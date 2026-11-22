# llm-client-resilience — see README.md; RUNBOOK.md (full run sequence) is in the Zenodo code archive
GO_IMAGE := golang:1.27.3-bookworm@sha256:d9b6a1beb9474adc2a1ce842573639b44b2a0dd49b6669f51d3821baf9ec37c9
VERSION  ?= $(shell git describe --always --dirty 2>/dev/null || echo dev)

.PHONY: check analyze-confirm analyze-variants classify images test test-mock test-unit verify-e0 verify-e0-quick verify-e1 analyze clean-slots

images:
	docker build -f runner/images/mock.Dockerfile   -t lcr-mock:dev --build-arg VERSION=$(VERSION) .
	docker build -f runner/images/python.Dockerfile -t lcr-run-python:dev .
	docker build -f runner/images/probe.Dockerfile  -t lcr-probe:dev .
	docker build -f runner/images/node.Dockerfile   -t lcr-run-node:dev .
	docker build -f runner/images/java.Dockerfile   -t lcr-run-java:dev . && docker tag lcr-run-java:dev lcr-build-java:dev
	docker build -f runner/images/go-build.Dockerfile -t lcr-build-go:dev .
	docker build -f runner/images/go-run.Dockerfile -t lcr-run-go:dev .
	docker build -f runner/images/lint-py.Dockerfile -t lcr-lint-py:dev .
	docker build -f runner/images/lint-go.Dockerfile -t lcr-lint-go:dev .
	docker build -f runner/images/analysis-r.Dockerfile -t lcr-analysis-r:dev .

test: test-mock test-unit

test-mock:
	docker run --rm -v "$(CURDIR)":/src -w /src/mock $(GO_IMAGE) sh -c 'go vet ./... && go test -count=1 ./...'

test-unit: images
	python3 -m unittest discover -s tests/unit -v

# End-to-end verification of E0 (isolation, TLS trust, all scenarios, 330 s repetition).
verify-e0: images
	python3 -u tests/integration/e0_verify.py --slots 4

verify-e0-quick: images
	python3 -u tests/integration/e0_verify.py --slots 4 --quick

# A trivial solution through S0-S9 in all four languages (~8 min on 4 slots).
verify-e1: images
	python3 -u tests/integration/e1_verify.py --slots 4

# Stage A: everything in analysis/out/main/ from data/main/ alone.
analyze:
	python3 analysis/e4_baselines.py data/dev/e4/baselines data/dev/e4/s4lead-baselines
	python3 analysis/collect.py --run main --jobs 6
	python3 analysis/primary.py --run main
	docker run --rm --network none --user $$(id -u):$$(id -g) -v "$(CURDIR)/analysis:/a:ro" -v "$(CURDIR)/analysis/out/main:/d" lcr-analysis-r:dev Rscript /a/models.R /d
	python3 analysis/descriptive.py
	python3 analysis/fig_km.py
	python3 analysis/review_round8.py
	python3 analysis/fig_dumbbell.py
	python3 analysis/vs_baseline.py --run main
	python3 analysis/s4_mechanism.py --run main
	python3 analysis/exploratory.py --run main
	python3 analysis/independent_check.py --run main
	python3 analysis/collect.py --run main-rep --jobs 6
	python3 analysis/repeatability.py --run main --rep main-rep
	python3 analysis/paper_tables.py --run main

# D43: confirmatory replication, scripts frozen in protocol/CONFIRM_FREEZE.json
analyze-confirm:
	python3 tools/verify_confirm_freeze.py
	python3 analysis/collect_confirm.py --run confirm --jobs 4
	python3 classify/features.py --run confirm
	python3 classify/lint.py --run confirm
	python3 analysis/confirm_analysis.py
	docker run --rm --network none --user $$(id -u):$$(id -g) -v "$(CURDIR)/analysis:/a:ro" -v "$(CURDIR)/analysis/out/confirm:/d" lcr-analysis-r:dev Rscript /a/confirm_model.R /d

# D38, D39, D45: S4 gap variants, held-out check of the revisions, S0slow
analyze-variants:
	python3 analysis/variants_analysis.py

clean-slots:
	-docker ps -a --format '{{.Names}}' | grep -E '^lcr-(mock|sol)-' | xargs docker rm -f
	-docker network ls --format '{{.Name}}' | grep -E '^lcr-(int|ctl)-' | xargs docker network rm

# E9: classification (features.csv), linters (lint/), agreement with the author's manual check.
classify:
	python3 classify/features.py --run main
	python3 classify/lint.py --run main
	@python3 -c "import csv,sys; r=list(csv.DictReader(open('data/main/classify/manual_check.csv'))); sys.exit(0 if r and all(x.get('author_library') for x in r) else 1)" 2>/dev/null && python3 classify/agreement.py --run main || echo 'manual check not filled in yet: agreement skipped'

# Key numbers of the article from the released summary data (standard library, under a minute, no Docker).
check:
	python3 tools/check_key_numbers.py
