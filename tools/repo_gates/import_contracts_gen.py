# module_category: gate
# primary_trade: common
"""import-linter 계약(.importlinter) 생성기 — 이 저장소의 기존 구조 규칙을 표준 도구(import-linter) 계약으로 옮긴다.

왜(2026-10-08 대표님 승인 '표준 도구 채택' 1단계): 층·금지 import·분리 규칙을 자체 스크립트(code_map/modules.py,
skeleton_gate, module_separation_gate, check_blog_separability)만 재고 있었다. 같은 규칙을 표준 도구로도 재서
둘을 나란히 비교한 뒤 옮겨 탄다. 이번 단계는 '추가'만 한다 — 기존 게이트는 그대로 둔다.

정본은 계속 기존 설정이다(.importlinter 는 손으로 고치지 않는 생성물):
  - 층·허용 방향: configs/module_registry.json 의 files[].layer + allowed_deps (없으면 layer_rules.classify_path)
  - 금지 import 쌍: tools/code_map/layer_rules.py 의 _FORBIDDEN_IMPORT_PAIRS
  - leaf 분리: tools/repo_gates/module_separation_gate.py 의 SEPARATED_MODULES
  - 블로그 분리: scripts/naver/blog/cli/check_blog_separability.py 의 FORBIDDEN_DOMAINS (import 하지 않고 AST 로 읽는다 —
    운영 도구가 들어낼 수 있어야 하는 블로그 모듈에 import 의존을 새로 만들지 않도록)

기존 측정과 같은 판정을 내도록 맞춘 점:
  - 층은 파일 단위다(폴더 136개 중 85개가 여러 층 혼재). 그래서 층 계약은 파일 모듈을 그대로 나열하고 as_packages = False.
  - code_map 은 '직접 import' 만 센다 → 모든 forbidden 계약에 allow_indirect_imports = True.
  - __init__.py(패키지 자체)는 code_map 이 방향 검사에서 뺀다 → 계약에도 넣지 않는다.
알려진 차이(import-linter 가 못 보는 곳): 저장소 루트의 평면 .py, __init__.py 가 없는 폴더(scripts/ops 등 namespace) 아래 파일,
importlib.import_module 같은 동적 import. 목록은 --gaps 로 출력한다.

사용:
    python tools/repo_gates/import_contracts_gen.py           # .importlinter 다시 쓰기
    python tools/repo_gates/import_contracts_gen.py --check   # 정본과 어긋나면 exit 1 (CI 비차단 단계에서 lint-imports 전에)
    python tools/repo_gates/import_contracts_gen.py --gaps    # import-linter 가 볼 수 없는 층 파일 목록
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

_BOOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402
from tools.code_map.layer_rules import _FORBIDDEN_IMPORT_PAIRS, classify_path  # noqa: E402
from tools.repo_gates.module_separation_gate import SEPARATED_MODULES  # noqa: E402

ROOT = repo_root()
OUT = ROOT / ".importlinter"
REGISTRY = ROOT / "configs" / "module_registry.json"
BLOG_CHECKER = ROOT / "scripts" / "naver" / "blog" / "cli" / "check_blog_separability.py"
ROOT_PACKAGES = ("ai_orchestrator", "scripts", "local_agent", "orchestrator_v1")
CODE_LAYERS = [f"L{i}" for i in range(1, 11)]  # code_map 과 같다(L11 시험·L12 문서는 방향 규칙 밖)


def _tracked_py(root: Path) -> list[str]:
    r = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "*.py"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return sorted(r.stdout.splitlines())


def visible_module(path: str, root: Path) -> str | None:
    """import-linter(grimp)가 그래프에 넣는 모듈 이름. 루트 패키지에서 그 파일까지 모든 폴더에 __init__.py 가 있어야 보인다."""
    parts = PurePosixPath(path).parts
    if len(parts) < 2 or parts[0] not in ROOT_PACKAGES:
        return None
    for i in range(1, len(parts)):
        if not (root.joinpath(*parts[:i]) / "__init__.py").is_file():
            return None
    names = list(parts[:-1])
    stem = PurePosixPath(path).stem
    if stem != "__init__":
        names.append(stem)
    if not all(n.isidentifier() for n in names):
        return None
    return ".".join(names)


def file_layers(root: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    """파일 → 층 (code_map/modules.py 의 _load_layer_and_module_maps 와 같은 규칙) + allowed_deps."""
    doc = json.loads((root / "configs" / "module_registry.json").read_text(encoding="utf-8"))
    reg = doc.get("files", {})
    layers = {f: (reg[f]["layer"] if f in reg else classify_path(f)[0]) for f in _tracked_py(root)}
    return layers, doc["allowed_deps"]


def _layer_modules(root: Path, layers: dict[str, str]) -> tuple[dict[str, list[str]], list[str]]:
    by_layer: dict[str, list[str]] = {lv: [] for lv in CODE_LAYERS}
    gaps: list[str] = []
    for f, lv in sorted(layers.items()):
        if lv not in by_layer or PurePosixPath(f).name == "__init__.py":
            continue
        mod = visible_module(f, root)
        if mod is None:
            gaps.append(f"{f} ({lv})")
        else:
            by_layer[lv].append(mod)
    return by_layer, gaps


def _block(key: str, values: list[str]) -> list[str]:
    return [f"{key} ="] + [f"    {v}" for v in values]


def _forbidden(cid: str, name: str, src: list[str], bad: list[str], *, as_packages: bool) -> list[str]:
    lines = [f"[importlinter:contract:{cid}]", f"name = {name}", "type = forbidden"]
    lines += _block("source_modules", src) + _block("forbidden_modules", bad)
    lines += ["allow_indirect_imports = True", f"as_packages = {as_packages}", ""]
    return lines


def layer_contracts(by_layer: dict[str, list[str]], allowed: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    for lv in CODE_LAYERS:
        if lv not in allowed or not by_layer[lv]:
            continue
        bad_layers = [x for x in CODE_LAYERS if x not in allowed[lv]]
        bad = sorted(m for x in bad_layers for m in by_layer[x])
        if bad:
            name = f"층 {lv} 는 {','.join(allowed[lv])} 만 직접 import (module_registry allowed_deps)"
            out += _forbidden(f"layer-{lv}", name, by_layer[lv], bad, as_packages=False)
    return out


def _prefix_match(prefix: str, modules: list[str]) -> tuple[list[str], bool]:
    """code_map 처럼 점 이름 startswith 로 고른다. 모두 prefix 패키지 자신·하위면 (prefix 하나, True)로 접는다."""
    hits = [m for m in modules if m.startswith(prefix)]
    if hits and prefix in modules and all(m == prefix or m.startswith(prefix + ".") for m in hits):
        return [prefix], True
    return hits, False


def pair_contracts(modules: list[str]) -> tuple[list[str], list[str]]:
    out: list[str] = []
    skipped: list[str] = []
    known = set(modules)
    for i, (src_p, bad_p, reason) in enumerate(_FORBIDDEN_IMPORT_PAIRS, 1):
        src, src_pkg = _prefix_match(src_p, modules)
        if "." not in bad_p and bad_p not in ROOT_PACKAGES:  # 외부 패키지(fastapi 등)
            bad, bad_pkg = [bad_p], True
        else:
            bad, bad_pkg = _prefix_match(bad_p, modules)
        if not src or not bad:
            skipped.append(f"{src_p} -> {bad_p} (해당 모듈 없음)")
            continue
        if src_pkg and bad_pkg:
            out += _forbidden(f"pair-{i:02d}", reason, src, bad, as_packages=True)
            continue
        # 한쪽이라도 접을 수 없으면(예: scripts.cdp_ 처럼 이름 앞부분) 양쪽 모두 모듈을 펼쳐 정확히 나열한다
        src = [m for m in modules if m.startswith(src_p)]
        if bad_p in known or "." in bad_p or bad_p in ROOT_PACKAGES:
            bad = [m for m in modules if m.startswith(bad_p)]
        out += _forbidden(f"pair-{i:02d}", reason, src, bad, as_packages=False)
    return out, skipped


def separation_contracts(modules: list[str]) -> list[str]:
    """leaf → 다른(공유 아닌) leaf 직접 import 금지. module_separation_gate 처럼 직접 import 만 본다.

    independence 계약은 간접 경로(leaf → 공유 leaf → 루트 → 다른 leaf)까지 위반으로 세고 끌 수 없어서
    기존 게이트와 판정이 달라진다(2026-10-08 실측: google_live_inputs·google_workflows 가 루트 경유로만 BROKEN).
    그래서 source = 모든 leaf, forbidden = 공유 아닌 leaf 인 forbidden 계약으로 같은 판정을 낸다(같은 모듈 쌍은 import-linter 가 건너뜀).
    """
    out: list[str] = []
    for spec in SEPARATED_MODULES:
        root_mod = spec["root"][:-3].replace("/", ".")
        shared = {f"{root_mod}_{s}" for s in spec.get("shared_leaves", set())}
        leaves = sorted(m for m in modules if m.startswith(root_mod + "_") and "." not in m[len(root_mod) + 1 :])
        bad = [m for m in leaves if m not in shared]
        if len(leaves) < 2 or not bad:
            continue
        name = f"{spec['name']} leaf 는 공유 아닌 다른 leaf 직접 import 금지(module_separation_gate)"
        out += _forbidden(f"sep-{spec['name']}", name, leaves, bad, as_packages=False)
    return out


def _blog_forbidden_domains() -> list[str]:
    tree = ast.parse(BLOG_CHECKER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "FORBIDDEN_DOMAINS" for t in node.targets
        ):
            return [str(x) for x in ast.literal_eval(node.value)]
    raise SystemExit(f"FORBIDDEN_DOMAINS 를 찾지 못함: {BLOG_CHECKER}")


def blog_contracts(modules: list[str]) -> list[str]:
    known = set(modules)
    bad = [d for d in _blog_forbidden_domains() if d in known]
    if "scripts.naver.blog" not in known or not bad:
        return []
    name = "블로그 모듈은 다른 업무 도메인 import 금지(check_blog_separability)"
    return _forbidden("blog-separability", name, ["scripts.naver.blog"], bad, as_packages=True)


def render(root: Path) -> tuple[str, list[str]]:
    layers, allowed = file_layers(root)
    by_layer, gaps = _layer_modules(root, layers)
    modules = sorted({m for f in _tracked_py(root) if (m := visible_module(f, root))})
    pairs, skipped = pair_contracts(modules)
    head = [
        "# 생성물 — 손으로 고치지 말 것. 다시 만들기: python tools/repo_gates/import_contracts_gen.py",
        "# 정본: configs/module_registry.json · tools/code_map/layer_rules.py · tools/repo_gates/module_separation_gate.py ·",
        "#       scripts/naver/blog/cli/check_blog_separability.py (머리말: tools/repo_gates/import_contracts_gen.py)",
        f"# import-linter 가 볼 수 없는 층 파일 {len(gaps)}개(루트 평면·namespace 폴더) — 목록: --gaps",
    ]
    head += [f"# 건너뛴 금지 쌍: {s}" for s in skipped]
    head += ["", "[importlinter]", *_block("root_packages", list(ROOT_PACKAGES))]
    head += ["include_external_packages = True", ""]
    body = layer_contracts(by_layer, allowed) + pairs + separation_contracts(modules) + blog_contracts(modules)
    return "\n".join(head + body), gaps


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help=".importlinter 가 정본과 같은지만 확인")
    ap.add_argument("--gaps", action="store_true", help="import-linter 가 볼 수 없는 층 파일 목록")
    args = ap.parse_args()
    text, gaps = render(ROOT)
    if args.gaps:
        print("\n".join(gaps))
        return 0
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(
                "[import_contracts_gen] .importlinter 가 정본과 다릅니다 — python tools/repo_gates/import_contracts_gen.py 로 다시 만드세요"
            )
            return 1
        print("[import_contracts_gen] .importlinter 최신")
        return 0
    _write_atomic(OUT, text)
    print(f"[import_contracts_gen] {OUT.name} 작성 — 층 계약 밖 파일 {len(gaps)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
