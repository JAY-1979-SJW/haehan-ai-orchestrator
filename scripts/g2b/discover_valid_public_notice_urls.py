#!/usr/bin/env python
"""
G2B 공개 공고 유효 URL Discovery 스크립트

기존 허용 fixture URL actual-live read → content validator 적용 →
CONTENT_VALID_PASS가 아닌 경우 해당 페이지 앵커 후보 수집 →
policy/gate 분류 후 safe 후보만 순차 actual-live read →
CONTENT_VALID_PASS 후보 기록.

실행 환경: 사용자 PC (local-agent 환경) 전용
서버에서 실행 금지.

결과:
- data/reports/g2b/g2b_public_notice_valid_url_discovery_YYYYMMDD_HHMMSS.json
- docs/reports/g2b_public_notice_valid_url_discovery_YYYYMMDD.md
- tests/fixtures/g2b_public_notice_valid_url_candidates_YYYYMMDD.json

주의:
- click/type/fill/submit/download 실행 없음
- cookie/session/token/password/otp 저장 없음
- max-depth 1 고정
- 서버 환경 실행 금지
- 과도한 반복 접속 금지 (요청 사이 대기)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from ai_orchestrator.connectors.g2b.g2b_public_notice_content_validator import (  # noqa: E402
    CONTENT_INVALID,
    CONTENT_VALID_PASS,
    REACHABLE_BUT_NOT_CONTENT_VALID,
    enrich_live_result_with_content_verdict,
)
from ai_orchestrator.connectors.g2b.g2b_public_notice_dryrun_adapter import (  # noqa: E402
    evaluate_g2b_public_notice_dryrun,
)
from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (  # noqa: E402
    GATE_READONLY_EXECUTION_CANDIDATE,
    evaluate_g2b_public_notice_execution_gate,
)
from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (  # noqa: E402
    _check_playwright_available,
    run_g2b_public_notice_readonly_live,
)

_FIXTURE_DEFAULT = _repo_root / "tests" / "fixtures" / "g2b_public_notice_workflow_fixture_20260507.json"
_REPORT_JSON_DIR = _repo_root / "data" / "reports" / "g2b"
_REPORT_MD_DIR = _repo_root / "docs" / "reports"
_FIXTURE_OUT_DIR = _repo_root / "tests" / "fixtures"

_ALLOWED_DOMAINS: frozenset[str] = frozenset({"g2b.go.kr", "www.g2b.go.kr"})
_NEEDS_VERIFICATION_DOMAINS: frozenset[str] = frozenset({"shop.g2b.go.kr", "api.g2b.go.kr"})

_BLOCKED_HREF_PATTERNS: tuple[str, ...] = (
    "/login",
    "/cert",
    "/bid_submit",
    "/contract",
    "/payment",
    "/download",
    "/upload",
    "egovuserreqstlogin",
    "usercert",
    "ptb05001p",
    "ctb01001",
    "checkout",
    "ptb04001p",
)
_DOWNLOAD_HREF_PATTERNS: tuple[str, ...] = (
    "/file/download",
    "fileDown",
    "attachDown",
    ".hwp",
    ".hwpx",
    ".pdf",
    ".zip",
    ".xls",
    ".xlsx",
    ".doc",
)

_BODY_TEXT_MAX = 1000
_REQUEST_DELAY_SEC = 1.5


def _load_fixture_allowed_urls(fixture_path: Path) -> list[dict[str, Any]]:
    with fixture_path.open(encoding="utf-8") as f:
        data = json.load(f)
    cases = data if isinstance(data, list) else data.get("cases", [])
    allowed = []
    for c in cases:
        # expected_verdict 또는 expected.verdict 지원
        expected_verdict = c.get("expected_verdict") or (
            c.get("expected", {}).get("verdict") if isinstance(c.get("expected"), dict) else None
        )
        if expected_verdict == "ALLOWED":
            op = c.get("operation", "read")
            if op in ("read", "open_url", "navigate"):
                allowed.append({"id": c.get("id", ""), "url": c["url"], "operation": op})
    return allowed


def _extract_anchors_from_page(page: Any, base_url: str) -> list[str]:
    """페이지에서 앵커 href를 추출한다. click/submit 없음."""
    hrefs: list[str] = []
    try:
        links = page.query_selector_all("a[href]")
        for link in links:
            href = link.get_attribute("href") or ""
            href = href.strip()
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue
            if not href.startswith("http"):
                href = urljoin(base_url, href)
            hrefs.append(href)
    except Exception:  # noqa: BLE001 - 나라장터 공고 URL 탐색(읽기 전용) -- 앵커 추출 실패 시 빈 리스트, 페이지 방문 전체 실패도 빈 리스트 반환(수집 실패가 다른 URL 탐색을 막지 않도록)
        pass
    return hrefs


def _classify_href(href: str) -> str:
    parsed = urlparse(href)
    netloc = parsed.netloc
    lower = href.lower()
    if netloc in _NEEDS_VERIFICATION_DOMAINS:
        return "needs_verification"
    if netloc not in _ALLOWED_DOMAINS:
        return "external"
    if any(p in lower for p in _BLOCKED_HREF_PATTERNS):
        return "blocked"
    if any(p in lower for p in _DOWNLOAD_HREF_PATTERNS):
        return "blocked"
    return "safe"


def _run_live_read_with_anchors(
    url: str,
    operation: str,
    forbid_mock: bool,
    fail_on_mock: bool,
) -> dict[str, Any]:
    """live runner를 호출하고 페이지 앵커도 함께 수집한다."""
    dryrun = evaluate_g2b_public_notice_dryrun(url=url, operation=operation)
    gate_result = evaluate_g2b_public_notice_execution_gate(dryrun)
    if gate_result.get("gate_verdict") != GATE_READONLY_EXECUTION_CANDIDATE:
        return {
            "input_url": url,
            "final_url": url,
            "title": "",
            "body_text_sample": "",
            "body_text_length": 0,
            "verdict": "GATE_BLOCKED",
            "mock_used": False,
            "local_agent_used": False,
            "server_browser_used": False,
            "links": [],
            "error": f"gate_verdict={gate_result.get('gate_verdict')}",
        }

    # live runner는 playwright를 사용해 실제 브라우저에서 실행
    live_result = run_g2b_public_notice_readonly_live(
        candidate=gate_result,
        forbid_mock=forbid_mock,
        actual_live_required=fail_on_mock,
    )

    # 앵커 추출은 live runner 내부에서 page 객체 접근이 필요하므로
    # 별도 playwright 실행으로 수집 (read-only)
    links: list[str] = _collect_anchors_via_playwright(url)
    live_result["links"] = links
    return live_result


def _collect_anchors_via_playwright(url: str) -> list[str]:
    """Playwright로 페이지를 열어 앵커 href만 수집한다. click/submit 없음."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            hrefs = _extract_anchors_from_page(page, url)
            browser.close()
        return hrefs
    except Exception:  # noqa: BLE001 - 나라장터 공고 URL 탐색(읽기 전용) -- 앵커 추출 실패 시 빈 리스트, 페이지 방문 전체 실패도 빈 리스트 반환(수집 실패가 다른 URL 탐색을 막지 않도록)
        return []


