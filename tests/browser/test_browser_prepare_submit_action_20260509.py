"""
browser.prepare_submit 핸들러 테스트
"""

from ai_orchestrator.agent_hub.actions.browser_prepare_submit import execute

ACTION_NAME = "browser.prepare_submit"


def test_basic_prepare_submit():
    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        page_title="제출 폼",
        submit_selector="button.submit",
        form_summary="공고 12345 제출",
        target_id="공고 12345",
        organization_name="기관명",
        amount="100,000",
    )
    assert result["ok"] is True
    assert result["verdict"] in ("PREPARE_SUCCESS", "PREPARE_WARN")


def test_url_safe_format():
    result = execute(
        page_url="https://www.g2b.go.kr:8080/submit/form?id=123&token=abc",
        submit_selector="button.submit",
    )
    assert result["ok"] is True
    # URL은 host+path만 (query string 제외)
    assert "g2b.go.kr" in result["page_url_safe"]
    assert "?" not in result["page_url_safe"]


def test_no_submit_selector_warning():
    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        submit_selector="",
    )
    assert result["ok"] is True
    # submit_selector 없으면 WARN
    assert "warnings" in result or result["verdict"] == "PREPARE_WARN"


def test_password_in_params_blocked():
    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        form_summary="password: secret123",
        submit_selector="button.submit",
    )
    assert result["ok"] is False
    assert "BLOCKED_SENSITIVE" in result["verdict"]


def test_otp_in_params_blocked():
    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        risk_notes="otp_code: 123456",
        submit_selector="button.submit",
    )
    assert result["ok"] is False
    assert "BLOCKED_SENSITIVE" in result["verdict"]


def test_cert_password_in_params_blocked():
    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        form_summary="cert_password: mypass",
        submit_selector="button.submit",
    )
    assert result["ok"] is False
    assert "BLOCKED_SENSITIVE" in result["verdict"]


def test_attached_files_basename_only():
    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        attached_files=["/home/user/documents/bid.hwp", "C:\\Users\\John\\Downloads\\proposal.hwpx"],
        submit_selector="button.submit",
    )
    assert result["ok"] is True
    assert "bid.hwp" in result["attached_files_safe"]
    assert "proposal.hwpx" in result["attached_files_safe"]
    # Full path should not be included
    assert "/home/user" not in str(result["attached_files_safe"])


def test_no_real_submit():
    """실제 submit 클릭이 일어나지 않았는지 확인"""
    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        submit_selector="button.submit",
    )
    # 반환값이 handoff가 아니라 prepare summary
    assert "handoff_payload" not in result
    assert result["verdict"] in ("PREPARE_SUCCESS", "PREPARE_WARN")


def test_evidence_collected():
    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        submit_selector="button.submit",
    )
    assert result["ok"] is True
    assert "evidence" in result
