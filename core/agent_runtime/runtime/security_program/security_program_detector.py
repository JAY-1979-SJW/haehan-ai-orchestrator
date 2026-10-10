"""Security Program Detector — 현재 페이지에서 보안프로그램 설치 필요 신호를 감지한다."""
from __future__ import annotations

from typing import Any

# 감지 신호 상수
SIGNAL_SECURITY_PROGRAM_REQUIRED = "SECURITY_PROGRAM_REQUIRED"
SIGNAL_KEYBOARD_SECURITY_REQUIRED = "KEYBOARD_SECURITY_REQUIRED"
SIGNAL_CERT_MODULE_REQUIRED = "CERT_MODULE_REQUIRED"
SIGNAL_E_SIGNATURE_MODULE_REQUIRED = "E_SIGNATURE_MODULE_REQUIRED"
SIGNAL_BROWSER_EXTENSION_REQUIRED = "BROWSER_EXTENSION_REQUIRED"
SIGNAL_INSTALL_GUIDE_PAGE_DETECTED = "INSTALL_GUIDE_PAGE_DETECTED"
SIGNAL_INSTALL_COMPLETE_RETRY_REQUIRED = "INSTALL_COMPLETE_RETRY_REQUIRED"
SIGNAL_UNSUPPORTED_BROWSER = "UNSUPPORTED_BROWSER"
SIGNAL_ADMIN_PERMISSION_REQUIRED = "ADMIN_PERMISSION_REQUIRED"

# 키워드 맵 — 신호 → 감지 키워드 목록
_SIGNAL_KEYWORDS: dict[str, list[str]] = {
    SIGNAL_SECURITY_PROGRAM_REQUIRED: [
        "보안프로그램", "보안 프로그램", "보안모듈", "보안 모듈",
        "보안솔루션", "보안 솔루션", "안전결제", "안전 결제",
        "security program", "security module", "보안설치",
        "인터넷뱅킹 이용을 위해", "이용하시려면 설치",
    ],
    SIGNAL_KEYBOARD_SECURITY_REQUIRED: [
        "키보드보안", "키보드 보안", "키보드보안프로그램",
        "keyboard security", "키보드 암호화", "키로거 방지",
        "nProtect", "TouchEn", "AhnLab Safe Transaction",
    ],
    SIGNAL_CERT_MODULE_REQUIRED: [
        "공동인증서", "공인인증서", "인증서 모듈", "공동인증 모듈",
        "전자인증", "NPKI", "공인인증", "인증서 설치",
        "CrossCert", "SignKorea", "KICA", "yessign",
    ],
    SIGNAL_E_SIGNATURE_MODULE_REQUIRED: [
        "전자서명", "전자서명 모듈", "전자서명 프로그램",
        "e-signature", "디지털서명", "서명모듈",
    ],
    SIGNAL_BROWSER_EXTENSION_REQUIRED: [
        "브라우저 확장", "확장 프로그램 설치", "플러그인 설치",
        "extension", "browser plugin", "브라우저 플러그인",
    ],
    SIGNAL_INSTALL_GUIDE_PAGE_DETECTED: [
        "설치 안내", "설치안내", "프로그램 설치", "설치 방법",
        "install guide", "설치 페이지", "설치가이드",
        "다운로드 후 설치", "설치 후 다시",
    ],
    SIGNAL_INSTALL_COMPLETE_RETRY_REQUIRED: [
        "설치 후 새로고침", "설치 완료 후", "설치 후 재시도",
        "설치하신 후", "설치 완료 후 다시", "refresh after install",
        "설치 후 다시 접속", "설치 완료 후 로그인",
    ],
    SIGNAL_UNSUPPORTED_BROWSER: [
        "지원하지 않는 브라우저", "브라우저를 지원하지", "익스플로러",
        "Internet Explorer", "IE 전용", "크롬에서 이용",
        "Edge 브라우저", "지원 브라우저",
    ],
    SIGNAL_ADMIN_PERMISSION_REQUIRED: [
        "관리자 권한", "관리자로 실행", "administrator",
        "UAC", "사용자 계정 컨트롤", "권한 상승",
        "Run as administrator",
    ],
}

