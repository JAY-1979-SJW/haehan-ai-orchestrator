"""보안 신호 감지 모듈 테스트"""

from __future__ import annotations

from ai_orchestrator.browser_tool.policy.security_signal_detector import (
    SIG_BID_SUBMIT,
    SIG_CAPTCHA,
    SIG_CERT_AUTH,
    SIG_E_SIGNATURE,
    SIG_HTTP_401,
    SIG_HTTP_403,
    SIG_LOGIN_REQUIRED,
    SIG_OTP,
    SIG_PAYMENT_OR_TRANSFER,
    SIG_REDIRECTED_TO_LOGIN,
    SIG_SECURITY_PROGRAM,
    classify_signals,
    detect_from_page_text,
    detect_from_result,
)


# C-1: 신호 없음 → SERVER_FIRST
def test_no_signal_server_first():
    r = detect_from_page_text(title="공고 목록", body_text="나라장터 공고 조회")
    assert r["has_security_signal"] is False
    assert r["recommended_execution"] == "SERVER_FIRST"
    assert r["fallback_allowed"] is True


# C-2: HTTP 401 → login_required LOCAL
def test_http_401_signal():
    r = detect_from_page_text(http_status=401)
    assert SIG_HTTP_401 in r["signals"]
    assert r["recommended_execution"] == "LOCAL_REQUIRED"


# C-3: HTTP 403
def test_http_403_signal():
    r = detect_from_page_text(http_status=403)
    assert SIG_HTTP_403 in r["signals"]


# C-4: 로그인 텍스트
def test_login_text_detected():
    r = detect_from_page_text(body_text="로그인이 필요합니다")
    assert SIG_LOGIN_REQUIRED in r["signals"]


# C-5: 인증서 텍스트
def test_cert_text_detected():
    r = detect_from_page_text(body_text="공인인증서로 로그인하세요")
    assert SIG_CERT_AUTH in r["signals"]


# C-6: OTP 텍스트
def test_otp_text_detected():
    r = detect_from_page_text(body_text="OTP 번호를 입력하세요")
    assert SIG_OTP in r["signals"]
    assert r["recommended_execution"] == "USER_DIRECT_ONLY"


# C-7: captcha 텍스트
def test_captcha_detected():
    r = detect_from_page_text(body_text="자동입력 방지 문자를 입력하세요")
    assert SIG_CAPTCHA in r["signals"]


# C-8: 보안프로그램
def test_security_program_detected():
    r = detect_from_page_text(body_text="보안프로그램을 설치해야 합니다")
    assert SIG_SECURITY_PROGRAM in r["signals"]


# C-9: URL login 리다이렉트
def test_url_login_redirect():
    r = detect_from_page_text(url="https://www.g2b.go.kr/login?redirect=/notice")
    assert SIG_REDIRECTED_TO_LOGIN in r["signals"]


# C-10: 투찰 텍스트
def test_bid_submit_detected():
    r = detect_from_page_text(body_text="입찰서 제출을 진행합니다")
    assert SIG_BID_SUBMIT in r["signals"]
    assert r["recommended_execution"] == "USER_DIRECT_ONLY"


# C-11: 전자서명
def test_e_signature_detected():
    r = detect_from_page_text(body_text="전자서명을 해주세요")
    assert SIG_E_SIGNATURE in r["signals"]


# C-12: 결제
def test_payment_detected():
    r = detect_from_page_text(body_text="결제를 진행합니다")
    assert SIG_PAYMENT_OR_TRANSFER in r["signals"]


# C-13: detect_from_result - 민감값 읽지 않음
def test_detect_from_result_no_sensitive_read():
    result = {
        "title": "로그인",
        "body_text_sample": "인증서를 사용해주세요",
        "final_url": "https://www.g2b.go.kr",
        "http_status": 200,
        "password": "secret123",  # 읽지 않음
        "cookie": "sess=abc",  # 읽지 않음
    }
    r = detect_from_result(result)
    assert r["has_security_signal"] is True
    # password/cookie 값이 signals에 포함되지 않음
    for sig in r["signals"]:
        assert "secret" not in sig
        assert "sess=" not in sig


# C-14: classify_signals
def test_classify_signals_priority():
    signals = [SIG_LOGIN_REQUIRED, SIG_OTP]
    r = classify_signals(signals)
    # OTP는 USER_DIRECT_ONLY (우선순위 높음)
    assert r["recommended_execution"] == "USER_DIRECT_ONLY"


# C-15: 빈 신호 목록
def test_classify_empty_signals():
    r = classify_signals([])
    assert r["has_security_signal"] is False
    assert r["recommended_execution"] == "SERVER_FIRST"
