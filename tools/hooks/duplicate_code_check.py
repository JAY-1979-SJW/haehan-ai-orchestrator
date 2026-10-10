"""코드 중복 구현 탐지 — 함수/클래스 본문 복붙 중복 + 동일 파일명 병렬 모듈.

CLAUDE.md "기존 구현 확인 의무" 위반(같은 기능을 여러 곳에 새로 짜는 것)을
사후에 잡아내는 게이트. 두 가지 신호를 본다:

  1. BODY_DUPLICATE — 서로 다른 파일의 함수/클래스 본문이 (공백·주석 제거 후)
     사실상 동일함. 최소 줄 수(min_lines) 이상인 것만 잡아 흔한 보일러플레이트
     오탐을 줄인다.
  2. DUPLICATE_BASENAME — 서로 다른 디렉터리에 동일한 파일명이 존재.
     과거 실제 사고 사례: `scripts/smartstore/actions.py` 와
     `scripts/naver/smartstore/product/*.py` 가 같은 기능을 병렬로 구현했다가
     하나를 나중에 삭제한 일이 있었다. 이 신호는 그런 병렬 구현의 조기 경보.

Usage:
    python tools/hooks/duplicate_code_check.py
    python tools/hooks/duplicate_code_check.py --path scripts --min-lines 8
    python tools/hooks/duplicate_code_check.py --json
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "data",
    "logs",
    "runs",
    "storage",
    "tmp",
    "node_modules",
    ".next",
    ".claude",
    "archive",
    "_internal",
    # 빌드 산출물 — 소스 트리 전체가 복사돼 들어가 있어 전부 오탐이 된다
    "dist",
    "dist-build-tmp",
    "dist-electron",
    "dist-electron-new",
    "dist-electron-release",
    "dist-electron-setup",
    "dist-installer",
    "build",
    "venv",
    ".venv",
}

DEFAULT_ROOTS = ["scripts", "ai_orchestrator"]


@dataclass
class UnitDup:
    kind: str  # "function" | "class"
    name: str
    lines: int
    locations: list[str]


@dataclass
class BasenameDup:
    basename: str
    paths: list[str]


def _iter_py_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def _normalize_source(src: str) -> str:
    """공백/주석/docstring 차이를 무시하고 비교하기 위한 정규화.

    완전 정확한 비교는 아니다(변수명이 다르면 다른 것으로 본다) — 이건
    "완전 복붙" 탐지용이지 의미론적 유사도 분석이 아니다.
    """
    lines = []
    for line in src.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        lines.append(re.sub(r"\s+", " ", stripped))
    return "\n".join(lines)


def _hash_body(src: str) -> str:
    return hashlib.sha256(_normalize_source(src).encode("utf-8")).hexdigest()


def _collect_unit(groups, src, rel, node, min_lines):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        segment = ast.get_source_segment(src, node)
        if not segment:
            return
        line_count = segment.count("\n") + 1
        if line_count < min_lines:
            return
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        h = _hash_body(segment)
        loc = f"{rel}:{node.lineno} ({node.name})"
        groups[h].append((kind, loc, line_count))


def find_body_duplicates(files: list[Path], min_lines: int) -> list[UnitDup]:
    """서로 다른 파일에 있는, 본문이 사실상 동일한 함수/클래스를 찾는다."""
    groups: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    # hash -> [(kind, "path:line(name)", line_count), ...]

    for path in files:
        try:
            src = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue

        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            _collect_unit(groups, src, rel, node, min_lines)

    dups: list[UnitDup] = []
    for locs in groups.values():
        if len(locs) < 2:
            continue
        # 같은 파일 안에서만 반복되는 경우(예: 동일 클래스가 여러 서브클래스에
        # 오버라이드 패턴으로) 는 신호가 아니다 — 서로 다른 파일에 걸쳐야 한다.
        files_involved = {loc.split(":")[0] for _, loc, _ in locs}
        if len(files_involved) < 2:
            continue
        kind = locs[0][0]
        name = locs[0][1].split("(")[-1].rstrip(")")
        dups.append(
            UnitDup(
                kind=kind,
                name=name,
                lines=locs[0][2],
                locations=sorted(loc for _, loc, _ in locs),
            )
        )
    dups.sort(key=lambda d: -d.lines)
    return dups


def find_basename_duplicates(files: list[Path]) -> list[BasenameDup]:
    """같은 파일명이 서로 다른 디렉터리에 존재 — 병렬 모듈 구현 의심."""
    by_name: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        if path.name == "__init__.py":
            continue
        by_name[path.name].append(path)

    dups: list[BasenameDup] = []
    for name, paths in by_name.items():
        if len(paths) < 2:
            continue
        dups.append(
            BasenameDup(
                basename=name,
                paths=sorted(p.relative_to(ROOT).as_posix() for p in paths),
            )
        )
    dups.sort(key=lambda d: d.basename)
    return dups


def run(roots: list[str], min_lines: int) -> dict:
    files: list[Path] = []
    for r in roots:
        base = ROOT / r
        if base.is_dir():
            files.extend(_iter_py_files(base))

    body_dups = find_body_duplicates(files, min_lines=min_lines)
    basename_dups = find_basename_duplicates(files)

    return {
        "scanned_files": len(files),
        "body_duplicates": [asdict(d) for d in body_dups],
        "basename_duplicates": [asdict(d) for d in basename_dups],
    }


def _print_report(result: dict) -> None:
    print("=" * 60)
    print("코드 중복 검사")
    print("=" * 60)
    print(f"스캔한 파일: {result['scanned_files']}개")
    print()

    bd = result["body_duplicates"]
    print(f"[본문 복붙 중복] {len(bd)}건")
    for d in bd:
        print(f"  - {d['kind']} {d['name']} ({d['lines']}줄)")
        for loc in d["locations"]:
            print(f"      {loc}")
    print()

    fn = result["basename_duplicates"]
    print(f"[동일 파일명 병렬 모듈] {len(fn)}건")
    for d in fn:
        print(f"  - {d['basename']}")
        for p in d["paths"]:
            print(f"      {p}")
    print()
    print("=" * 60)
    total = len(bd) + len(fn)
    if total == 0:
        print("PASS — 중복 신호 없음")
    else:
        print(f"WARN — 총 {total}건, 위 목록을 검토해 실제 중복 구현인지 확인하세요.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path", action="append", dest="paths", help="스캔 루트 (반복 지정 가능, 기본: scripts ai_orchestrator)"
    )
    parser.add_argument("--min-lines", type=int, default=6, help="이 줄 수 미만인 함수/클래스는 무시 (기본 6)")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args()

    roots = args.paths or DEFAULT_ROOTS
    result = run(roots, min_lines=args.min_lines)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_report(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
