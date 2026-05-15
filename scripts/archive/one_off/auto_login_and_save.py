"""자동 로그인 + 세션 저장 스크립트.

사용자가 데몬 크롬에서 로그인하면 자동으로 세션을 저장하고 로깅합니다.

사용법:
  python scripts/auto_login_and_save.py <사이트> [URL]

  예:
    python scripts/auto_login_and_save.py naver https://www.naver.com
    python scripts/auto_login_and_save.py eum.cw.or.kr https://eum.cw.or.kr/web/log/WEBLOG400M00
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return

    site = sys.argv[1]
    url = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"\n[작업] {site} 자동 로그인 + 세션 저장")
    print(f"  사이트: {site}")
    if url:
        print(f"  URL: {url}")

    from scripts.navigator import goto, wait_login
    from scripts import cdp_db
    from scripts.logger import get_logger

    log = get_logger(__name__)

    try:
        # 데이터베이스 초기화
        cdp_db.init_db()

        # 사이트로 이동
        if url:
            print(f"⏳ {url}로 이동 중...")
            goto(url)
        else:
            print(f"⏳ {site}로 이동 중...")

        # 자동 탐지 모드: 주기적으로 로그인 감지
        print("⏳ 자동 로그인 탐지 중... (최대 300초)")
        print("   → 브라우저에서 로그인을 진행하세요")
        print("   (자동으로 감지되어 세션이 저장됩니다)")

        from scripts.login_detector import monitor_for_login

        result = monitor_for_login(None, check_interval=5, timeout_s=300)

        if result.get("detected"):
            detected_site = result.get("site") or site
            elapsed = result.get("elapsed_s", 0)
            print(f"\n✓ {detected_site} 로그인 자동 감지됨 ({elapsed}초)")
            print(f"✓ 세션 자동 저장 완료")
            print(f"  - 로그인 사이트: {detected_site}")
            print(f"  - 저장 위치: data/cdp.db")
            print(f"\n  다음에 이 사이트를 방문할 때 자동으로 복원됩니다.")
            log.info("[auto-login] %s 로그인 자동 감지 + 저장 (%ds)", detected_site, elapsed)

        else:
            print(f"\n✗ {site} 로그인 감지 타임아웃 (300초 경과)")
            log.warning("[auto-login] %s 로그인 감지 타임아웃", site)
            sys.exit(1)

    except Exception as e:
        print(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
