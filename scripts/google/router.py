"""Google 서비스 라우터"""
from __future__ import annotations

from . import calendar, docs, drive, gmail, sheets


def run_google(site: str, task: str, sub: str, args: list[str]) -> None:
    """Google 서비스 라우팅.

    site: google | gmail
    task: mail | drive | calendar | docs | sheets
    sub: list | compose | create | insert 등 하위 명령
    args: 추가 인수
    """

    # site=gmail인 경우 task=mail로 정규화
    if site == "gmail":
        task = "mail"

    match task:
        case "mail":
            gmail.run(sub or "list", args)
        case "drive":
            drive.run(sub or "list", args)
        case "calendar":
            calendar.run(sub or "today", args)
        case "docs":
            docs.run(sub or "recent", args)
        case "sheets":
            sheets.run(sub or "recent", args)
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")
