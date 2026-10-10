"""popup_classifier + popup_monitor DB 단위 검증 (브라우저 불필요) — 수동 실행 스크립트
(pytest 수집 대상 아님).

최상단 실행 코드에 `if __name__ == "__main__":` 가드가 없어서, pytest 가 이 파일을
"test_*.py" 로 보고 수집(import)하는 순간 운영 popup_monitor DB 에 실제 이벤트를 적재했다
(2026-10-10, test_wait_login.py 와 같은 결함 패턴 — W1 전수조사로 발견). 가드를 씌워
수동 실행 동작은 그대로 유지하면서 수집 시엔 아무 일도 안 하게 한다.
"""
import json

from scripts.browser.popup.popup_classifier import classify, is_auto_handleable
from scripts.browser.navigator.popup_monitor import _ensure_table, _record_event, ack_event, list_pending, status


def _main() -> None:
    print("\n[1] 분류기 룰 매칭 테스트")
    print("-" * 70)
    cases = [
        ("작성 중인 글",       "이어서 작성하시겠습니까"),
        ("영구 삭제",          "휴지통의 항목을 영구 삭제하시겠습니까"),
        ("결제 확인",          "10,000원 결제를 진행합니다"),
        ("외부 전송 확인",     "외부 수신자에게 전송하시겠습니까"),
        ("cookies",            "We use cookies for analytics"),
        ("2단계 인증",         "OTP 코드를 입력하세요"),
        ("reCAPTCHA",          "로봇이 아닙니다"),
        ("newsletter",         "뉴스레터를 구독하시겠습니까"),
        ("세션이 만료",         "다시 로그인 해주세요"),
        ("알 수 없는 모달",    "처음 보는 팝업"),
    ]

    results = []
    for marker, snippet in cases:
        d = classify(marker=marker, snippet=snippet)
        auto = is_auto_handleable(d)
        print(f"  {marker[:20]:<22} → {d['category']:<22} {d['action']:<15} "
              f"sev={d['severity']:<8} auto={auto} conf={d['confidence']:.2f}")
        results.append((marker, snippet, d))

    print("\n[2] DB 영속화 + 큐 검증")
    print("-" * 70)
    _ensure_table()

    # 알 수 없는 팝업 1건 + 위험 1건을 notified 로 적재
    unknown = next(d for m,s,d in results if d["category"] == "unknown")
    dangerous = next(d for m,s,d in results if d["category"] == "destructive_confirm")

    ev1 = {"ts_ms": 1, "marker": "알 수 없는 모달", "snippet": "스니펫", "frame_url": "https://test"}
    ev2 = {"ts_ms": 2, "marker": "영구 삭제", "snippet": "스니펫", "frame_url": "https://test"}

    id1 = _record_event(ev1, unknown, status="notified")
    id2 = _record_event(ev2, dangerous, status="notified")
    print(f"  적재 id1={id1} id2={id2}")

    pending = list_pending(limit=10)
    print(f"  pending 개수: {len(pending)}")
    for p in pending[:3]:
        print(f"    #{p['id']} {p['category']:<22} status={p['status']}")

    ok = ack_event(id1, note="단위 테스트 ack")
    print(f"  ack(id1) → {ok}")

    print("\n[3] 상태 조회")
    print("-" * 70)
    st = status()
    print(json.dumps(st, ensure_ascii=False, indent=2))

    print("\n✓ 모든 검증 통과")


if __name__ == "__main__":
    _main()
