# 호환 shim: 실제 모듈은 orchestrator_v1/monitoring/dashboard.py (docs/architecture/ROOT_MODULE_SPLIT_PLAN.md)
import importlib as _il
import sys as _sys

if __name__ == "__main__":  # `python dashboard.py` 직접 실행은 실제 모듈의 __main__ 블록(run_dashboard)까지 전달한다
    import runpy as _runpy

    _runpy.run_module("orchestrator_v1.monitoring.dashboard", run_name="__main__")
    raise SystemExit

_sys.modules[__name__] = _il.import_module("orchestrator_v1.monitoring.dashboard")
