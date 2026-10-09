# module_category: audit
# primary_trade: common
"""코드맵 전체 확장 — 저장소의 모든 파일·폴더를 노드로 연결한다.

엣지 종류
- contains  : 폴더 → 바로 아래 파일·폴더
- py_import : 파이썬 import·문자열 참조(reach.build_graph 결과 그대로)
- ts_import : TS/JS import·require·동적 import (상대경로, '@/' = admin-web/src)
- path_ref  : 모든 텍스트 파일 속 경로 문자열 → 존재하는 파일·폴더
진입점 추가: Next.js 라우트 파일(page·layout·route…), 도구 설정 파일(package.json·tsconfig 등).
폴더 참조는 그 폴더의 비코드 파일(데이터·설정·자산)만 살린다 — "scripts/" 언급이 전체 코드를 살리지 않게.
읽기 전용.
"""

from __future__ import annotations

import posixpath
import re
from collections import Counter, defaultdict, deque
from pathlib import PurePosixPath

from tools.code_map import scan

TEXT_EXTS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".md",
    ".txt",
    ".ps1",
    ".vbs",
    ".bat",
    ".cmd",
    ".sh",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".spec",
    ".html",
    ".css",
    ".sql",
    ".env.example",
    ".xml",
    ".csv",
}
TEXT_NAMES = {"Dockerfile", "pre-commit", "pre-push", "commit-msg", "pre-commit.orig", ".gitignore", ".mcp.json"}
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
MAX_BYTES = 2_000_000
TS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
TS_IMPORT_RE = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(\s*|\brequire\s*\(\s*|^\s*import\s+)['"]([^'"\n]+)['"]""", re.M)
JS_COMMENT_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
JS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
PATHLIKE_RE = re.compile(
    r"[A-Za-z0-9_.@()\[\]\-]+(?:[/\\]+[A-Za-z0-9_.@()\[\]\-]+)+/?"
    r"|[A-Za-z0-9_\-][A-Za-z0-9_.\-]*\.[A-Za-z][A-Za-z0-9]{0,5}"
)
NEXT_ROOT_RE = re.compile(
    r"^admin-web/src/(?:app/(?:.*/)?(?:page|layout|route|loading|error|not-found|template|default|global-error)"
    r"|middleware)\.(?:tsx|ts|jsx|js)$"
)
TOOL_ROOT_NAMES = {
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "next.config.mjs",
    "next.config.js",
    "postcss.config.js",
    "postcss.config.mjs",
    "tailwind.config.ts",
    "tailwind.config.js",
    ".eslintrc.json",
    "eslint.config.mjs",
    "ruff.toml",
    "pytest.ini",
    "Dockerfile",
    "docker-compose.yml",
    ".mcp.json",
    "CLAUDE.md",
    "AGENTS.md",
    ".gitignore",
    "requirements.txt",
    ".dockerignore",
    ".gitattributes",
    ".env.example",
    "requirements-dev.txt",
}
PRIORITY = ("LIVE", "CLI", "TEST_ONLY", "MENTIONED", "DOC", "DATA", "UNREACHED")
DOC_ROOTS = {"CLAUDE.md", "AGENTS.md", "SKILL.md"}  # 실행 지침 문서 — 진입점으로 취급


def _is_text(rel: str) -> bool:
    p = PurePosixPath(rel)
    return p.suffix.lower() in TEXT_EXTS or p.name in TEXT_NAMES or rel.endswith(".env.example")


def _dirs_of(files: list[str]) -> set[str]:
    out: set[str] = set()
    for f in files:
        parts = PurePosixPath(f).parts[:-1]
        for i in range(1, len(parts) + 1):
            out.add("/".join(parts[:i]))
    return out


class NodeResolver:
    def __init__(self, files: list[str], dirs: set[str]):
        self.files = set(files)
        self.dirs = dirs
        self.by_base: dict[str, list[str]] = defaultdict(list)
        for n in list(self.files) + list(dirs):
            self.by_base[PurePosixPath(n).name].append(n)
        self.file_base_count = Counter(PurePosixPath(f).name for f in files)

    def resolve(self, src: str, cand: str) -> list[str]:
        cand = cand.replace("\\", "/")
        while "//" in cand:
            cand = cand.replace("//", "/")
        cand = cand.strip("/").lstrip("./") if not cand.startswith("../") else cand
        if not cand or cand in (".", ".."):
            return []
        if "/" not in cand:
            base_dir = str(PurePosixPath(src).parent)
            sib = cand if base_dir in ("", ".") else f"{base_dir}/{cand}"
            if sib in self.files:
                return [sib]
            if cand in self.files:  # 저장소 루트 파일
                return [cand]
            if self.file_base_count.get(cand) == 1:  # 저장소에 그 이름이 하나뿐일 때만
                return [n for n in self.by_base[cand] if n in self.files]
            return []
        if cand.startswith("../"):
            norm = posixpath.normpath(posixpath.join(str(PurePosixPath(src).parent), cand))
            return [norm] if norm in self.files or norm in self.dirs else []
        name = PurePosixPath(cand).name
        return [n for n in self.by_base.get(name, ()) if n == cand or n.endswith("/" + cand) or cand.endswith("/" + n)]

    def resolve_ts(self, src: str, spec: str) -> list[str]:
        if spec.startswith("@/"):
            base = "admin-web/src/" + spec[2:]
        elif spec.startswith("."):
            base = posixpath.normpath(posixpath.join(str(PurePosixPath(src).parent), spec))
        else:
            return []  # 외부 패키지
        for cand in (base, *(base + e for e in TS_EXTS), *(f"{base}/index{e}" for e in TS_EXTS)):
            if cand in self.files:
                return [cand]
        return [base] if base in self.dirs else []


def _build_contains(files: list[str], dirs: set[str]) -> dict[str, set[str]]:
    contains: dict[str, set[str]] = defaultdict(set)
    for n in list(files) + sorted(dirs):
        parent = str(PurePosixPath(n).parent)
        if parent not in ("", "."):
            contains[parent].add(n)
    return contains


def _scan_text_refs(
    files: list[str],
    res: NodeResolver,
    edges: dict[str, set[str]],
    import_edges: dict[str, set[str]],
    kinds: Counter,
) -> None:
    """ts imports + path refs. edges/import_edges/kinds 를 제자리에서 채운다(extend() 분리, 2026-09-29 STD-08)."""
    for rel in files:
        if not _is_text(rel):
            continue
        path = scan.ROOT / rel
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        if PurePosixPath(rel).suffix.lower() in TS_EXTS:
            for spec in TS_IMPORT_RE.findall(text):
                tg = [t for t in res.resolve_ts(rel, spec) if t != rel]
                edges[rel].update(tg)
                import_edges[rel].update(tg)
                kinds["ts_import"] += len(tg)
        path_text = _ref_scan_text(rel, text)
        for cand in set(PATHLIKE_RE.findall(path_text)):
            tg = [t for t in res.resolve(rel, cand) if t != rel]
            new = set(tg) - edges[rel]
            edges[rel].update(new)
            kinds["path_ref"] += len(new)


def _ref_scan_text(rel: str, text: str) -> str:
    """path_ref 검색 대상 텍스트 — 주석·docstring·bare 문자열 statement 는 제외(거짓 참조 방지)."""
    if rel.endswith(".py"):
        # scan.scan_py() 가 AST 로 뽑은, 실제 코드에 쓰인 문자열 상수만 대상으로 한다.
        pf = scan.scan_py(rel)
        return "\n".join(pf.strings)
    if rel.endswith(JS_COMMENT_EXT):
        # TS/JS 주석 속 파일명도 실제 참조가 아니다 — 블록 주석(/* */)과 줄 전체 주석(//)만 걷어낸다.
        # 줄 끝 주석은 문자열 속 '//'(URL 등)과 구분하기 어려워 남긴다(보수적).
        return "\n".join(
            ln for ln in JS_BLOCK_COMMENT_RE.sub("", text).splitlines() if not ln.lstrip().startswith("//")
        )
    return text


def _build_roots(files: list[str], graph: dict, manual_roots: dict[str, list[str]]) -> dict[str, set[str]]:
    roots: dict[str, set[str]] = defaultdict(set)
    for t, srcs in graph["launcher_roots"].items():
        roots[t].update(srcs)
    for t, srcs in manual_roots.items():
        roots[t].update(srcs)
    for f in files:
        if NEXT_ROOT_RE.match(f):
            roots[f].add("next_route")
        elif PurePosixPath(f).name in TOOL_ROOT_NAMES or re.match(r"^(.*/)?tsconfig(\.[\w-]+)?\.json$", f):
            roots[f].add("tool_config")
        elif f.startswith(".githooks/") and "." not in PurePosixPath(f).name:
            roots[f].add("git_hook")  # core.hooksPath=.githooks — git 이 이름으로 실행
    return roots


def _is_doc(n: str) -> bool:
    return n.endswith(".md") and PurePosixPath(n).name not in DOC_ROOTS


def _dir_children_noncode(d: str, contains: dict[str, set[str]], dirs: set[str]) -> list[str]:
    """폴더 참조 → 그 폴더의 비코드 파일(재귀)만 살림."""
    out: list[str] = []
    q = deque([d])
    while q:
        cur = q.popleft()
        for c in contains.get(cur, ()):
            if c in dirs:
                q.append(c)
            elif PurePosixPath(c).suffix.lower() not in CODE_EXTS:
                out.append(c)
    return out


def _bfs_live(seeds: set[str], edges: dict[str, set[str]], dirs: set[str], contains: dict[str, set[str]]) -> set[str]:
    seen, q = set(seeds), deque(seeds)
    while q:
        cur = q.popleft()
        if _is_doc(cur):  # 문서 속 링크로는 연쇄하지 않음
            continue
        nxt = set(edges.get(cur, ()))
        if cur in dirs and "/" in cur:  # 최상위 폴더(data/·docs/ 등) 언급은 전체를 살리지 않음
            nxt.update(_dir_children_noncode(cur, contains, dirs))
        for n in nxt:
            if n not in seen:
                seen.add(n)
                q.append(n)
    return seen


def _classify_node(
    f: str, live: set[str], cli: set[str], test_only: set[str], words: dict[str, set[str]], roots: dict[str, set[str]]
) -> dict:
    info: dict = {"kind": "file", "ext": PurePosixPath(f).suffix.lower() or PurePosixPath(f).name}
    if _is_doc(f):
        cls = "DOC"
        info["referenced"] = f in live
    elif f in live:
        cls = "LIVE"
        if f in roots:
            info["root"] = sorted(roots[f])[:3]
    elif f in cli:
        cls = "CLI"
    elif f in test_only:
        cls = "TEST_ONLY"
    elif f.startswith("docs/"):
        cls = "DOC"
    elif f.startswith("data/"):
        cls = "DATA"
    else:
        stem = PurePosixPath(f).stem
        key = PurePosixPath(f).parent.name if stem in ("__init__", "index") else stem
        mentions = sorted(words.get(key, set()) - {f})
        if mentions:
            cls = "MENTIONED"
            info["mentioned_in"] = mentions[:3]
        else:
            cls = "UNREACHED"
    info["class"] = cls
    return info


def _classify_nodes(
    files: list[str],
    live: set[str],
    cli: set[str],
    test_only: set[str],
    words: dict[str, set[str]],
    roots: dict[str, set[str]],
) -> dict[str, dict]:
    return {f: _classify_node(f, live, cli, test_only, words, roots) for f in files}


def _build_dir_nodes(dirs: set[str], nodes: dict[str, dict], live: set[str]) -> dict[str, dict]:
    """폴더: 하위 파일 분류 집계, 대표 분류 = 우선순위 최상."""
    dir_counts: dict[str, Counter] = defaultdict(Counter)
    for f, info in nodes.items():
        parts = PurePosixPath(f).parts[:-1]
        for i in range(1, len(parts) + 1):
            dir_counts["/".join(parts[:i])][info["class"]] += 1
    dir_nodes = {}
    for d in sorted(dirs):
        c = dir_counts[d]
        rep = next((k for k in PRIORITY if c.get(k)), "UNREACHED")
        dir_nodes[d] = {"kind": "dir", "class": rep, "counts": dict(c), "referenced": d in live}
    return dir_nodes


def extend(graph: dict, files: list[str], manual_roots: dict[str, list[str]]) -> dict:
    """모든 파일·폴더 그래프를 만든다. graph = reach.build_graph 결과.

    2026-09-29 STD-08(복잡도) 리팩터: 원래 이 함수 하나(C901=44)에 있던 각 단계를
    위 _build_*/_scan_*/_bfs_live/_classify_* 함수로 분리했다. 로직·순서·자료구조는
    그대로이고, 여기서는 그 단계를 순서대로 호출만 한다.
    """
    dirs = _dirs_of(files)
    res = NodeResolver(files, dirs)
    edges: dict[str, set[str]] = defaultdict(set)
    kinds = Counter()
    import_edges: dict[str, set[str]] = defaultdict(set)  # 실제 import 만(py + ts) — 층간 방향 판정용
    for s, ts in graph.get("import_edges", {}).items():
        import_edges[s].update(ts)
    for s, ts in graph["edges"].items():
        edges[s].update(ts)
        kinds["py_import"] += len(ts)

    contains = _build_contains(files, dirs)
    kinds["contains"] = sum(len(v) for v in contains.values())

    _scan_text_refs(files, res, edges, import_edges, kinds)

    roots = _build_roots(files, graph, manual_roots)

    tests = {
        f for f in files if scan.is_test(f) or "/__tests__/" in f or f.endswith((".test.ts", ".test.tsx", ".spec.ts"))
    }
    live = _bfs_live(set(roots), edges, dirs, contains)
    cli = _bfs_live({p for p in graph["has_main"] if p not in tests}, edges, dirs, contains) - live
    test_only = _bfs_live(tests, edges, dirs, contains) - live - cli
    words = scan.word_index(files)

    nodes = _classify_nodes(files, live, cli, test_only, words, roots)
    dir_nodes = _build_dir_nodes(dirs, nodes, live)

    return {
        "nodes": nodes,
        "dirs": dir_nodes,
        "edges": {k: sorted(v) for k, v in edges.items() if v},
        "import_edges": {k: sorted(v) for k, v in import_edges.items() if v},
        "edge_kinds": dict(kinds),
        "roots": {k: sorted(v) for k, v in roots.items()},
    }
