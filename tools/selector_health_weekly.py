"""셀렉터 헬스체크 주간 실행 래퍼 (Windows 작업 스케줄러용).

스케줄러가 직접 selector_health_check.py 를 호출하면, CDP 브라우저가 꺼져 있을 때
매번 exit 2(실행 오류)만 남고 정작 드리프트는 확인하지 못한다. 이 래퍼가
    CDP 기동 확인 → 헬스체크 실행 → 결과 로그 적재
까지 한 번에 처리한다.

등록:
    python tools/selector_health_weekly.py --install   # 매주 월요일 09:00
    python tools/selector_health_weekly.py --uninstall
    python tools/selector_health_weekly.py             # 즉시 1회 실행

로그: data/selector_health/weekly_log.jsonl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[1]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
sys.path.insert(0, str(ROOT))

TASK_NAME = "HaehanSelectorHealthWeekly"
LOG_DIR = ROOT / "data" / "selector_health"
LOG_FILE = LOG_DIR / "weekly_log.jsonl"

CHECKER = ROOT / "tools" / "selector_health" / "selector_health_check.py"
CDP_STARTER = ROOT / "scripts" / "browser" / "cdp" / "cdp_force_start.py"


def _run_schtasks(args: list[str], timeout: int = 30) -> tuple[int, str]:
    """schtasks 실행 + 안전 디코딩.

    schtasks 는 한국어 Windows 에서 CP949 로 출력한다. text=True(UTF-8) 로 받으면
    UnicodeDecodeError 로 죽는다(2026-08-15 실제 발생). 바이트로 받아 관대하게 디코딩한다.
    """
    r = subprocess.run(args, capture_output=True, timeout=timeout)
    raw = (r.stdout or b"") + (r.stderr or b"")
    for enc in ("cp949", "utf-8"):
        try:
            return r.returncode, raw.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return r.returncode, raw.decode("utf-8", errors="replace").strip()


def _log(record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record["at"] = datetime.now().isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _cdp_alive() -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3):
            return True
    except Exception:  # noqa: BLE001 - CDP 연결 상태 확인 실패시 False(미연결)로 안전한 기본값 반환하는 읽기전용 헬스체크
        return False


def ensure_cdp() -> bool:
    """CDP 가 꺼져 있으면 기동. 로그인 세션은 영구 프로필에 남아 있으므로 재로그인 불필요."""
    if _cdp_alive():
        return True
    try:
        subprocess.run(
            [sys.executable, str(CDP_STARTER), "start"],
            capture_output=True,
            text=True,
            timeout=90,
            cwd=str(ROOT),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001 - CDP 연결 상태 확인 실패시 False(미연결)로 안전한 기본값 반환하는 읽기전용 헬스체크
        return False
    return _cdp_alive()


def run_check() -> int:
    if not ensure_cdp():
        _log({"status": "cdp_down", "exit": 2, "message": "CDP 기동 실패 — 헬스체크 미실행"})
        print("CDP 기동 실패 — 헬스체크를 실행할 수 없습니다.")
        return 2

    proc = subprocess.run(
        [sys.executable, str(CHECKER), "--all", "--json"],
        capture_output=True,
        text=True,
        timeout=900,
        cwd=str(ROOT),
        encoding="utf-8",
    )
    out = proc.stdout or ""
    print(out)
    if proc.stderr:
        print(proc.stderr[:500], file=sys.stderr)

    status = {0: "ok", 1: "drift_detected", 2: "error"}.get(proc.returncode, "unknown")
    # 리포트에서 문제 건수만 추출
    problems = [ln.strip() for ln in out.splitlines() if "조치 필요" in ln or ln.strip().startswith("- ")]
    _log({"status": status, "exit": proc.returncode, "problems": problems[:20]})

    if proc.returncode == 1:
        print("\n⚠ 셀렉터 드리프트가 감지됐습니다. 자동화가 깨지기 전에 수정하세요.")
    return proc.returncode


def install_task(time_str: str = "09:00") -> int:
    """매주 월요일 지정 시각에 실행되도록 등록."""
    cmd = f'"{sys.executable}" "{Path(__file__).resolve()}"'
    args = [
        "schtasks",
        "/create",
        "/tn",
        TASK_NAME,
        "/tr",
        cmd,
        "/sc",
        "WEEKLY",
        "/d",
        "MON",
        "/st",
        time_str,
        "/f",  # 기존 동일 이름 있으면 덮어쓰기
    ]
    code, msg = _run_schtasks(args)
    print(msg)
    if code == 0:
        print(f"\n등록 완료: {TASK_NAME} — 매주 월요일 {time_str}")
        print(f"  실행: {cmd}")
        print(f"  로그: {LOG_FILE}")
    return code


def uninstall_task() -> int:
    code, msg = _run_schtasks(["schtasks", "/delete", "/tn", TASK_NAME, "/f"])
    print(msg)
    return code


def show_status() -> int:
    code, msg = _run_schtasks(["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"])
    if code != 0:
        print(f"'{TASK_NAME}' 미등록")
        return 1
    print(msg)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="셀렉터 헬스체크 주간 실행/등록")
    ap.add_argument("--install", action="store_true", help="매주 월요일 스케줄 등록")
    ap.add_argument("--uninstall", action="store_true", help="스케줄 해제")
    ap.add_argument("--status", action="store_true", help="등록 상태 확인")
    ap.add_argument("--time", default="09:00", help="실행 시각 (기본 09:00)")
    args = ap.parse_args()

    if args.install:
        return install_task(args.time)
    if args.uninstall:
        return uninstall_task()
    if args.status:
        return show_status()
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
