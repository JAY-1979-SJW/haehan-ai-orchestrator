# module_category: audit
# primary_trade: common
"""코드맵 L1·L2 스캔 — 추적 파일 목록, 파이썬 AST 에서 import·문자열 참조·__main__ 추출.

읽기 전용: git ls-files 와 파일 읽기만 한다. 원본·DB 에 쓰지 않는다.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()

# 런처 텍스트로 스캔하는 비파이썬 파일(여기서 참조된 파이썬 파일 = 진입점)
LAUNCHER_EXTS = {
    ".js",
    ".cjs",
    ".mjs",
    ".ts",
    ".tsx",
    ".json",
    ".ps1",
    ".vbs",
    ".bat",
    ".cmd",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".spec",
    ".sh",
}
LAUNCHER_NAMES = {"Dockerfile", "CLAUDE.md", "AGENTS.md", "pre-commit", "pre-push", "commit-msg", "pre-commit.orig"}
# 런처로 보지 않는 경로(산출물·문서·데이터) — 여기의 언급은 "살아 있음" 근거가 아니다
NON_LAUNCHER_PREFIXES = (
    "docs/",
    "data/",
    "tests/",
    "memory/",
    "configs/codebase_layer_audit",
    "configs/module_boundaries",
    "configs/root_legacy_scripts",  # 루트 스크립트 재고 목록(실행기 아님)
)
# 단어 언급(MENTIONED) 판정에서 제외할 경로
MENTION_EXCLUDE_PREFIXES = ("docs/", "data/", "memory/")
TEXT_EXTS = LAUNCHER_EXTS | {".py", ".md", ".txt", ".html", ".css"}

PATH_RE = re.compile(r"([\w.\-]+(?:[/\\]+[\w.\-]+)*\.py)\b")
DOTTED_RE = re.compile(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)\b")
WORD_RE = re.compile(r"[A-Za-z_]\w{2,}")


@dataclass
class PyFile:
    rel: str
    parse_error: str | None = None
    has_main: bool = False
    # (모듈명, 레벨, from-import 이름들) — 레벨>0 = 상대 import
    imports: list[tuple[str, int, tuple[str, ...]]] = field(default_factory=list)
    dynamic_literal: list[str] = field(default_factory=list)  # importlib.import_module("x.y")
    dynamic_unresolved: int = 0  # 비리터럴 importlib/__import__
    strings: list[str] = field(default_factory=list)  # 문자열 상수 + '/' 경로 조합


def tracked_files() -> list[str]:
    """추적 파일 + 미추적(.gitignore 제외) 파일 — 진행 중인 미커밋 작업의 참조도 놓치지 않게."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8", errors="replace")
    return sorted(p for p in out.split("\0") if p and (ROOT / p).is_file())


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig", errors="replace")


# 파이썬이 이름으로 자동 로드하는 파일
SPECIAL_AUTOLOAD = {"sitecustomize.py", "usercustomize.py", "conftest.py"}
# 모듈 최상단에서 흔한 준비 호출 — 이것만 있으면 스크립트로 보지 않는다
_SETUP_CALLS = {
    "insert",
    "append",
    "basicConfig",
    "filterwarnings",
    "simplefilter",
    "setdefault",
    "load_dotenv",
    "reconfigure",
    "register",
    "getLogger",
    "setLevel",
    "addHandler",
    "chdir",
}


def _is_script_stmt(stmt: ast.stmt) -> bool:
    if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, (ast.Call, ast.Await)):
        call = stmt.value.value if isinstance(stmt.value, ast.Await) else stmt.value
        fn = getattr(call, "func", None)
        name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
        return name not in _SETUP_CALLS
    return False


