# 호환 shim: 실제 모듈은 ai_orchestrator/connectors/kakao/skill_router.py (docs/architecture/TOOL_HOME_MAP.md — 도구 집으로 이동)
import importlib as _il
import sys as _sys

_sys.modules[__name__] = _il.import_module("ai_orchestrator.connectors.kakao.skill_router")
