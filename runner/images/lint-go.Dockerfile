# golangci-lint for RQ5 (E9): noctx only. Built on the Go prepare image (same toolchain and module cache).
FROM lcr-build-go:dev
USER 0
RUN GOFLAGS=-mod=mod GOBIN=/usr/local/bin go install github.com/golangci/golangci-lint/v2/cmd/golangci-lint@v2.15.0 \
 && rm -rf /root/.cache /root/go && golangci-lint version > /etc/lcr-golangci-version.txt
ENV GOFLAGS=-mod=mod GOPROXY=off GOCACHE=/tmp/gocache GOLANGCI_LINT_CACHE=/tmp/lintcache
USER 65534:65534
WORKDIR /tmp
