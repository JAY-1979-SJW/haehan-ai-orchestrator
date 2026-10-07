# 호환 shim: 실제 패키지는 scripts.naver.mail.read (docs/architecture/TOOL_HOME_MAP.md)
# 하위 모듈(scripts.naver.mail_read.cdp 등)까지 같은 모듈이 나오도록 sys.modules 별칭을 건다.
import importlib as _il
import sys as _sys

_real_pkg = _il.import_module("scripts.naver.mail.read")
_sys.modules[__name__] = _real_pkg

for _sub in ("cdp", "body_reader", "classify", "entry", "list_collector", "pipeline"):
    _sys.modules[f"{__name__}.{_sub}"] = _il.import_module(f"scripts.naver.mail.read.{_sub}")
