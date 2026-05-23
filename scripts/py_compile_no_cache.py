"""Run py_compile without writing repository __pycache__ files."""
from __future__ import annotations

import argparse
import hashlib
import os
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cfile_for(path: Path) -> Path:
    key = hashlib.sha256(str(path.resolve()).encode("utf-8", errors="ignore")).hexdigest()[:16]
    out_dir = Path(os.environ.get("HAEHAN_PY_COMPILE_TMP", str(Path(os.environ["TEMP"]) / "haehan_py_compile_no_cache")))
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{path.stem}.{key}.pyc"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile Python files without creating pyc artifacts")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)

    failed = False
    for raw in args.paths:
        path = Path(raw)
        cfile = cfile_for(path)
        try:
            py_compile.compile(str(path), cfile=str(cfile), doraise=True)
            try:
                cfile.unlink(missing_ok=True)
            except OSError:
                pass
            print(f"[PASS] py_compile {path}")
        except py_compile.PyCompileError as exc:
            failed = True
            print(f"[FAIL] py_compile {path}: {exc.msg}", file=sys.stderr)
        except OSError as exc:
            failed = True
            print(f"[FAIL] py_compile {path}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
