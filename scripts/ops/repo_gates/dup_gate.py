# haehan-shim: tools.repo_gates.dup_gate
# 호환 shim: 실제 모듈은 tools.repo_gates.dup_gate 로 이동했다 (tools/repo_gates/dup_gate.py).
# 옛 경로의 import · 파일 경로 로드 · 직접 실행을 모두 받는다. 새 코드는 새 경로를 쓸 것.
# 생성: tools/devflow/make_shim.py — 계약 테스트: tests/test_shim_contract.py
import importlib as _il
import sys as _sys

if __name__ == "__main__":  # 직접 실행(python old.py / -m old)은 새 모듈의 __main__ 으로 전달
    import runpy as _runpy
    from pathlib import Path as _Path

    # haehan-root-bootstrap: 하위 폴더 shim 직접 실행용 루트 부트스트랩(정본 paths import 전이라 불가피, G5 예외)
    _root = str(_Path(__file__).resolve().parents[3])
    if _root not in _sys.path:
        _sys.path.insert(0, _root)

    _runpy.run_module("tools.repo_gates.dup_gate", run_name="__main__")
    raise SystemExit


def _install(real, g, mods):
    # spec_from_file_location 으로 이 파일을 직접 읽는 쪽은 sys.modules 교체를 못 본다 → 실제 속성을 복사해 준다.
    g.update({k: v for k, v in vars(real).items() if not (k.startswith("__") and k.endswith("__"))})
    mods[g["__name__"]] = real


_install(_il.import_module("tools.repo_gates.dup_gate"), globals(), _sys.modules)
