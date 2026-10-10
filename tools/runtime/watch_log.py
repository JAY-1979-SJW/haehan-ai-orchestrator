#!/usr/bin/env python3
"""Follow a log file in realtime.

Defaults to the realtime audit text log.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))

from scripts.common.realtime_audit import AUDIT_TEXT, follow_file  # noqa: E402 - sys.path 부트스트랩 뒤 import


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch a log file")
    parser.add_argument("path", nargs="?", default=str(AUDIT_TEXT))
    parser.add_argument("--from-start", action="store_true")
    args = parser.parse_args()

    path = Path(args.path)
    print(f"watching: {path}")
    for line in follow_file(path, from_start=args.from_start):
        print(line, flush=True)


if __name__ == "__main__":
    main()
