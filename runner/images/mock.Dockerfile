# Mock service image. Build context: repository root.
FROM golang:1.27.3-bookworm@sha256:d9b6a1beb9474adc2a1ce842573639b44b2a0dd49b6669f51d3821baf9ec37c9 AS build
WORKDIR /src
COPY mock/go.mod mock/go.sum ./
RUN go mod download
COPY mock/*.go ./
ARG VERSION=dev
RUN CGO_ENABLED=0 go build -trimpath -ldflags "-X main.version=${VERSION}" -o /mock .

FROM debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3
RUN apt-get update \
 && apt-get install -y --no-install-recommends nftables tcpdump iproute2 \
 && rm -rf /var/lib/apt/lists/* \
 && dpkg-query -W -f='${Package}=${Version}\n' nftables tcpdump libpcap0.8 iproute2 > /etc/lcr-packages.txt
COPY --from=build /mock /usr/local/bin/mock
COPY certs/mock.pem certs/mock-key.pem /certs/
ENTRYPOINT ["/usr/local/bin/mock"]
