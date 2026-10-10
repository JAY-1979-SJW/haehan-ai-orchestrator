"""tests/test_security_program_detector_20260508.py"""

from core.agent_runtime.runtime.security_program.security_program_detector import (
    SIGNAL_ADMIN_PERMISSION_REQUIRED,
    SIGNAL_CERT_MODULE_REQUIRED,
    SIGNAL_INSTALL_GUIDE_PAGE_DETECTED,
    SIGNAL_KEYBOARD_SECURITY_REQUIRED,
    SIGNAL_SECURITY_PROGRAM_REQUIRED,
    detect_security_signals,
    get_signal_grade,
    is_install_guide_page,
    needs_retry_after_install,
)

_CLEAN_PAGE = {
    "url": "https://example.com/",
    "title": "일반 사이트",
    "text_content": "일반 콘텐츠 페이지입니다.",
    "buttons": [],
    "links": [],
    "form_labels": [],
    "heading_texts": [],
}

_SECURITY_PAGE = {
    "url": "https://bank.example.com/login",
    "title": "인터넷뱅킹 로그인",
    "text_content": "보안프로그램 설치가 필요합니다. 키보드보안 프로그램을 설치해 주세요.",
    "buttons": ["설치", "확인"],
    "links": ["setup.exe"],
    "form_labels": [],
    "heading_texts": ["보안 설치"],
}

_KEYBOARD_PAGE = {
    "url": "https://card.example.com/",
    "title": "카드사",
    "text_content": "키보드보안 프로그램을 설치해주세요. TouchEn nProtect",
    "buttons": ["설치"],
    "links": [],
    "form_labels": [],
    "heading_texts": [],
}

_CERT_PAGE = {
    "url": "https://tax.go.kr/",
    "title": "홈택스",
    "text_content": "공동인증서 모듈을 설치하세요. NPKI 인증서 설치",
    "buttons": ["설치"],
    "links": [],
    "form_labels": [],
    "heading_texts": [],
}

_INSTALL_GUIDE_PAGE = {
    "url": "https://bank.example.com/install",
    "title": "설치 안내",
    "text_content": "설치 안내 페이지입니다. 다운로드 후 설치 하세요.",
    "buttons": ["다운로드"],
    "links": ["setup.exe"],
    "form_labels": [],
    "heading_texts": ["설치가이드"],
}

_RETRY_PAGE = {
    "url": "https://bank.example.com/",
    "title": "설치 완료",
    "text_content": "설치 완료 후 다시 접속해 주세요. 설치 후 새로고침 하세요.",
    "buttons": ["새로고침"],
    "links": [],
    "form_labels": [],
    "heading_texts": [],
}


def test_clean_page_no_signals():
    r = detect_security_signals(_CLEAN_PAGE)
    # 일반 페이지는 신호 없거나 최소
    assert r["server_browser_used"] is False


def test_security_program_required_detected():
    r = detect_security_signals(_SECURITY_PAGE)
    assert SIGNAL_SECURITY_PROGRAM_REQUIRED in r["signals"]


def test_keyboard_security_required_detected():
    r = detect_security_signals(_KEYBOARD_PAGE)
    assert SIGNAL_KEYBOARD_SECURITY_REQUIRED in r["signals"]


def test_cert_module_required_detected():
    r = detect_security_signals(_CERT_PAGE)
    assert SIGNAL_CERT_MODULE_REQUIRED in r["signals"]


def test_install_guide_page_detected():
    r = detect_security_signals(_INSTALL_GUIDE_PAGE)
    assert SIGNAL_INSTALL_GUIDE_PAGE_DETECTED in r["signals"]


def test_is_install_guide_page():
    assert is_install_guide_page(_INSTALL_GUIDE_PAGE) is True


def test_is_not_install_guide_page():
    assert is_install_guide_page(_CLEAN_PAGE) is False


def test_needs_retry_after_install():
    assert needs_retry_after_install(_RETRY_PAGE) is True


def test_no_retry_needed():
    assert needs_retry_after_install(_CLEAN_PAGE) is False


def test_server_browser_used_always_false():
    r = detect_security_signals(_SECURITY_PAGE)
    assert r["server_browser_used"] is False


def test_security_site_domain_detected():
    page = {**_CLEAN_PAGE, "url": "https://mybank.co.kr/"}
    r = detect_security_signals(page)
    assert r["is_security_site"] is True


def test_install_hints_collected():
    r = detect_security_signals(_SECURITY_PAGE)
    assert "setup.exe" in r["install_candidates_hint"]


def test_get_signal_grade_admin():
    assert get_signal_grade(SIGNAL_ADMIN_PERMISSION_REQUIRED) == "USER_DIRECT_REQUIRED"


def test_get_signal_grade_security():
    assert get_signal_grade(SIGNAL_SECURITY_PROGRAM_REQUIRED) == "USER_DELEGATED_PERMISSION_REQUIRED"


def test_get_signal_grade_install_guide():
    assert get_signal_grade(SIGNAL_INSTALL_GUIDE_PAGE_DETECTED) == "AUTO_ALLOWED"
