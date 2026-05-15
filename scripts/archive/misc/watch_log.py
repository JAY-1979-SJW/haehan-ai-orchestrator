#!/usr/bin/env python3
"""실시간 로그 감시.

사용법:
  python scripts/watch_log.py                    # 기본 (data/setup_log.txt)
  python scripts/watch_log.py data/my_log.txt    # 특정 파일
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
log_file = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "setup_log.txt"

print(f"감시 중: {log_file}")
print("=" * 60)

if not log_file.exists():
    print("파일 없음 — 생성 대기 중...")
    while not log_file.exists():
        time.sleep(0.5)

with open(log_file, encoding="utf-8", errors="replace") as f:
    f.seek(0)
    while True:
        line = f.readline()
        if line:
            print(line, end="", flush=True)
        else:
            time.sleep(0.3)
