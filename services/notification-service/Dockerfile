FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

FROM python:3.12-slim
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src/ ./src/
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8004
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/health')" || exit 1
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8004", "--workers", "2"]
