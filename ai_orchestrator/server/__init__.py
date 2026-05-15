# server package
# server.py(FastAPI app)가 server/ 패키지로 가려진 문제를 해소한다.
#
# 기존 즉시 로딩 방식은 다음 순환 import를 유발했다:
#   router.py → action_router.py → server/action_task_api.py
#   → server/__init__.py (server.py 즉시 실행)
#   → server.py → from .router import router (아직 초기화 중) → ImportError
#
# __getattr__로 lazy load하여 순환 import를 방지한다.
# from ai_orchestrator.server import app 패턴은 그대로 동작한다.
import importlib.util as _ilu
import pathlib as _pl


def __getattr__(name: str):
    if name == "app":
        _server_py = _pl.Path(__file__).parent.parent / "server.py"
        _spec = _ilu.spec_from_file_location("ai_orchestrator._server_module", _server_py)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        # 이후 접근 시 __getattr__ 재호출 없이 바로 반환되도록 캐시
        globals()["app"] = _mod.app
        return _mod.app
    raise AttributeError(f"module 'ai_orchestrator.server' has no attribute {name!r}")
