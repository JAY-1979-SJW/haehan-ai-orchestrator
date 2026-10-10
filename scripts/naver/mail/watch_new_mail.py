"""scripts/naver/mail/watch_new_mail.py — 새 메일 도착 감시 → OS 알림.

기존 CDP 세션에 attach만 한다(브라우저 실행/재시작/종료 없음 — collection/background_runner.py
의 "attach-only, read/prepare only" 원칙을 그대로 따름). 목록만 읽고(LIST_ONLY, 본문 열람·
읽음상태 변경 없음), 새로 발견된 안읽은 메일의 발신자/제목만 OS 알림으로 보여준다.

중복 알림 방지: 알림을 보낸 메일의 영속 식별자(sn)를 data/naver_mail_watch_state.json 에
기록한다.

사용:
    python scripts/naver/mail/watch_new_mail.py            # 1회 점검 + 알림
    python scripts/naver/mail/watch_new_mail.py --json      # JSON 출력
    python scripts/naver/mail/watch_new_mail.py --no-notify # 점검만, 알림 안 보냄(테스트용)

(docs/specs/2026-09-29_construction_ai_agent_direction.md 에서 이어진 "네이버 메일 수신시
알림" 요청 — 2026-09-29)
"""

from __future__ import annotations

import argparse
import json
import sys

from scripts.common.app_paths import repo_root

ROOT = repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.agent_runtime.runtime.notify.user_notification_adapter import notify_new_mail  # noqa: E402
from scripts.naver.mail.collection.background_runner import (  # noqa: E402
    create_isolated_mail_target,
    select_naver_session,
)
from scripts.naver.mail.read import list_collector  # noqa: E402

STATE_PATH = ROOT / "data" / "naver_mail_watch_state.json"
_MAX_SEEN_KEEP = 500


def _load_seen() -> set[str]:
    if not STATE_PATH.exists():
        return set()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return set(data.get("seen_sn", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_seen(seen: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    trimmed = list(seen)[-_MAX_SEEN_KEEP:]
    STATE_PATH.write_text(json.dumps({"seen_sn": trimmed}, ensure_ascii=False, indent=1), encoding="utf-8")


def check_once(*, max_items: int = 30, notify: bool = True) -> dict:
    """네이버메일함을 1회 점검하고, 새로 발견된 안읽은 메일이 있으면 알림을 보낸다."""
    session, selection = select_naver_session(allow_mixed_readonly=False)
    if session is None:
        return {"ok": False, "code": selection.code, "messages": list(selection.messages)}

    target_id, _page = create_isolated_mail_target(port=session.port)
    if not target_id:
        return {"ok": False, "code": "no_mail_target", "port": session.port}

    items, _meta = list_collector.collect_all_pages(target_id, max_pages=1, max_items=max_items)

    seen = _load_seen()
    new_unread = [it for it in items if it.is_unread and it.sn and it.sn not in seen]

    if notify and new_unread:
        if len(new_unread) == 1:
            only = new_unread[0]
            notify_new_mail(sender=only.sender_name, subject=only.subject)
        else:
            notify_new_mail(count=len(new_unread))

    for it in items:
        if it.sn:
            seen.add(it.sn)
    _save_seen(seen)

    return {
        "ok": True,
        "port": session.port,
        "checked": len(items),
        "new_unread_count": len(new_unread),
        "new_unread": [{"sender": it.sender_name, "subject": it.subject} for it in new_unread],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    ap.add_argument("--no-notify", action="store_true", help="점검만 하고 알림은 보내지 않음(테스트용)")
    ap.add_argument("--max-items", type=int, default=30, help="1회 점검 시 확인할 최대 메일 수")
    args = ap.parse_args(argv)

    result = check_once(max_items=args.max_items, notify=not args.no_notify)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif not result.get("ok"):
        print(f"[watch_new_mail] 건너뜀: {result.get('code')}")
    else:
        print(f"[watch_new_mail] 점검 {result['checked']}건, 새 안읽음 {result['new_unread_count']}건")

    return 0


if __name__ == "__main__":
    sys.exit(main())
