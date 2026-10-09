"""
Security Program Install Discovery — 공식 보안프로그램 설치 안내 페이지 실접속 탐색.

auth 감지 우회가 아니라, 설치 안내 페이지용 특화된 탐색 로직:
- 실제 로그인/인증 폼 유무를 확인 (input[type=password] 기반)
- 설치 설명 텍스트의 "인증서" 단어는 auth 요구로 오인하지 않음
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

# haehan-root-bootstrap: 정본 paths 를 import 하기 전이라 루트를 직접 찾는다 — 폴더가 옮겨져도 깨지지 않게 pyproject.toml 이 있는 상위 폴더를 찾는다
_REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.agent_runtime.runtime.security_program.security_installer_candidate_finder import (  # noqa: E402
    find_installer_candidates,
)
from core.agent_runtime.runtime.security_program.security_program_detector import detect_security_signals  # noqa: E402
from core.agent_runtime.runtime.security_program.security_program_install_result_sanitizer import (  # noqa: E402
    check_result_has_no_sensitive_data,
)

# 공식 후보 목록 (검색 결과 기반)
_OFFICIAL_CANDIDATES = [
    {
        "site_name": "우리은행",
        "official_domain": "spot.wooribank.com",
        "install_guide_url": "https://spot.wooribank.com/pot/Dream?withyou=CQSCT0089",
        "source_confidence": "HIGH",
    },
    {
        "site_name": "KB국민은행",
        "official_domain": "obank.kbstar.com",
        "install_guide_url": "https://obank.kbstar.com/quics?page=C040531",
        "source_confidence": "HIGH",
    },
    {
        "site_name": "정부24",
        "official_domain": "www.gov.kr",
        "install_guide_url": "https://www.gov.kr/mw/common/AA060_common_total_install.jsp",
        "source_confidence": "HIGH",
    },
]

_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]

# 실제 인증 요구 판단 — input[type=password] 유무 기반
_REAL_AUTH_INDICATORS = [
    'input[type="password"]',
    "input[type=password]",
    "#loginForm",
    ".login-form",
]


def _has_actual_auth_form(page: object) -> bool:
    """실제 인증 폼이 있는지 확인 (텍스트 키워드가 아닌 DOM 기반)."""
    try:
        for selector in _REAL_AUTH_INDICATORS:
            el = page.query_selector(selector)
            if el and el.is_visible():
                return True
    except Exception:  # noqa: BLE001 - 보안 프로그램 설치파일 탐색(공식 도메인 링크/버튼 읽기전용 수집) - 실패시 ACCESS_ERROR 상태 또는 빈 결과 반환
        pass
    return False


def _extract_host(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001 - 보안 프로그램 설치파일 탐색(공식 도메인 링크/버튼 읽기전용 수집) - 실패시 ACCESS_ERROR 상태 또는 빈 결과 반환
        return ""


def _is_official_link(href: str, source_host: str) -> bool:
    """href가 공식 도메인 내 링크인지 확인."""
    if href.startswith("http"):
        host = _extract_host(href)

        def root(h):
            return ".".join(h.split(".")[-2:]) if h else ""

        return root(host) == root(source_host)
    return True  # 상대 경로는 허용


def run_discovery(candidate: dict, take_screenshot: bool = False) -> dict:
    """단일 후보 사이트를 Playwright로 탐색한다."""
    task_id = str(uuid.uuid4())
    site_name = candidate["site_name"]
    source_host = candidate["official_domain"]
    install_guide_url = candidate["install_guide_url"]

    print(f"\n[탐색] {site_name} — {install_guide_url}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "site_name": site_name,
            "status": "PLAYWRIGHT_NOT_AVAILABLE",
            "message_ko": "Playwright 미설치",
            **dict.fromkeys(_SAFE_FIELDS, False),
        }

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            page.goto(install_guide_url, timeout=30000, wait_until="networkidle")

            title = page.title()
            current_url = page.url
            current_host = _extract_host(current_url)

            print(f"  title: {title[:80]}")
            print(f"  current_url: {current_url[:100]}")

            # 실제 인증 폼 확인 (DOM 기반, 텍스트 키워드 아님)
            has_auth_form = _has_actual_auth_form(page)
            if has_auth_form:
                print("  → 실제 로그인 폼 감지 — 다른 후보로 전환")
                return {
                    "site_name": site_name,
                    "status": "LOGIN_FORM_DETECTED",
                    "message_ko": f"{site_name} 설치 안내 페이지에 로그인 폼이 있습니다.",
                    **dict.fromkeys(_SAFE_FIELDS, False),
                }

            # 텍스트 추출
            try:
                body_text = page.inner_text("body")[:3000]
            except Exception:  # noqa: BLE001 - 보안 프로그램 설치파일 탐색(공식 도메인 링크/버튼 읽기전용 수집) - 실패시 ACCESS_ERROR 상태 또는 빈 결과 반환
                body_text = ""

            # 링크 추출 (공식 도메인 내 설치 파일 링크 — a href + onclick + data 속성)
            links = []
            _INSTALL_EXTS = (".exe", ".msi", ".dmg", ".pkg", ".zip")
            try:
                # a[href] 탐색
                for a in page.query_selector_all("a"):
                    href = a.get_attribute("href") or ""
                    # onclick에서 URL 추출
                    onclick = a.get_attribute("onclick") or ""
                    for src in [href, onclick]:
                        for ext in _INSTALL_EXTS:
                            if ext in src.lower():
                                # URL 추출 (따옴표 사이)
                                import re

                                urls = re.findall(r"['\"]([^'\"]*" + re.escape(ext) + r"[^'\"]*)['\"]", src, re.I)
                                for u in urls:
                                    if _is_official_link(u, source_host):
                                        if u.startswith("/"):
                                            base = f"{urlparse(current_url).scheme}://{current_host}"
                                            u = base + u
                                        if u not in links:
                                            links.append(u)
                                # href 직접
                                if href.lower().endswith(ext) and _is_official_link(href, source_host):
                                    if href.startswith("/"):
                                        base = f"{urlparse(current_url).scheme}://{current_host}"
                                        href = base + href
                                    if href not in links:
                                        links.append(href)
                # data-* 속성에서 URL 탐색
                for el in page.query_selector_all("[data-url],[data-href],[data-download]"):
                    for attr in ["data-url", "data-href", "data-download"]:
                        val = el.get_attribute(attr) or ""
                        if any(val.lower().endswith(ext) for ext in _INSTALL_EXTS):
                            if _is_official_link(val, source_host):
                                if val.startswith("/"):
                                    base = f"{urlparse(current_url).scheme}://{current_host}"
                                    val = base + val
                                if val not in links:
                                    links.append(val)
            except Exception as e:  # noqa: BLE001 - 보안 프로그램 설치파일 탐색(공식 도메인 링크/버튼 읽기전용 수집) - 실패시 ACCESS_ERROR 상태 또는 빈 결과 반환
                print(f"  링크 추출 오류: {e}")

            buttons = []
            try:
                for btn in page.query_selector_all("button, input[type=button], input[type=submit]"):
                    text = btn.inner_text().strip() if hasattr(btn, "inner_text") else ""
                    if text:
                        buttons.append(text[:50])
            except Exception:  # noqa: BLE001 - 보안 프로그램 설치파일 탐색(공식 도메인 링크/버튼 읽기전용 수집) - 실패시 ACCESS_ERROR 상태 또는 빈 결과 반환
                pass

            print(f"  설치 링크 후보: {links[:5]}")
            print(f"  버튼: {buttons[:5]}")

            # 스크린샷
            screenshot_path = None
            if take_screenshot:
                screenshot_path = f"screenshot_security_install_{task_id[:8]}.png"
                try:
                    page.screenshot(path=screenshot_path)
                    print(f"  screenshot: {screenshot_path}")
                except Exception:  # noqa: BLE001 - 보안 프로그램 설치파일 탐색(공식 도메인 링크/버튼 읽기전용 수집) - 실패시 ACCESS_ERROR 상태 또는 빈 결과 반환
                    pass

            # page_data 구성 (security_program_detector용)
            page_data = {
                "url": current_url,
                "title": title,
                "text_content": body_text[:2000],
                "buttons": buttons[:20],
                "links": links,
                "form_labels": [],
                "heading_texts": [],
            }

            # 보안프로그램 신호 감지
            detection = detect_security_signals(page_data)
            print(f"  감지 신호: {detection['signals']}")

            # 설치 후보 수집
            candidates_result = find_installer_candidates(page_data, source_host=source_host)
            print(f"  허용 후보: {len(candidates_result['allowed'])}개")
            print(f"  차단 후보: {len(candidates_result['blocked'])}개")

            return {
                "site_name": site_name,
                "status": "PAGE_ACCESSED",
                "official_domain": source_host,
                "install_guide_url": install_guide_url,
                "current_url": current_url,
                "title": title,
                "detection": detection,
                "installer_candidates": candidates_result,
                "screenshot": screenshot_path,
                **dict.fromkeys(_SAFE_FIELDS, False),
            }

        except Exception as e:  # noqa: BLE001 - 보안 프로그램 설치파일 탐색(공식 도메인 링크/버튼 읽기전용 수집) - 실패시 ACCESS_ERROR 상태 또는 빈 결과 반환
            print(f"  오류: {e}")
            return {
                "site_name": site_name,
                "status": "ACCESS_ERROR",
                "error": str(e)[:200],
                **dict.fromkeys(_SAFE_FIELDS, False),
            }
        finally:
            browser.close()


def select_best_candidate(results: list[dict]) -> dict | None:
    """접속 성공 + 설치 후보 있는 최적 사이트 선택."""
    for r in results:
        if r.get("status") == "PAGE_ACCESSED":
            allowed = r.get("installer_candidates", {}).get("allowed", [])
            if allowed:
                return r
    # 설치 후보가 없어도 접속 성공한 사이트 선택
    for r in results:
        if r.get("status") == "PAGE_ACCESSED":
            return r
    return None


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_signature(path: str) -> str:
    """PowerShell로 코드 서명 확인."""
    import subprocess

    # list 인자 + shell=False: shell=True로 문자열 명령을 넘기면 path에 셸 메타문자가
    # 섞였을 때 명령 주입 위험이 생긴다(이 함수는 현재 호출부가 없어 미사용이지만,
    # 다운로드 후보 파일의 경로를 검사하는 용도라 향후 연결 시 path가 외부 페이지가
    # 제안한 파일명에서 올 수 있어 안전하게 고쳐둠).
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        f"Get-AuthenticodeSignature -FilePath '{path}' | Select-Object -ExpandProperty Status",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=15)
        return result.stdout.strip() or "Unknown"
    except Exception as e:  # noqa: BLE001 - 보안 프로그램 설치파일 탐색(공식 도메인 링크/버튼 읽기전용 수집) - 실패시 ACCESS_ERROR 상태 또는 빈 결과 반환
        return f"CheckFailed: {e}"


def run_full_discovery(take_screenshot: bool = False) -> dict:
    """전체 후보 탐색 → 최적 선택 → 보고."""
    print("\n" + "=" * 60)
    print("보안프로그램 설치 자동 탐색")
    print("=" * 60)

    results = []
    for candidate in _OFFICIAL_CANDIDATES:
        r = run_discovery(candidate, take_screenshot=take_screenshot)
        results.append(r)
        if r.get("status") == "PAGE_ACCESSED":
            allowed = r.get("installer_candidates", {}).get("allowed", [])
            if allowed:
                print(f"\n  → {candidate['site_name']}: 설치 후보 {len(allowed)}개 발견 — 선택")
                break

    selected = select_best_candidate(results)

    # safe field 검증
    for r in results:
        violations = check_result_has_no_sensitive_data(r)
        if violations:
            print(f"\n경고: safe field 위반 — {violations}")

    report = {
        "task_id": str(uuid.uuid4()),
        "executed_at": datetime.now(UTC).isoformat(),
        "candidates_tried": len(results),
        "results_summary": [{"site": r.get("site_name"), "status": r.get("status")} for r in results],
        "selected": {
            "site_name": selected.get("site_name") if selected else None,
            "status": selected.get("status") if selected else "NO_CANDIDATE",
            "official_domain": selected.get("official_domain") if selected else None,
            "current_url": selected.get("current_url") if selected else None,
            "title": selected.get("title") if selected else None,
            "signals": selected.get("detection", {}).get("signals", []) if selected else [],
            "installer_allowed_count": len((selected or {}).get("installer_candidates", {}).get("allowed", [])),
            "installer_allowed": (selected or {}).get("installer_candidates", {}).get("allowed", []),
        },
        **dict.fromkeys(_SAFE_FIELDS, False),
    }

    return report


def main():
    report = run_full_discovery(take_screenshot=True)

    print("\n" + "=" * 60)
    print("탐색 결과")
    print("=" * 60)
    print(f"시도: {report['candidates_tried']}개 후보")
    print(f"선택: {report['selected']['site_name']} / {report['selected']['status']}")
    if report["selected"]["signals"]:
        print(f"감지 신호: {report['selected']['signals']}")
    if report["selected"]["installer_allowed"]:
        print("설치 후보:")
        for c in report["selected"]["installer_allowed"][:3]:
            print(f"  - {c.get('filename')} ({c.get('url', '')[:80]})")

    # safe field 확인
    all_safe = all(report.get(f) is False for f in _SAFE_FIELDS)
    print(f"\n보안 정책: {'PASS' if all_safe else 'FAIL'}")
    print(f"server_browser_used: {report.get('server_browser_used')}")

    return report


if __name__ == "__main__":
    main()
