"""KAKAO-DEV-4 — Kakao 앱 상세 심층 관찰.

로그인 후 앱 목록에서 app_id를 추출해 각 앱의 상세 페이지를 순회한다.
- 동의항목(scope) 승인 상태
- 플랫폼 등록 여부
- 카카오 로그인 활성화 여부
- Redirect URI 등록 여부
- 비즈앱 여부
- 권한 신청 현황

절대 금지: 클릭/입력/저장/신청 제출/secret 원문 저장/cookie export
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time as _time_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TARGET_URL = "https://developers.kakao.com/console/app"
_SECRET_PATTERN = re.compile(r"[0-9a-f]{32,}|[A-Za-z0-9+/]{40,}={0,2}", re.IGNORECASE)
_APP_ID_PATTERN = re.compile(r"/console/app/(\d+)")

# 앱 URL 구조
_APP_URLS = {
    "overview":   "/console/app/{id}",
    "login":      "/console/app/{id}/product/login",
    "scope":      "/console/app/{id}/product/login/scope",
    "platform":   "/console/app/{id}/config/platform",
    "biz":        "/console/app/{id}/product/biz",
    "permission": "/console/app/{id}/product/permission",
}
_BASE = "https://developers.kakao.com"

# 동의항목 상태 키워드
_SCOPE_STATUS = {
    "required": ("필수", "required"),
    "optional": ("선택", "optional"),
    "pending": ("검토 중", "심사 중", "pending", "under review"),
    "approved": ("사용 중", "approved", "active"),
    "rejected": ("거절", "rejected", "반려"),
    "not_used": ("사용 안 함", "not used", "inactive"),
    "biz_required": ("비즈앱", "biz app", "사업자", "business"),
}

# 로그인 완료 신호
_LOGIN_SUCCESS_TEXTS = ["내 애플리케이션", "앱 목록", "로그아웃"]
_LOGIN_SUCCESS_URLS = ["/console/app"]
_LOGIN_TOKENS = ("로그인", "카카오 계정", "이메일", "비밀번호", "sign in")
_LOGIN_COMPLETE_PROMPT = (
    "\n[observe_kakao_app_details] 로그인 완료 후 Enter, 아직이면 n + Enter: "
)


def _mask(text: str) -> str:
    return _SECRET_PATTERN.sub("[MASKED]", text)


def _safe_text(text: str, limit: int = 2000) -> str:
    t = (text or "")[:limit]
    return _mask(t)


def _is_interactive_stdin() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _observe_page(page: Any, max_chars: int = 80_000) -> dict[str, Any]:
    """read-only 관찰: title / url / content만 수집."""
    try:
        title = page.title() or ""
    except Exception:
        title = ""
    try:
        url = page.url or ""
    except Exception:
        url = ""
    try:
        html = page.content() or ""
        if not isinstance(html, str):
            html = ""
        html = html[:max_chars]
    except Exception:
        html = ""
    return {"title": title, "url": url, "html": html}


def _has_login_signal(obs: dict) -> bool:
    text = (obs.get("title", "") + " " + obs.get("html", "")[:3000]).lower()
    return any(t.lower() in text for t in _LOGIN_SUCCESS_TEXTS)


def _needs_login(obs: dict) -> bool:
    text = (obs.get("title", "") + " " + obs.get("html", "")[:3000]).lower()
    return any(t.lower() in text for t in _LOGIN_TOKENS)


def _extract_app_ids(html: str) -> list[str]:
    ids = _APP_ID_PATTERN.findall(html)
    seen: dict[str, None] = {}
    for i in ids:
        seen[i] = None
    return list(seen.keys())


def _extract_app_names(html: str, app_ids: list[str]) -> dict[str, str]:
    """앱 카드에서 이름 힌트 추출."""
    names: dict[str, str] = {}
    for aid in app_ids:
        # URL 앞뒤 30자 텍스트에서 이름 힌트 추출
        pattern = re.compile(
            rf'/console/app/{re.escape(aid)}[^"\']*["\'][\s\S]{{0,200}}',
            re.IGNORECASE,
        )
        m = pattern.search(html)
        if m:
            snippet = re.sub(r"<[^>]+>", " ", m.group())
            snippet = re.sub(r"\s+", " ", snippet).strip()[:80]
            names[aid] = _mask(snippet)
        else:
            names[aid] = ""
    return names


def _parse_scope_page(html: str) -> dict[str, Any]:
    """동의항목 페이지에서 승인 상태 분석."""
    html_lower = html.lower()
    result: dict[str, Any] = {
        "has_required": False,
        "has_optional": False,
        "has_pending": False,
        "has_approved": False,
        "has_rejected": False,
        "has_not_used": False,
        "biz_required_items": False,
        "raw_hint": "",
    }
    for status, tokens in _SCOPE_STATUS.items():
        for tok in tokens:
            if tok.lower() in html_lower:
                result[f"has_{status}"] = True
                break

    # 심사가 필요한 항목 감지
    review_tokens = ("심사", "검토", "비즈니스", "제한", "권한 신청", "추가 기능 신청")
    result["review_needed"] = any(t in html_lower for t in review_tokens)

    # 텍스트 힌트 (secret 마스킹)
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean)
    result["raw_hint"] = _safe_text(clean, 1500)
    return result


def _parse_platform_page(html: str) -> dict[str, Any]:
    html_lower = html.lower()
    return {
        "web_registered": "web" in html_lower and "사이트 도메인" in html_lower,
        "android_registered": "android" in html_lower and "패키지" in html_lower,
        "ios_registered": "ios" in html_lower and "번들" in html_lower,
        "no_platform": "등록된 플랫폼" not in html_lower and "platform" not in html_lower,
        "raw_hint": _safe_text(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)), 800),
    }


def _parse_login_page(html: str) -> dict[str, Any]:
    html_lower = html.lower()
    return {
        "login_activated": "활성화" in html_lower or "activated" in html_lower or "on" in html_lower,
        "redirect_uri_registered": "redirect" in html_lower and ("http" in html_lower or "등록" in html_lower),
        "logout_uri_registered": "logout" in html_lower,
        "raw_hint": _safe_text(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)), 800),
    }


def _parse_biz_page(html: str) -> dict[str, Any]:
    html_lower = html.lower()
    return {
        "biz_app": "비즈앱" in html_lower and "완료" in html_lower,
        "biz_pending": "심사" in html_lower or "검토" in html_lower,
        "biz_required": "비즈앱 전환" in html_lower or "신청" in html_lower,
        "raw_hint": _safe_text(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)), 600),
    }


def _navigate_and_observe(page: Any, url: str, wait_ms: int = 8000) -> dict[str, Any]:
    """페이지 이동 후 read-only 관찰. 클릭/입력 금지."""
    try:
        page.goto(url, wait_until="networkidle", timeout=wait_ms)
    except Exception:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=wait_ms)
        except Exception as exc:
            return {"title": "", "url": url, "html": "", "error": str(exc)[:100]}
    return _observe_page(page)


def _diagnose_reasons(app_detail: dict) -> list[str]:
    """승인 미완료 이유 분석."""
    reasons: list[str] = []
    scope = app_detail.get("scope") or {}
    platform = app_detail.get("platform") or {}
    login = app_detail.get("login") or {}
    biz = app_detail.get("biz") or {}

    if scope.get("has_rejected"):
        reasons.append("동의항목 거절됨 — 거절 사유 확인 후 재신청 필요")
    if scope.get("has_pending"):
        reasons.append("동의항목 심사 진행 중 — 승인 대기")
    if scope.get("biz_required_items") or scope.get("review_needed"):
        reasons.append("일부 동의항목이 비즈앱 전환 또는 권한 신청 필요")
    if not platform.get("web_registered") and not platform.get("android_registered") and not platform.get("ios_registered"):
        reasons.append("플랫폼(Web/Android/iOS) 미등록 — 플랫폼 등록 필요")
    if not login.get("login_activated"):
        reasons.append("카카오 로그인 비활성화 상태")
    if not login.get("redirect_uri_registered"):
        reasons.append("Redirect URI 미등록")
    if biz.get("biz_required"):
        reasons.append("비즈앱 전환 필요 — 일부 기능은 비즈앱 전용")
    if biz.get("biz_pending"):
        reasons.append("비즈앱 전환 심사 중")

    if not reasons:
        reasons.append("명확한 미승인 사유 미감지 — 상세 스크린샷 확인 권장")
    return reasons


# ── 메인 관찰 ────────────────────────────────────────────────────────────────

def observe_details(
    out_dir: str = "runs/developer_console",
    login_timeout_seconds: int = 300,
    poll_interval_seconds: int = 5,
    *,
    _browser_factory: Optional[Callable[[], Any]] = None,
    _clock: Any = None,
    _input_reader: Optional[Callable[[str], str]] = None,
) -> dict[str, Any]:
    from local_agent.browser_login_probe import _observe as _lp_observe
    from local_agent.browser_reader import _safe_close

    time_mod = _clock or _time_mod
    interactive_mode = (_input_reader is not None) or _is_interactive_stdin()
    input_fn = _input_reader if _input_reader is not None else input

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(out_dir) / f"kakao_app_details_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    factory = _browser_factory
    if factory is None:
        try:
            from playwright.sync_api import sync_playwright
            factory = sync_playwright
        except ImportError:
            return {"error": "playwright not installed", "apps": []}

    apps_result: list[dict] = []
    session_status = "UNKNOWN"

    # 저장된 세션 재사용 시도
    try:
        from ai_orchestrator.sites import secrets_policy as _sp
        _state_path = _sp.session_state_path("kakao_developers")
        _storage_state_arg: dict = {"storage_state": str(_state_path)} if _state_path.is_file() else {}
    except Exception:
        _storage_state_arg = {}

    try:
        with factory() as pw:
            try:
                browser = pw.chromium.launch(headless=False)
            except Exception as exc:
                return {"error": f"browser launch failed: {exc}", "apps": []}

            try:
                context = browser.new_context(**_storage_state_arg)
                try:
                    page = context.new_page()
                    try:
                        # ── 1) 로그인 대기 ───────────────────────────────────
                        try:
                            page.goto(_TARGET_URL, wait_until="domcontentloaded", timeout=15000)
                        except Exception as exc:
                            print(f"[observe] goto warn: {exc}", file=sys.stderr)
                        try:
                            page.bring_to_front()
                        except Exception:
                            pass

                        from local_agent.browser_login_probe import _observe as _obs_fn
                        from local_agent.browser_login_probe import _detect_completion
                        initial = _obs_fn(page, max_html_chars=500_000)

                        # 저장된 세션으로 이미 로그인된 경우 대기 루프 생략
                        initial_logged_in = _has_login_signal(
                            {"title": initial.get("title", ""),
                             "html": (initial.get("page_structure") or {}).get("visible_text", "")}
                        )

                        completion_reasons: list[str] = []
                        has_signal = False

                        if initial_logged_in:
                            has_signal = True
                            completion_reasons = ["session_reused"]
                            print("[observe_kakao_app_details] 저장된 세션 재사용 — 로그인 생략", file=sys.stderr)
                        else:
                            deadline = time_mod.monotonic() + login_timeout_seconds
                            hard_deadline = deadline * 4
                            sixty_warned = False
                            last_obs = initial

                            while True:
                                now = time_mod.monotonic()
                                if now >= hard_deadline or now >= deadline:
                                    break
                                remaining = deadline - now
                                if remaining <= 60 and not sixty_warned:
                                    sixty_warned = True
                                    print("[observe_kakao_app_details] 로그인 대기 60초 남았습니다", file=sys.stderr)
                                sleep_for = min(poll_interval_seconds, remaining)
                                if sleep_for > 0:
                                    time_mod.sleep(sleep_for)
                                last_obs = _obs_fn(page, max_html_chars=500_000)
                                completion_reasons = _detect_completion(
                                    initial=initial, current=last_obs,
                                    success_urls=_LOGIN_SUCCESS_URLS,
                                    success_texts=_LOGIN_SUCCESS_TEXTS,
                                )
                                non_url = [r for r in completion_reasons
                                           if r != "url_changed" and not r.startswith("success_url_match:")]
                                if non_url:
                                    break

                            has_signal = bool([r for r in completion_reasons
                                               if r != "url_changed" and not r.startswith("success_url_match:")])

                        login_confirmed = False
                        if interactive_mode:
                            try:
                                ans = input_fn(_LOGIN_COMPLETE_PROMPT)
                                if (ans or "").strip().lower() not in {"n", "no", "아니오"}:
                                    login_confirmed = True
                            except (EOFError, KeyboardInterrupt):
                                pass
                        else:
                            login_confirmed = has_signal

                        if not login_confirmed and not has_signal:
                            session_status = "NEEDS_REAUTH_TIMEOUT"
                            _write_results({"session_status": session_status, "apps": []}, run_dir)
                            return {"session_status": session_status, "apps": [], "result_dir": str(run_dir)}

                        session_status = "READY_LOGGED_IN"
                        # 세션 저장 (다음 실행 시 재사용)
                        try:
                            from ai_orchestrator.sites import secrets_policy as _sp2
                            _sp_path = _sp2.session_state_path("kakao_developers")
                            _sp_path.parent.mkdir(parents=True, exist_ok=True)
                            context.storage_state(path=str(_sp_path))
                        except Exception as _se:
                            print(f"[observe_kakao_app_details] session save warn: {_se}", file=sys.stderr)
                        print("[observe_kakao_app_details] 로그인 감지. 앱 목록 수집 시작...", file=sys.stderr)

                        # ── 2) 앱 목록에서 app_id 추출 ──────────────────────
                        try:
                            page.goto(_TARGET_URL, wait_until="networkidle", timeout=15000)
                        except Exception:
                            pass
                        list_obs = _observe_page(page)
                        app_ids = _extract_app_ids(list_obs["html"])
                        app_names = _extract_app_names(list_obs["html"], app_ids)
                        print(f"[observe_kakao_app_details] 앱 {len(app_ids)}개 감지: {app_ids}", file=sys.stderr)

                        # ── 3) 각 앱 상세 페이지 순회 ────────────────────────
                        for app_id in app_ids:
                            print(f"[observe_kakao_app_details] 앱 {app_id} 관찰 중...", file=sys.stderr)
                            app_data: dict[str, Any] = {
                                "app_id": app_id,
                                "app_name_hint": app_names.get(app_id, ""),
                                "pages": {},
                                "scope": {},
                                "platform": {},
                                "login": {},
                                "biz": {},
                                "diagnosis": [],
                            }

                            for page_key, url_tmpl in _APP_URLS.items():
                                url = _BASE + url_tmpl.format(id=app_id)
                                obs = _navigate_and_observe(page, url)
                                html = obs.get("html", "")
                                title = obs.get("title", "")
                                # 페이지별 파싱
                                if page_key == "scope":
                                    app_data["scope"] = _parse_scope_page(html)
                                elif page_key == "platform":
                                    app_data["platform"] = _parse_platform_page(html)
                                elif page_key == "login":
                                    app_data["login"] = _parse_login_page(html)
                                elif page_key == "biz":
                                    app_data["biz"] = _parse_biz_page(html)

                                # 페이지 요약 저장 (secret 마스킹, raw_html 제외)
                                clean = re.sub(r"<[^>]+>", " ", html)
                                clean = re.sub(r"\s+", " ", clean).strip()
                                app_data["pages"][page_key] = {
                                    "url": url,
                                    "title": title[:100],
                                    "text_hint": _safe_text(clean, 600),
                                    "error": obs.get("error"),
                                }

                                time_mod.sleep(1)  # 페이지 간 최소 대기

                            app_data["diagnosis"] = _diagnose_reasons(app_data)
                            apps_result.append(app_data)

                    finally:
                        _safe_close(page)
                finally:
                    _safe_close(context)
            finally:
                _safe_close(browser)

    except Exception as exc:
        return {"error": str(exc)[:300], "apps": apps_result}

    output = {
        "session_status": session_status,
        "observed_at": ts,
        "app_count": len(apps_result),
        "apps": apps_result,
        "result_dir": str(run_dir),
    }
    _write_results(output, run_dir)
    return output


def _write_results(output: dict, run_dir: Path) -> None:
    (run_dir / "app_details.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "app_details.md").write_text(_build_md(output), encoding="utf-8")


def _build_md(output: dict) -> str:
    lines = [
        "# Kakao 앱 상세 관찰 결과 (KAKAO-DEV-4)",
        "",
        f"- observed_at: {output.get('observed_at')}",
        f"- session_status: {output.get('session_status')}",
        f"- app_count: {output.get('app_count')}",
        "",
        "## 앱별 승인 미완료 진단",
        "",
    ]
    for app in output.get("apps") or []:
        lines += [
            f"### 앱 {app['app_id']} — {app.get('app_name_hint', '')}",
            "",
            "**진단 결과:**",
        ]
        for d in app.get("diagnosis") or []:
            lines.append(f"- {d}")

        scope = app.get("scope") or {}
        login = app.get("login") or {}
        platform = app.get("platform") or {}
        biz = app.get("biz") or {}

        lines += [
            "",
            "**상태 요약:**",
            f"| 항목 | 상태 |",
            f"|------|------|",
            f"| 비즈앱 | {'✓' if biz.get('biz_app') else ('심사중' if biz.get('biz_pending') else '미전환')} |",
            f"| 카카오 로그인 활성화 | {'✓' if login.get('login_activated') else '✗'} |",
            f"| Redirect URI | {'✓' if login.get('redirect_uri_registered') else '✗'} |",
            f"| 플랫폼 Web | {'✓' if platform.get('web_registered') else '✗'} |",
            f"| 동의항목 심사중 | {'있음' if scope.get('has_pending') else '없음'} |",
            f"| 동의항목 거절 | {'있음' if scope.get('has_rejected') else '없음'} |",
            f"| 비즈앱 전용 항목 | {'있음' if scope.get('biz_required_items') else '없음'} |",
            "",
        ]

        if scope.get("raw_hint"):
            lines += [
                "<details><summary>동의항목 페이지 텍스트 힌트</summary>",
                "",
                f"```",
                scope["raw_hint"][:800],
                "```",
                "</details>",
                "",
            ]

    lines += [
        "## 보안 확인",
        "- 클릭/입력: 없음",
        "- password value 읽기: 없음",
        "- cookie/session export: 없음",
        "- secret 원문 저장: 없음 (마스킹 처리)",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="KAKAO-DEV-4 app details observer")
    parser.add_argument("--out-dir", default="runs/developer_console")
    parser.add_argument("--login-timeout-seconds", type=int, default=300)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    output = observe_details(
        out_dir=args.out_dir,
        login_timeout_seconds=args.login_timeout_seconds,
    )

    rd = output.get("result_dir", "")
    if rd:
        print(f"[결과] {rd}", file=sys.stderr)
        print(f"  app_details.json: {Path(rd) / 'app_details.json'}", file=sys.stderr)
        print(f"  app_details.md  : {Path(rd) / 'app_details.md'}", file=sys.stderr)

    if args.json_output:
        # apps 내 raw_hint 제외하고 진단 요약만 출력
        summary = {
            "session_status": output.get("session_status"),
            "app_count": output.get("app_count"),
            "result_dir": rd,
            "apps": [
                {
                    "app_id": a["app_id"],
                    "app_name_hint": a.get("app_name_hint", ""),
                    "diagnosis": a.get("diagnosis", []),
                    "biz_app": (a.get("biz") or {}).get("biz_app"),
                    "login_activated": (a.get("login") or {}).get("login_activated"),
                    "redirect_uri": (a.get("login") or {}).get("redirect_uri_registered"),
                    "web_platform": (a.get("platform") or {}).get("web_registered"),
                    "scope_pending": (a.get("scope") or {}).get("has_pending"),
                    "scope_rejected": (a.get("scope") or {}).get("has_rejected"),
                    "scope_biz_required": (a.get("scope") or {}).get("biz_required_items"),
                }
                for a in (output.get("apps") or [])
            ],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