def _build_markdown_report(report: dict[str, Any], run_ts: str) -> str:
    lines = [
        "# G2B 공개 공고 유효 URL Discovery 보고서",
        "",
        f"- 실행일시: {run_ts}",
        f"- actual_live_required: {report.get('actual_live_required')}",
        f"- mock_used: {report.get('mock_used')}",
        f"- local_agent_used: {report.get('local_agent_used')}",
        f"- server_browser_used: {report.get('server_browser_used')}",
        "",
        "## 기존 fixture 콘텐츠 판정 요약",
        "",
        f"- 총 허용 fixture: {report.get('fixture_allowed_count', 0)}",
        f"- CONTENT_VALID_PASS: {report.get('content_valid_pass_count', 0)}",
        f"- REACHABLE_BUT_NOT_CONTENT_VALID: {report.get('reachable_but_not_valid_count', 0)}",
        f"- CONTENT_INVALID: {report.get('content_invalid_count', 0)}",
        f"- CONTENT_UNKNOWN: {report.get('content_unknown_count', 0)}",
        "",
        "## 후보 URL 수집 결과",
        "",
        f"- 전체 후보: {report.get('total_candidates', 0)}",
        f"- safe 후보: {report.get('safe_candidate_count', 0)}",
        f"- blocked 후보: {report.get('blocked_candidate_count', 0)}",
        f"- needs_verification 후보: {report.get('needs_verification_candidate_count', 0)}",
        "",
        "## Discovery CONTENT_VALID_PASS 후보",
        "",
    ]
    valid_candidates = report.get("content_valid_pass_candidates", [])
    if valid_candidates:
        for c in valid_candidates:
            lines.append(f"- {c.get('url', '')} — {c.get('title', '')}")
    else:
        lines.append("- 없음 (WARN: 발견된 CONTENT_VALID_PASS 후보 없음)")
    lines += [
        "",
        "## 정책 준수",
        "",
        "- click/type/fill/submit/download 실행: 없음",
        "- cookie/session/token/password/otp 저장: 없음",
        "- max-depth: 1",
        "- 서버 브라우저 G2B 접속: 없음",
        "- wildcard 도메인 허용: 없음",
        "- 기존 fixture 직접 수정: 없음",
        "- DB write: 없음",
        "",
        "## 케이스별 상세",
        "",
    ]
    for item in report.get("fixture_results", []):
        lines.append(f"### {item.get('id', '')} — {item.get('url', '')}")
        lines.append(f"- live_verdict: {item.get('live_verdict', '')}")
        lines.append(f"- content_verdict: {item.get('content_verdict', '')}")
        lines.append(f"- invalid_reason: {item.get('content_invalid_reason', '')}")
        lines.append(f"- positive_signals: {item.get('positive_signals', [])}")
        lines.append(f"- negative_signals: {item.get('negative_signals', [])}")
        lines.append(f"- safe_candidates: {item.get('safe_candidate_count', 0)}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="G2B 공개 공고 유효 URL Discovery")
    parser.add_argument("--mode", default="actual-live", choices=["actual-live"])
    parser.add_argument("--forbid-mock", action="store_true", default=True)
    parser.add_argument("--require-local-agent", action="store_true", default=True)
    parser.add_argument("--fail-on-mock", action="store_true", default=True)
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--max-depth", type=int, default=1)
    parser.add_argument("--no-click", action="store_true", default=True)
    parser.add_argument("--no-download", action="store_true", default=True)
    parser.add_argument("--fixture", type=Path, default=_FIXTURE_DEFAULT)
    args = parser.parse_args()

    # max-depth 강제 1
    max_depth = 1

    # 서버 환경 차단
    if os.environ.get("IS_SERVER_ENV", "").lower() == "true":
        print("[FAIL] IS_SERVER_ENV=true 서버 환경에서 실행 금지", file=sys.stderr)
        sys.exit(1)

    # playwright 확인
    pw_check = _check_playwright_available()
    if not pw_check.get("playwright_available"):
        print(f"[FAIL] playwright 없음: {pw_check.get('error')}", file=sys.stderr)
        sys.exit(1)
    if not pw_check.get("chromium_available"):
        print("[FAIL] chromium 없음", file=sys.stderr)
        sys.exit(1)

    run_ts = datetime.now(UTC).isoformat()
    ts_label = datetime.now().strftime("%Y%m%d_%H%M%S")
    date_label = datetime.now().strftime("%Y%m%d")

    allowed_cases = _load_fixture_allowed_urls(args.fixture)
    print(f"[INFO] fixture 허용 케이스 {len(allowed_cases)}개 로드")

    fixture_results: list[dict[str, Any]] = []
    content_valid_pass_count = 0
    reachable_but_not_valid_count = 0
    content_invalid_count = 0
    content_unknown_count = 0
    mock_used = False
    local_agent_used = False
    server_browser_used = False

    all_safe_candidates: list[str] = []
    all_blocked_candidates: list[str] = []
    all_needs_v_candidates: list[str] = []

    # ── 1. 기존 허용 fixture actual-live 읽기 + content 판정 ──────────────────
    seen_urls: set[str] = set()
    for case in allowed_cases:
        url = case["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        print(f"[INFO] fixture live read: {url}")

        live_result = _run_live_read_with_anchors(
            url=url,
            operation=case["operation"],
            forbid_mock=args.forbid_mock,
            fail_on_mock=args.fail_on_mock,
        )
        time.sleep(_REQUEST_DELAY_SEC)

        if live_result.get("mock_used"):
            mock_used = True
        if live_result.get("local_agent_used"):
            local_agent_used = True
        if live_result.get("server_browser_used"):
            server_browser_used = True

        enriched = enrich_live_result_with_content_verdict(live_result)
        cv = enriched.get("content_verdict", "CONTENT_UNKNOWN")
        print(f"  → live_verdict={live_result.get('verdict')} content_verdict={cv}")

        links: list[str] = live_result.get("links", [])
        safe_c, blocked_c, needs_v_c = [], [], []
        for href in links:
            cls = _classify_href(href)
            if cls == "safe":
                safe_c.append(href)
            elif cls == "blocked":
                blocked_c.append(href)
            elif cls == "needs_verification":
                needs_v_c.append(href)

        all_safe_candidates.extend(safe_c)
        all_blocked_candidates.extend(blocked_c)
        all_needs_v_candidates.extend(needs_v_c)

        if cv == CONTENT_VALID_PASS:
            content_valid_pass_count += 1
        elif cv == REACHABLE_BUT_NOT_CONTENT_VALID:
            reachable_but_not_valid_count += 1
        elif cv == CONTENT_INVALID:
            content_invalid_count += 1
        else:
            content_unknown_count += 1

        fixture_results.append(
            {
                "id": case["id"],
                "url": url,
                "operation": case["operation"],
                "live_verdict": live_result.get("verdict", ""),
                "content_verdict": cv,
                "content_invalid_reason": enriched.get("content_invalid_reason", ""),
                "positive_signals": enriched.get("positive_signals", []),
                "negative_signals": enriched.get("negative_signals", []),
                "title": live_result.get("title", ""),
                "body_text_length": live_result.get("body_text_length", 0),
                "mock_used": live_result.get("mock_used", False),
                "local_agent_used": live_result.get("local_agent_used", False),
                "server_browser_used": live_result.get("server_browser_used", False),
                "safe_candidate_count": len(safe_c),
                "blocked_candidate_count": len(blocked_c),
                "needs_verification_candidate_count": len(needs_v_c),
            }
        )

    # ── 2. safe 후보 URL discovery (depth=1, 최대 N개) ────────────────────────
    unique_safe = list(dict.fromkeys(all_safe_candidates))
    safe_to_check = [u for u in unique_safe if u not in seen_urls][: args.max_candidates]
    print(f"[INFO] safe 후보 {len(unique_safe)}개 중 {len(safe_to_check)}개 discovery 실행")

    content_valid_pass_candidates: list[dict[str, Any]] = []

    for url in safe_to_check:
        print(f"[INFO] candidate live read: {url}")
        gate_result = evaluate_g2b_public_notice_execution_gate({"input_url": url, "operation": "read"})
        if gate_result.get("gate_verdict") != GATE_READONLY_EXECUTION_CANDIDATE:
            print("  → gate blocked, skip")
            continue

        live_result = _run_live_read_with_anchors(
            url=url,
            operation="read",
            forbid_mock=args.forbid_mock,
            fail_on_mock=args.fail_on_mock,
        )
        time.sleep(_REQUEST_DELAY_SEC)

        if live_result.get("mock_used"):
            mock_used = True
        if live_result.get("local_agent_used"):
            local_agent_used = True
        if live_result.get("server_browser_used"):
            server_browser_used = True

        enriched = enrich_live_result_with_content_verdict(live_result)
        cv = enriched.get("content_verdict", "CONTENT_UNKNOWN")
        print(f"  → content_verdict={cv}")

        if cv == CONTENT_VALID_PASS:
            content_valid_pass_candidates.append(
                {
                    "url": url,
                    "title": live_result.get("title", ""),
                    "content_verdict": cv,
                    "positive_signals": enriched.get("positive_signals", []),
                }
            )

    # ── 3. fail-on-mock 검사 ─────────────────────────────────────────────────
    if args.fail_on_mock and mock_used:
        print("[FAIL] mock 사용 감지됨 (--fail-on-mock)", file=sys.stderr)
        sys.exit(2)

    # ── 4. 보고서 구성 ───────────────────────────────────────────────────────
    unique_blocked = list(dict.fromkeys(all_blocked_candidates))
    unique_needs_v = list(dict.fromkeys(all_needs_v_candidates))

    report: dict[str, Any] = {
        "run_at": run_ts,
        "actual_live_required": True,
        "mock_used": mock_used,
        "local_agent_used": local_agent_used,
        "server_browser_used": server_browser_used,
        "fixture_path": str(args.fixture),
        "fixture_allowed_count": len(allowed_cases),
        "content_valid_pass_count": content_valid_pass_count,
        "reachable_but_not_valid_count": reachable_but_not_valid_count,
        "content_invalid_count": content_invalid_count,
        "content_unknown_count": content_unknown_count,
        "total_candidates": len(unique_safe) + len(unique_blocked) + len(unique_needs_v),
        "safe_candidate_count": len(unique_safe),
        "blocked_candidate_count": len(unique_blocked),
        "needs_verification_candidate_count": len(unique_needs_v),
        "safe_candidate_urls": unique_safe,
        "blocked_candidate_urls": unique_blocked,
        "needs_verification_candidate_urls": unique_needs_v,
        "content_valid_pass_candidates": content_valid_pass_candidates,
        "fixture_results": fixture_results,
        "max_depth": max_depth,
        "no_click": True,
        "no_download": True,
        "policy_wildcard_allowed": False,
        "policy_login_blocked": True,
        "policy_cert_blocked": True,
        "policy_bid_blocked": True,
        "policy_contract_blocked": True,
        "policy_payment_blocked": True,
        "policy_download_auto_allowed": False,
        "policy_click_type_fill_submit_blocked": True,
        "policy_secret_token_saved": False,
        "policy_db_write": False,
    }

    # ── 5. 파일 저장 ─────────────────────────────────────────────────────────
    _REPORT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_MD_DIR.mkdir(parents=True, exist_ok=True)
    _FIXTURE_OUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = _REPORT_JSON_DIR / f"g2b_public_notice_valid_url_discovery_{ts_label}.json"
    md_path = _REPORT_MD_DIR / f"g2b_public_notice_valid_url_discovery_{date_label}.md"
    fixture_path = _FIXTURE_OUT_DIR / f"g2b_public_notice_valid_url_candidates_{date_label}.json"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[INFO] JSON 보고서: {json_path}")

    md_content = _build_markdown_report(report, run_ts)
    with md_path.open("w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[INFO] Markdown 보고서: {md_path}")

    candidate_fixture = {
        "generated_at": run_ts,
        "source_fixture": str(args.fixture),
        "fixture_content_verdicts": [
            {
                "id": r["id"],
                "url": r["url"],
                "content_verdict": r["content_verdict"],
                "invalid_reason": r["content_invalid_reason"],
            }
            for r in fixture_results
        ],
        "safe_candidate_urls": unique_safe,
        "content_valid_pass_candidates": content_valid_pass_candidates,
        "recommended_fixture_upgrade": bool(content_valid_pass_candidates),
        "mock_used": mock_used,
        "local_agent_used": local_agent_used,
        "server_browser_used": server_browser_used,
    }
    with fixture_path.open("w", encoding="utf-8") as f:
        json.dump(candidate_fixture, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 후보 fixture: {fixture_path}")

    # ── 6. 최종 판정 ─────────────────────────────────────────────────────────
    final_verdict = "PASS"
    if not local_agent_used:
        final_verdict = "WARN"
        print("[WARN] local_agent_used=False")
    if server_browser_used:
        final_verdict = "FAIL"
        print("[FAIL] server_browser_used=True")
    if mock_used:
        final_verdict = "FAIL"
        print("[FAIL] mock_used=True")
    if not content_valid_pass_candidates:
        if final_verdict == "PASS":
            final_verdict = "WARN"
        print("[WARN] CONTENT_VALID_PASS 후보 없음")

    print(f"\n[최종 판정] {final_verdict}")
    print(f"  fixture content_valid_pass={content_valid_pass_count}")
    print(f"  reachable_but_not_valid={reachable_but_not_valid_count}")
    print(f"  content_invalid={content_invalid_count}")
    print(f"  safe_candidates={len(unique_safe)}")
    print(f"  discovery_content_valid_pass={len(content_valid_pass_candidates)}")

    if final_verdict == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
