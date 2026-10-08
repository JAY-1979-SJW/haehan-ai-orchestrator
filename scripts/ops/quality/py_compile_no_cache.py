"""Run py_compile without writing repository __pycache__ files."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
import py_compile
import sys
from pathlib import Path

# 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
_BOOT = Path(__file__).resolve().parents[3]
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()


def cfile_for(path: Path) -> Path:
    key = hashlib.sha256(str(path.resolve()).encode("utf-8", errors="ignore")).hexdigest()[:16]
    out_dir = Path(
        os.environ.get("HAEHAN_PY_COMPILE_TMP", str(Path(os.environ["TEMP"]) / "haehan_py_compile_no_cache"))
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{path.stem}.{key}.pyc"


def expand(raw: str) -> list[Path]:
    """파일이면 그대로, 폴더면 그 아래 *.py 전부(정렬). 폴더를 주면 새로 생긴 파일도 자동으로 검사 대상이 된다."""
    path = Path(raw)
    if path.is_dir():
        return sorted(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
    return [path]


def compile_one(path: Path) -> bool:
    """한 파일을 컴파일한다. 실패하면 True."""
    cfile = cfile_for(path)
    try:
        py_compile.compile(str(path), cfile=str(cfile), doraise=True)
        with contextlib.suppress(OSError):
            cfile.unlink(missing_ok=True)
        print(f"[PASS] py_compile {path}")
    except py_compile.PyCompileError as exc:
        print(f"[FAIL] py_compile {path}: {exc.msg}", file=sys.stderr)
        return True
    except OSError as exc:
        print(f"[FAIL] py_compile {path}: {exc}", file=sys.stderr)
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile Python files without creating pyc artifacts")
    parser.add_argument("paths", nargs="+", help="파일 또는 폴더(폴더는 그 아래 *.py 전부)")
    args = parser.parse_args(argv)

    failed = False
    for raw in args.paths:
        for path in expand(raw):
            failed = compile_one(path) or failed
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
