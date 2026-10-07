FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -c constraints.txt -r requirements.txt

COPY . .

RUN mkdir -p /app/ai_orchestrator/storage

# 빌드 식별: /api/v1/health 가 git_sha·build_time 으로 노출한다(없으면 "unknown").
# COPY 뒤에 두어 값이 바뀌어도 pip install·COPY 레이어 캐시는 유지된다.
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ENV GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME}

EXPOSE 8400

# 헬스체크: 내부에서 /api/v1/health 만 확인 (stdlib 사용, curl 미설치)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys;\
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8400/api/v1/health',timeout=3).status==200 else 1)" || exit 1

CMD ["uvicorn", "ai_orchestrator.asgi:app", "--host", "0.0.0.0", "--port", "8400"]
