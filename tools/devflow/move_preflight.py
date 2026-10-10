"""파일 이동 전/후 참조 전수 점검 (G1).

사용:
    python tools/devflow/move_preflight.py <옛경로.py> [...] [--json]
    python tools/devflow/move_preflight.py <폴더>/ [--json]            # 하위 패키지를 통째로 옮길 때: 폴더 안 .py(__init__.py 포함) 전부 + 같은 폴더 bare import(`import 패키지`) 참조까지
    python tools/devflow/move_preflight.py --staged-renames          # 커밋 훅용: git mv 한 것만 점검, 막을 것 있으면 exit 1

찾는 참조 종류 (kind):
    import          import / from-import (절대·상대)           → alias shim 으로 충분
    import_string   importlib.import_module("a.b") · patch("a.b.x") · 일정표의 모듈:함수 문자열
    path_load       spec_from_file_location 으로 파일 경로 로드   → 속성 복사 shim 필요 (make_shim 이 처리)
    runpy           runpy.run_path / run_module                  → 실행 전달 shim 필요
    direct_exec     bat/ps1/sh/subprocess 가 `python <파일>` / `-m 모듈` 로 직접 실행
    path_string     py 안의 경로 문자열(Path 조인 포함)
    config_path     json/yaml/toml 안의 경로 (entrypoints_manual.json 포함)
    hook            .claude/settings*.json 훅
    doc             .claude/skills · docs 의 실행 예시 (경고만)

옛 경로에 맞는 shim 이 없는데 path_load/runpy/direct_exec/path_string/config_path/hook 참조가 남아 있으면
"막음" 이다. (2026-10-07 hiworks 경로 로드·dashboard 직접 실행 회귀를 이동 전에 잡기 위한 도구)
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.devflow.make_shim import has_main_block, module_name, shim_target  # noqa: E402

BLOCKING = {"path_load", "runpy", "direct_exec", "path_string", "config_path", "hook"}
_TEXT_EXT = {
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".bat",
    ".cmd",
    ".ps1",
    ".sh",
    ".md",
    ".txt",
    ".cfg",
    ".ini",
    ".mjs",
    ".js",
    ".ts",
}
_MAX_BYTES = 2_000_000
_PYTHON_RUN_RE = re.compile(r"(?:python[\d.]*(?:\.exe)?|py(?:\s+-[\d.]+)?)\s+(?:-[\w]+\s+)*[\"']?([^\s\"']+)")


def _tracked_files(root: Path) -> list[str]:
    r = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=str(root),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode == 0 and r.stdout:
        return [f for f in r.stdout.split("\0") if f]
    return [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]


def _path_variants(rel: str) -> list[str]:
    p = rel.replace("\\", "/")
    return [p, p.replace("/", "\\"), p.replace("/", "\\\\")]


def _path_re(rel: str) -> re.Pattern[str]:
    """경로 변형(슬래시·역슬래시)이 다른 파일명의 꼬리(analytics_dashboard.py ⊃ dashboard.py)로 매칭되지 않게 앞 경계를 건다."""
    alts = "|".join(re.escape(v) for v in _path_variants(rel))
    return re.compile(r"(?<![\w.\-])(?:" + alts + r")(?![\w])")


def _dotted_module_re(mod: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w.])" + re.escape(mod) + r"(?![\w])")


class _Target:
    def __init__(self, rel: str, root: Path, main_from: str | None = None):
        self.rel = rel.replace("\\", "/")
        self.module = module_name(self.rel)
        self.stem = Path(self.rel).stem if not self.rel.endswith("__init__.py") else Path(self.rel).parent.name
        self.parent_dir = Path(self.rel).parent.name
        self.parent_module = self.module.rpartition(".")[0]
        # 같은 폴더 안의 bare import(`import smartstore` / `from smartstore import x`) 후보 위치: 패키지(__init__)면 그 패키지 폴더의 부모, 모듈이면 자기 폴더.
        # 파이썬 3 에서 단독 이름 import 는 sys.path 에 그 폴더가 있을 때만 되지만(스크립트 실행·sys.path 부트스트랩) 실제로 쓰이므로 참조로 센다.
        self.bare_dir = (
            Path(self.rel).parent.parent.as_posix()
            if self.rel.endswith("__init__.py")
            else Path(self.rel).parent.as_posix()
        )
        self.variants = _path_variants(self.rel)
        self.mod_re = _dotted_module_re(self.module)
        self.path_re = _path_re(self.rel)
        f = root / (main_from or self.rel)  # 이미 옮겨졌으면 새 위치에서 __main__ 을 본다
        self.has_main = f.is_file() and has_main_block(f.read_text(encoding="utf-8", errors="replace"))
        # 같은 basename("policy.py" 등)을 가진 **다른** 파일이 저장소에 더 있으면, 문자열에 디렉터리가
        # 없는 bare 파일명만으로는 "이 이동 대상을 가리킨다"고 확신할 수 없다(이름만 같은 다른 파일 참조일
        # 수 있음) — 그런 경우 bare-name 매칭의 신뢰도를 낮춘다(대표님 지시: maps 전체경로 판정 원칙).
        self.ambiguous_basename = any(
            p.is_file() and p.relative_to(root).as_posix() != self.rel
            for p in root.rglob(f"{self.stem}.py")
            if "__pycache__" not in p.parts
        )


def _divide_chain_join(node: ast.AST) -> str | None:
    """`Path(...) / "a" / "b.py"` 체인(ast.BinOp, Divide)을 "a/b.py" 로 이어붙인다.
    세그먼트가 하나뿐이면(단일 문자열) 일반 상수 처리로 충분하므로 None."""
    segs: list[str] = []
    cur = node
    while (
        isinstance(cur, ast.BinOp)
        and isinstance(cur.op, ast.Div)
        and isinstance(cur.right, ast.Constant)
        and isinstance(cur.right.value, str)
    ):
        segs.append(cur.right.value)
        cur = cur.left
    if len(segs) < 2:
        return None
    return "/".join(reversed(segs))


def _py_refs(rel: str, text: str, t: _Target) -> list[dict]:  # noqa: C901, PLR0912, PLR0915 - 참조 종류별 분기를 한 곳에서 판정하는 스캐너(분리하면 종류 간 문맥 공유가 늘어남)
    refs: list[dict] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    consts: list[tuple[int, str]] = []
    chain_join_by_line: dict[int, str] = {}
    pkg_parts = module_name(rel).split(".")
    pkg = pkg_parts if rel.endswith("__init__.py") else pkg_parts[:-1]
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                joined = _divide_chain_join(node)
                if joined:
                    chain_join_by_line[node.right.lineno] = joined
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == t.module or a.name.startswith(t.module + "."):
                        refs.append({"kind": "import", "line": node.lineno, "text": f"import {a.name}"})
                    elif (a.name == t.stem or a.name.startswith(t.stem + ".")) and Path(
                        rel
                    ).parent.as_posix() == t.bare_dir:
                        refs.append(
                            {
                                "kind": "import",
                                "line": node.lineno,
                                "text": f"import {a.name}  (같은 폴더 bare import — sys.path 의존)",
                            }
                        )
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    cut = len(pkg) - (node.level - 1)
                    base = ".".join([*pkg[: max(cut, 0)], *([base] if base else [])])
                if (
                    not node.level
                    and (node.module == t.stem or (node.module or "").startswith(t.stem + "."))
                    and Path(rel).parent.as_posix() == t.bare_dir
                ):
                    refs.append(
                        {
                            "kind": "import",
                            "line": node.lineno,
                            "text": f"from {node.module} import ...  (같은 폴더 bare import — sys.path 의존)",
                        }
                    )
                elif base == t.module or base.startswith(t.module + "."):
                    refs.append(
                        {
                            "kind": "import",
                            "line": node.lineno,
                            "text": f"from {'.' * node.level}{node.module or ''} import ...",
                        }
                    )
                elif base == t.parent_module and any(a.name == t.stem for a in node.names):
                    refs.append({"kind": "import", "line": node.lineno, "text": f"from {base} import {t.stem}"})
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                consts.append((node.lineno, node.value))
    # 문자열 상수 기반
    strs = [v for _, v in consts]
    has_spec = "spec_from_file_location" in text
    has_runpy_path = "run_path" in text
    has_runpy_mod = "run_module" in text
    has_subproc = bool(re.search(r"subprocess|os\.system|Popen|create_subprocess", text))
    parent_present = (not t.parent_dir) or t.parent_dir in strs or any(t.parent_dir in v for v in strs)
    for line, v in consts:
        single = "." not in t.module
        if single:
            # 루트 단일 이름 모듈은 일반 단어("dashboard" 라우트명 등)와 구분이 안 된다 → import 계열 호출이 있는 파일의 정확히 같은 문자열만
            mod_hit = bool(re.search(r"import_module|run_module|__import__|patch\(", text)) and v.strip() == t.module
        else:
            mod_hit = bool(
                t.mod_re.fullmatch(v.strip()) or (t.mod_re.search(v) and "/" not in v and " " not in v.strip())
            )
        if mod_hit:
            kind = "runpy" if has_runpy_mod else "import_string"
            refs.append({"kind": kind, "line": line, "text": v[:120]})
            continue
        m = _PYTHON_RUN_RE.findall(v)
        direct = any(t.rel in x.replace("\\", "/") or x.replace("\\", "/").endswith("/" + t.rel) for x in m)
        full_path = bool(t.path_re.search(v)) and (" " not in v.strip() or "/" in v or "\\" in v)
        # 디렉터리가 있는 문자열(v 에 "/"·"\\" 포함)은 그 디렉터리가 이 대상의 바로 위 폴더
        # (parent_dir)와 실제로 일치할 때만 "같은 파일"로 본다 — 파일명만 같고 폴더가 다르면
        # (예: ai_orchestrator/browser_tool/policy.py ≠ tools/gates/policy.py) 이 대상의
        # 참조가 아니다(대표님 지시: maps 전체경로 판정과 동일 원칙).
        has_dir_in_string = "/" in v or "\\" in v
        seg_match = v.endswith(f"/{t.parent_dir}/{t.stem}.py") or v.endswith(f"\\{t.parent_dir}\\{t.stem}.py")
        # 디렉터리 없이 파일명만(Path 조인 체인의 마지막 세그먼트 분리형) 인 경우에만 bare 매칭 허용
        # — 그 경우에도 같은 basename 을 가진 다른 파일이 저장소에 있으면(이름만으론 식별 불가) 쓰지 않는다.
        bare_only = (not has_dir_in_string) and v == f"{t.stem}.py" and not t.ambiguous_basename
        if direct or full_path or seg_match or (bare_only and parent_present):
            if has_spec:
                kind = "path_load"
            elif has_runpy_path:
                kind = "runpy"
            elif direct or (has_subproc and (direct or full_path)):
                kind = "direct_exec"
            else:
                kind = "path_string"
            # Path(...) / "a" / "b.py" 체인의 마지막 세그먼트만 보면 디렉터리를 잃는다 — 전체
            # 이어붙인 경로를 text 로 남겨야 report() 의 new_path 일치 판정이 정확해진다.
            ref_text = chain_join_by_line.get(line, v)
            refs.append({"kind": kind, "line": line, "text": ref_text[:120]})
    # Path 조인 `/ "x.py"` 처럼 문자열이 쪼개진 경우는 위 base_only 가 잡는다. 중복 줄 제거.
    seen: set[tuple[str, int]] = set()
    uniq = []
    for r_ in refs:
        key = (r_["kind"], r_["line"])
        if key not in seen:
            seen.add(key)
            uniq.append(r_)
    return uniq


_REGISTRY_PREFIXES = (
    "configs/module_registry",
    "configs/module_boundaries",
    "configs/root_legacy_scripts",
    "data/code_map/",
    "docs/",
)


def _is_registry(low: str) -> bool:
    """registry_sync·문서 이력이 관리하는 메타 파일 — 이동 시 훅(skeleton_gate)이 따로 정리하므로 막지 않는다."""
    return low.startswith(_REGISTRY_PREFIXES) and not low.endswith("entrypoints_manual.json")


def _text_refs(rel: str, text: str, t: _Target) -> list[dict]:  # noqa: C901, PLR0912 - 참조 종류별 분기를 한 곳에서 판정하는 스캐너(분리하면 종류 간 문맥 공유가 늘어남)
    refs: list[dict] = []
    low = rel.lower()
    ext = Path(rel).suffix.lower()
    if low.startswith(".claude/") and "settings" in low:
        default_kind = "hook"
    elif _is_registry(low):
        default_kind = "registry"
    elif low.endswith("entrypoints_manual.json") or ext in {".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"}:
        default_kind = "config_path"
    elif ext in {".bat", ".cmd", ".ps1", ".sh"}:
        default_kind = "direct_exec"
    elif ext in {".md", ".txt"}:
        default_kind = "doc"
    else:
        default_kind = "path_string"
    for i, line in enumerate(text.splitlines(), 1):
        hit_path = bool(t.path_re.search(line))
        hit_mod = bool(t.mod_re.search(line))
        if hit_mod and not hit_path and "." not in t.module:
            # 루트 단일 이름 모듈(dashboard 등)은 일반 단어와 구분이 안 된다 → import/-m 형태만 인정
            hit_mod = bool(re.search(rf"(?:import\s+|from\s+|-m\s+){re.escape(t.module)}", line))
        if not (hit_path or hit_mod):
            continue
        if default_kind == "doc" and _PYTHON_RUN_RE.search(line) and (hit_path or hit_mod):
            runs = [x.replace("\\", "/") for x in _PYTHON_RUN_RE.findall(line)]
            if any(r_ == t.rel or r_.endswith("/" + t.rel) or r_ == t.module for r_ in runs) or re.search(
                r"-m\s+" + re.escape(t.module), line
            ):
                refs.append({"kind": "direct_exec", "line": i, "text": line.strip()[:140]})
                continue
        if hit_mod and not hit_path:
            kind = (
                "direct_exec"
                if re.search(r"-m\s+" + re.escape(t.module), line) and default_kind != "doc"
                else ("doc" if default_kind == "doc" else "import_string")
            )
        else:
            kind = default_kind
        refs.append({"kind": kind, "line": i, "text": line.strip()[:140]})
    return refs


def scan(targets: list[str], root: Path = ROOT) -> dict[str, list[dict]]:
    ts = [_Target(x, root) for x in targets]
    out: dict[str, list[dict]] = {t.rel: [] for t in ts}
    for rel in _tracked_files(root):
        if Path(rel).suffix.lower() not in _TEXT_EXT or rel == ACK_FILE:  # 확인 목록 파일 자신은 참조로 세지 않는다
            continue
        if rel.startswith(("node_modules/", "_archive/", "dist-build-tmp/")):
            continue
        f = root / rel
        try:
            if not f.is_file() or f.stat().st_size > _MAX_BYTES:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for t in ts:
            if rel == t.rel:
                continue
            if t.stem not in text and t.module not in text:
                continue
            found = _py_refs(rel, text, t) if rel.endswith(".py") else _text_refs(rel, text, t)
            for r in found:
                out[t.rel].append({"file": rel, **r})
    return out


def _has_matching_shim(t: _Target, root: Path, new_module: str | None) -> bool:
    f = root / t.rel
    if not f.is_file():
        return False
    target = shim_target(f.read_text(encoding="utf-8", errors="replace"))
    if not target:
        return False
    return new_module is None or target == new_module


def recommend(t: _Target, refs: list[dict], *, cannot_reason: str | None = None) -> dict:
    kinds = sorted({r["kind"] for r in refs})
    if cannot_reason:
        return {"shim": "cannot move", "reason": cannot_reason, "kinds": kinds}
    need_exec = t.has_main and bool(set(kinds) & {"direct_exec", "runpy", "path_string", "config_path", "hook"})
    if "path_load" in kinds or need_exec or (t.has_main and kinds):
        why = []
        if "path_load" in kinds:
            why.append("spec_from_file_location 경로 로드(실제 속성 필요)")
        if t.has_main:
            why.append("__main__ 블록 있음 — 직접 실행 전달 필요")
        return {"shim": "execution-forward", "reason": "; ".join(why) or "경로 참조", "kinds": kinds}
    if set(kinds) & BLOCKING:
        return {
            "shim": "alias",
            "reason": "경로 문자열/설정 참조가 남음 — 옛 경로 유지용 shim, 또는 참조를 새 경로로 수정",
            "kinds": kinds,
        }
    if kinds:
        return {
            "shim": "alias",
            "reason": "import 참조만 있음 — 참조를 새 경로로 바꾸면 shim 불필요(외부 소비자 있으면 alias)",
            "kinds": kinds,
        }
    return {"shim": "none", "reason": "참조 없음", "kinds": kinds}


ACK_FILE = "configs/move_preflight_ack.json"


def _acked(root: Path) -> set[str]:
    """'__main__ 블록이 있는 파일을 shim 없이 옮겨도 된다'고 **참조 전수 수정 후** 확인해 둔 옛 경로 목록(리뷰 대상 설정 파일).

    암묵 직접 실행(__main__ 블록) 차단만 풀어 준다 — 경로 로드·직접 실행·설정·훅 같은 **명시 참조**가 남아 있으면 여전히 막는다.
    항목 형식: {"acked": [{"file": "scripts/x.py", "reason": "...", "date": "2026-10-07"}]} (사유 필수)."""
    p = root / ACK_FILE
    if not p.is_file():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {e["file"].replace("\\", "/") for e in data.get("acked", []) if e.get("file") and e.get("reason")}


def report(files: list[str], root: Path = ROOT, new_paths: dict[str, str] | None = None) -> list[dict]:
    refs_by = scan(files, root)
    out = []
    for rel in files:
        rel = rel.replace("\\", "/")
        t = _Target(rel, root, (new_paths or {}).get(rel))
        refs = refs_by[rel]
        new_rel = (new_paths or {}).get(rel)
        if new_rel:
            # 참조 문자열이 이동 목록표의 new_path(디렉터리 포함) 와 일치하면 이미 고쳐진 참조 —
            # 막지 않는다. 파일명만 같고 디렉터리가 다르면(= _path_re 가 전체 경로를 요구하므로
            # 매칭 안 됨) 여전히 다른 파일로 보고 막는다. 옛 경로 문자열은 new_rel 과 다르므로
            # 당연히 매칭 안 되어 그대로 차단된다.
            new_re = _path_re(new_rel.replace("\\", "/"))
            refs = [r for r in refs if not (r["kind"] in BLOCKING and new_re.search(r["text"]))]
        reason = None
        if Path(rel).name in {"__init__.py", "conftest.py", "sitecustomize.py"}:
            reason = f"{Path(rel).name} 은(는) 위치가 의미를 가진다(패키지 경계/pytest 수집 범위)"
        rec = recommend(t, refs, cannot_reason=reason)
        new_mod = module_name(new_paths[rel]) if new_paths and rel in new_paths else None
        shim_ok = _has_matching_shim(t, root, new_mod)
        if t.has_main and not shim_ok and t.rel not in _acked(root):
            refs = [
                *refs,
                {
                    "kind": "direct_exec",
                    "file": "(암묵)",
                    "line": 0,
                    "text": "__main__ 블록이 있어 `python <옛경로>` 직접 실행이 가능 — 옛 경로가 사라지면 사람·작업 스케줄러 실행이 깨진다",
                },
            ]
        blocking = [r for r in refs if r["kind"] in BLOCKING]
        out.append(
            {
                "file": rel,
                "module": t.module,
                "has_main": t.has_main,
                "references": refs,
                "recommendation": rec,
                "shim_present": shim_ok,
                "blocking": [] if shim_ok else blocking,
            }
        )
    return out


def load_maps_csv(paths: list[Path]) -> dict[str, str]:
    """maps\\*.csv(old_path,new_path) 를 읽어 old->new 딕셔너리로 합친다(헤더행 제외)."""
    import csv

    out: dict[str, str] = {}
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for row in csv.reader(f):
                if not row or row[0].strip().lower() in ("old_path", "#", ""):
                    continue
                old, new = row[0].strip().replace("\\", "/"), row[1].strip().replace("\\", "/")
                out[old] = new
    return out


def staged_renames(root: Path = ROOT) -> dict[str, str]:
    r = subprocess.run(
        ["git", "diff", "--cached", "--name-status", "-M", "--diff-filter=R", "-z"],
        cwd=str(root),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    parts = [p for p in r.stdout.split("\0") if p]
    pairs: dict[str, str] = {}
    i = 0
    while i + 2 < len(parts) and parts[i].startswith("R"):
        pairs[parts[i + 1]] = parts[i + 2]
        i += 3
    return {o: n for o, n in pairs.items() if o.endswith(".py")}


def _render_text(rows: list[dict]) -> str:
    lines: list[str] = []
    for row in rows:
        lines.append(f"■ {row['file']}  (module {row['module']}{', __main__ 있음' if row['has_main'] else ''})")
        refs = row["references"]
        if not refs:
            lines.append("   참조 없음")
        by_kind: dict[str, list[dict]] = {}
        for r in refs:
            by_kind.setdefault(r["kind"], []).append(r)
        for kind, items in sorted(by_kind.items()):
            mark = "‼" if kind in BLOCKING else " "
            lines.append(f"  {mark} {kind} ({len(items)})")
            for r in items[:15]:
                lines.append(f"       {r['file']}:{r['line']}  {r['text']}")
            if len(items) > 15:
                lines.append(f"       ... +{len(items) - 15}")
        rec = row["recommendation"]
        lines.append(f"  → shim 권고: {rec['shim']} — {rec['reason']}")
        if row["shim_present"]:
            lines.append("  → 옛 경로에 맞는 shim 이 이미 있음")
        lines.append("")
    return "\n".join(lines)


def expand_targets(paths: list[str], root: Path) -> list[str]:
    """폴더 인자는 그 안의 .py 전부(__init__.py 포함)로 펼친다 — 하위 패키지를 통째로 옮길 때 패키지 자체(`from . import <패키지>`)를 가리키는
    참조는 __init__.py 를 대상으로 해야 잡히므로, 파일을 하나씩 나열하다 __init__.py 를 빼먹는 일을 막는다."""
    out: list[str] = []
    for raw in paths:
        rel = raw.replace("\\", "/").rstrip("/")
        p = root / rel
        if p.is_dir():
            out += sorted(f.relative_to(root).as_posix() for f in p.rglob("*.py") if "__pycache__" not in f.parts)
        else:
            out.append(rel)
    return out


def main(argv: list[str] | None = None) -> int:  # noqa: C901 - CLI 진입점: 인자 해석과 훅 차단 메시지 출력
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")  # 훅/파이프의 cp949 기본값에서 ■ ‼ → 가 터지지 않게
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--staged-renames", action="store_true")
    ap.add_argument(
        "--maps",
        nargs="+",
        type=Path,
        default=None,
        help="maps\\*.csv(old_path,new_path) — new_path 로 고쳐진 참조는 해결 처리",
    )
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    root = a.root.resolve()
    new_paths: dict[str, str] | None = None
    if a.maps:
        new_paths = load_maps_csv(a.maps)
    files = expand_targets(a.files, root)
    if a.staged_renames:
        staged = staged_renames(root)
        new_paths = {**(new_paths or {}), **staged}
        files = list(staged)
        if not files:
            return 0
    if not files:
        ap.error("파일을 주거나 --staged-renames 를 쓴다")
    rows = report(files, root, new_paths)
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(_render_text(rows))
    if a.staged_renames:
        bad = [r for r in rows if r["blocking"]]
        if bad:
            print("=" * 60, file=sys.stderr)
            print(
                "move_preflight: 이동한 파일에 shim 없이 남은 경로 로드/직접 실행/경로 참조가 있어 커밋을 막는다.",
                file=sys.stderr,
            )
            for r in bad:
                new = (new_paths or {}).get(r["file"], "<새경로>")
                print(
                    f"  - {r['file']}: {len(r['blocking'])}건 → python tools/devflow/make_shim.py {r['file']} {new}",
                    file=sys.stderr,
                )
                for b in r["blocking"][:5]:
                    print(f"      {b['kind']}: {b['file']}:{b['line']} {b['text']}", file=sys.stderr)
            print("  (참조를 새 경로로 고치거나 shim 을 만든 뒤 다시 커밋. 우회 옵션 없음.)", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
