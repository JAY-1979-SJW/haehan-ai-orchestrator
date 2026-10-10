"""번들 경로 일관성 게이트 (G17) — 파이썬 밖에서 저장소 경로·모듈을 가리키는 참조가 실제로 있는지 확인한다.

폴더를 옮길 때 파이썬 import 는 고쳐도 PyInstaller spec(진입 파일·hiddenimports·datas), electron-builder
extraResources(package.json), Electron 이 번들 exe 를 찾는 경로(admin-web/electron/lib/*.js), 데스크톱 릴리스
워크플로(.github/workflows/desktop-release.yml) 안의 경로는 그대로 남아 데스크톱 앱이 여러 번 깨졌다(2026-10-08).

검사 항목:
  1. spec(haehan-server·local-agent·mcp-server): Analysis 진입 파일이 있는가, hiddenimports·collect_submodules 중
     우리 모듈(ai_orchestrator·orchestrator_v1·scripts·local_agent·루트 .py)이 실제 파일/패키지로 풀리는가
     (서드파티 이름은 보지 않는다), ROOT / '...' 로 만든 경로(datas·binaries·icon 등)가 있는가.
     spec 은 실행하지 않고 AST 로만 읽는다.
  2. admin-web/electron/package.json: build.files·extraResources 의 원본(from·filter)이 소스 트리에 있는가.
     빌드 산출물(../../dist/<이름> 은 그 이름을 만드는 spec 이 있는지만, ../.next/* 는 확인 안 함)은 따로 표시한다.
     main.js·lib/*.js 의 path.join(process.resourcesPath, ...) 경로가 어떤 extraResources `to` 와 맞는가,
     그 `to` 가 spec 산출물이면 exe 이름이 spec 의 EXE name 과 같은가.
  3. desktop-release.yml: working-directory·cache-dependency-path·*.spec·*.py·-r/-c 인자 경로가 있는가.
존재 판정은 git 추적 파일 기준이다(로컬에만 있는 미추적 파일로 통과했다가 CI 에서 깨지는 일 방지).

사용:
    python tools/repo_gates/bundle_path_gate.py --staged     # pre-commit: 관련 파일이 staged 일 때만 전체 검사
    python tools/repo_gates/bundle_path_gate.py --check-all  # CI: 항상 전체 검사
우회 옵션 없음 — 깨진 참조는 spec·package.json·js·워크플로를 실제 경로에 맞게 고친다.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import importlib
import json
import posixpath
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

_BOOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

# 부트스트랩 뒤라 import 문 대신 import_module — git 헬퍼는 G11(tool_home_gate)의 것을 그대로 쓴다.
repo_root = importlib.import_module("scripts.common.app_paths").repo_root
tracked_files = importlib.import_module("tools.repo_gates.tool_home_gate").tracked_files

ROOT = repo_root()
SPECS = ("haehan-server.spec", "local-agent.spec", "mcp-server.spec")
OUR_PACKAGES = frozenset({"ai_orchestrator", "orchestrator_v1", "scripts", "local_agent"})
ELECTRON_DIR = "admin-web/electron"
PACKAGE_JSON = f"{ELECTRON_DIR}/package.json"
ELECTRON_JS = ("main.js", "lib/*.js")
WORKFLOW = ".github/workflows/desktop-release.yml"
DIST_PREFIX = "../../dist/"  # electron 폴더 기준 PyInstaller 산출물 (--distpath dist)
BUILD_OUTPUT_PREFIXES = ("../.next/",)  # next build 산출물 — 소스 트리에 없다
WORKFLOW_BUILD_OUTPUTS = ("dist/", "dist-electron-new/", "release-out/", "e2e-app-logs/")
GLOB_CHARS = frozenset("*?[")

_RESOURCES_JOIN_RE = re.compile(r"path\.join\(\s*process\.resourcesPath\s*((?:,\s*(?:\"[^\"]*\"|'[^']*')\s*)*)")
_JS_STR_RE = re.compile(r"\"([^\"]*)\"|'([^']*)'")
_WF_SPEC_RE = re.compile(r"(?<![\w./-])([\w./-]+\.spec)(?![\w.])")
_WF_PY_RE = re.compile(r"(?<![\w./-])([\w./-]+\.py)(?![\w.])")
_WF_RC_RE = re.compile(r"\s-[rc]\s+([\w./-]+)")
_WF_WD_RE = re.compile(r"^\s*working-directory:\s*(\S+)\s*$")
_WF_STEP_RE = re.compile(r"^\s*-\s+(?:name|uses):")


@dataclass
class Finding:
    area: str  # spec · electron · workflow
    source: str  # 참조가 적힌 파일
    ref: str  # 참조 내용
    status: str  # OK · FAIL · SKIP
    detail: str = ""


@dataclass
class RepoIndex:
    """git 추적 파일 기준 존재 판정."""

    root: Path
    files: frozenset[str]
    dirs: frozenset[str] = field(default_factory=frozenset)
    py_dirs: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def build(cls, root: Path) -> RepoIndex:
        files = frozenset(f for f in tracked_files(root) if (root / f).exists())
        dirs: set[str] = set()
        py_dirs: set[str] = set()
        for f in files:
            parents = [str(p) for p in PurePosixPath(f).parents if str(p) != "."]
            dirs.update(parents)
            if f.endswith(".py"):
                py_dirs.update(parents)
        return cls(root, files, frozenset(dirs), frozenset(py_dirs))

    def exists(self, rel: str) -> bool:
        rel = posixpath.normpath(rel.replace("\\", "/")).strip("/")
        return rel in self.files or rel in self.dirs

    def is_dir(self, rel: str) -> bool:
        return posixpath.normpath(rel).strip("/") in self.dirs

    def glob_any(self, pattern: str) -> bool:
        pats = {pattern, pattern.replace("**/", "")}
        return any(fnmatch.fnmatchcase(f, p) for f in self.files for p in pats)

    def root_modules(self) -> frozenset[str]:
        return frozenset(f[:-3] for f in self.files if "/" not in f and f.endswith(".py"))

    def resolve_module(self, name: str) -> bool | None:
        """우리 모듈이면 실제로 있는지(True/False), 서드파티면 None."""
        top = name.split(".")[0]
        if top not in OUR_PACKAGES and top not in self.root_modules():
            return None
        rel = name.replace(".", "/")
        return f"{rel}.py" in self.files or f"{rel}/__init__.py" in self.files or rel in self.py_dirs


# ── 1. PyInstaller spec ─────────────────────────────────────────────────────


@dataclass
class SpecInfo:
    name: str
    entries: list[str] = field(default_factory=list)
    hidden: list[str] = field(default_factory=list)
    collect: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)  # ROOT / ... 와 datas 의 상대 문자열 경로
    exe_name: str | None = None
    collect_name: str | None = None


def _root_chain(node: ast.AST) -> str | None:
    """`ROOT / 'a' / 'b'` (str(...) 로 감싼 것 포함) → 'a/b'. 상수 아닌 조각이 섞이면 None."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str" and len(node.args) == 1:
        node = node.args[0]
    parts: list[str] = []
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        if not (isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)):
            return None
        parts.append(node.right.value)
        node = node.left
    if isinstance(node, ast.Name) and node.id == "ROOT" and parts:
        return "/".join(reversed(parts))
    return None


