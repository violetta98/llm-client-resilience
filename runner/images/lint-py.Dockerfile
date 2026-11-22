# Python linters for RQ5 (E9). Same Python base as the solution runner. Build context: repository root.
FROM python:3.13.18-slim-bookworm@sha256:281d39ff02e3b389401586134ff9e6572954687822a58055ec07a60ded4e0b7f
RUN pip install --no-cache-dir --no-compile bandit==1.9.4 ruff==0.17.4 && pip freeze > /etc/lcr-pip-freeze.txt
USER 65534:65534
WORKDIR /tmp
