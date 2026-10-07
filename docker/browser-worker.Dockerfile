# 서버 배포 폐기(2026-10-07 18:05 결정) 후 미사용 — T4 때 존치/보관 재판단
# Playwright 1.63 은 Debian 13(trixie) 공식 지원(#36916)이나 --with-deps 실측 미검증 -> bookworm 고정
FROM python:3.14-slim-bookworm

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

# Copy the worker package (ai_orchestrator.browser_tool.worker); browser_tool/__init__ imports only within browser_tool
COPY ai_orchestrator/__init__.py ./ai_orchestrator/__init__.py
COPY ai_orchestrator/browser_tool/ ./ai_orchestrator/browser_tool/

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8500/health',timeout=3).status==200 else 1)"

# Start browser worker service
CMD ["uvicorn", "ai_orchestrator.browser_tool.worker.app:app", "--host", "0.0.0.0", "--port", "8500"]
