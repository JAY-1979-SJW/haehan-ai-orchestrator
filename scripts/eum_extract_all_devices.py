# 호환 shim: 실제 모듈은 scripts/eum/extract_all_devices.py (도구 지도 B2·split-eum)
import importlib as _il
import sys as _sys

_sys.modules[__name__] = _il.import_module("scripts.eum.extract_all_devices")
