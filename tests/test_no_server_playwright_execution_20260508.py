"""tests/test_no_server_playwright_execution_20260508.py

서버 코드(ai_orchestrator/server/) 안에서 Playwright/Selenium/Pyppeteer
import 또는 browser launch 호출이 없는지 검증한다.

문서/주석/금지 메시지 텍스트는 허용 — 실제 실행 코드만 검사.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_DIR = _REPO_ROOT / "ai_orchestrator" / "server"

# 차단 import 패턴 (실제 실행 import만)
_FORBIDDEN_IMPORTS = [
    re.compile(r"^\s*from\s+playwright(\.\w+)*\s+import"),
    re.compile(r"^\s*import\s+playwright"),
    re.compile(r"^\s*from\s+selenium\s+import"),
    re.compile(r"^\s*from\s+selenium\.\w+"),
    re.compile(r"^\s*import\s+selenium"),
    re.compile(r"^\s*import\s+pyppeteer"),
    re.compile(r"^\s*from\s+pyppeteer\s+import"),
]

# 차단 호출 패턴
_FORBIDDEN_CALLS = [
    re.compile(r"\bsync_playwright\s*\(\s*\)"),
    re.compile(r"\basync_playwright\s*\(\s*\)"),
    re.compile(r"\.chromium\.launch\s*\("),
    re.compile(r"\.firefox\.launch\s*\("),
    re.compile(r"\.webkit\.launch\s*\("),
    re.compile(r"\bwebdriver\.Chrome\s*\("),
    re.compile(r"\bwebdriver\.Firefox\s*\("),
]


def _collect_python_files():
    files = []
    if not _SERVER_DIR.exists():
        return files
    for p in _SERVER_DIR.rglob("*.py"):
        if "__pycache__" in str(p):
            continue
        files.append(p)
    return files


def _read_lines_excluding_strings_comments(path: Path) -> list[tuple[int, str]]:
    """간이 — 주석(#)으로 시작하는 줄과 docstring 블록 안의 줄은 검사 제외."""
    in_docstring = False
    docstring_quote = None
    out = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="cp949", errors="replace")

    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        # docstring 블록 추적
        if not in_docstring:
            for q in ('"""', "'''"):
                if stripped.startswith(q):
                    rest = stripped[len(q) :]
                    if rest.endswith(q) and len(rest) >= len(q):
                        # 한 줄 docstring
                        break
                    in_docstring = True
                    docstring_quote = q
                    break
            else:
                # 일반 줄
                if stripped.startswith("#"):
                    continue
                out.append((idx, line))
                continue
            # docstring 시작했으면 그 줄도 skip
            continue
        else:
            # docstring 닫힘 검사
            if docstring_quote and docstring_quote in stripped:
                in_docstring = False
                docstring_quote = None
            continue
    return out


def test_no_playwright_import_in_server():
    violations = []
    for path in _collect_python_files():
        for line_no, line in _read_lines_excluding_strings_comments(path):
            for pat in _FORBIDDEN_IMPORTS:
                if pat.search(line):
                    violations.append(f"{path.relative_to(_REPO_ROOT)}:{line_no}: {line.strip()}")
    assert not violations, f"서버 코드 내 금지 import 발견: {violations}"


def test_no_browser_launch_call_in_server():
    violations = []
    for path in _collect_python_files():
        for line_no, line in _read_lines_excluding_strings_comments(path):
            for pat in _FORBIDDEN_CALLS:
                if pat.search(line):
                    violations.append(f"{path.relative_to(_REPO_ROOT)}:{line_no}: {line.strip()}")
    assert not violations, f"서버 코드 내 browser launch 호출 발견: {violations}"


def test_no_server_browser_used_true_in_server():
    """server_browser_used=True 또는 server_browser_used = True 실행 대입 없음."""
    violations = []
    pat = re.compile(r"server_browser_used\s*=\s*True\b")
    for path in _collect_python_files():
        for line_no, line in _read_lines_excluding_strings_comments(path):
            # 테스트 파일이 아닌 server 모듈에서 검사
            if pat.search(line):
                # 단, "= False" 형태나 강제 False 강조 코드는 위 정규식에서 매칭 안됨
                violations.append(f"{path.relative_to(_REPO_ROOT)}:{line_no}: {line.strip()}")
    assert not violations, f"server_browser_used=True 실행 코드: {violations}"


def test_no_external_fetch_in_server():
    """requests/urllib/httpx 등으로 외부 host에 대한 직접 fetch 없음."""
    # 단, 정책 모듈은 제외 (server_egress_policy.py는 정책 정의 포함)
    excluded = {"server_egress_policy.py", "external_url_blocker.py", "execution_location_guard.py"}
    suspicious_patterns = [
        re.compile(r"requests\.(get|post|put|delete)\s*\(\s*[fr]?[\"']https?://(?!localhost|127\.0\.0\.1)"),
        re.compile(r"httpx\.(get|post|put|delete)\s*\(\s*[fr]?[\"']https?://(?!localhost|127\.0\.0\.1)"),
    ]
    violations = []
    for path in _collect_python_files():
        if path.name in excluded:
            continue
        for line_no, line in _read_lines_excluding_strings_comments(path):
            for pat in suspicious_patterns:
                if pat.search(line):
                    violations.append(f"{path.relative_to(_REPO_ROOT)}:{line_no}: {line.strip()}")
    assert not violations, f"서버에서 외부 fetch 시도 발견: {violations}"


def test_server_directory_exists():
    assert _SERVER_DIR.exists(), f"server 디렉터리 미존재: {_SERVER_DIR}"


def test_python_files_collected():
    files = _collect_python_files()
    assert len(files) > 0, "server 디렉터리에 Python 파일이 없음"
