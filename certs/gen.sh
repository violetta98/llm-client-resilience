#!/bin/sh
# Generates the TEST certificate authority and the mock's server certificate.
# Test-only keys; committed so that runs are reproducible. Never trust this CA
# outside the benchmark containers.
set -eu
cd "$(dirname "$0")"
SANS="IP:127.0.0.1"
k=0; while [ $k -le 63 ]; do SANS="$SANS,IP:10.77.$k.2"; k=$((k+1)); done
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
  -keyout ca-key.pem -out ca.pem -days 3650 -subj "/CN=LCR Benchmark Test CA" \
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"
openssl req -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
  -keyout mock-key.pem -out mock.csr -subj "/CN=lcr-mock"
printf "subjectAltName=%s\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n" "$SANS" > mock.ext
openssl x509 -req -in mock.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -out mock.pem -days 1825 -extfile mock.ext
rm -f mock.csr mock.ext ca.srl
chmod 644 *.pem
