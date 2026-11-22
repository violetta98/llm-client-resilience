# TypeScript/Node.js runner and prepare image. Build context: repository root.
FROM node:26.12.1-bookworm-slim@sha256:88e480776c6149ff1d098cd304f44bf18057fb5d284a3329b78162d29821e28c
# Offered libraries in /node_modules: resolvable from /solution and /tmp.
COPY runner/node/libs/package.json runner/node/libs/package-lock.json /
RUN cd / && npm ci --ignore-scripts --no-audit --no-fund \
 && npm ls --all --json > /etc/lcr-npm-ls.json && npm cache clean --force
# Harness tools (esbuild) outside the solutions' resolution path.
COPY runner/node/tools/package.json runner/node/tools/package-lock.json /opt/lcr-tools/
RUN cd /opt/lcr-tools && npm ci --no-audit --no-fund && npm cache clean --force
COPY certs/ca.pem /usr/local/share/ca-certificates/lcr-test-ca.crt
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/* && update-ca-certificates >/dev/null
ENV NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/lcr-test-ca.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt NODE_ENV=production
COPY runner/node/driver.mjs runner/node/prepare.mjs /driver/
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["node", "/driver/driver.mjs"]
