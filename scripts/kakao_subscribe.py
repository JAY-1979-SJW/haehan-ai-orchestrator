"""카카오 채팅방 구독 관리 CLI.

사용법:
  python scripts/kakao_subscribe.py list                          # 구독 목록
  python scripts/kakao_subscribe.py rooms                         # 카카오워크 채팅방 목록
  python scripts/kakao_subscribe.py add "카드 사용방"              # 구독 추가 (카카오워크)
  python scripts/kakao_subscribe.py add "홍길동" --app kakaotalk   # 카카오톡 방 구독
  python scripts/kakao_subscribe.py remove "카드 사용방"           # 구독 해제
  python scripts/kakao_subscribe.py pause "카드 사용방"            # 일시 중지
  python scripts/kakao_subscribe.py resume "카드 사용방"           # 재개
  python scripts/kakao_subscribe.py collect "카드 사용방"          # 1회성 수집 (비구독 방도 가능)
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai_orchestrator.local_agent.desktop.subscriptions import (
    list_subscriptions, subscribe, unsubscribe, set_active, is_subscribed,
)
from ai_orchestrator.local_agent.desktop.mixins.kakaowork_mixin import KakaoworkMixin


def cmd_list():
    subs = list_subscriptions()
    if not subs:
        print("구독된 방 없음. 'rooms' 명령으로 채팅방 목록 확인 후 'add'로 추가하세요.")
        return
    print(f"구독 목록 ({len(subs)}개)")
    print("-" * 60)
    for s in subs:
        status = "활성" if s.get("active") else "일시중지"
        flags = []
        if s.get("collect_files"): flags.append("파일")
        if s.get("collect_messages"): flags.append("메시지")
        print(f"  [{status}] {s['app']:10s} | {s['room']:30s} | {','.join(flags)}")
        if s.get("note"):
            print(f"             {s['note']}")


def cmd_rooms():
    class _T(KakaoworkMixin): pass
    rooms = _T().kakaowork_list_rooms()
    if not rooms:
        print("카카오워크 채팅방 미발견 (앱 실행 확인)")
        return
    print(f"카카오워크 채팅방 ({len(rooms)}개)")
    print("-" * 60)
    for r in rooms:
        sub_mark = "★" if is_subscribed(r["name"], app="kakaowork") else " "
        unread = f"({r['unread_count']})" if r['unread_count'] > 0 else "    "
        print(f"  {sub_mark} {r['name']:30s} {unread}  {r['last_msg'][:40]}")


def cmd_add(args: list[str]):
    name = args[0] if args else None
    if not name:
        print("사용법: add <채팅방이름> [--app kakaowork|kakaotalk] [--no-files] [--no-messages] [--note '...']")
        return
    app = "kakaowork"
    if "--app" in args:
        app = args[args.index("--app") + 1]
    collect_files = "--no-files" not in args
    collect_messages = "--no-messages" not in args
    note = ""
    if "--note" in args:
        note = args[args.index("--note") + 1]
    e = subscribe(name, app=app, collect_files=collect_files,
                   collect_messages=collect_messages, note=note)
    print(f"구독 추가: [{e['app']}] {e['room']}")
    print(f"  파일: {e['collect_files']} / 메시지: {e['collect_messages']}")


def cmd_remove(args: list[str]):
    name = args[0] if args else None
    if not name:
        print("사용법: remove <채팅방이름>"); return
    app = "kakaowork"
    if "--app" in args:
        app = args[args.index("--app") + 1]
    ok = unsubscribe(name, app=app)
    print("해제 완료" if ok else "해당 구독 없음")


def cmd_pause_resume(name: str | None, active: bool, args: list[str]):
    if not name:
        print("사용법: pause|resume <채팅방이름>"); return
    app = "kakaowork"
    if "--app" in args:
        app = args[args.index("--app") + 1]
    ok = set_active(name, active, app=app)
    print(("재개" if active else "일시중지") + (" 완료" if ok else " 실패 (구독 없음)"))


def cmd_collect(args: list[str]):
    """1회성 수집 — 비구독 방도 명령 시점 직전에 들어온 파일들을 모아서 정리."""
    name = args[0] if args else None
    if not name:
        print("사용법: collect <채팅방이름> [--hours 24]"); return
    hours = 24
    if "--hours" in args:
        hours = int(args[args.index("--hours") + 1])

    from ai_orchestrator.local_agent.desktop.download_watcher import scan_existing
    from ai_orchestrator.local_agent.desktop.classifier import organize_file

    print(f"[1회성 수집] {name!r} 최근 {hours}시간 파일")
    files = scan_existing(age_hours=hours)
    print(f"  최근 {hours}시간 내 inbox 파일: {len(files)}개")

    organized = 0
    for f in files:
        path = Path(f["path"])
        try:
            r = organize_file(path, room_hint=name, copy=True)
            if r["status"].startswith(("copied", "moved")):
                organized += 1
                print(f"    {f['name']} → {r['suggested_folder']}")
        except Exception as e:
            print(f"    {f['name']} 실패: {e}")
    print(f"\n수집 완료: {organized}개")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    cmd = args[0]; rest = args[1:]
    match cmd:
        case "list": cmd_list()
        case "rooms": cmd_rooms()
        case "add": cmd_add(rest)
        case "remove" | "rm": cmd_remove(rest)
        case "pause": cmd_pause_resume(rest[0] if rest else None, False, rest)
        case "resume": cmd_pause_resume(rest[0] if rest else None, True, rest)
        case "collect": cmd_collect(rest)
        case _: print(__doc__)


if __name__ == "__main__":
    main()
