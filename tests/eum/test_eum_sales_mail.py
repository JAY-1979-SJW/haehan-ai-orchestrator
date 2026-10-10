import json
from datetime import date

from scripts.eum.sales_mail import normalize_project, prepare_sales_mail, score_project


def _row(**overrides):
    row = {
        "공사번호": "901793",
        "공제가입번호": "26-03010-2605",
        "공사명": "테스트 전자카드 현장",
        "현장주소": "인천광역시 테스트로 1",
        "업체명": "테스트건설",
        "설치예정일": "2026-05-20",
        "설치예정대수": "1",
        "관할지사": "인천",
        "담당자": "홍길동",
        "연락처": "02-1234-5678",
        "이메일": "sales@example.com",
        "등록일": "2026-05-01",
        "공사시작일": "2026-05-01",
        "공사종료일": "2027-05-31",
    }
    row.update(overrides)
    return row


def test_normalize_project_maps_eum_korean_fields():
    project = normalize_project(_row())

    assert project["project_no"] == "901793"
    assert project["project_name"] == "테스트 전자카드 현장"
    assert project["email"] == "sales@example.com"
    assert project["branch"] == "인천"


def test_score_project_prioritizes_urgent_long_running_site():
    project = normalize_project(_row())

    score, grade, reasons = score_project(project, today=date(2026, 5, 12))

    assert grade == "A"
    assert score >= 80
    assert "30일 이내 설치 예정" in reasons
    assert "수도권 관할" in reasons


def test_prepare_sales_mail_writes_targets_drafts_and_queue(tmp_path):
    source = tmp_path / "new_sites.json"
    source.write_text(
        json.dumps({"projects": [_row(), _row(이메일="bad-email")]}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = prepare_sales_mail(
        source=source,
        output_dir=tmp_path,
        limit=10,
        min_grade="A",
        today=date(2026, 5, 12),
    )

    assert result["selected_targets"] == 1
    assert result["send_status"] == "not_sent_prepare_only"
    assert (tmp_path / "eum_sales_mail_targets_latest.json").exists()
    assert (tmp_path / "eum_sales_mail_drafts_latest.txt").exists()
    assert (tmp_path / "eum_sales_mail_queue_latest.jsonl").exists()

    queue_line = (tmp_path / "eum_sales_mail_queue_latest.jsonl").read_text(encoding="utf-8").strip()
    queued = json.loads(queue_line)
    assert queued["status"] == "pending"
    assert queued["provider"] == "company_mail"
    assert queued["to"] == "sales@example.com"
