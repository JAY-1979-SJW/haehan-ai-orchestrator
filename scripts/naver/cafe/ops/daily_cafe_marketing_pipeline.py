"""건설공무 카페 일일 수집 + 마케팅 요약 재빌드 — 스케줄러용 단일 진입점.

흐름:
  1. CDP 브라우저 확인(꺼져 있으면 강제 시작)
  2. 오늘 신규 게시글 수집 → 누적 JSONL append (daily_snapshot.run_daily_snapshot)
  3. marketing_summary_build.main() 재실행 → data/marketing/summary_latest.json 갱신

로그인 세션이 끊겨있으면 수집은 건너뛰고(예외 삼키지 않고 기록만) 요약 재빌드는
기존 누적 데이터로 계속 진행한다 — 하루 실패가 전체 파이프라인을 막지 않게.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime

from scripts.common.app_paths import repo_root

ROOT = repo_root()
sys.path.insert(0, str(ROOT))

LOG_PATH = ROOT / "data" / "daily_cafe_pipeline_log.jsonl"


def _log(payload: dict) -> None:
    import json

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload["ts"] = datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> int:
    result = {"snapshot_ok": False, "snapshot_error": "", "build_ok": False, "build_error": ""}

    try:
        from scripts.browser.cdp.cdp_force_start import _is_cdp_alive, cmd_start

        if not _is_cdp_alive():
            cmd_start()
    except Exception:  # noqa: BLE001 - CDP 강제시작 헬퍼가 없거나 실패해도 무시 — 아래 단계에서 자체적으로 연결 상태를 다시 확인함
        pass  # 강제시작 도우미가 없거나 실패해도 아래 단계에서 자체 확인

    try:
        from scripts.naver.cafe.collection.daily_snapshot import run_daily_snapshot
        from scripts.browser.cdp.connection import get_page

        page = get_page()
        snap_result = run_daily_snapshot(page)
        result["snapshot_ok"] = True
        result["snapshot_summary"] = snap_result
        print(f"[daily-pipeline] 수집 완료: {snap_result}")
    except Exception as e:  # noqa: BLE001 - 카페마케팅 일일 파이프라인 오케스트레이션 — CDP 강제시작 실패 무시(다음 단계에서 자체 확인), 수집/요약재빌드 실패는 result dict에 에러 기록 후 다음 단계 계속 진행할 뿐 쓰기 대상은 로컬 요약 파일
        result["snapshot_error"] = f"{type(e).__name__}: {e}"
        print(f"[daily-pipeline] 수집 실패(건너뜀): {result['snapshot_error']}")

    try:
        from scripts.naver.cafe.ops import marketing_summary_build

        marketing_summary_build.main()
        result["build_ok"] = True
        print("[daily-pipeline] 마케팅 요약 재빌드 완료")
    except Exception as e:  # noqa: BLE001 - 카페마케팅 일일 파이프라인 오케스트레이션 — CDP 강제시작 실패 무시(다음 단계에서 자체 확인), 수집/요약재빌드 실패는 result dict에 에러 기록 후 다음 단계 계속 진행할 뿐 쓰기 대상은 로컬 요약 파일
        result["build_error"] = f"{type(e).__name__}: {e}"
        print(f"[daily-pipeline] 요약 재빌드 실패: {result['build_error']}")
        traceback.print_exc()

    _log(result)
    return 0 if result["build_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
