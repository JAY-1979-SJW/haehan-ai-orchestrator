"""서버 로그 실시간 감시 — ERROR/WARNING/Exception 감지 시 콘솔 출력.

사용:
    python tools/runtime/log_watcher.py [로그파일경로]
    기본: data/logs/server.log
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
LOG_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "logs" / "server.log"

ALERT_KEYWORDS = (
    "ERROR",
    "CRITICAL",
    "Exception",
    "Traceback",
    "수집 실패",
    "오류",
    "FAIL",
    "500",
)
SKIP_KEYWORDS = (
    "DEBUG",  # DEBUG 레벨은 제외
)


def tail_follow(path: Path):
    """파일 끝부터 새 줄만 실시간 스트림."""
    with path.open(encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)  # 파일 끝으로 이동 (기존 로그 무시)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.3)
                continue
            yield line


def is_alert(line: str) -> bool:
    if any(skip in line for skip in SKIP_KEYWORDS):
        return False
    return any(kw in line for kw in ALERT_KEYWORDS)


def main():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"[watcher] 감시 시작: {LOG_PATH}", flush=True)
    print(f"[watcher] 감지 키워드: {', '.join(ALERT_KEYWORDS)}", flush=True)

    # 파일이 생길 때까지 대기
    while not LOG_PATH.exists():
        print(f"[watcher] 로그 파일 대기 중: {LOG_PATH}", flush=True)
        time.sleep(2)

    consecutive_errors = []
    last_flush = time.time()

    for line in tail_follow(LOG_PATH):
        line = line.rstrip()
        if not line:
            continue

        if is_alert(line):
            consecutive_errors.append(line)
            print(f"[ALERT] {line}", flush=True)

        # 5초마다 정상 신호
        if time.time() - last_flush > 30:
            print(f"[watcher] ✓ 정상 감시 중 (최근 에러: {len(consecutive_errors)}건)", flush=True)
            consecutive_errors.clear()
            last_flush = time.time()


if __name__ == "__main__":
    main()
