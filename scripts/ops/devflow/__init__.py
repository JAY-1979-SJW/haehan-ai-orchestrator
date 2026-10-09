# haehan-shim: tools.devflow
# 호환 shim: 실제 모듈은 tools.devflow 로 이동했다 (tools/devflow/__init__.py).
# 옛 경로의 import · 파일 경로 로드 · 직접 실행을 모두 받는다. 새 코드는 새 경로를 쓸 것.
# 생성: tools/devflow/make_shim.py — 계약 테스트: tests/test_shim_contract.py
import importlib as _il
import sys as _sys


def _install(real, g, mods):
    # spec_from_file_location 으로 이 파일을 직접 읽는 쪽은 sys.modules 교체를 못 본다 → 실제 속성을 복사해 준다.
    g.update({k: v for k, v in vars(real).items() if not (k.startswith("__") and k.endswith("__"))})
    mods[g["__name__"]] = real


_install(_il.import_module("tools.devflow"), globals(), _sys.modules)

# 형제 하위 모듈 선등록 — import old.sub.a 가 부모 __path__ 를 따라 새로 실행되는 것을 막는다
_sys.modules[f"{__name__}.make_constraints"] = _il.import_module("tools.devflow.make_constraints")
_sys.modules[f"{__name__}.make_shim"] = _il.import_module("tools.devflow.make_shim")
_sys.modules[f"{__name__}.merge_step_check"] = _il.import_module("tools.devflow.merge_step_check")
_sys.modules[f"{__name__}.move_preflight"] = _il.import_module("tools.devflow.move_preflight")
_sys.modules[f"{__name__}.pre_change_dry_run"] = _il.import_module("tools.devflow.pre_change_dry_run")
_sys.modules[f"{__name__}.run_impacted_tests"] = _il.import_module("tools.devflow.run_impacted_tests")
_sys.modules[f"{__name__}.worktree_change_index"] = _il.import_module("tools.devflow.worktree_change_index")
