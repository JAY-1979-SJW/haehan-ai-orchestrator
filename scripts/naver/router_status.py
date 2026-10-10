"""네이버 라우터 작업 상태 표(__status__) — router.py 가 재노출한다.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

__status__ = {
    "tasks": {
        "blog write": "done",
        "blog publish": "done",
        # 2026-09-29 정정(defect_index #38): 이 CLI 라우터의 "mail" 분기는 mail.run()
        # 을 호출하는데 그 함수 자체가 존재한 적이 없음(scripts/naver/mail/ 은 발송/답장을
        # 모듈 차원에서 금지하는 읽기전용 패키지로 재구성됨). 실제 메일 조회/조작은
        # ai_orchestrator/connectors/naver_mail/naver_mail_router.py(API)로만 가능.
        "mail inbox": "not_implemented_cli",
        "mail compose": "not_implemented",
        "mail send": "not_implemented",
        "content explore": "done",
        "content actions": "done",
        "company seo": "done",
        "developers entrypoints": "done",
        "shopping competitors": "done",
        "keyword tools": "done",
        "excel report": "done",
        "cafe list": "done",
        "cafe write": "done",
        "calendar list/add": "done",
        "mybox list/search/upload": "done",
        "pay orders/points": "done",
        "talk list/send": "done",
        "place list/reviews": "done",
        "smartstore alias": "done",
        "service catalog": "done",
        "login": "done",
        "session-check": "done",
    },
    "note": "블로그 글쓰기·발행 완성. 메일은 API 라우터(naver_mail_router.py)만 구현됨 —"
    " 이 CLI 라우터의 mail 분기는 미구현(2026-09-29 정정).",
}
