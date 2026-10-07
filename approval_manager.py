# 호환 shim: 실제 모듈은 orchestrator_v1/tasks/approval_manager.py (docs/architecture/ROOT_MODULE_SPLIT_PLAN.md)
import importlib as _il
import sys as _sys

_sys.modules[__name__] = _il.import_module("orchestrator_v1.tasks.approval_manager")
