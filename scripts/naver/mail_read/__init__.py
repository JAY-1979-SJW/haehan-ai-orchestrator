# haehan-shim: scripts.naver.mail.read
# 호환 shim: 실제 모듈은 scripts.naver.mail.read 로 이동했다 (scripts/naver/mail/read/__init__.py).
# 옛 경로의 import · 파일 경로 로드 · 직접 실행을 모두 받는다. 새 코드는 새 경로를 쓸 것.
# 생성: scripts/ops/make_shim.py — 계약 테스트: tests/test_shim_contract.py
import importlib as _il
import sys as _sys


def _install(real, g, mods):
    # spec_from_file_location 으로 이 파일을 직접 읽는 쪽은 sys.modules 교체를 못 본다 → 실제 속성을 복사해 준다.
    g.update({k: v for k, v in vars(real).items() if not (k.startswith("__") and k.endswith("__"))})
    mods[g["__name__"]] = real


_install(_il.import_module("scripts.naver.mail.read"), globals(), _sys.modules)

# 형제 하위 모듈 선등록 — import old.sub.a 가 부모 __path__ 를 따라 새로 실행되는 것을 막는다
_sys.modules[f"{__name__}.body_reader"] = _il.import_module("scripts.naver.mail.read.body_reader")
_sys.modules[f"{__name__}.cdp"] = _il.import_module("scripts.naver.mail.read.cdp")
_sys.modules[f"{__name__}.classify"] = _il.import_module("scripts.naver.mail.read.classify")
_sys.modules[f"{__name__}.entry"] = _il.import_module("scripts.naver.mail.read.entry")
_sys.modules[f"{__name__}.list_collector"] = _il.import_module("scripts.naver.mail.read.list_collector")
_sys.modules[f"{__name__}.pipeline"] = _il.import_module("scripts.naver.mail.read.pipeline")
