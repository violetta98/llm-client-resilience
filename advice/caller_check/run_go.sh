#!/bin/sh
# D56: run inside lcr-build-go:dev with --network none; mounts advice/ read-only at /adv.
set -e
for prog in go-context-caller go-retry-budget go-idem-key; do
  d=$(mktemp -d); cd $d
  case $prog in
    go-idem-key) cp /adv/W1/$prog.go p.go; printf 'package main\nimport "context"\nfunc call(ctx context.Context, b string) (map[string]any, error) { return CreatePaymentContext(ctx, b, "ord-1", "1.00", "EUR", "") }\n' > c.go ;;
    *) cp /adv/R1/$prog.go p.go; printf 'package main\nimport "context"\nfunc call(ctx context.Context, b string) (map[string]any, error) { return GetUserProfileContext(ctx, b, "u-1") }\n' > c.go ;;
  esac
  cp /adv/caller_check/main.go.txt main.go
  go mod init check >/dev/null 2>&1
  GOFLAGS=-mod=mod GOCACHE=/tmp/gocache go run . $prog
done
