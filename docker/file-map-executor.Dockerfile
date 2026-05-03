# Dockerfile for file-map-executor service
# Dedicated Python service for file cleanup operations (dry_run=true only)

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn==0.24.0 \
    pydantic==2.5.0 \
    requests==2.31.0

# Copy executor service code
COPY services/file_map_executor ./services/file_map_executor

# Create necessary directories
RUN mkdir -p /app/audit /app/logs

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=8510
ENV EXECUTOR_MODE=service

# Health check
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8510/health', timeout=3)" || exit 1

EXPOSE 8510

# Run FastAPI app
CMD ["python", "-m", "uvicorn", "services.file_map_executor.app:app", "--host=0.0.0.0", "--port=8510"]
