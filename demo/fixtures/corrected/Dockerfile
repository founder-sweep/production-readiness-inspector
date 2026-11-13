# Synthetic digest for parsing tests; do not build this fixture.
FROM python:3.12-slim@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa AS builder
USER root
FROM python:3.12-slim@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa AS runtime
USER 10001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0"]
