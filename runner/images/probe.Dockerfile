# Manual-verification probe (curl, openssl s_client). Never used to run solutions.
FROM debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3
RUN apt-get update && apt-get install -y --no-install-recommends curl openssl iproute2 netcat-openbsd \
 && rm -rf /var/lib/apt/lists/*
COPY certs/ca.pem /ca.pem
