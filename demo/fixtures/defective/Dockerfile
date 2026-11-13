FROM python:3.12-slim AS base
USER root
FROM base AS runtime
CMD uvicorn app:app --reload
