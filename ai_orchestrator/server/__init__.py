# server 패키지 — 서버 보조 모듈(작업 큐·정책·스토어) 모음.
# FastAPI 앱 본체는 ai_orchestrator/asgi.py 에 있다. 기존 진입점 표기
# `ai_orchestrator.server:app` 은 그대로 동작하도록 여기서 lazy 로 넘겨준다.
#
# 즉시 import 하지 않는 이유(순환 방지):
#   router.py → action_router.py → server/action_task_api.py
#   → server/__init__.py → (즉시) asgi.py → from .router import router (초기화 중) → ImportError
# 앱은 실제로 `app` 을 요청받을 때 처음 불러온다.


def __getattr__(name: str):
    if name == "app":
        from ai_orchestrator.asgi import app

        globals()["app"] = app  # 이후 접근은 __getattr__ 없이 바로 반환
        return app
    raise AttributeError(f"module 'ai_orchestrator.server' has no attribute {name!r}")