def _div_chain_parts(node: ast.AST) -> list[str] | None:
    """ROOT / "scripts" / "x.py" 같은 '/' 경로 조합에서 문자열 조각만 모은다."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _div_chain_parts(node.left) or []
        right = _div_chain_parts(node.right) or []
        return left + right
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    return []


def _bare_string_stmt_ids(tree: ast.AST) -> set[int]:
    """모듈/클래스/함수 docstring 은 첫 statement 가 Expr(Constant str) 인 경우다.
    이는 "bare 문자열 표현식 statement"의 특수 케이스이므로, 위치 무관하게
    Expr(Constant str) 형태의 statement 를 모두 걸러내면 docstring 도 함께 제외된다.
    이 id 집합에 속한 Constant 노드는 실제 코드에서 값으로 쓰인 것이 아니라
    (할당·호출 인자·반환값 등이 아니라) 그 자체가 문장이므로 path_ref 후보에서 뺀다.
    """
    excluded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            excluded.add(id(node.value))
    return excluded


def _scan_call(pf, node):
    fn = node.func
    name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
    if name in ("import_module", "__import__"):
        arg = node.args[0] if node.args else None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            pf.dynamic_literal.append(arg.value)
        else:
            pf.dynamic_unresolved += 1


def _mark_main_guard(pf, node):
    t = node.test
    if (
        isinstance(t, ast.Compare)
        and isinstance(t.left, ast.Name)
        and t.left.id == "__name__"
        and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in t.comparators)
    ):
        pf.has_main = True


def _scan_div(pf, node):
    parts = _div_chain_parts(node)
    if parts and len(parts) > 1:
        pf.strings.append("/".join(parts))


def _scan_str(pf, node, excluded_str_ids):
    if id(node) not in excluded_str_ids:  # docstring·bare 문자열 statement 는 실제 코드 참조가 아니다
        pf.strings.append(node.value)


def scan_py(rel: str) -> PyFile:
    pf = PyFile(rel=rel)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(_read(rel), filename=rel)
    except (SyntaxError, ValueError) as e:
        pf.parse_error = f"{type(e).__name__}: {e}"
        return pf
    # __main__ 가드 없이 모듈 최상단에서 바로 실행하는 스크립트도 CLI 진입점
    pf.has_main = Path(rel).name in SPECIAL_AUTOLOAD or any(_is_script_stmt(s) for s in tree.body)
    excluded_str_ids = _bare_string_stmt_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                pf.imports.append((a.name, 0, ()))
        elif isinstance(node, ast.ImportFrom):
            pf.imports.append((node.module or "", node.level, tuple(a.name for a in node.names)))
        elif isinstance(node, ast.Call):
            _scan_call(pf, node)
        elif isinstance(node, ast.If) and not pf.has_main:
            _mark_main_guard(pf, node)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            _scan_div(pf, node)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 2000:
            _scan_str(pf, node, excluded_str_ids)
    return pf


def string_refs(text: str) -> tuple[set[str], set[str]]:
    """텍스트에서 .py 경로 후보와 점표기 모듈명 후보를 뽑는다(해석은 reach 에서)."""
    paths = {m.replace("\\", "/") for m in PATH_RE.findall(text)}
    dotted = set(DOTTED_RE.findall(text))
    return paths, dotted


def is_launcher(rel: str) -> bool:
    if rel.startswith(NON_LAUNCHER_PREFIXES) or "/node_modules/" in rel:
        return False
    p = Path(rel)
    return p.suffix.lower() in LAUNCHER_EXTS or p.name in LAUNCHER_NAMES or rel.startswith((".claude/", ".codex/"))


def is_test(rel: str) -> bool:
    name = Path(rel).name
    return (
        rel.startswith("tests/")
        or "/tests/" in rel
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def word_index(files: list[str]) -> dict[str, set[str]]:
    """단어 → 등장 파일 집합 (MENTIONED 판정용, docs/·data/ 제외)."""
    idx: dict[str, set[str]] = {}
    for rel in files:
        if rel.startswith(MENTION_EXCLUDE_PREFIXES) or Path(rel).suffix.lower() not in TEXT_EXTS:
            continue
        try:
            words = set(WORD_RE.findall(_read(rel)))
        except OSError:
            continue
        for w in words:
            idx.setdefault(w, set()).add(rel)
    return idx
