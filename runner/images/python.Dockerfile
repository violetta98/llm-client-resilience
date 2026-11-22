# Python solution runner. Build context: repository root.
FROM python:3.13.18-slim-bookworm@sha256:281d39ff02e3b389401586134ff9e6572954687822a58055ec07a60ded4e0b7f
COPY runner/python/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-compile -r /tmp/requirements.txt \
 && pip freeze > /etc/lcr-pip-freeze.txt && rm /tmp/requirements.txt
# Test CA: system trust store + env vars (requests uses its own bundle).
COPY certs/ca.pem /usr/local/share/ca-certificates/lcr-test-ca.crt
RUN update-ca-certificates >/dev/null
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONHASHSEED=0
COPY runner/python/driver.py runner/python/prepare.py /driver/
USER 65534:65534
WORKDIR /tmp
# -s -P (not -I): no user site, no script dir on sys.path, but env vars apply.
ENTRYPOINT ["python", "-s", "-P", "/driver/driver.py"]
