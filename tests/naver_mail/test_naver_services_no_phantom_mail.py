"""NaverServices 에서 없는 NaverMail 을 지연 import 하던 `mail` 속성을 없앴다.

scripts.naver.mail 은 읽기전용 수집·분석 패키지라 NaverMail(발송·목록 클래스)이 존재한 적이 없다 — 예전엔 `NaverServices(page).mail`
접근이 ImportError 로 죽었다(defect_index #38 과 같은 계열). 이 시험은 그 유령 속성이 다시 생기지 않는지와,
알림 워크플로의 메일 항목이 '미구현'을 명확한 결과로 돌려주는지를 고정한다.
"""

from __future__ import annotations

from pathlib import Path

from scripts.naver.services import NaverServices

REPO = Path(__file__).resolve().parents[2]


def test_naver_services_has_no_mail_property():
    assert not hasattr(NaverServices, "mail")


def test_no_source_imports_the_missing_naver_mail_class():
    hits = [
        str(p.relative_to(REPO))
        for root in ("scripts", "ai_orchestrator")
        for p in (REPO / root).rglob("*.py")
        if "archive" not in p.parts
        and "from scripts.naver.mail import NaverMail" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not hits, hits


def test_workflow_mail_alert_reports_not_implemented():
    src = (REPO / "scripts" / "naver" / "workflow.py").read_text(encoding="utf-8")
    assert "self.n.mail" not in src
    assert '"naver_mail_send_not_implemented"' in src
