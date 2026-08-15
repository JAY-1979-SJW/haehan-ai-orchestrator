"""기존 구현 조회 — 자동화/수집/사이트 코드 작성 전 필수 실행.

사용:
    python scripts/ops/capability_check.py <키워드>
    python scripts/ops/capability_check.py cafe
    python scripts/ops/capability_check.py smartstore
    python scripts/ops/capability_check.py naver mail
    python scripts/ops/capability_check.py eum

출력:
    - API 엔드포인트 (ai_orchestrator/connectors/)
    - Python 진입점 (scripts/ __init__.py __all__)
    - CLI 커맨드 (service_catalog.py)
    - 데이터 파일 경로
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 이 스크립트는 `python scripts/ops/capability_check.py` 로 직접 실행된다.
# 그때는 저장소 루트가 sys.path 에 없어 scripts 패키지를 import 할 수 없다.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops.vendor_api_registry import cdp_warning as vendor_cdp_warning  # noqa: E402
from scripts.ops.vendor_api_registry import find as find_vendor_apis  # noqa: E402
from scripts.ops.vendor_api_registry import format_report as format_vendor_report  # noqa: E402


def _search_terms(argv: list[str]) -> list[str]:
    terms = [t.lower() for t in argv[1:] if t]
    return terms or [""]


def _match(text: str, terms: list[str]) -> bool:
    t = text.lower()
    return all(term in t for term in terms)


# ── 1. API 엔드포인트 ─────────────────────────────────────────────────


def _scan_routers(terms: list[str]) -> list[dict]:
    results = []
    connector_dir = ROOT / "ai_orchestrator" / "connectors"
    for f in sorted(connector_dir.glob("*_router.py")):
        if not _match(f.name, terms):
            continue
        src = f.read_text(encoding="utf-8", errors="ignore")
        prefix_m = re.search(r'prefix\s*=\s*["\']([^"\']+)["\']', src)
        prefix = prefix_m.group(1) if prefix_m else ""
        endpoints = re.findall(
            r'@\w+\.(?:get|post|put|delete|patch)\(\s*["\']([^"\']*)["\']',
            src,
        )
        methods = re.findall(
            r"@\w+\.(get|post|put|delete|patch)\(",
            src,
        )
        for method, path in zip(methods, endpoints):
            full = f"/api/v1{prefix}{path}" if not path.startswith("/api") else path
            results.append(
                {
                    "file": f.name,
                    "method": method.upper(),
                    "path": full,
                }
            )
    return results


# ── 2. Python 진입점 (__init__.py __all__ + docstring) ───────────────


def _scan_init(terms: list[str]) -> list[dict]:
    results = []
    for init in ROOT.rglob("__init__.py"):
        # dist-build-tmp 제외
        if "dist-build-tmp" in str(init):
            continue
        rel = str(init.relative_to(ROOT))
        if not _match(rel, terms):
            continue
        src = init.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        # __all__ 추출
        all_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "__all__":
                        if isinstance(node.value, ast.List):
                            all_names = [
                                elt.value
                                for elt in node.value.elts
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                            ]
        # docstring 첫 줄
        docstring = ""
        if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
            docstring = str(tree.body[0].value.value).strip().split("\n")[0]
        if all_names:
            results.append(
                {
                    "file": rel,
                    "exports": all_names,
                    "doc": docstring,
                }
            )
    return results


# ── 3. service_catalog CLI 커맨드 ──────────────────────────────────────


def _scan_catalog(terms: list[str]) -> list[dict]:
    try:
        sys.path.insert(0, str(ROOT))
        from scripts.naver.service_catalog import FEATURE_CATALOG  # type: ignore
    except Exception:
        return []
    results = []
    for name, info in FEATURE_CATALOG.items():
        if not _match(name, terms):
            continue
        results.append(
            {
                "service": name,
                "commands": info.get("commands", []),
                "api_endpoints": info.get("api_endpoints", {}),
                "python_entry": info.get("python_entry", ""),
                "data_files": info.get("data_files", ""),
                "policy": info.get("policy", ""),
            }
        )
    return results


# ── 4. 최근 데이터 파일 ───────────────────────────────────────────────


def _scan_data_files(terms: list[str]) -> list[str]:
    data_dir = ROOT / "data"
    if not data_dir.exists():
        return []
    files = []
    for f in sorted(data_dir.rglob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if "dist-build-tmp" in str(f):
            continue
        rel = str(f.relative_to(ROOT))
        if _match(rel, terms):
            files.append(rel)
        if len(files) >= 10:
            break
    return files


# ── 출력 ──────────────────────────────────────────────────────────────


def _hr(char: str = "─", width: int = 60) -> str:
    return char * width


def run(argv: list[str]) -> None:
    terms = _search_terms(argv)
    label = " + ".join(terms) if any(terms) else "(전체)"
    print(f"\n{'═' * 60}")
    print(f"  capability_check  키워드: {label}")
    print(f"{'═' * 60}\n")

    # 0. 벤더 공식 API — 저장소 안이 아니라 **밖**을 먼저 본다.
    #    이 도구는 원래 '저장소 내 구현' 만 찾았다. 그래서 네이버 커머스API 가
    #    무료로 제공하는 상품등록을 CDP 로 만들다 하루를 버렸다(2026-08-15).
    #    "API가 있으면 API 호출, CDP는 최후 수단"(CLAUDE.md)을 실제로 지키려면
    #    맨 앞에 있어야 한다.
    vendors = find_vendor_apis(terms)
    if vendors:
        print(f"[0] 벤더 공식 API  ({len(vendors)}건)  ★ CDP 착수 전 필독")
        print(_hr())
        print(format_vendor_report(vendors))

    # 1. service_catalog
    catalog = _scan_catalog(terms)
    if catalog:
        print(f"[1] CLI / 서비스 카탈로그  ({len(catalog)}건)")
        print(_hr())
        for c in catalog:
            print(f"  서비스: {c['service']}")
            if c["commands"]:
                print(f"  CLI 커맨드: {', '.join(c['commands'])}")
            if c["python_entry"]:
                print(f"  Python:  {c['python_entry']}")
            if c["api_endpoints"]:
                print("  API 엔드포인트:")
                for ep, desc in c["api_endpoints"].items():
                    print(f"    {ep}")
                    print(f"      → {desc}")
            if c["data_files"]:
                print(f"  데이터:  {c['data_files']}")
            if c["policy"]:
                print(f"  정책:    {c['policy']}")
            print()

    # 2. API 엔드포인트
    routers = _scan_routers(terms)
    if routers:
        print(f"[2] API 엔드포인트  ({len(routers)}건)")
        print(_hr())
        cur_file = ""
        for r in routers:
            if r["file"] != cur_file:
                print(f"  📄 {r['file']}")
                cur_file = r["file"]
            print(f"    {r['method']:<6} {r['path']}")
        print()

    # 3. Python __init__ exports
    inits = _scan_init(terms)
    if inits:
        print(f"[3] Python 패키지 진입점  ({len(inits)}건)")
        print(_hr())
        for i in inits:
            print(f"  📦 {i['file']}")
            if i["doc"]:
                print(f"     {i['doc']}")
            print(f"     exports: {', '.join(i['exports'])}")
            print()

    # 4. 데이터 파일
    data_files = _scan_data_files(terms)
    if data_files:
        print(f"[4] 최근 데이터 파일  ({len(data_files)}건)")
        print(_hr())
        for f in data_files:
            print(f"  {f}")
        print()

    warn = vendor_cdp_warning(vendors)
    if warn:
        print(_hr("═"))
        print(warn)
        print(_hr("═"))
        print()

    if not catalog and not routers and not inits and not data_files:
        if vendors:
            print("  ⚠  저장소 내 구현 없음 — 단, 위 벤더 API 를 먼저 검토하세요.")
        else:
            print("  ⚠  기존 구현 없음 — 신규 작성 가능")
    else:
        print("  ✅ 위 구현을 먼저 사용하세요. 없을 때만 신규 작성.")
    print()


if __name__ == "__main__":
    run(sys.argv)
