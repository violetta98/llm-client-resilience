# Go runner: executes the prepared static binary (driver + solution).
FROM debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY certs/ca.pem /usr/local/share/ca-certificates/lcr-test-ca.crt
RUN update-ca-certificates >/dev/null
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
USER 65534:65534
WORKDIR /tmp
