FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY requirements-hosted.txt /app/requirements-hosted.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /app/requirements-hosted.txt
COPY contentsweep_prodcheck-0.3.0-py3-none-any.whl /app/dist/contentsweep_prodcheck-0.3.0-py3-none-any.whl
COPY contentsweep_prodcheck-0.3.0.tar.gz /app/dist/contentsweep_prodcheck-0.3.0.tar.gz
COPY manifest.json /app/dist/manifest.json
RUN pip install --no-cache-dir --no-deps /app/dist/contentsweep_prodcheck-0.3.0-py3-none-any.whl
USER 10001
EXPOSE 8080
CMD ["python", "-m", "mcp_products.inspector.hosted"]
