"""이동한 파일(또는 패키지 전체)의 옛 경로에 호환 shim 을 만든다 (G2).

사용(파일 1개):
    python tools/devflow/make_shim.py <옛경로.py> <새경로.py> [--dry-run]
사용(패키지 — 하위 모듈째 옮긴 경우, 둘 다 디렉터리로 준다):
    python tools/devflow/make_shim.py <옛패키지디렉터리> <새패키지디렉터리> [--dry-run]
    (새 디렉터리의 .py 파일(__init__.py 포함) 각각에 옛 자리 shim 을 1개씩 만든다 —
     __init__.py 뿐 아니라 하위 모듈도 전부 4계약을 독립적으로 만족해야
     mail_read.cdp 같은 "하위 모듈 직접 import·경로 로드·직접 실행"이 깨지지 않는다.
     2026-10-07 W2 실측 — 동적 sys.modules 별칭만으로는 mypy attr-defined 가 나고,
     __init__.py 하나만 shim 이면 하위 모듈의 파일 경로 로드·직접 실행은 못 받는다.)

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

_BOOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()

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


BOOTSTRAP_MARK = "haehan-root-bootstrap"


def _bootstrap_lines(old_path: str) -> list[str]:
    """하위 폴더 shim 을 `python 옛경로` 로 직접 실행하면 sys.path[0] 이 shim 폴더라 저장소 루트의 패키지를 못 찾는다.

    정본 paths 를 import 하기 전이라 루트를 직접 계산할 수밖에 없는 불가피한 예외 — 마커 주석으로 표시해
    나중의 '새 루트 직접 계산 차단' 게이트(G5)가 예외로 등록하게 한다. 루트 shim 은 sys.path[0] 이 곧 루트라 필요 없다.
    """
    depth = len([x for x in old_path.replace("\\", "/").split("/") if x]) - 1
    if depth <= 0:
        return []
    return [
        # import 두 줄은 붙여서(ruff I001: import 블록 중간에 주석이 끼면 정렬·서식 위반), 그 뒤 빈 줄, 그다음 마커 주석과 코드
        "    from pathlib import Path as _Path",
        "",
        f"    # {BOOTSTRAP_MARK}: 하위 폴더 shim 직접 실행용 루트 부트스트랩(정본 paths import 전이라 불가피, G5 예외)",
        f"    _root = str(_Path(__file__).resolve().parents[{depth}])",
        "    if _root not in _sys.path:",
        "        _sys.path.insert(0, _root)",
    ]


def render_shim(new_module: str, *, with_main: bool, old_path: str = "", new_path: str = "") -> str:
    lines = [
        f"{MARKER} {new_module}",
        f"# 호환 shim: 실제 모듈은 {new_module} 로 이동했다" + (f" ({new_path})." if new_path else "."),
        "# 옛 경로의 import · 파일 경로 로드 · 직접 실행을 모두 받는다. 새 코드는 새 경로를 쓸 것.",
        "# 생성: tools/devflow/make_shim.py — 계약 테스트: tests/test_shim_contract.py",
        "import importlib as _il",
        "import sys as _sys",
        "",
    ]
    if with_main:
        lines += [
            'if __name__ == "__main__":  # 직접 실행(python old.py / -m old)은 새 모듈의 __main__ 으로 전달',
            "    import runpy as _runpy",
            *_bootstrap_lines(old_path),
            "",
            f'    _runpy.run_module("{new_module}", run_name="__main__")',
            "    raise SystemExit",
            "",
        ]
    lines += [
        "",
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


def make_package_shim(old_dir: str, new_dir: str, root: Path, *, dry_run: bool = False) -> dict[str, str]:
    """패키지 전체 이동 — 새 디렉터리의 .py 파일마다 옛 자리에 shim 을 1개씩 만든다.

    각 shim 은 make_shim() 과 같은 생성기를 재사용해 4계약을 전부 받는다(코드 중복 없음).
    옛 디렉터리에 이미 파일이 있으면(부분 이동 등) 그 파일은 건너뛰고 경고만 남긴다 —
    전체를 막지는 않는다(다른 담당이 이미 손으로 처리했을 수 있음).
    """
    old_rel = old_dir.replace("\\", "/").rstrip("/")
    new_rel = new_dir.replace("\\", "/").rstrip("/")
    new_path = root / new_rel
    if not new_path.is_dir():
        raise FileNotFoundError(f"새 패키지 디렉터리가 없다: {new_rel} (먼저 git mv)")
    py_files = sorted(p.name for p in new_path.glob("*.py"))
    if not py_files:
        raise FileNotFoundError(f"새 패키지 디렉터리에 .py 파일이 없다: {new_rel}")
    bodies: dict[str, str] = {}
    for name in py_files:
        old_file_rel = f"{old_rel}/{name}"
        new_file_rel = f"{new_rel}/{name}"
        if (root / old_file_rel).exists():
            print(f"make_shim: 건너뜀(이미 있음) {old_file_rel}", file=sys.stderr)
            continue
        bodies[old_file_rel] = make_shim(old_file_rel, new_file_rel, root, dry_run=dry_run)

    # __init__.py 가 새로 생겼으면, 형제 하위모듈을 sys.modules 에 먼저 등록해 둔다.
    # 안 하면 `import old.sub.a` 가 부모(old.sub)의 __path__(= 별칭 교체로 실제 new.sub 를
    # 가리키게 됨) 를 따라가 old.sub.a 를 새로 다시 실행해 old/sub/a.py shim 과는 별개의
    # 모듈 객체가 돼버린다(실측 확인) — sys.modules 선등록이면 캐시에 먼저 걸려 이 문제가 없다.
    init_rel = f"{old_rel}/__init__.py"
    if init_rel in bodies and not dry_run:
        new_module = module_name(f"{new_rel}/__init__.py")
        siblings = [p.stem for p in new_path.glob("*.py") if p.stem != "__init__"]
        if siblings:
            extra = [
                "",
                "# 형제 하위 모듈 선등록 — import old.sub.a 가 부모 __path__ 를 따라 새로 실행되는 것을 막는다",
            ]
            for sib in siblings:
                extra.append(f'_sys.modules[f"{{__name__}}.{sib}"] = _il.import_module("{new_module}.{sib}")')
            init_path = root / init_rel
            init_path.write_text(
                init_path.read_text(encoding="utf-8") + "\n".join(extra) + "\n", encoding="utf-8", newline="\n"
            )
            bodies[init_rel] = init_path.read_text(encoding="utf-8")
    return bodies


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
    ap.add_argument("--root", type=Path, default=ROOT)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")  # cp949 콘솔에서 --help/dry-run 한글이 터지지 않게
    a = ap.parse_args(argv)
    is_pkg_call = not a.old.endswith(".py") and not a.new.endswith(".py")
    try:
        if is_pkg_call:
            bodies = make_package_shim(a.old, a.new, a.root, dry_run=a.dry_run)
            if a.dry_run:
                for rel, body in bodies.items():
                    print(f"# ── {rel} ──")
                    print(body)
            else:
                for rel in bodies:
                    print(f"shim 생성: {rel}")
                print(f"패키지 shim {len(bodies)}개 생성: {a.old} → {a.new}")
        else:
            body = make_shim(a.old, a.new, a.root, dry_run=a.dry_run)
            if a.dry_run:
                print(body)
            else:
                print(f"shim 생성: {a.old} → {module_name(a.new.replace(chr(92), '/'))}")
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        print(f"make_shim: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