# 보안 관련 사이트 도메인 패턴
_SECURITY_SITE_PATTERNS = (
    "go.kr", "gov.kr", "bank", "card", "insurance",
    "hometax", "g2b", "보험", "세무", "협회",
)


def detect_security_signals(page_data: dict[str, Any]) -> dict[str, Any]:
    """
    페이지 데이터에서 보안프로그램 관련 신호를 감지한다.

    Returns:
        {
            "signals": list[str],           # 감지된 신호 목록
            "signal_count": int,
            "requires_security_program": bool,
            "requires_user_action": bool,   # USER_DIRECT 수준 필요 여부
            "is_security_site": bool,
            "install_candidates_hint": list[str],  # 설치 링크 힌트
            "server_browser_used": False,
        }
    """
    text = _extract_text(page_data)
    url = page_data.get("url", "")
    links = page_data.get("links", [])
    buttons = page_data.get("buttons", [])
    headings = page_data.get("heading_texts", [])

    combined = " ".join([text] + list(buttons) + list(headings)).lower()

    signals: list[str] = []
    for signal, keywords in _SIGNAL_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in combined:
                if signal not in signals:
                    signals.append(signal)
                break

    # 설치 링크 힌트 수집 (exe/msi/dmg/pkg)
    install_hints = [
        lnk for lnk in links
        if any(lnk.lower().endswith(ext) for ext in (".exe", ".msi", ".dmg", ".pkg", ".zip"))
    ]

    is_security_site = any(p in url for p in _SECURITY_SITE_PATTERNS)

    requires_security_program = bool(signals) or is_security_site
    requires_user_action = (
        SIGNAL_ADMIN_PERMISSION_REQUIRED in signals
        or SIGNAL_CERT_MODULE_REQUIRED in signals
        or SIGNAL_E_SIGNATURE_MODULE_REQUIRED in signals
    )

    return {
        "signals": signals,
        "signal_count": len(signals),
        "requires_security_program": requires_security_program,
        "requires_user_action": requires_user_action,
        "is_security_site": is_security_site,
        "install_candidates_hint": install_hints,
        "server_browser_used": False,
    }


def is_install_guide_page(page_data: dict[str, Any]) -> bool:
    """현재 페이지가 설치 안내 페이지인지 확인."""
    result = detect_security_signals(page_data)
    return SIGNAL_INSTALL_GUIDE_PAGE_DETECTED in result["signals"]


def needs_retry_after_install(page_data: dict[str, Any]) -> bool:
    """설치 완료 후 재시도가 필요한지 확인."""
    result = detect_security_signals(page_data)
    return SIGNAL_INSTALL_COMPLETE_RETRY_REQUIRED in result["signals"]


def get_signal_grade(signal: str) -> str:
    """신호별 실행 등급 반환."""
    if signal in (SIGNAL_ADMIN_PERMISSION_REQUIRED,):
        return "USER_DIRECT_REQUIRED"
    if signal in (
        SIGNAL_SECURITY_PROGRAM_REQUIRED,
        SIGNAL_KEYBOARD_SECURITY_REQUIRED,
        SIGNAL_CERT_MODULE_REQUIRED,
        SIGNAL_E_SIGNATURE_MODULE_REQUIRED,
        SIGNAL_BROWSER_EXTENSION_REQUIRED,
    ):
        return "USER_DELEGATED_PERMISSION_REQUIRED"
    if signal in (
        SIGNAL_INSTALL_GUIDE_PAGE_DETECTED,
        SIGNAL_INSTALL_COMPLETE_RETRY_REQUIRED,
        SIGNAL_UNSUPPORTED_BROWSER,
    ):
        return "AUTO_ALLOWED"
    return "AUTO_ALLOWED"


def _extract_text(page_data: dict[str, Any]) -> str:
    parts = [
        page_data.get("title", ""),
        page_data.get("text_content", ""),
    ]
    return " ".join(str(p) for p in parts if p)
