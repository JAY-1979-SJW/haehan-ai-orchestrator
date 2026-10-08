"""EUM(건설근로자공제회) 공지사항 게시판 감시 — 시스템 장애/점검/기한연장 공지 감지.

배경: 퇴직공제EDI·건설e음 시스템 개편/장애 시 카페 회원들이 "오늘 신고
가능할까요" 하며 불안해하는 게시글이 반복된다(건설공무카페 심층 분석 참고).
법령상 일반 원칙(정보통신망 장애 시 기한연장 인정)은 있지만 기관별 실제
적용 여부는 공식 공지로만 확인 가능하므로, 추측 대신 이 게시판을 감시해
실제 공지가 뜨는 순간만 신뢰할 수 있는 정보로 다룬다.

공지사항(WEBCEN010M00)은 로그인 없이 공개 접근 가능하다(2026-08-17 확인).

흐름:
  1. https://eum.cw.or.kr/web/cen/WEBCEN010M00 목록 수집
  2. 이전 실행 대비 신규 공지만 추출
  3. 제목에 장애/점검/지연/유예/연장/오류/긴급 키워드가 있으면 별도 플래그
  4. 결과를 data/eum/notice_monitor/ 에 저장 (자동 게시는 하지 않음 — 정책상
     외부 공개 발행은 매번 사용자 확인 필요, CLAUDE.md)

사용:
    python scripts/eum/notice_monitor.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common.logger import get_logger  # noqa: E402

log = get_logger(__name__)

NOTICE_URL = "https://eum.cw.or.kr/web/cen/WEBCEN010M00"

# 시스템 장애/점검/기한연장 관련 공지를 구분하기 위한 키워드.
# "부득이한" 은 국세기본법 등에서 기한연장 사유를 표현할 때 흔히 쓰이는 표현.
_ALERT_KEYWORDS = ("장애", "점검", "지연", "유예", "연장", "오류", "긴급", "중단", "먹통", "부득이한")


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


def _state_path() -> Path:
    return _eum_dir() / "notice_monitor" / "seen_notices.json"


def _load_seen() -> set[str]:
    p = _state_path()
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - 이미 처리한 공지 ID 캐시(seen) 로드 실패 시 빈 set 반환 - 읽기전용 중복방지 캐시 폴백, 최악의 경우 중복 알림 정도일 뿐 위험 조작 없음
        return set()


def _save_seen(ids: set[str]) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def _notice_key(row: dict) -> str:
    """행 고유키. article_id가 없으므로 (구분, 제목, 등록일) 조합 사용."""
    return f"{row.get('category', '')}|{row.get('title', '')}|{row.get('date', '')}"


def fetch_notices(page, limit_rows: int = 30) -> list[dict]:
    """공지사항 목록 최신 N건을 읽기 전용으로 수집."""
    page.goto(NOTICE_URL, timeout=25000, wait_until="domcontentloaded")
    time.sleep(2.5)

    rows = page.evaluate(
        """
        () => {
            const out = [];
            document.querySelectorAll('table tbody tr').forEach(tr => {
                const tds = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
                if (tds.length >= 5) {
                    out.push({
                        badge: tds[0] || '',
                        category: tds[1] || '',
                        title: (tds[2] || '').replace(/^NEW\\s*/, ''),
                        attachment: tds[3] || '',
                        date: tds[4] || '',
                        views: tds[5] || '',
                    });
                }
            });
            return out;
        }
        """
    )
    return rows[:limit_rows]


def is_alert(title: str) -> bool:
    return any(kw in title for kw in _ALERT_KEYWORDS)


def check_once(page) -> dict:
    """공지 목록을 조회해 신규 공지·경보성 공지를 분류."""
    notices = fetch_notices(page)
    seen = _load_seen()

    new_notices = [n for n in notices if _notice_key(n) not in seen]
    alert_notices = [n for n in new_notices if is_alert(n["title"])]

    _save_seen(seen | {_notice_key(n) for n in notices})

    result = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "total_fetched": len(notices),
        "new_count": len(new_notices),
        "alert_count": len(alert_notices),
        "new_notices": new_notices,
        "alert_notices": alert_notices,
    }

    out_dir = _eum_dir() / "notice_monitor"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d_%H%M%S")
    (out_dir / f"check_{today}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if alert_notices:
        log.warning(
            "[eum-notice] 장애/점검성 신규 공지 %d건 감지: %s",
            len(alert_notices),
            ", ".join(n["title"][:40] for n in alert_notices),
        )
    else:
        log.info("[eum-notice] 신규 공지 %d건, 경보성 없음", len(new_notices))

    return result


def check_once_headless() -> dict:
    """사용자 CDP 브라우저(탭)에 의존하지 않는 독립 헤드리스 조회.

    공지사항 페이지는 로그인이 필요 없는 공개 페이지이므로, 사용자가 쓰고
    있는 브라우저 탭을 가로채지 않고 별도 헤드리스 인스턴스로 확인한다.
    서버 백그라운드 스케줄러(항상 켜져 있는 루프)에서 호출하기 위한 진입점.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            return check_once(page)
        finally:
            browser.close()


def _main() -> None:
    result = check_once_headless()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
