"""데스크 앱 검증 스크립트 — WebSocket 메뉴/연결 상태 확인."""
import asyncio
import json
import sys


async def test_menu():
    import websockets  # type: ignore

    uri = "ws://127.0.0.1:8765/ws/ui"
    print(f"[1] WebSocket 연결 시도: {uri}")
    try:
        async with websockets.connect(uri) as ws:
            print("[1] ✅ WebSocket 연결 성공")

            # 메뉴 요청
            await ws.send(json.dumps({"action": "load_menu", "user_id": "default", "role": "admin"}))
            resp = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(resp)

            items = data.get("items", [])
            sections: dict = {}
            for item in items:
                sec = item.get("section", "?")
                sections.setdefault(sec, []).append(item["id"])

            print(f"\n[2] 메뉴 로드 결과 — 총 {len(items)}개")
            required_sections = {"AI 대화", "업무 조회", "관리 웹", "시스템"}
            for sec, ids in sections.items():
                mark = "✅" if sec in required_sections else "⚠️"
                print(f"  {mark} [{sec}] {ids}")

            missing = required_sections - set(sections.keys())
            if missing:
                print(f"\n[FAIL] 누락된 섹션: {missing}")
                return False

            # 관리 웹 항목 검증
            admin_web_ids = {"admin_dashboard", "admin_ops", "admin_approvals", "admin_agents"}
            present_ids = {item["id"] for item in items}
            missing_admin = admin_web_ids - present_ids
            if missing_admin:
                print(f"\n[FAIL] 관리 웹 누락 항목: {missing_admin}")
                return False

            print("\n[3] ✅ 모든 섹션 및 관리 웹 항목 정상 확인")
            return True

    except Exception as e:
        print(f"[FAIL] {e}")
        return False


async def test_static():
    import urllib.request
    print("\n[4] HTTP index.html 응답 확인")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/", timeout=5) as r:
            body = r.read().decode()
            if "Haehan AI" in body:
                print("[4] ✅ index.html 정상 (Haehan AI 타이틀 확인)")
                return True
            else:
                print(f"[4] ⚠️ 응답 내용 예상과 다름: {body[:100]}")
                return False
    except Exception as e:
        print(f"[4] [FAIL] {e}")
        return False


async def main():
    r1 = await test_menu()
    r2 = await test_static()
    print("\n" + ("=" * 40))
    if r1 and r2:
        print("최종 판정: ✅ PASS — 데스크 앱 정상")
    else:
        print("최종 판정: ❌ FAIL — 위 항목 확인 필요")
        sys.exit(1)


asyncio.run(main())