def _str_consts(node: ast.AST | None) -> list[str]:
    if isinstance(node, ast.List | ast.Tuple):
        return [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []


def _kw(call: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _named_lists(tree: ast.Module, value: ast.AST | None) -> list[ast.AST]:
    """kwarg 값이 리스트면 그대로, 이름이면 모듈 수준에서 그 이름에 대입·+= 된 리스트 리터럴 전부."""
    if not isinstance(value, ast.Name):
        return [value] if value is not None else []
    out: list[ast.AST] = []
    for st in tree.body:
        if not isinstance(st, ast.Assign | ast.AugAssign):
            continue
        targets = st.targets if isinstance(st, ast.Assign) else [st.target]
        if any(isinstance(t, ast.Name) and t.id == value.id for t in targets):
            out.append(st.value)
    return [v for v in out if isinstance(v, ast.List)]


def _call_name(call: ast.Call) -> str | None:
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def _scan_analysis(tree: ast.Module, call: ast.Call, info: SpecInfo, entry_ids: set[int]) -> None:
    for e in call.args[0].elts if call.args and isinstance(call.args[0], ast.List) else []:
        rel = _root_chain(e)
        if rel is None and isinstance(e, ast.Constant) and isinstance(e.value, str):
            rel = e.value
        if rel is not None:
            info.entries.append(rel)
            entry_ids.add(id(e.args[0]) if isinstance(e, ast.Call) else id(e))
    for lst in _named_lists(tree, _kw(call, "hiddenimports")):
        info.hidden.extend(_str_consts(lst))
    for key in ("datas", "binaries"):
        for lst in _named_lists(tree, _kw(call, key)):
            for item in getattr(lst, "elts", []):
                src = item.elts[0] if isinstance(item, ast.Tuple) and item.elts else None
                if isinstance(src, ast.Constant) and isinstance(src.value, str):
                    info.paths.append(src.value)


def _scan_call(tree: ast.Module, node: ast.Call, info: SpecInfo, entry_ids: set[int]) -> None:
    cname = _call_name(node)
    if cname == "Analysis":
        _scan_analysis(tree, node, info, entry_ids)
    elif cname == "collect_submodules" and node.args:
        info.collect.extend(_str_consts(ast.Tuple(elts=node.args[:1])))
    elif cname in ("EXE", "COLLECT"):
        nm = _kw(node, "name")
        if isinstance(nm, ast.Constant) and isinstance(nm.value, str):
            setattr(info, "exe_name" if cname == "EXE" else "collect_name", nm.value)


def _collect_loop_packages(tree: ast.Module) -> list[str]:
    """`for _pkg in ("a", "b"): ... collect_submodules(_pkg)` 형태의 패키지 이름."""
    return [
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and any(isinstance(c, ast.Call) and _call_name(c) == "collect_submodules" for c in ast.walk(node))
        for name in _str_consts(node.iter)
    ]


def parse_spec(text: str, name: str) -> SpecInfo:
    tree = ast.parse(text, filename=name)
    info = SpecInfo(name)
    entry_ids: set[int] = set()
    left_children: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left_children.add(id(node.left))
        elif isinstance(node, ast.Call):
            _scan_call(tree, node, info, entry_ids)
    info.collect.extend(_collect_loop_packages(tree))
    for node in ast.walk(tree):
        if id(node) in left_children or id(node) in entry_ids:
            continue
        rel = _root_chain(node) if isinstance(node, ast.BinOp) else None
        if rel is not None:
            info.paths.append(rel)
    return info


def load_specs(root: Path, idx: RepoIndex) -> tuple[dict[str, SpecInfo], list[Finding]]:
    specs: dict[str, SpecInfo] = {}
    out: list[Finding] = []
    for spec in SPECS:
        if spec not in idx.files:
            out.append(Finding("spec", spec, spec, "FAIL", "spec 파일이 없다"))
            continue
        try:
            specs[spec] = parse_spec((root / spec).read_text(encoding="utf-8"), spec)
        except SyntaxError as e:
            out.append(Finding("spec", spec, spec, "FAIL", f"구문 해석 실패: {e}"))
    return specs, out


def check_spec(info: SpecInfo, idx: RepoIndex) -> list[Finding]:
    out: list[Finding] = []
    if not info.entries:
        out.append(Finding("spec", info.name, "Analysis 진입점", "FAIL", "진입 파일을 찾지 못했다"))
    for rel in info.entries:
        ok = rel in idx.files
        out.append(Finding("spec", info.name, f"entry {rel}", "OK" if ok else "FAIL", "" if ok else "진입 파일 없음"))
    for kind, names in (("hiddenimport", info.hidden), ("collect_submodules", info.collect)):
        for mod in dict.fromkeys(names):
            r = idx.resolve_module(mod)
            if r is None:
                continue  # 서드파티·표준 라이브러리 — 보지 않는다
            out.append(
                Finding("spec", info.name, f"{kind} {mod}", "OK" if r else "FAIL", "" if r else "모듈 파일/패키지 없음")
            )
    for rel in dict.fromkeys(info.paths):
        ok = idx.exists(rel)
        out.append(Finding("spec", info.name, f"path {rel}", "OK" if ok else "FAIL", "" if ok else "경로 없음"))
    return out


# ── 2. Electron (package.json · lib/*.js) ───────────────────────────────────


def _has_glob(s: str) -> bool:
    return any(c in GLOB_CHARS for c in s)


def _edir(rel: str) -> str:
    return posixpath.normpath(f"{ELECTRON_DIR}/{rel}")


def _check_from(res: dict, specs: dict[str, SpecInfo], idx: RepoIndex) -> list[Finding]:
    src = str(res.get("from", ""))
    to = str(res.get("to", ""))
    ref = f"extraResources {src} → {to}"
    if src.startswith(DIST_PREFIX):
        dist_name = src[len(DIST_PREFIX) :].strip("/")
        owner = next((s for s, i in specs.items() if i.collect_name == dist_name), None)
        if owner:
            return [Finding("electron", PACKAGE_JSON, ref, "OK", f"빌드 산출물 — {owner} COLLECT name={dist_name}")]
        return [Finding("electron", PACKAGE_JSON, ref, "FAIL", f"dist/{dist_name} 를 만드는 spec(COLLECT name) 없음")]
    if src.startswith(BUILD_OUTPUT_PREFIXES):
        return [Finding("electron", PACKAGE_JSON, ref, "SKIP", "build output, not checked")]
    if not idx.exists(_edir(src)):
        return [Finding("electron", PACKAGE_JSON, ref, "FAIL", f"원본 없음: {_edir(src)}")]
    out = [Finding("electron", PACKAGE_JSON, ref, "OK")]
    for flt in res.get("filter", []) if isinstance(res.get("filter"), list) else []:
        if _has_glob(flt):
            continue
        ok = idx.exists(_edir(f"{src}/{flt}"))
        out.append(
            Finding("electron", PACKAGE_JSON, f"{ref} filter {flt}", "OK" if ok else "FAIL", "" if ok else "파일 없음")
        )
    return out


def _check_js_paths(resources: list[dict], specs: dict[str, SpecInfo], idx: RepoIndex, root: Path) -> list[Finding]:
    tos = {str(r.get("to", "")).strip("/"): str(r.get("from", "")) for r in resources}
    exe_of = {
        to: next((i.exe_name for i in specs.values() if f"{DIST_PREFIX}{i.collect_name}" == src.rstrip("/")), None)
        for to, src in tos.items()
    }
    out: list[Finding] = []
    js_files = sorted(f for f in idx.files for g in ELECTRON_JS if fnmatch.fnmatchcase(f, f"{ELECTRON_DIR}/{g}"))
    for js in js_files:
        text = (root / js).read_text(encoding="utf-8", errors="replace")
        for m in _RESOURCES_JOIN_RE.finditer(text):
            segs = [a or b for a, b in _JS_STR_RE.findall(m.group(1))]
            if not segs:
                continue
            rel = "/".join(segs)
            if segs[0] == "..":
                out.append(Finding("electron", js, f"resourcesPath/{rel}", "SKIP", "개발용 경로(resources 밖)"))
                continue
            to = next((t for t in tos if rel == t or rel.startswith(f"{t}/")), None)
            if to is None:
                out.append(Finding("electron", js, f"resourcesPath/{rel}", "FAIL", "맞는 extraResources `to` 없음"))
                continue
            rest = rel[len(to) :].strip("/").split("/")[0]
            exe = exe_of.get(to)
            if exe and rest.endswith(".exe") and rest != f"{exe}.exe":
                out.append(Finding("electron", js, f"resourcesPath/{rel}", "FAIL", f"spec EXE name 은 {exe}.exe"))
                continue
            out.append(Finding("electron", js, f"resourcesPath/{rel}", "OK", f"extraResources to={to}"))
    return out


def check_electron(root: Path, idx: RepoIndex, specs: dict[str, SpecInfo]) -> list[Finding]:
    if PACKAGE_JSON not in idx.files:
        return [Finding("electron", PACKAGE_JSON, PACKAGE_JSON, "FAIL", "package.json 없음")]
    build = json.loads((root / PACKAGE_JSON).read_text(encoding="utf-8")).get("build", {})
    out: list[Finding] = []
    for f in build.get("files", []):
        if not isinstance(f, str) or f.startswith("!"):
            continue
        ok = idx.glob_any(_edir(f)) if _has_glob(f) else idx.exists(_edir(f))
        out.append(Finding("electron", PACKAGE_JSON, f"files {f}", "OK" if ok else "FAIL", "" if ok else "파일 없음"))
    resources = [r if isinstance(r, dict) else {"from": r, "to": r} for r in build.get("extraResources", [])]
    for res in resources:
        out.extend(_check_from(res, specs, idx))
    out.extend(_check_js_paths(resources, specs, idx, root))
    return out


# ── 3. desktop-release.yml ──────────────────────────────────────────────────


def _wf_refs(text: str) -> list[tuple[str, str]]:
    """(종류, 저장소 상대 경로). working-directory 는 그 스텝 안의 상대 경로 해석에 쓴다."""
    refs: list[tuple[str, str]] = []
    wd = ""
    cache_indent: int | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if cache_indent is not None:
            if indent > cache_indent and ":" not in stripped:
                refs.append(("cache-dependency-path", stripped.removeprefix("- ").strip()))
                continue
            cache_indent = None
        if _WF_STEP_RE.match(line):
            wd = ""
        if m := _WF_WD_RE.match(line):
            wd = m.group(1)
            refs.append(("working-directory", wd))
            continue
        if stripped.startswith("cache-dependency-path:"):
            cache_indent = indent
            continue
        for kind, rx in (("spec", _WF_SPEC_RE), ("script", _WF_PY_RE), ("-r/-c", _WF_RC_RE)):
            for tok in rx.findall(line):
                refs.append((kind, posixpath.normpath(f"{wd}/{tok}") if wd else tok))
    return refs


def check_workflow(root: Path, idx: RepoIndex) -> list[Finding]:
    if WORKFLOW not in idx.files:
        return [Finding("workflow", WORKFLOW, WORKFLOW, "FAIL", "워크플로 파일 없음")]
    out: list[Finding] = []
    for kind, rel in dict.fromkeys(_wf_refs((root / WORKFLOW).read_text(encoding="utf-8"))):
        if rel.startswith(WORKFLOW_BUILD_OUTPUTS):
            out.append(Finding("workflow", WORKFLOW, f"{kind} {rel}", "SKIP", "build output, not checked"))
            continue
        ok = idx.is_dir(rel) if kind == "working-directory" else idx.exists(rel)
        out.append(Finding("workflow", WORKFLOW, f"{kind} {rel}", "OK" if ok else "FAIL", "" if ok else "경로 없음"))
    return out


# ── 실행 ────────────────────────────────────────────────────────────────────


def check_all(root: Path = ROOT) -> list[Finding]:
    idx = RepoIndex.build(root)
    specs, out = load_specs(root, idx)
    for info in specs.values():
        out.extend(check_spec(info, idx))
    out.extend(check_electron(root, idx, specs))
    out.extend(check_workflow(root, idx))
    return out


def staged_names(root: Path = ROOT) -> list[str]:
    """staged 변경 전부(추가·수정·삭제, 이름변경은 삭제+추가로) — 삭제된 모듈도 잡아야 해서 A/R 만 보는 staged_added 로는 부족."""
    r = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--no-renames", "-z"],
        cwd=str(root),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return [f for f in r.stdout.split("\0") if f]


def needs_check(names: list[str], root: Path = ROOT) -> bool:
    """관련 파일이 staged 일 때만 검사(싼 판정): spec·package.json·electron·워크플로, 또는 spec 에 이름이 적힌 .py."""
    for n in names:
        if n.endswith(".spec") or PurePosixPath(n).name == "package.json":
            return True
        if n.startswith((f"{ELECTRON_DIR}/", ".github/workflows/")):
            return True
    py = [n for n in names if n.endswith(".py")]
    if not py:
        return False
    spec_text = "".join((root / s).read_text(encoding="utf-8") for s in SPECS if (root / s).is_file())
    for n in py:
        p = PurePosixPath(n)
        mod = ".".join(p.with_suffix("").parts[:-1] if p.stem == "__init__" else p.with_suffix("").parts)
        if any(f"{q}{x}{q}" in spec_text for x in (mod, p.name) for q in "\"'"):
            return True
    return False


def report(findings: list[Finding], verbose: bool) -> int:
    fails = [f for f in findings if f.status == "FAIL"]
    skips = [f for f in findings if f.status == "SKIP"]
    oks = [f for f in findings if f.status == "OK"]
    stream = sys.stderr if fails else sys.stdout
    print("=" * 60, file=stream)
    print(
        f"[bundle_path_gate] G17 번들 경로 일관성 — OK {len(oks)} · FAIL {len(fails)} · SKIP {len(skips)}", file=stream
    )
    shown = findings if verbose else fails + skips
    for f in shown:
        print(f"  [{f.status}] {f.area:8} {f.source}: {f.ref}" + (f"  — {f.detail}" if f.detail else ""), file=stream)
    if fails:
        print("  → spec·package.json·electron js·워크플로의 경로/모듈 이름을 실제 위치에 맞게 고치세요.", file=stream)
        print("  (우회 옵션 없음. 정본: tools/repo_gates/bundle_path_gate.py 머리말)", file=stream)
    else:
        print("[bundle_path_gate] PASS — 깨진 번들 경로 참조 없음", file=stream)
    print("=" * 60, file=stream)
    return 1 if fails else 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--check-all", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true", help="OK 항목까지 모두 출력")
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    root = a.root.resolve()
    if a.staged:
        if not needs_check(staged_names(root), root):
            return 0
        return report(check_all(root), a.verbose)
    if a.check_all:
        return report(check_all(root), a.verbose)
    ap.error("--staged / --check-all 중 하나")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
