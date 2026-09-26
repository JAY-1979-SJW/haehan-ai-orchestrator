FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install Python dependencies (Playwright package, FastAPI, uvicorn)
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -c constraints.txt -r requirements.txt

# Install Playwright Chromium binary and dependencies
RUN python -m playwright install --with-deps chromium

# Copy browser_worker package only
COPY browser_worker/ ./browser_worker/

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8500/health',timeout=3).status==200 else 1)"

# Start browser worker service
CMD ["uvicorn", "browser_worker.app:app", "--host", "0.0.0.0", "--port", "8500"]
