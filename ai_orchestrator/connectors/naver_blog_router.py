# haehan-shim: ai_orchestrator.connectors.naver_blog.naver_blog_router
# 호환 shim: 실제 모듈은 ai_orchestrator.connectors.naver_blog.naver_blog_router 로 이동했다 (ai_orchestrator/connectors/naver_blog/naver_blog_router.py).
# 옛 경로의 import · 파일 경로 로드 · 직접 실행을 모두 받는다. 새 코드는 새 경로를 쓸 것.
# 생성: scripts/ops/make_shim.py — 계약 테스트: tests/test_shim_contract.py
import importlib as _il
import sys as _sys


def _install(real, g, mods):
    # spec_from_file_location 으로 이 파일을 직접 읽는 쪽은 sys.modules 교체를 못 본다 → 실제 속성을 복사해 준다.
    g.update({k: v for k, v in vars(real).items() if not (k.startswith("__") and k.endswith("__"))})
    mods[g["__name__"]] = real


_install(_il.import_module("ai_orchestrator.connectors.naver_blog.naver_blog_router"), globals(), _sys.modules)
