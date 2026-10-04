"""L2 Policy/Gate — 새 메일 알림 판정(순수). 저장·네트워크 부작용 없음.

기준서: docs/specs/2026-10-02_mailbox_new_mail_alert.md
받은편지함의 UIDNEXT/UIDVALIDITY 를 이전 확인값과 비교해 새 메일 개수를 구한다.
"""

from __future__ import annotations

from typing import Any

COUNT_CAP = 99


def new_since(prev: dict[str, Any] | None, cur: dict[str, Any]) -> dict[str, Any]:
    """`{"reset": bool, "count": int}` — reset=True 는 기준만 새로 잡는다(알림 없음)."""
    if not prev or prev.get("uidvalidity") != cur.get("uidvalidity"):
        return {"reset": True, "count": 0}
    gap = int(cur.get("uidnext", 0)) - int(prev.get("uidnext", 0))
    if gap < 0:  # 서버가 번호를 새로 매긴 경우
        return {"reset": True, "count": 0}
    return {"reset": False, "count": gap}


def count_label(count: int) -> str:
    return f"{COUNT_CAP}+" if count > COUNT_CAP else str(count)
