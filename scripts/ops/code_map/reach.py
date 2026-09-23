# module_category: audit
# primary_trade: common
"""코드맵 L2 해석 + L5 도달성 — import/문자열 참조를 파일 엣지로 해석하고 진입점에서 BFS 로 분류.

분류(우선순위 순): LIVE > CLI > TEST_ONLY > MENTIONED > UNREACHED
- LIVE      : 런처(비파이썬 실행 파일·훅·스케줄러·스킬)에서 도달
- CLI       : __main__ 파일에서만 도달(파일 자신 또는 그 의존)
- TEST_ONLY : 테스트에서만 도달
- MENTIONED : 미도달이지만 파일명이 코드·설정에 단어로 등장(동적 호출 가능성 → 수동 확인)
- UNREACHED : 미도달 + 언급 없음(삭제 후보, 강한 근거)
"""

from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path, PurePosixPath

from scripts.ops.code_map import scan

STDLIB = set(sys.stdlib_module_names)
CLASSES = ("LIVE", "CLI", "TEST_ONLY", "MENTIONED", "UNREACHED")


class Resolver:
    def __init__(self, py_files: list[str]):
        self.py = set(py_files)
        self.dirs = {str(PurePosixPath(p).parent) for p in py_files}
        # 파일명(.py 포함) → 경로들 (문자열 경로 참조 접미사 매칭용)
        self.by_name: dict[str, list[str]] = {}
        for p in py_files:
            self.by_name.setdefault(PurePosixPath(p).name, []).append(p)

    @staticmethod
    def _roots(rel: str) -> list[str]:
        """검색 루트: 파일 폴더 → 상위 … → 저장소 루트('')."""
        parts = PurePosixPath(rel).parent.parts
        return ["/".join(parts[:i]) for i in range(len(parts), -1, -1)]

    def _module_file(self, base: str, dotted: str) -> str | None:
        path = "/".join(x for x in (base, dotted.replace(".", "/")) if x)
        if f"{path}.py" in self.py:
            return f"{path}.py"
        if f"{path}/__init__.py" in self.py:
            return f"{path}/__init__.py"
        return None

    def _pkg_exists(self, base: str, dotted: str) -> bool:
        path = "/".join(x for x in (base, dotted.replace(".", "/")) if x)
        return path in self.dirs

    @staticmethod
    def _parent_inits(target: str, base: str) -> list[str]:
        """a/b/c.py 를 import 하면 a/__init__.py, a/b/__init__.py 도 실행된다."""
        rel_parts = PurePosixPath(target[len(base) + 1 :] if base else target).parts[:-1]
        out = []
        for i in range(1, len(rel_parts) + 1):
            out.append("/".join(x for x in (base, *rel_parts[:i]) if x) + "/__init__.py")
        return out

    def resolve_import(self, rel: str, module: str, level: int, names: tuple[str, ...]) -> tuple[list[str], str]:
        """반환: (대상 파일들, 상태 internal|external|failed)."""
        if level:
            pkg = PurePosixPath(rel).parent
            for _ in range(level - 1):
                pkg = pkg.parent
            bases = [str(pkg) if str(pkg) != "." else ""]
            dotted_candidates = [module] if module else [""]
        else:
            if module.split(".")[0] in STDLIB:
                return [], "external"
            bases = self._roots(rel)
            dotted_candidates = [module]
        for base in bases:
            for dotted in dotted_candidates:
                hits: list[str] = []
                mod_file = (
                    self._module_file(base, dotted)
                    if dotted
                    else (f"{base}/__init__.py" if f"{base}/__init__.py" in self.py else None)
                )
                if mod_file:
                    hits.append(mod_file)
                # from X import Y — Y 가 하위 모듈이면 그 파일도
                for n in names:
                    if n == "*":
                        continue
                    sub = self._module_file(base, f"{dotted}.{n}" if dotted else n)
                    if sub:
                        hits.append(sub)
                if hits or (dotted and self._pkg_exists(base, dotted)):
                    extra = []
                    for h in hits:
                        extra += [i for i in self._parent_inits(h, base) if i in self.py]
                    return sorted(set(hits + extra)), "internal"
        if level:
            return [], "failed"
        # 어떤 루트에서든 첫 세그먼트가 내부 패키지/모듈이면 해석 실패, 아니면 외부 라이브러리
        top = module.split(".")[0]
        for base in bases:
            if self._module_file(base, top) or self._pkg_exists(base, top):
                return [], "failed"
        return [], "external"

    def resolve_dotted(self, rel: str, dotted: str) -> list[str]:
        """문자열 속 점표기(scripts.x.y, ai_orchestrator.server:app) → 내부 모듈 파일(루트 기준만)."""
        if dotted.split(".")[0] in STDLIB:
            return []
        f = self._module_file("", dotted)
        return [f] if f else []

    def resolve_path(self, rel: str, cand: str) -> list[str]:
        """문자열 속 .py 경로 → 추적 파일. 접미사 일치, 파일명만이면 같은 폴더 우선."""
        cand = cand.replace("\\", "/").lstrip("./")
        while "//" in cand:
            cand = cand.replace("//", "/")
        name = PurePosixPath(cand).name
        options = self.by_name.get(name, [])
        if not options:
            return []
        if "/" not in cand:
            sib = "/".join(x for x in (str(PurePosixPath(rel).parent), name) if x and x != ".")
            return [sib] if sib in self.py else []
        return [p for p in options if p == cand or cand.endswith("/" + p) or p.endswith("/" + cand)]


