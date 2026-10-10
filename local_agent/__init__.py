# haehan-shim: core.agent_runtime
# 호환 shim: 실제 모듈은 core.agent_runtime 로 이동했다 (core/agent_runtime/__init__.py).
# 옛 경로의 import · 파일 경로 로드 · 직접 실행을 모두 받는다. 새 코드는 새 경로를 쓸 것.
# 생성: tools/devflow/make_shim.py — 계약 테스트: tests/test_shim_contract.py
import importlib as _il
import sys as _sys

from core.agent_runtime import __version__ as __version__  # 동작엔 영향 없음(아래 sys.modules
# 교체가 실제 값을 돌려준다) — _install() 이 더블언더스코어 이름은 복사에서 빼므로(__name__ 등
# 보호용), mypy 같은 정적 분석은 globals() 만 보고 __version__ 이 없다고 오판한다(run38009465088
# 실측 재현: "Module 'local_agent' has no attribute '__version__'"). 정적 시야에도 보이게
# 명시적으로 다시 내보낸다.


def _install(real, g, mods):
    # spec_from_file_location 으로 이 파일을 직접 읽는 쪽은 sys.modules 교체를 못 본다 → 실제 속성을 복사해 준다.
    g.update({k: v for k, v in vars(real).items() if not (k.startswith("__") and k.endswith("__"))})
    mods[g["__name__"]] = real


_install(_il.import_module("core.agent_runtime"), globals(), _sys.modules)
