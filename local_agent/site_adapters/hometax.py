"""F-4C — 홈택스 site adapter skeleton.

본 모듈은 **page classifier 와 download plan 빌더만** 제공한다. 실제
브라우저 클릭/입력/제출 자동화는 본 단계에 포함되지 않는다. 분류 함수는
``local_agent.browser_observer`` 가 수집한 ``title`` / ``final_url`` /
``text_excerpt`` 같은 read-only 신호를 받아 다음 페이지 분류를 반환한다:

  - "login_required"           — 로그인 진입 화면
  - "authenticated"            — 로그인 후 메인/마이홈택스 화면
  - "download_page"            — 자료 다운로드 메뉴 화면
  - "sensitive_submission"     — 신고/납부/발행 같은 차단 대상 화면
  - "unknown"                  — 위 어디에도 매칭 안 됨

Trusted automation 정책 (``trusted_browser_policy``) 과 함께:
  - 분류 결과 ``sensitive_submission`` 은 자동 진행을 차단한다.
  - 분류 결과 ``login_required`` 는 ``trusted_login`` action 으로
    secret_id 기반 로그인 시도 (구현은 후속 단계).
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


# ─── 분류 키워드 ─────────────────────────────────────────────────────────

_LOGIN_TOKENS: tuple[str, ...] = (
    "공동인증서", "공인인증서", "간편인증", "금융인증서",
    "아이디 로그인", "회원가입",
    "sign in", "signin",
)

# 로그인 후 메인/마이홈택스 화면 식별 토큰.
_AUTH_TOKENS: tuple[str, ...] = (
    "마이홈택스", "my홈택스",
    "납세자정보", "기본정보",
    "로그아웃", "logout", "sign out",
)

# 다운로드 페이지 식별 토큰. 메인/마이홈택스 페이지에서 흔히 보이는
# 일반 단어("조회") 는 제외해 우선순위 충돌을 피한다.
_DOWNLOAD_TOKENS: tuple[str, ...] = (
    "내려받기", "다운로드", "엑셀 다운로드",
    "전자세금계산서 합계", "현금영수증 내역",
    "발급내역 조회", "수취내역 조회",
    ".csv", ".xls", ".xlsx",
)

# 신고/납부/발행 등 차단 대상 토큰 — 매우 보수적으로 잡는다.
# 메인 페이지 메뉴 카탈로그에 흔한 단독 단어("납부", "결제", "전송",
# "위임", "수임", "발급", "발행", "신고") 만으로는 sensitive_submission 으로
# 잡지 않는다. 실제 위험한 동작 맥락(동사 결합/제출/이체/발행하기 등) 일
# 때만 sensitive_submission 판정.
_SENSITIVE_TOKENS: tuple[str, ...] = (
    # 제출 계열 — 신고서 최종 제출 단계.
    "신고서 제출", "신고 제출", "최종 제출", "제출하기",
    "확인 후 제출", "최종 확인",
    # 납부/결제/이체 계열 — 자금 이동 동사 결합형.
    "납부하기", "전자납부", "계좌이체", "결제하기", "이체",
    # 발행/발급 계열 — 동사 결합형 (단독 "발행"/"발급" 은 제외).
    "발행하기",
    "세금계산서 발행", "세금계산서 발급", "전자세금계산서 발급",
    "전자세금계산서 발행", "현금영수증 발행",
    # 권한/정보 변경 — 사업자/위임 변경 같은 명시적 변경 액션.
    "사업자정보 변경", "사업자등록정보 변경", "권한 변경",
    "위임/수임 변경", "위임 변경", "수임 변경",
    # 전송 — 단독 "전송" 은 제외하고 동사 결합형/최종전송만.
    "최종전송", "전송하기",
)

_HOMETAX_HOST_SUFFIXES: tuple[str, ...] = (
    "hometax.go.kr",
)

# 홈택스 메인(랜딩) 페이지 식별. title 또는 URL path 가 메인 성격이면
# sensitive_submission 검사를 건너뛴다 — 메인은 신고/납부/발급/발행 단어가
# 메뉴 카탈로그로 다수 노출되지만 사용자가 어떤 동작도 시작하지 않은 상태.
_HOMETAX_MAIN_TITLE_TOKENS: tuple[str, ...] = (
    "홈택스 - 메인", "홈택스-메인", "홈택스 메인",
    "국세청 홈택스 - 메인",
)
_HOMETAX_MAIN_PATH_TOKENS: tuple[str, ...] = (
    "/index", "/websquare/websquare.html", "/main",
)


# ─── 외부 API ────────────────────────────────────────────────────────────

def is_hometax_host(url_or_host: str) -> bool:
    """주어진 URL/호스트가 홈택스 도메인인지."""
    host = _extract_host(url_or_host)
    if not host:
        return False
    for suffix in _HOMETAX_HOST_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            return True
    return False


def classify_hometax_page(
    title: str = "",
    url: str = "",
    text: str = "",
) -> str:
    """홈택스 페이지 분류 (정책 우선순위).

    우선순위:
      0) 메인(랜딩) 페이지         — sensitive_submission 으로 잡지 않는다
      1) sensitive_submission     — 강한 신호 토큰 (제출/이체/발행하기 등)
      2) download_page            — 명시적 다운로드 토큰 (페이지 목적이 분명)
      3) login_required           — 인증서/간편인증/sign in 토큰
      4) authenticated            — 마이홈택스/로그아웃 토큰
      5) unknown                  — 그 외

    메인 페이지 가드: title 이 "홈택스 - 메인" 류이거나 URL path 가 메인
    형식이면 sensitive_submission 검사를 건너뛴다. 메인은 신고/납부/발급/
    발행 단어가 메뉴 카탈로그로 다수 노출되지만 사용자가 어떤 위험 동작도
    시작하지 않은 상태이기 때문이다.
    """
    title_l = (title or "").lower()
    url_l = (url or "").lower()
    text_l = (text or "").lower()
    blob = " ".join([title_l, url_l, text_l])

    is_main = _looks_like_hometax_main(title_l, url_l)

    if not is_main and _has_any_token(blob, _SENSITIVE_TOKENS):
        return "sensitive_submission"
    if _has_any_token(blob, _DOWNLOAD_TOKENS):
        return "download_page"
    if _has_any_token(blob, _LOGIN_TOKENS):
        return "login_required"
    if _has_any_token(blob, _AUTH_TOKENS):
        return "authenticated"
    return "unknown"


def _looks_like_hometax_main(title_l: str, url_l: str) -> bool:
    """홈택스 메인(랜딩) 페이지 신호. title 또는 URL path 둘 중 하나면 True."""
    for t in _HOMETAX_MAIN_TITLE_TOKENS:
        if t and t.lower() in title_l:
            return True
    if url_l:
        try:
            parsed = urlparse(url_l)
        except Exception:  # noqa: BLE001
            parsed = None
        host = (parsed.hostname or "").lower() if parsed else ""
        path = (parsed.path or "").lower() if parsed else ""
        if host and any(host == s or host.endswith("." + s)
                        for s in _HOMETAX_HOST_SUFFIXES):
            # 정확히 루트(/) 이거나 메인 path 토큰을 포함.
            if path in ("", "/"):
                return True
            for p in _HOMETAX_MAIN_PATH_TOKENS:
                if p and p in path:
                    return True
    return False


def is_hometax_login_required(
    title: str = "", url: str = "", text: str = "",
) -> bool:
    return classify_hometax_page(title, url, text) == "login_required"


def is_hometax_authenticated(
    title: str = "", url: str = "", text: str = "",
) -> bool:
    return classify_hometax_page(title, url, text) == "authenticated"


def is_hometax_download_page(
    title: str = "", url: str = "", text: str = "",
) -> bool:
    return classify_hometax_page(title, url, text) == "download_page"


def is_hometax_sensitive_submission(
    title: str = "", url: str = "", text: str = "",
) -> bool:
    return classify_hometax_page(title, url, text) == "sensitive_submission"


# ─── download plan ──────────────────────────────────────────────────────

# 사용자 지시문에서 정의한 download_type 후보.
DOWNLOAD_TYPES: tuple[str, ...] = (
    "tax_invoice_sales",        # 매출 (전자)세금계산서
    "tax_invoice_purchases",    # 매입 (전자)세금계산서
    "cash_receipt_sales",       # 매출 현금영수증
    "cash_receipt_purchases",   # 매입 현금영수증
    "vat_reference_docs",       # 부가세 참고/증빙
    "withholding_docs",         # 원천징수 자료
)


def build_hometax_download_plan(
    download_type: str,
    period: str,
    output_folder: str,
) -> dict[str, Any]:
    """홈택스 다운로드 plan 메타데이터를 만든다 (실행은 본 단계에 없음).

    검증:
      - download_type 은 ``DOWNLOAD_TYPES`` 안.
      - period 는 비어있지 않은 str.
      - output_folder 는 비어있지 않은 str (실제 폴더 검증은
        ``trusted_browser_policy.validate_trusted_automation_request``
        가 담당).

    반환:
      {
        "ok": bool, "error_code": str, "warnings": [str, ...],
        "site_key": "hometax",
        "download_type": str,
        "period": str,
        "output_folder": str,
        "requires_user_presence": bool,
      }
    """
    if download_type not in DOWNLOAD_TYPES:
        return _err(
            "INVALID_DOWNLOAD_TYPE",
            site_key="hometax",
            download_type=download_type or "",
            period=period or "",
            output_folder=output_folder or "",
        )
    if not isinstance(period, str) or not period.strip():
        return _err(
            "MISSING_PERIOD",
            site_key="hometax",
            download_type=download_type,
            period="",
            output_folder=output_folder or "",
        )
    if not isinstance(output_folder, str) or not output_folder.strip():
        return _err(
            "MISSING_OUTPUT_FOLDER",
            site_key="hometax",
            download_type=download_type,
            period=period,
            output_folder="",
        )

    # withholding_docs 는 첫 다운로드 시 흐름이 다양해 사용자 화면 확인 권장.
    requires_presence = download_type == "withholding_docs"

    return {
        "ok": True,
        "error_code": "",
        "warnings": [],
        "site_key": "hometax",
        "download_type": download_type,
        "period": period,
        "output_folder": output_folder,
        "requires_user_presence": bool(requires_presence),
    }


# ─── helpers ─────────────────────────────────────────────────────────────

def _has_any_token(haystack: str, tokens: tuple[str, ...]) -> bool:
    if not haystack:
        return False
    for t in tokens:
        if not t:
            continue
        if t.lower() in haystack:
            return True
    return False


def _extract_host(url_or_host: Any) -> str:
    if not isinstance(url_or_host, str):
        return ""
    s = url_or_host.strip()
    if not s:
        return ""
    if "://" in s:
        try:
            parsed = urlparse(s)
        except Exception:  # noqa: BLE001
            return ""
        # http(s) 만 허용 — ftp/javascript 등은 host 자체를 노출하지 않는다.
        if (parsed.scheme or "").lower() not in ("http", "https"):
            return ""
        return (parsed.hostname or "").lower()
    if "/" in s or " " in s:
        return ""
    return s.lower()


def _err(code: str, **fields: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": False,
        "error_code": code,
        "warnings": [code.lower()],
    }
    out.update(fields)
    out.setdefault("requires_user_presence", False)
    return out


__all__ = [
    "DOWNLOAD_TYPES",
    "is_hometax_host",
    "classify_hometax_page",
    "is_hometax_login_required",
    "is_hometax_authenticated",
    "is_hometax_download_page",
    "is_hometax_sensitive_submission",
    "build_hometax_download_plan",
]
