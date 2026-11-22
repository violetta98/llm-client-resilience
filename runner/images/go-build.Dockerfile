# Go prepare (compile) image. Build context: repository root.
FROM golang:1.27.3-bookworm@sha256:d9b6a1beb9474adc2a1ce842573639b44b2a0dd49b6669f51d3821baf9ec37c9
ENV GOMODCACHE=/opt/lcr-go/pkg/mod GOTOOLCHAIN=local CGO_ENABLED=0
COPY runner/go/libs/go.mod runner/go/libs/go.sum runner/go/libs/deps.go /opt/lcr-go/libs/
RUN cd /opt/lcr-go/libs && GOFLAGS=-mod=mod go mod download all && go build ./... \
 && go list -m all > /etc/lcr-go-modules.txt && chmod -R a+rX /opt/lcr-go
COPY runner/go/prepare/main.go /opt/lcr-go/prepare/main.go
RUN cd /opt/lcr-go/prepare && go mod init lcrprepare >/dev/null 2>&1 && go build -o /opt/lcr-go/bin/lcr-prepare . && rm -rf /root/.cache
COPY runner/go/driver/lcr_driver.go /opt/lcr-go/driver/
RUN printf '#!/bin/sh\nexec /opt/lcr-go/bin/lcr-prepare "$@"\n' > /opt/lcr-go/prepare.sh && chmod 755 /opt/lcr-go/prepare.sh
USER 65534:65534
