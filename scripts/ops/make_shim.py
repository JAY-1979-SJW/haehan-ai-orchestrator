"""이동한 파일의 옛 경로에 호환 shim 을 만든다 (G2).

사용:
    python scripts/ops/make_shim.py <옛경로.py> <새경로.py> [--dry-run]

shim 이 지키는 4가지 (alias 한 줄만으로는 1·2번만 된다 — 2026-10-07 hiworks·dashboard 회귀):
    1. import 별칭      `import old.module` 이 새 모듈과 같은 객체
    2. 파일 경로 로드    spec_from_file_location(옛 경로) 로 읽은 모듈에도 실제 속성이 있다
    3. 직접 실행         `python old.py` / `python -m old.module` 이 새 모듈의 __main__ 을 돌린다
       (새 파일에 `if __name__ == "__main__"` 이 있을 때만 전달 코드를 넣는다)
    4. 식별             첫 줄 마커 `# haehan-shim: <새.모듈>` — 계약 테스트가 자동 순회한다
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

MARKER = "# haehan-shim:"
# 마커 이전에 만든 기존 shim(approval_manager.py 형태)도 잡는다.
_ALIAS_RE = re.compile(
    r"""_?sys\.modules\[__name__\]\s*=\s*_?(?:il|importlib)\.import_module\(\s*["']([\w.]+)["']\s*\)"""
)
_MARKER_RE = re.compile(r"^#\s*haehan-shim:\s*([\w.]+)", re.M)

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist-build-tmp", "_archive"}


def module_name(rel_path: str) -> str:
    """저장소 상대 경로 → 점 모듈 이름. (`a/b/__init__.py` → `a.b`)"""
    p = rel_path.replace("\\", "/")
    if p.endswith(".py"):
        p = p[:-3]
    parts = [x for x in p.split("/") if x]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def has_main_block(source: str) -> bool:
    """`if __name__ == "__main__":` 블록이 있는지 (AST 로 판정)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        t = node.test
        if (
            isinstance(t, ast.Compare)
            and isinstance(t.left, ast.Name)
            and t.left.id == "__name__"
            and len(t.comparators) == 1
            and isinstance(t.comparators[0], ast.Constant)
            and t.comparators[0].value == "__main__"
        ):
            return True
    return False


def shim_target(source: str) -> str | None:
    """shim 이면 대상 모듈 이름, 아니면 None. 마커 우선, 없으면 옛 alias 형태로 판별."""
    m = _MARKER_RE.search(source[:600])
    if m:
        return m.group(1)
    m = _ALIAS_RE.search(source)
    if m and len(source.splitlines()) <= 40:  # 실제 코드가 섞인 큰 파일은 shim 으로 보지 않는다
        return m.group(1)
    return None


def render_shim(new_module: str, *, with_main: bool, old_path: str = "", new_path: str = "") -> str:
    lines = [
        f"{MARKER} {new_module}",
        f"# 호환 shim: 실제 모듈은 {new_module} 로 이동했다" + (f" ({new_path})." if new_path else "."),
        "# 옛 경로의 import · 파일 경로 로드 · 직접 실행을 모두 받는다. 새 코드는 새 경로를 쓸 것.",
        "# 생성: scripts/ops/make_shim.py — 계약 테스트: tests/test_shim_contract.py",
        "import importlib as _il",
        "import sys as _sys",
        "",
    ]
    if with_main:
        lines += [
            'if __name__ == "__main__":  # 직접 실행(python old.py / -m old)은 새 모듈의 __main__ 으로 전달',
            "    import runpy as _runpy",
            "",
            f'    _runpy.run_module("{new_module}", run_name="__main__")',
            "    raise SystemExit",
            "",
        ]
    lines += [
        "def _install(real, g, mods):",
        "    # spec_from_file_location 으로 이 파일을 직접 읽는 쪽은 sys.modules 교체를 못 본다 → 실제 속성을 복사해 준다.",
        '    g.update({k: v for k, v in vars(real).items() if not (k.startswith("__") and k.endswith("__"))})',
        '    mods[g["__name__"]] = real',
        "",
        "",
        f'_install(_il.import_module("{new_module}"), globals(), _sys.modules)',
        "",
    ]
    return "\n".join(lines)


def make_shim(old: str, new: str, root: Path, *, dry_run: bool = False) -> str:
    """shim 본문을 만들어 옛 경로에 쓴다(이미 파일이 있으면 거부). 본문을 반환한다."""
    old_rel = old.replace("\\", "/")
    new_rel = new.replace("\\", "/")
    new_file = root / new_rel
    if not new_file.is_file():
        raise FileNotFoundError(f"새 경로에 파일이 없다: {new_rel} (먼저 git mv)")
    old_file = root / old_rel
    if old_file.exists():
        raise FileExistsError(f"옛 경로에 이미 파일이 있다: {old_rel}")
    if not old_rel.endswith(".py") or not new_rel.endswith(".py"):
        raise ValueError("shim 은 .py 파일만 지원한다")
    body = render_shim(
        module_name(new_rel),
        with_main=has_main_block(new_file.read_text(encoding="utf-8", errors="replace")),
        old_path=old_rel,
        new_path=new_rel,
    )
    if not dry_run:
        old_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = old_file.with_name(old_file.name + ".tmp")
        tmp.write_text(body, encoding="utf-8", newline="\n")
        tmp.replace(old_file)  # 원자적 쓰기
    return body


def find_shims(root: Path) -> list[tuple[str, str]]:
    """저장소 안 모든 shim 을 (상대경로, 대상 모듈) 로 돌려준다."""
    out: list[tuple[str, str]] = []
    for p in sorted(root.rglob("*.py")):
        rel_parts = p.relative_to(root).parts
        if any(part in _SKIP_DIRS or part.startswith("hhwt-") for part in rel_parts):
            continue
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "import_module" not in src and MARKER not in src:
            continue
        target = shim_target(src)
        if target:
            out.append(("/".join(rel_parts), target))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    a = ap.parse_args(argv)
    try:
        body = make_shim(a.old, a.new, a.root, dry_run=a.dry_run)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        print(f"make_shim: {e}", file=sys.stderr)
        return 2
    if a.dry_run:
        print(body)
    else:
        print(f"shim 생성: {a.old} → {module_name(a.new.replace(chr(92), '/'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
