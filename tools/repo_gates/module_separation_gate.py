"""모듈 분리 게이트 (Module Separation Gate).

docs/module_separation_standard.md 기준을 강제한다. 분리한 모듈을 레지스트리에
등록하고, 각 모듈에 대해:
  1) 컴포지션 루트 LOC ≤ max_root_loc  (분리 진행하며 ratchet down)
  2) leaf 서브모듈은 sibling leaf 를 직접 import 금지 (shared/주입/이벤트만 허용)
를 검사한다.

판정: ROOT_TOO_LARGE > 0 또는 LEAF_COUPLING > 0 → FAIL.

사용:
    python tools/repo_gates/module_separation_gate.py
    python tools/repo_gates/module_separation_gate.py --json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

# ── 분리 완료/진행 모듈 레지스트리 ───────────────────────────────────────────
# 모듈을 분리할 때마다 등록하고, 루트가 줄면 max_root_loc 를 낮춘다(ratchet).
SEPARATED_MODULES: list[dict] = [
    {
        "name": "local_agent_router",
        "root": "ai_orchestrator/agent_hub/router/root.py",
        # 진행 ratchet: 분리할수록 낮춘다. 목표 ≤ 400(얇은 컴포지션 루트).
        "max_root_loc": 150,
        # 폴더형(T4 C6): leaf 는 root 와 같은 폴더의 *.py
        "leaf_dir": "ai_orchestrator/agent_hub/router",
        "package": "ai_orchestrator.agent_hub.router",
        # 누구나 import 가능한 공유 leaf (계약/공용 유틸/검증/큐상태)
        "shared_leaves": {"schemas", "guards", "validation", "up_queue"},
    },
    {
        "name": "google_live_inputs",
        "root": "scripts/google/common/live_inputs.py",
        # 진행 ratchet: 분리할수록 낮춘다. 목표 ≤ 400.
        "max_root_loc": 400,
        "leaf_glob": "scripts/google/common/live_inputs_*.py",
        # 공유 leaf (설정/상수/env, CDP 프리미티브 등)
        "shared_leaves": {"config", "cdp", "fill"},
    },
    {
        "name": "cafe_mixin",
        "root": "scripts/naver/agent_mixins/cafe_mixin.py",
        "max_root_loc": 30,  # ratchet: 서브믹스인 분리하며 낮춘다(목표 ≤ 200)
        "leaf_glob": "scripts/naver/agent_mixins/cafe_mixin_*.py",
        # 공유 leaf (_js 등 공통 헬퍼)
        "shared_leaves": {"common"},
    },
    {
        "name": "blog_mixin",
        "root": "scripts/naver/agent_mixins/blog_mixin.py",
        "max_root_loc": 30,
        "leaf_glob": "scripts/naver/agent_mixins/blog_mixin_*.py",
        "shared_leaves": {"common"},
    },
    {
        "name": "page_helper",
        "root": "scripts/browser/page/page_helper.py",
        "max_root_loc": 45,
        "leaf_glob": "scripts/page_helper_*.py",
        "shared_leaves": {"common", "interact"},
    },
    {
        "name": "navigator",
        "root": "scripts/browser/navigator/navigator.py",
        "max_root_loc": 25,
        "leaf_glob": "scripts/navigator_*.py",
        "shared_leaves": {"common", "scan", "verify"},
    },
    {
        "name": "local_agent_registry",
        "root": "ai_orchestrator/agent_hub/registry/facade.py",
        "max_root_loc": 75,
        # 폴더형(T4 C5): leaf 는 root 와 같은 폴더의 *.py (root·__init__ 제외), 서로의 import 는 `from .x`·`from <package>.x`·`from <package> import x` 로 본다.
        "leaf_dir": "ai_orchestrator/agent_hub/registry",
        "package": "ai_orchestrator.agent_hub.registry",
        "shared_leaves": {"common", "sanitize", "agent"},
    },
    {
        "name": "google_workflows",
        "root": "scripts/google/common/workflows.py",
        "max_root_loc": 35,
        "leaf_glob": "scripts/google/common/workflows_*.py",
        "shared_leaves": {"common", "actions"},
    },
    {
        "name": "naver_router",
        "root": "scripts/naver/router.py",
        "max_root_loc": 95,
        "leaf_glob": "scripts/naver/router_*.py",
        "shared_leaves": {"common"},
    },
    {
        "name": "youtube_search",
        "root": "scripts/google/youtube/search.py",
        "max_root_loc": 40,
        "leaf_glob": "scripts/google/youtube/search_*.py",
        "shared_leaves": {"common", "search", "score", "transcript"},
    },
    {
        "name": "youtube_research",
        "root": "scripts/youtube/research.py",
        "max_root_loc": 40,
        "leaf_glob": "scripts/youtube/research_*.py",
        "shared_leaves": {"common", "search", "analysis", "captions"},
    },
    {
        "name": "module_quality_gate",
        "root": "tools/quality/module_quality_gate.py",
        "max_root_loc": 45,
        "leaf_glob": "scripts/ops/quality/module_quality_gate_*.py",
        "shared_leaves": {"common", "modules", "checks_repo", "checks_audit", "checks_web"},
    },
]


@dataclass
class Finding:
    category: str  # ROOT_TOO_LARGE | LEAF_COUPLING | MISSING
    detail: str


@dataclass
class GateResult:
    findings: list[Finding] = field(default_factory=list)

    def add(self, c: str, d: str) -> None:
        self.findings.append(Finding(c, d))

    def count(self, c: str) -> int:
        return sum(1 for f in self.findings if f.category == c)

    @property
    def failed(self) -> bool:
        return len(self.findings) > 0


def _loc(path: Path) -> int:
    try:
        return sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
    except OSError:
        return 0


def _leaf_key(path: Path, root_stem: str) -> str:
    """local_agent_router_schemas.py → 'schemas' (root stem 이후 suffix)."""
    name = path.stem  # local_agent_router_schemas
    prefix = root_stem + "_"
    return name[len(prefix) :] if name.startswith(prefix) else name


_IMPORT_RE = re.compile(r"""(?:from|import)\s+(?:\.|[\w.]*\.)?([A-Za-z_][\w]*)""")


def _sibling_imports(src: str, package: str) -> set[str]:
    """한 파일이 같은 패키지의 어떤 sibling 모듈을 import 하는지(상대·절대 import 모두)."""
    pkg = re.escape(package)
    found: set[str] = set()
    for pattern in (
        r"from\s+\.(\w+)(?:\.\w+)*\s+import",
        rf"from\s+{pkg}\.(\w+)(?:\.\w+)*\s+import",
        rf"import\s+{pkg}\.(\w+)",
    ):
        found.update(m.group(1) for m in re.finditer(pattern, src))
    for pattern in (r"from\s+\.\s+import\s+\(?([\w,\s]+)", rf"from\s+{pkg}\s+import\s+\(?([\w,\s]+)"):
        for m in re.finditer(pattern, src):
            found.update(name.strip() for name in m.group(1).split(",") if name.strip().isidentifier())
    return found


def _check_dir_leaves(result: GateResult, mod: dict, root_path: Path) -> None:
    """폴더형 모듈: leaf 대상이 0개면(경로 이동 뒤 설정이 낡은 경우) 조용히 통과하지 않고 MISSING 으로 알린다."""
    leaf_dir = ROOT / mod["leaf_dir"]
    leaf_paths = [p for p in sorted(leaf_dir.glob("*.py")) if p != root_path and p.name != "__init__.py"]
    if not leaf_paths:
        result.add("MISSING", f"{mod['name']}: leaf 가 없음 {mod['leaf_dir']}")
        return
    leaf_keys = {p.stem for p in leaf_paths}
    shared = set(mod.get("shared_leaves", set()))
    for lp in leaf_paths:
        try:
            src = lp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for dep in sorted(_sibling_imports(src, mod["package"]) & leaf_keys):
            if dep != lp.stem and dep not in shared:
                result.add(
                    "LEAF_COUPLING",
                    f"{mod['name']}: leaf '{lp.stem}' 가 sibling leaf '{dep}' 직접 import (shared/주입/이벤트로 통신해야 함)",
                )


def run_gate() -> GateResult:
    result = GateResult()
    for mod in SEPARATED_MODULES:
        root_path = ROOT / mod["root"]
        root_stem = root_path.stem  # local_agent_router
        if not root_path.exists():
            result.add("MISSING", f"{mod['name']}: 루트 없음 {mod['root']}")
            continue

        # 1) 루트 LOC ratchet
        loc = _loc(root_path)
        if loc > mod["max_root_loc"]:
            result.add(
                "ROOT_TOO_LARGE",
                f"{mod['name']}: 루트 {mod['root']} {loc} LOC > 상한 {mod['max_root_loc']} (분리 진행 필요)",
            )

        # 2) leaf 간 직접 import 금지
        if "leaf_dir" in mod:  # 폴더형: leaf 는 같은 폴더의 다른 파일
            _check_dir_leaves(result, mod, root_path)
            continue
        leaf_paths = list(ROOT.glob(mod["leaf_glob"]))
        leaf_keys = {_leaf_key(p, root_stem) for p in leaf_paths}
        shared = set(mod.get("shared_leaves", set()))
        for lp in leaf_paths:
            this_key = _leaf_key(lp, root_stem)
            try:
                src = lp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # 같은 모듈군의 다른 leaf 를 import 하는지 (root_stem_ 접두 토큰)
            for m in re.finditer(rf"{re.escape(root_stem)}_([A-Za-z_][\w]*)", src):
                dep = m.group(1)
                if dep in leaf_keys and dep != this_key and dep not in shared:
                    result.add(
                        "LEAF_COUPLING",
                        f"{mod['name']}: leaf '{this_key}' 가 sibling leaf "
                        f"'{dep}' 직접 import (shared/주입/이벤트로 통신해야 함)",
                    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = run_gate()
    cats = ["ROOT_TOO_LARGE", "LEAF_COUPLING", "MISSING"]
    counts = {c: result.count(c) for c in cats}

    if args.json:
        print(
            json.dumps(
                {
                    "pass": not result.failed,
                    "counts": counts,
                    "findings": [{"category": f.category, "detail": f.detail} for f in result.findings],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("=== 모듈 분리 게이트 ===")
        for c in cats:
            print(f"  {c}: {counts[c]}")
        for f in result.findings:
            print(f"  [{f.category}] {f.detail}")
        print("판정:", "FAIL" if result.failed else "PASS")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
