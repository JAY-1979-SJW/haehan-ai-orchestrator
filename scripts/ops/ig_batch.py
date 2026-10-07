# haehan-shim: scripts.instagram.ops.ig_batch
# 호환 shim: 실제 모듈은 scripts.instagram.ops.ig_batch 로 이동했다 (scripts/instagram/ops/ig_batch.py).
# 옛 경로의 import · 파일 경로 로드 · 직접 실행을 모두 받는다. 새 코드는 새 경로를 쓸 것.
# 생성: scripts/ops/make_shim.py — 계약 테스트: tests/test_shim_contract.py
import importlib as _il
import sys as _sys

if __name__ == "__main__":  # 직접 실행(python old.py / -m old)은 새 모듈의 __main__ 으로 전달
    import pathlib as _pl
    import runpy as _runpy

    # 스크립트로 직접 실행하면 sys.path[0] 이 이 파일의 폴더라 저장소 루트를 넣어 줘야 새 모듈을 찾는다(make_shim 은 이 부트스트랩을 만들지 않는다).
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
    _runpy.run_module("scripts.instagram.ops.ig_batch", run_name="__main__")
    raise SystemExit

def _install(real, g, mods):
    # spec_from_file_location 으로 이 파일을 직접 읽는 쪽은 sys.modules 교체를 못 본다 → 실제 속성을 복사해 준다.
    g.update({k: v for k, v in vars(real).items() if not (k.startswith("__") and k.endswith("__"))})
    mods[g["__name__"]] = real


_install(_il.import_module("scripts.instagram.ops.ig_batch"), globals(), _sys.modules)
