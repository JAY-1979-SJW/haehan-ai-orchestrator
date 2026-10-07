# 호환 shim: 실제 모듈은 ai_orchestrator/connectors/eum/router.py (도구 지도 B3·split-eum)
import importlib as _il
import sys as _sys

_sys.modules[__name__] = _il.import_module("ai_orchestrator.connectors.eum.router")
