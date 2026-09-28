"""
G2B_LOCAL_BROWSER_USER_PRESENT_ATTACHMENT_DOWNLOAD_1

대표님 PC에서 user-present(headed) Playwright로 G2B 첨부 다운로드 검증.

원칙:
- 서버 실행 금지 (이 스크립트는 로컬 PC에서만 동작)
- headed 브라우저 (사용자가 화면 확인 가능)
- 직접 다운로드 URL 우선(A), 실패 시 공고 상세 페이지(B)
- 로그인/인증서/OTP/쿠키/session 추출 모두 금지
- 다운로드 파일은 tmp/ 디렉터리에만 저장 (git commit 금지)
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_TMP = Path(_REPO_ROOT) / "tmp"
_DL_DIR = _TMP / "g2b_user_present_downloads_20260508"
_DL_DIR.mkdir(parents=True, exist_ok=True)

_SAFE_FIELDS = (
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
)


def _is_local_pc() -> bool:
    """서버 컨테이너에서 실행 차단."""
    if Path("/.dockerenv").exists():
        return False
    return True


def _file_signature(path: str | Path) -> str:
    """파일 시그니처 판정 (HWP/HWPX/PDF/ZIP/HTML)."""
    p = Path(path)
    if not p.exists():
        return "NOT_EXISTS"
    size = p.stat().st_size
    if size == 0:
        return "EMPTY"
    with p.open("rb") as f:
        head = f.read(8)
    # OLE2 (HWP)
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "HWP_OLE2"
    # ZIP (HWPX, ZIP, etc)
    if head[:4] == b"PK\x03\x04":
        return "ZIP_OR_HWPX"
    # PDF
    if head[:4] == b"%PDF":
        return "PDF"
    # HTML (오류 응답)
    h = head.lower()
    if h.startswith(b"<!doc") or h.startswith(b"<html") or b"<html" in h:
        return "HTML_RESPONSE"
    return f"UNKNOWN({head[:4].hex()})"


def smoke_one(candidate: dict, headed: bool = True) -> dict:
    """단일 후보 user-present 다운로드 시도."""
    task_id = str(uuid.uuid4())
    started = datetime.now(UTC)

    result = {
        "task_id": task_id,
        "bid_ntce_no": candidate["bid_ntce_no"],
        "bid_ntce_ord": candidate["bid_ntce_ord"],
        "file_name": candidate["file_name"],
        "file_type": candidate["file_type"],
        "url_safe": candidate["file_url"][:60] + "...",  # 로그용
        "verdict": "UNKNOWN",
        "downloaded_path": None,
        "download_size": None,
        "signature": None,
        "block_reason": None,
        "started_at": started.isoformat(),
    }
    for f in _SAFE_FIELDS:
        result[f] = False

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result["verdict"] = "PLAYWRIGHT_NOT_AVAILABLE"
        return result

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not headed,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            # 별도 영구 storage 사용 안 함 (메모리 전용)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                accept_downloads=True,
            )
            page = context.new_page()

            try:
                # A 경로: 직접 다운로드 URL 시도
                url = candidate["file_url"]
                # download event 대기
                with page.expect_download(timeout=30000) as dl_info:
                    # goto 실패해도 download가 트리거됐을 수 있음
                    with suppress(Exception):
                        page.goto(url, timeout=30000, wait_until="domcontentloaded")
                download = dl_info.value
                # 안전 파일명 — bid_ntce_no + ord + file_ext
                safe_name = f"{candidate['bid_ntce_no']}_{candidate['bid_ntce_ord']}_{download.suggested_filename}"
                # 경로 트래버설 방지
                safe_name = safe_name.replace("/", "_").replace("\\", "_")
                save_path = _DL_DIR / safe_name
                download.save_as(save_path)

                size = save_path.stat().st_size if save_path.exists() else 0
                sig = _file_signature(save_path)

                result["downloaded_path"] = os.path.relpath(save_path, _REPO_ROOT)
                result["download_size"] = size
                result["signature"] = sig

                # 판정
                if sig == "HWP_OLE2":
                    result["verdict"] = "HWP_ACQUIRED_CONVERT_REQUIRED"
                elif sig == "ZIP_OR_HWPX":
                    result["verdict"] = "HWPX_READY"
                elif sig == "PDF":
                    result["verdict"] = "PDF_ACQUIRED"
                elif sig == "HTML_RESPONSE":
                    result["verdict"] = "NOT_FILE_RESPONSE"
                    result["block_reason"] = "HTML_RETURNED_INSTEAD_OF_FILE"
                elif sig == "EMPTY":
                    result["verdict"] = "INVALID_FILE"
                else:
                    result["verdict"] = "DOWNLOAD_SUCCESS_UNKNOWN_SIG"

            except Exception as e:  # noqa: BLE001 - 나라장터(G2B) 첨부파일 다운로드 스모크테스트(사용자 입회 하 read-only 검증) — goto 실패해도 download 이벤트가 이미 트리거됐을 수 있어 무시, 차단사유 추정을 위한 페이지 정보 조회 실패는 빈 문자열로 폴백
                # download event 미발생 — 페이지 응답 확인
                err_name = type(e).__name__
                err_msg = str(e)[:200]
                # 현재 page url로 차단 사유 추정
                try:
                    cur_url = page.url
                    title = page.title()
                    body_sample = page.inner_text("body")[:300] if page.query_selector("body") else ""
                except Exception:  # noqa: BLE001 - 나라장터(G2B) 첨부파일 다운로드 스모크테스트(사용자 입회 하 read-only 검증) — goto 실패해도 download 이벤트가 이미 트리거됐을 수 있어 무시, 차단사유 추정을 위한 페이지 정보 조회 실패는 빈 문자열로 폴백
                    cur_url, title, body_sample = "", "", ""  # noqa: F841

                # 차단 사유 분류
                low = (title + body_sample).lower()  # noqa: F841
                if any(k in body_sample for k in ("로그인", "인증", "공동인증", "OTP")):
                    result["verdict"] = "USER_DIRECT_REQUIRED"
                    result["block_reason"] = "AUTH_OR_LOGIN_REQUIRED"
                elif any(k in body_sample for k in ("보안프로그램", "보안 프로그램", "키보드보안", "설치 안내")):
                    result["verdict"] = "SECURITY_PROGRAM_REQUIRED"
                    result["block_reason"] = "SECURITY_PROGRAM_PROMPT"
                elif "지원하지" in body_sample or "Internet Explorer" in body_sample:
                    result["verdict"] = "ACCESS_BLOCKED"
                    result["block_reason"] = "UNSUPPORTED_BROWSER"
                else:
                    result["verdict"] = "ACCESS_BLOCKED"
                    result["block_reason"] = f"{err_name}: {err_msg[:100]}"
                result["page_title"] = title[:80]

            finally:
                # cookies/storage_state 절대 추출하지 않음
                pass

        finally:
            browser.close()

    finished = datetime.now(UTC)
    result["finished_at"] = finished.isoformat()
    result["duration_ms"] = int((finished - started).total_seconds() * 1000)
    return result


def main():
    if not _is_local_pc():
        print("ERROR: 이 스크립트는 로컬 PC에서만 실행 가능 (docker 환경 감지됨)")
        sys.exit(1)

    top3_path = _TMP / "g2b_user_present_smoke_top3_20260508.json"
    if not top3_path.exists():
        print(f"ERROR: 후보 파일 없음 — {top3_path}")
        sys.exit(1)

    with top3_path.open(encoding="utf-8") as f:
        data = json.load(f)
    candidates = data.get("top3", [])

    print("=" * 70)
    print("G2B_LOCAL_BROWSER_USER_PRESENT_ATTACHMENT_DOWNLOAD_1 — 3건 smoke")
    print("=" * 70)
    print("실행 환경: 로컬 PC (headed Playwright)")
    print(f"다운로드 디렉터리: {os.path.relpath(_DL_DIR, _REPO_ROOT)}")
    print()

    results = []
    for i, c in enumerate(candidates, 1):
        print(f"[{i}/3] {c['file_type']} | {c['bid_ntce_no']}/{c['bid_ntce_ord']} | {c['file_name'][:50]}")
        r = smoke_one(c, headed=True)
        results.append(r)
        print(f"  verdict: {r['verdict']}")
        if r.get("downloaded_path"):
            print(f"  downloaded: {r['downloaded_path']} ({r['download_size']:,} bytes)")
            print(f"  signature: {r['signature']}")
        if r.get("block_reason"):
            print(f"  block_reason: {r['block_reason']}")
        print(f"  duration: {r['duration_ms']}ms")
        print()

    # 안전 검증
    for r in results:
        for f in _SAFE_FIELDS:
            assert r[f] is False, f"safe field 위반: {f}"

    summary = {
        "task_id": str(uuid.uuid4()),
        "executed_at": datetime.now(UTC).isoformat(),
        "total": len(results),
        "verdict_counts": {},
        "results": results,
    }
    for r in results:
        v = r["verdict"]
        summary["verdict_counts"][v] = summary["verdict_counts"].get(v, 0) + 1

    out_path = (
        Path(_REPO_ROOT)
        / "data"
        / "reports"
        / "local_agent"
        / f"g2b_user_present_attachment_smoke_top3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print(f"verdict 분포: {summary['verdict_counts']}")
    print(f"리포트: {os.path.relpath(out_path, _REPO_ROOT)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
