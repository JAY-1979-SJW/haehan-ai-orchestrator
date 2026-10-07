"""base..head 사이에 바뀐 함수를 mutmut 패턴(`*모듈.함수*`)으로 출력한다.

변이 검증(mutation.yml)이 PR 에서 바뀐 함수만 대상으로 삼게 하기 위한 도구. 사용: changed_functions.py BASE [HEAD] [--limit N]
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

SOURCE_ROOTS = ("ai_orchestrator", "scripts", "local_agent", "orchestrator_v1")
_HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@")


def changed_line_ranges(base: str, head: str) -> dict[str, set[int]]:
    """파일별로 head 쪽에서 추가·수정된 줄 번호 집합."""
    out = subprocess.run(
        ["git", "diff", "-U0", "--diff-filter=ACMR", base, head, "--", *SOURCE_ROOTS],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    return parse_diff(out)


def parse_diff(diff: str) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current = path[2:] if path.startswith("b/") else None
            if current is not None and not current.endswith(".py"):
                current = None
        elif current and (m := _HUNK.match(line)):
            start, count = int(m.group(1)), int(m.group(2) or "1")
            if count:
                result.setdefault(current, set()).update(range(start, start + count))
    return result


def module_dotted_path(path: str) -> str:
    parts = list(Path(path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def functions_touching(source: str, lines: set[int]) -> list[str]:
    """변경 줄을 포함하는 함수/메서드 이름(클래스 안은 `클래스.메서드`)."""
    found: list[str] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = child.end_lineno or child.lineno
                if any(child.lineno <= n <= end for n in lines):
                    found.append(f"{prefix}{child.name}")

    try:
        visit(ast.parse(source), "")
    except SyntaxError:
        return []
    return found


def mutant_pattern(dotted: str, name: str) -> str:
    """mutmut 3 변이체 이름 형식: 함수 `모듈.x_함수__mutmut_N`, 메서드 `모듈.xǁ클래스ǁ메서드__mutmut_N`."""
    if "." in name:
        return f"{dotted}.xǁ{name.replace('.', 'ǁ')}__mutmut_*"
    return f"{dotted}.x_{name}__mutmut_*"


def patterns_for_diff(ranges: dict[str, set[int]], read=lambda p: Path(p).read_text(encoding="utf-8")) -> list[str]:
    patterns: list[str] = []
    for path in sorted(ranges):
        try:
            source = read(path)
        except OSError:
            continue
        dotted = module_dotted_path(path)
        patterns.extend(mutant_pattern(dotted, fn) for fn in functions_touching(source, ranges[path]))
    return patterns


def files_for_diff(ranges: dict[str, set[int]], read=lambda p: Path(p).read_text(encoding="utf-8")) -> list[str]:
    """바뀐 함수가 있는 파일만(변이체 생성 범위를 줄이는 데 쓴다)."""
    out = []
    for path in sorted(ranges):
        try:
            if functions_touching(read(path), ranges[path]):
                out.append(path)
        except OSError:
            continue
    return out


def tests_for_files(files: list[str], tests: list[str], read=lambda p: Path(p).read_text(encoding="utf-8", errors="replace")) -> list[str]:
    """바뀐 파일을 직접 가리키는 시험 파일(모듈 점 경로 또는 파일명이 본문에 나오는 것). 전이 영향까지 넓히면 수백 개라 직접 참조만 쓴다."""
    needles = [(module_dotted_path(f), Path(f).stem) for f in files]
    picked: list[str] = []
    file_set = set(files)
    for t in sorted(tests):
        if t in file_set:
            picked.append(t)
            continue
        try:
            text = read(t)
        except OSError:
            continue
        if any(dotted in text or re.search(rf"\b{re.escape(stem)}\b", text) for dotted, stem in needles):
            picked.append(t)
    return picked


def rewrite_toml_list(pyproject: str, key: str, values: list[str]) -> str:
    """pyproject 의 `key = [...]` 한 줄(여러 줄 가능)을 values 로 바꾼 텍스트(워크플로가 실행 중에만 쓴다)."""
    value = f"{key} = [" + ", ".join(f'"{v}"' for v in values) + "]"
    return re.sub(rf"^{re.escape(key)} = \[[^\]]*\]", lambda _m: value, pyproject, count=1, flags=re.M)


def rewrite_source_paths(pyproject: str, files: list[str]) -> str:
    return rewrite_toml_list(pyproject, "source_paths", files)


def main(argv: list[str]) -> int:
    """사용: BASE [HEAD] [--limit N] [--files] [--tests] [--write-source-paths PYPROJECT]"""
    opts = {"--limit": "", "--write-source-paths": ""}
    flags = {"--files": False, "--tests": False}
    args: list[str] = []
    it = iter(argv)
    for a in it:
        if a in opts:
            opts[a] = next(it, "")
        elif a in flags:
            flags[a] = True
        else:
            args.append(a)
    if not args:
        print("usage: changed_functions.py BASE [HEAD] [--limit N] [--files] [--tests] [--write-source-paths PYPROJECT]", file=sys.stderr)
        return 2
    base, head = args[0], (args[1] if len(args) > 1 else "HEAD")
    ranges = changed_line_ranges(base, head)
    if opts["--write-source-paths"]:
        target = Path(opts["--write-source-paths"])
        files = files_for_diff(ranges)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(rewrite_source_paths(target.read_text(encoding="utf-8"), files), encoding="utf-8", newline="\n")
        tmp.replace(target)
        return 0
    if flags["--tests"]:
        all_tests = [str(x).replace("\\", "/") for x in Path("tests").rglob("test_*.py")]
        print("\n".join(tests_for_files(files_for_diff(ranges), all_tests)))
        return 0
    if flags["--files"]:
        print("\n".join(files_for_diff(ranges)))
        return 0
    patterns = patterns_for_diff(ranges)
    limit = int(opts["--limit"] or 0)
    if limit and len(patterns) > limit:
        print(f"[changed_functions] {len(patterns)}개 중 앞 {limit}개만 출력(상한)", file=sys.stderr)
        patterns = patterns[:limit]
    print("\n".join(patterns))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
