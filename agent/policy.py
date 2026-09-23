"""에이전트 정책: 허용 action whitelist + URL 검증.

- read-only action: 입력/클릭/제출 불가.
- login_with_secret 만 예외적으로 최소 입력·클릭을 허용하되,
  site_profiles 에 명시적으로 등록된 프로필이 있을 때만 수행된다.
  회원가입/추가 제출/다운로드/설정 변경은 이 단계에서도 금지된다.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

# 이번 단계에서 허용되는 action 만 나열. 추가는 별도 단계의 승인이 필요.
ALLOWED_ACTIONS: frozenset[str] = frozenset(
    {
        "ping",
        "get_system_info",
        "open_page_readonly",
        "inspect_page",
        "login_with_secret",
        "inspect_after_login",
        # Excel 1단계: 읽기 + 결과 복사본 저장.
        "excel_read_sheet",
        "excel_write_report_copy",
        # Excel 2단계: 구조 요약 + 헤더 기반 표 읽기 (read-only).
        "excel_describe_workbook",
        "excel_read_table",
        # Excel COM (B안 4단계): 데스크톱 Excel 제어. local_agent 가 분기.
        "excel.run_poc",
        "excel.read_cell",
        "excel.write_cell",
        "excel.save_as",
        # local_agent 전용: 사용자 PC visible 브라우저 기동 (E단계).
        "open_local_browser",
        # local_agent 전용: Playwright dedicated 프로필 visible probe (E-2 단계).
        "open_local_browser_probe",
        # local_agent 전용: 공개 페이지 read-only observer (F-4B 단계).
        "observe_public_browser_page",
    }
)

# BROWSER_ACTIONS 는 "URL 파라미터 기반" action 의 집합.
# login_with_secret 는 site_key 기반이므로 여기에 포함하지 않는다.
BROWSER_ACTIONS: frozenset[str] = frozenset(
    {
        "open_page_readonly",
        "inspect_page",
    }
)

_BLOCKED_HOSTNAMES: frozenset[str] = frozenset(
    {
        "localhost",
        "ip6-localhost",
        "ip6-loopback",
        "broadcasthost",
    }
)


def is_allowed_action(action: str) -> bool:
    return isinstance(action, str) and action in ALLOWED_ACTIONS


def is_browser_action(action: str) -> bool:
    return isinstance(action, str) and action in BROWSER_ACTIONS


def _is_private_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified


def validate_url(url: str) -> tuple[bool, str]:
    """URL 이 외부 공개 http/https 이면 (True, "") 반환, 아니면 (False, reason).

    차단 기준:
      - 빈 문자열 / 잘못된 형식
      - http/https 외 스킴 (file://, ftp://, data:, javascript:, …)
      - localhost / 루프백 / 사설망 / 링크로컬 / 멀티캐스트 / .local mDNS
    """
    if not isinstance(url, str) or not url.strip():
        return False, "empty_url"

    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False, "malformed_url"

    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return False, f"scheme_not_allowed:{scheme or 'none'}"

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "missing_host"

    if host in _BLOCKED_HOSTNAMES:
        return False, f"blocked_host:{host}"

    if _is_private_ip(host):
        return False, f"blocked_private_ip:{host}"

    if host.endswith(".local"):
        return False, "blocked_mdns_local"

    return True, ""
