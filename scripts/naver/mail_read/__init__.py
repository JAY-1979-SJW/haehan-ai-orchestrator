# 호환 shim: 실제 패키지는 scripts.naver.mail.read 로 이동했다 (scripts/naver/mail/read/__init__.py).
# 옛 경로의 import · 파일 경로 로드를 모두 받는다. 하위 모듈(scripts.naver.mail_read.cdp 등)도
# 같은 모듈이 나오도록 별칭을 건다. make_shim.py는 패키지+다중 하위모듈을 지원하지 않아 수동 작성 —
# haehan-shim 마커는 일부러 안 붙인다: tests/test_shim_contract.py가 __init__.py 경로를
# "pkg.__init__" 로 import해 대조하는데, 패키지는 보통 "pkg"로 import되어 같은 파일이어도
# 별개 모듈 객체가 되어 해당 공통 계약(단일파일 전제)과 안 맞는다(실측 확인, 2026-10-07).
# 계약 테스트는 tests/test_naver_mail_read_shim.py 로 따로 둔다.
import importlib as _il
import sys as _sys


def _install(real, g, mods):
    # spec_from_file_location 으로 이 파일을 직접 읽는 쪽은 sys.modules 교체를 못 본다 → 실제 속성을 복사해 준다.
    g.update({k: v for k, v in vars(real).items() if not (k.startswith("__") and k.endswith("__"))})
    mods[g["__name__"]] = real


_install(_il.import_module("scripts.naver.mail.read"), globals(), _sys.modules)

for _sub in ("cdp", "body_reader", "classify", "entry", "list_collector", "pipeline"):
    _sys.modules[f"{__name__}.{_sub}"] = _il.import_module(f"scripts.naver.mail.read.{_sub}")
