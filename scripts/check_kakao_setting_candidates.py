"""KAKAO-DEV-5-LITE — Kakao 설정값 후보 HTTP 접근성 검증.

Kakao 콘솔 등록 전 후보 URL의 도달 가능성(reachable), HTTPS 여부,
응답 상태를 확인한다. 실제 Kakao 콘솔 저장/제출은 하지 않는다.

절대 금지: secret/cookie 원문 출력, Kakao 콘솔 write, ID/PW 저장
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SECRET_PATTERN = re.compile(r"[0-9a-f]{32,}|[A-Za-z0-9+/]{40,}={0,2}", re.IGNORECASE)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

_DEFAULT_DOMAIN = "https://attendance.haehan-ai.kr"
_DEFAULT_REDIRECT_URI = "https://attendance.haehan-ai.kr/auth/kakao/callback"
_DEFAULT_PRIVACY_CANDIDATES = [
    "https://attendance.haehan-ai.kr/privacy",
    "https://attendance.haehan-ai.kr/privacy-policy",
    "https://attendance.haehan-ai.kr/terms/privacy",
]

_HEADERS = {"User-Agent": "haehan-kakao-candidate-checker/1.0"}


def _mask(text: str) -> str:
    return _SECRET_PATTERN.sub("[MASKED]", text)


def _check_url(url: str, timeout: int = 10) -> dict[str, Any]:
    """단일 URL을 HEAD → GET 순으로 확인한다. 쿠키/세션 저장 없음."""
    result: dict[str, Any] = {
        "url": url,
        "https": url.startswith("https://"),
        "reachable": False,
        "status_code": None,
        "final_url": url,
        "title": "",
        "redirect": False,
        "error": None,
        "kakao_registerable": False,
    }

    req = urllib.request.Request(url, headers=_HEADERS, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result["status_code"] = resp.status
            result["final_url"] = resp.url
            result["redirect"] = resp.url != url
            result["reachable"] = True
    except urllib.error.HTTPError as e:
        result["status_code"] = e.code
        result["reachable"] = e.code < 500
        result["error"] = f"HTTP {e.code}"
    except Exception as exc:
        # HEAD 실패 시 GET 재시도
        req2 = urllib.request.Request(url, headers=_HEADERS)
        try:
            with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                result["status_code"] = resp2.status
                result["final_url"] = resp2.url
                result["redirect"] = resp2.url != url
                result["reachable"] = True
                raw = resp2.read(4096).decode("utf-8", errors="ignore")
                m = _TITLE_RE.search(raw)
                if m:
                    result["title"] = _mask(m.group(1).strip()[:120])
        except urllib.error.HTTPError as e2:
            result["status_code"] = e2.code
            result["reachable"] = e2.code < 500
            result["error"] = f"HTTP {e2.code}"
        except Exception as exc2:
            result["error"] = _mask(str(exc2)[:200])

    # Kakao 등록 가능성: HTTPS + 도메인 도달 가능 (4xx도 앱 경로이면 등록 가능)
    result["kakao_registerable"] = (
        result["https"]
        and result["reachable"]
        and result["status_code"] is not None
        and result["status_code"] < 500
    )
    return result


def _judge(domain_result: dict, redirect_result: dict, privacy_results: list[dict]) -> dict[str, Any]:
    warnings: list[str] = []
    blockers: list[str] = []

    if not domain_result["reachable"]:
        blockers.append("web_platform_domain 접근 불가 — 도메인 확인 필요")
    if not domain_result["https"]:
        blockers.append("web_platform_domain이 HTTPS가 아님 — Kakao 등록 불가")

    if not redirect_result["reachable"]:
        blockers.append("redirect_uri 도메인 접근 불가")
    elif redirect_result["status_code"] == 404:
        warnings.append("redirect_uri 404 — 경로 미구현, 도메인은 유효")
    elif redirect_result["status_code"] and redirect_result["status_code"] >= 500:
        blockers.append(f"redirect_uri 서버 오류 {redirect_result['status_code']}")

    privacy_ok = any(r["status_code"] == 200 for r in privacy_results)
    if not privacy_ok:
        warnings.append("개인정보처리방침 URL 200 응답 없음 — URL 확인 또는 신규 작성 필요")

    return {
        "ready_for_platform_registration": not blockers and domain_result["kakao_registerable"],
        "ready_for_redirect_uri_registration": not blockers and redirect_result["reachable"],
        "ready_for_permission_request": not blockers and privacy_ok,
        "blockers": blockers,
        "warnings": warnings,
    }


def check_candidates(
    domain: str = _DEFAULT_DOMAIN,
    redirect_uri: str = _DEFAULT_REDIRECT_URI,
    privacy_urls: list[str] | None = None,
    out_dir: str = "runs/developer_console",
    *,
    _http_checker: Any = None,
) -> dict[str, Any]:
    if privacy_urls is None:
        privacy_urls = _DEFAULT_PRIVACY_CANDIDATES

    checker = _http_checker or _check_url

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(out_dir) / f"kakao_setting_candidates_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"[check_candidates] 도메인 확인: {domain}", file=sys.stderr)
    domain_result = checker(domain)

    print(f"[check_candidates] Redirect URI 확인: {redirect_uri}", file=sys.stderr)
    redirect_result = checker(redirect_uri)

    privacy_results: list[dict] = []
    for pu in privacy_urls:
        print(f"[check_candidates] 개인정보처리방침 확인: {pu}", file=sys.stderr)
        privacy_results.append(checker(pu))

    judgment = _judge(domain_result, redirect_result, privacy_results)

    output: dict[str, Any] = {
        "checked_at": ts,
        "domain": domain_result,
        "redirect_uri": redirect_result,
        "privacy_candidates": privacy_results,
        "judgment": judgment,
        "account_email_note": (
            "account_email(카카오계정 이메일)은 현재 '필수 동의 [수집]'으로 설정됨. "
            "출퇴근 앱에서 이메일이 실제 로그인 식별자로 필요한지 확인 필요. "
            "전화번호/사번/관리자 등록 기반이면 email 필수성 낮음. "
            "단, 카카오 계정 매칭에는 email이 유용할 수 있음."
        ),
        "biz_app_note": (
            "비즈앱 전환 심사 중. 완료 후 이름·성별·연령대·전화번호·CI 등 "
            "추가 기능 신청 가능. 카카오싱크는 비즈니스 채널 연결 후 별도 검토 필요."
        ),
        "security": {
            "password_stored": False,
            "storage_state_printed": False,
            "secret_raw_stored": False,
            "kakao_console_write": False,
        },
        "result_dir": str(run_dir),
    }

    _write_results(output, run_dir)
    return output


def _write_results(output: dict, run_dir: Path) -> None:
    (run_dir / "candidates.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "candidates.md").write_text(_build_md(output), encoding="utf-8")
    (run_dir / "next_actions.md").write_text(_build_next_actions(output), encoding="utf-8")


def _build_md(output: dict) -> str:
    j = output.get("judgment") or {}
    d = output.get("domain") or {}
    r = output.get("redirect_uri") or {}
    privs = output.get("privacy_candidates") or []

    lines = [
        "# Kakao 설정 후보값 검증 결과",
        "",
        f"- checked_at: {output.get('checked_at')}",
        "",
        "## 판정 요약",
        f"- 플랫폼 도메인 등록 준비: {'✓' if j.get('ready_for_platform_registration') else '✗'}",
        f"- Redirect URI 등록 준비: {'✓' if j.get('ready_for_redirect_uri_registration') else '✗'}",
        f"- 권한 신청 준비: {'✓' if j.get('ready_for_permission_request') else '✗'}",
        "",
    ]
    if j.get("blockers"):
        lines += ["### 차단 사항 (FAIL)"]
        for b in j["blockers"]:
            lines.append(f"- ❌ {b}")
        lines.append("")
    if j.get("warnings"):
        lines += ["### 경고 (WARN)"]
        for w in j["warnings"]:
            lines.append(f"- ⚠️ {w}")
        lines.append("")

    lines += [
        "## Web 플랫폼 도메인",
        f"- URL: {d.get('url')}",
        f"- HTTPS: {d.get('https')}",
        f"- reachable: {d.get('reachable')}",
        f"- status_code: {d.get('status_code')}",
        f"- kakao_registerable: {d.get('kakao_registerable')}",
        "",
        "## Redirect URI",
        f"- URL: {r.get('url')}",
        f"- reachable: {r.get('reachable')}",
        f"- status_code: {r.get('status_code')}",
        f"- redirect: {r.get('redirect')}",
        f"- kakao_registerable: {r.get('kakao_registerable')}",
        "",
        "## 개인정보처리방침 후보",
    ]
    for p in privs:
        mark = "✓" if p.get("status_code") == 200 else "✗"
        lines.append(f"- {mark} {p['url']} → {p.get('status_code')} / reachable={p.get('reachable')}")

    lines += [
        "",
        "## account_email 결정 자료",
        output.get("account_email_note", ""),
        "",
        "## 비즈앱/카카오싱크 참고",
        output.get("biz_app_note", ""),
        "",
        "## 보안 확인",
        "- Kakao 콘솔 write 실행: 없음",
        "- secret/session 원문 출력: 없음",
    ]
    return "\n".join(lines)


def _build_next_actions(output: dict) -> str:
    j = output.get("judgment") or {}
    lines = [
        "# 다음 행동 (Next Actions)",
        "",
        "## 자동 확인 완료",
        f"- Web 플랫폼 도메인 접근성: {(output.get('domain') or {}).get('status_code')}",
        f"- Redirect URI 상태: {(output.get('redirect_uri') or {}).get('status_code')}",
        f"- 개인정보처리방침 후보 확인: {len(output.get('privacy_candidates') or [])}개",
        "",
        "## 대표님 판단 필요",
        "- [ ] Redirect URI 경로 확정 (/auth/kakao/callback 또는 실제 앱 경로)",
        "- [ ] 개인정보처리방침 URL 작성/배포 (없으면 신규 작성 필요)",
        "- [ ] account_email 필수 수집 유지 여부 결정",
        "  - 현재: 필수 동의 [수집] 설정됨",
        "  - 출퇴근 앱에서 이메일이 실제 로그인 식별자로 필요한지 확인",
        "  - 전화번호/사번/관리자 등록 기반이면 email 필수성 낮음",
        "  - 카카오 계정 매칭 목적이면 email 유용",
        "- [ ] 비즈앱 전환 심사 결과 확인 후 추가 기능 신청 진행",
        "- [ ] 카카오싱크 도입 여부 결정 (비즈니스 채널 연결 필요)",
        "",
        "## 자동 등록 가능 후보 (값 확정 후 수동 진행)",
    ]
    if j.get("ready_for_platform_registration"):
        lines.append("- ✓ Web 플랫폼 도메인 등록 가능")
    else:
        lines.append("- ✗ Web 플랫폼 도메인 등록 전 blocker 해소 필요")
    if j.get("ready_for_redirect_uri_registration"):
        lines.append("- ✓ Redirect URI 등록 가능 (경로 확정 후)")
    else:
        lines.append("- ✗ Redirect URI 등록 전 blocker 해소 필요")

    lines += [
        "",
        "## 승인형으로 남길 작업",
        "- 실제 Kakao 콘솔 설정값 저장 — 대표님이 직접 수행",
        "- 권한 신청 제출 — AI 자동 제출 안 함",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kakao 설정 후보값 HTTP 접근성 검증")
    parser.add_argument("--domain", default=_DEFAULT_DOMAIN)
    parser.add_argument("--redirect-uri", default=_DEFAULT_REDIRECT_URI, dest="redirect_uri")
    parser.add_argument("--privacy-url", action="append", dest="privacy_urls",
                        help="개인정보처리방침 URL 후보 (여러 번 지정 가능)")
    parser.add_argument("--out-dir", default="runs/developer_console")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    privacy_urls = args.privacy_urls or _DEFAULT_PRIVACY_CANDIDATES

    output = check_candidates(
        domain=args.domain,
        redirect_uri=args.redirect_uri,
        privacy_urls=privacy_urls,
        out_dir=args.out_dir,
    )

    rd = output.get("result_dir", "")
    if rd:
        print(f"[결과] {rd}", file=sys.stderr)

    if args.json_output:
        j = output.get("judgment") or {}
        slim = {
            "checked_at": output.get("checked_at"),
            "result_dir": rd,
            "domain": {
                "url": output["domain"]["url"],
                "reachable": output["domain"]["reachable"],
                "status_code": output["domain"]["status_code"],
                "https": output["domain"]["https"],
                "kakao_registerable": output["domain"]["kakao_registerable"],
            },
            "redirect_uri": {
                "url": output["redirect_uri"]["url"],
                "reachable": output["redirect_uri"]["reachable"],
                "status_code": output["redirect_uri"]["status_code"],
                "kakao_registerable": output["redirect_uri"]["kakao_registerable"],
            },
            "privacy_candidates": [
                {"url": p["url"], "status_code": p["status_code"], "reachable": p["reachable"]}
                for p in (output.get("privacy_candidates") or [])
            ],
            "judgment": j,
        }
        print(json.dumps(slim, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
