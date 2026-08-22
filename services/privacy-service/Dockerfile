FROM python:3.12-slim AS builder
WORKDIR /app
COPY libs/shared /app/libs/shared
COPY libs/seir-core /app/libs/seir-core
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /app/libs/shared /app/libs/seir-core

COPY services/privacy-service /app/svc
WORKDIR /app/svc
RUN pip install --no-cache-dir .

FROM python:3.12-slim
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/svc/src ./src
COPY --from=builder /app/svc/healthcheck.py ./healthcheck.py
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8006
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python healthcheck.py || exit 1
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8006", "--workers", "2"]