def build_graph(files: list[str], manual: dict) -> dict:
    py_files = [f for f in files if f.endswith(".py")]
    res = Resolver(py_files)
    edges: dict[str, set[str]] = {p: set() for p in py_files}
    stats = {
        "import_internal": 0,
        "import_external": 0,
        "import_failed": 0,
        "dynamic_literal": 0,
        "dynamic_unresolved": 0,
        "string_edges": 0,
    }
    failed_samples: list[str] = []
    parse_errors: dict[str, str] = {}
    has_main: set[str] = set()
    dynamic_files: dict[str, int] = {}

    for rel in py_files:
        pf = scan.scan_py(rel)
        if pf.parse_error:
            parse_errors[rel] = pf.parse_error
            continue
        if pf.has_main:
            has_main.add(rel)
        for module, level, names in pf.imports:
            targets, status = res.resolve_import(rel, module, level, names)
            stats[f"import_{status}"] += 1
            if status == "failed" and len(failed_samples) < 60:
                failed_samples.append(f"{rel}: {'.' * level}{module}")
            edges[rel].update(t for t in targets if t != rel)
        for dotted in pf.dynamic_literal:
            stats["dynamic_literal"] += 1
            edges[rel].update(res.resolve_dotted(rel, dotted))
        if pf.dynamic_unresolved:
            stats["dynamic_unresolved"] += pf.dynamic_unresolved
            dynamic_files[rel] = pf.dynamic_unresolved
        for s in pf.strings:
            paths, dotted_set = scan.string_refs(s)
            tg = set()
            for c in paths:
                tg.update(res.resolve_path(rel, c))
            for d in dotted_set:
                tg.update(res.resolve_dotted(rel, d))
            tg.discard(rel)
            stats["string_edges"] += len(tg - edges[rel])
            edges[rel].update(tg)

    # 런처 루트: 비파이썬 실행 파일에서 참조된 파이썬 파일
    launcher_roots: dict[str, set[str]] = {}

    def add_root(target: str, source: str) -> None:
        launcher_roots.setdefault(target, set()).add(source)

    for rel in files:
        if rel.endswith(".py") or not scan.is_launcher(rel):
            continue
        try:
            text = (scan.ROOT / rel).read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        paths, dotted_set = scan.string_refs(text)
        for c in paths:
            for t in res.resolve_path(rel, c):
                add_root(t, rel)
        for d in dotted_set:
            for t in res.resolve_dotted(rel, d):
                add_root(t, rel)
    # 수기 진입점(작업 스케줄러·시작프로그램 등)
    for item in manual.get("entrypoints", []):
        for t in res.resolve_path("", item["path"]):
            add_root(t, f"manual:{item['kind']}")
    # 사용자 스킬(~/.claude/skills/*/SKILL.md)
    skills = Path.home() / ".claude" / "skills"
    if skills.is_dir():
        for md in sorted(skills.glob("*/SKILL.md")):
            paths, dotted_set = scan.string_refs(md.read_text(encoding="utf-8", errors="replace"))
            for c in paths:
                for t in res.resolve_path("", c):
                    add_root(t, f"skill:{md.parent.name}")
            for d in dotted_set:
                for t in res.resolve_dotted("", d):
                    add_root(t, f"skill:{md.parent.name}")

    return {
        "py_files": py_files,
        "edges": {k: sorted(v) for k, v in edges.items()},
        "launcher_roots": {k: sorted(v) for k, v in launcher_roots.items()},
        "has_main": sorted(has_main),
        "parse_errors": parse_errors,
        "dynamic_files": dynamic_files,
        "stats": stats,
        "import_failed_samples": failed_samples,
    }


def _bfs(seeds: set[str], edges: dict[str, list[str]]) -> set[str]:
    seen = set(seeds)
    q = deque(seeds)
    while q:
        cur = q.popleft()
        for nxt in edges.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return seen


def classify(graph: dict, files: list[str]) -> dict[str, dict]:
    edges = graph["edges"]
    py = graph["py_files"]
    tests = {p for p in py if scan.is_test(p)}
    live = _bfs(set(graph["launcher_roots"]), edges)
    cli = _bfs({p for p in graph["has_main"] if p not in tests}, edges) - live
    test_only = _bfs(tests, edges) - live - cli
    words = scan.word_index(files)
    result: dict[str, dict] = {}
    for p in py:
        info: dict = {}
        if p in live:
            cls = "LIVE"
            if p in graph["launcher_roots"]:
                info["launched_by"] = graph["launcher_roots"][p][:3]
        elif p in cli:
            cls = "CLI"
            info["own_main"] = p in graph["has_main"]
        elif p in test_only:
            cls = "TEST_ONLY"
        else:
            stem = PurePosixPath(p).stem
            key = PurePosixPath(p).parent.name if stem == "__init__" else stem
            mentions = sorted(words.get(key, set()) - {p})
            if mentions:
                cls = "MENTIONED"
                info["mentioned_in"] = mentions[:3]
                info["mention_count"] = len(mentions)
            else:
                cls = "UNREACHED"
        info["class"] = cls
        result[p] = info
    return result


def load_manual() -> dict:
    path = scan.ROOT / "configs" / "code_map" / "entrypoints_manual.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
