"""데스크톱 번들 진입점·리소스 회귀 방지.

2026-10-08 첫 빌드 E2E 실측으로 확인된 두 결함을 고정한다.
1) PyInstaller 는 진입 파일을 단독 스크립트로 실행하므로, 진입 파일에 상대 import 가 있으면
   "attempted relative import with no known parent package" 로 서버가 시작되지 않는다.
2) electron-builder 가 Next standalone 의 node_modules 를 복사하지 않아 resources/nextjs/server.js 가
   "Cannot find module 'next'" 로 실패했다.
"""

import ast
import json
import re
from pathlib import Path

from ai_orchestrator.paths import repo_root

ROOT = repo_root()
SPECS = ("haehan-server.spec", "local-agent.spec", "mcp-server.spec")


def _entry_files(spec: Path) -> list[Path]:
    text = spec.read_text(encoding="utf-8")
    m = re.search(r"Analysis\(\s*(?:#[^\n]*\n\s*)*\[(.*?)\]", text, re.S)
    assert m, f"{spec.name}: Analysis 진입점 목록을 찾지 못함"
    # 진입점마다 str(ROOT / 'a' / 'b.py') 한 개 — 진입점별로 따로 경로를 만든다(여러 개여도 섞이지 않게)
    entries = re.findall(r"str\(\s*ROOT\s*((?:/\s*['\"][^'\"]+['\"]\s*)+)\)", m.group(1))
    assert entries, f"{spec.name}: 진입점 경로 식을 해석하지 못함"
    return [ROOT.joinpath(*re.findall(r"['\"]([^'\"]+)['\"]", e)) for e in entries]


def test_spec_entry_files_exist_and_have_no_relative_imports():
    for name in SPECS:
        for entry in _entry_files(ROOT / name):
            assert entry.is_file(), f"{name}: 진입 파일 없음 {entry}"
            tree = ast.parse(entry.read_text(encoding="utf-8"))
            imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
            assert imports, f"{name}: 진입 파일 {entry.name} 에 import 가 하나도 없음 — 검사 대상이 비어 있음"
            relative = [n.lineno for n in imports if isinstance(n, ast.ImportFrom) and n.level > 0]
            assert relative == [], f"{name}: 진입 파일 {entry.name} 에 상대 import(줄 {relative}) — 번들에서 실패"


def test_server_entry_runs_asgi_app():
    tree = ast.parse((ROOT / "ai_orchestrator" / "server" / "desktop_entry.py").read_text(encoding="utf-8"))
    imports = {(n.module, a.name) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert ("ai_orchestrator", "asgi") in imports


def test_next_standalone_node_modules_is_bundled():
    pkg = json.loads((ROOT / "admin-web" / "electron" / "package.json").read_text(encoding="utf-8"))
    pairs = {(r.get("from"), r.get("to")) for r in pkg["build"]["extraResources"]}
    assert ("../.next/standalone/node_modules", "nextjs/node_modules") in pairs
