# haehan-shim: tools.code_map
# 호환 shim: 실제 모듈은 tools.code_map 로 이동했다 (tools/code_map/__init__.py).
# 옛 경로의 import · 파일 경로 로드 · 직접 실행을 모두 받는다. 새 코드는 새 경로를 쓸 것.
# 생성: tools/devflow/make_shim.py — 계약 테스트: tests/test_shim_contract.py
import importlib as _il
import sys as _sys


def _install(real, g, mods):
    # spec_from_file_location 으로 이 파일을 직접 읽는 쪽은 sys.modules 교체를 못 본다 → 실제 속성을 복사해 준다.
    g.update({k: v for k, v in vars(real).items() if not (k.startswith("__") and k.endswith("__"))})
    mods[g["__name__"]] = real


_install(_il.import_module("tools.code_map"), globals(), _sys.modules)

# 형제 하위 모듈 선등록 — import old.sub.a 가 부모 __path__ 를 따라 새로 실행되는 것을 막는다
_sys.modules[f"{__name__}.agent_brief"] = _il.import_module("tools.code_map.agent_brief")
_sys.modules[f"{__name__}.build"] = _il.import_module("tools.code_map.build")
_sys.modules[f"{__name__}.classify"] = _il.import_module("tools.code_map.classify")
_sys.modules[f"{__name__}.fullmap"] = _il.import_module("tools.code_map.fullmap")
_sys.modules[f"{__name__}.layer_count"] = _il.import_module("tools.code_map.layer_count")
_sys.modules[f"{__name__}.layer_rules"] = _il.import_module("tools.code_map.layer_rules")
_sys.modules[f"{__name__}.modules"] = _il.import_module("tools.code_map.modules")
_sys.modules[f"{__name__}.proc_tree"] = _il.import_module("tools.code_map.proc_tree")
_sys.modules[f"{__name__}.query"] = _il.import_module("tools.code_map.query")
_sys.modules[f"{__name__}.reach"] = _il.import_module("tools.code_map.reach")
_sys.modules[f"{__name__}.ref_seeds"] = _il.import_module("tools.code_map.ref_seeds")
_sys.modules[f"{__name__}.registry_sync"] = _il.import_module("tools.code_map.registry_sync")
_sys.modules[f"{__name__}.runcheck"] = _il.import_module("tools.code_map.runcheck")
_sys.modules[f"{__name__}.scan"] = _il.import_module("tools.code_map.scan")
_sys.modules[f"{__name__}.skeleton_gate"] = _il.import_module("tools.code_map.skeleton_gate")
