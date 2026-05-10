"""카카오 모니터링 CLI.

사용법:
  python scripts/monitor_kakao.py            # 전체 리포트 1회
  python scripts/monitor_kakao.py --poll     # 카카오워크 미읽음 실시간 감시
  python scripts/monitor_kakao.py --export   # 카카오톡 export 파일 요약
  python scripts/monitor_kakao.py --files    # 다운로드 파일 스캔
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai_orchestrator.local_agent.desktop.desktop_agent import DesktopAgent
from ai_orchestrator.local_agent.desktop.kakaotalk_export import (
    find_export_files, parse_export_file,
)
from ai_orchestrator.local_agent.desktop.download_watcher import scan_existing
from ai_orchestrator.local_agent.desktop.classifier import classify_file

OUT_DIR = ROOT / "data" / "reports" / "local_agent"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def cmd_report():
    print("=" * 60)
    print("  카카오 전체 리포트")
    print("=" * 60)
    with DesktopAgent(watch_downloads=False) as a:
        report = a.full_report()

    # 카카오워크
    rooms = report["kakaowork_rooms"]
    unread = report["kakaowork_unread"]
    print(f"\n[카카오워크] 채팅방 {len(rooms)}개 / 미읽음 {len(unread)}개")
    for r in unread:
        print(f"  ★ {r['name']} ({r['unread_count']}건) — {r['last_msg'][:40]}")
    for r in rooms:
        if r["unread_count"] == 0:
            print(f"    {r['name']} — {r['last_msg'][:40]}")

    # 카카오톡
    print(f"\n[카카오톡] 채팅방: {report['kakaotalk_room'] or '(export 파일 없음)'}")
    print(f"  메시지 수: {report['kakaotalk_message_count']}건")
    if report["kakaotalk_summary"]:
        print(f"  요약:\n    {report['kakaotalk_summary']}")

    # 다운로드
    dl = report["recent_downloads"]
    print(f"\n[다운로드] 최근 파일 {len(dl)}개")
    for f in dl[:5]:
        print(f"  {f['type']:8s} {f['name']}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / f"kakao_report_{ts}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out}")


def cmd_poll():
    print("카카오워크 미읽음 실시간 감시 (Ctrl+C로 종료)")

    def on_unread(rooms):
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 미읽음 변화:")
        for r in rooms:
            print(f"  {r['name']} — {r['unread_count']}건 / {r['last_msg'][:50]}")

    a = DesktopAgent(watch_downloads=False)
    try:
        a.kakaowork_poll(interval=20, on_new_unread=on_unread)
    except KeyboardInterrupt:
        print("\n종료")


def cmd_export():
    print("[카카오톡 대화 내보내기]")
    files = find_export_files()
    if not files:
        print("  export 파일 없음. 카카오톡 채팅방 → 우상단 메뉴 → 대화 내보내기 실행 후 재시도")
        return
    for i, p in enumerate(files[:5]):
        print(f"  [{i}] {p}")
    path = files[0]
    print(f"\n파싱: {path.name}")
    data = parse_export_file(path)
    print(f"  채팅방: {data['room_name']}")
    print(f"  저장일: {data['saved_at']}")
    print(f"  메시지: {len(data['messages'])}건")
    for m in data["messages"][-5:]:
        print(f"  [{m['date']} {m['time']}] {m['sender']}: {m['text'][:60]}")

    if data["messages"]:
        print("\n요약 생성 중...")
        from ai_orchestrator.local_agent.desktop.summarizer import summarize_messages
        summary = summarize_messages(data["messages"][-50:])
        print(f"  {summary}")


def cmd_files():
    print("[다운로드 파일 스캔]")
    files = scan_existing()
    print(f"  총 {len(files)}개")
    for f in files[:20]:
        info = classify_file(Path(f["path"]))
        print(f"  {info['category']:8s} / {info['subcategory']:12s} → {f['name']}")


def main():
    args = sys.argv[1:]
    if "--poll" in args:
        cmd_poll()
    elif "--export" in args:
        cmd_export()
    elif "--files" in args:
        cmd_files()
    else:
        cmd_report()


if __name__ == "__main__":
    main()
