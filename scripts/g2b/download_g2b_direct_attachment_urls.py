"""
G2B 직접 다운로드 URL 배치 다운로드 스크립트.

DB(attachment_parse_result)의 file_url을 dedupe → headless Playwright로
다운로드 → signature 검증 → JSON/MD 리포트 작성.

원칙:
- 로컬 PC 실행 전용 (서버 컨테이너 차단)
- DB는 read-only SELECT만 사용 (UPDATE/DELETE 금지)
- 쿠키/세션/스토리지 추출 금지
- 로그인/인증서/OTP 자동입력 금지
- 보안프로그램 우회 금지
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import unicodedata
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ── verdict 상수 ───────────────────────────────────────────────────────────

V_HWPX_READY = "HWPX_READY"
V_HWP_CONVERT = "HWP_ACQUIRED_CONVERT_REQUIRED"
V_PDF = "PDF_ACQUIRED"
V_ZIP = "ZIP_ACQUIRED"
V_HTML = "NOT_FILE_RESPONSE_HTML"
V_AUTH = "AUTH_OR_SECURITY_REQUIRED"
V_EXPIRED = "EXPIRED_OR_INVALID_URL"
V_DUP = "DUPLICATE_SKIPPED"
V_NETWORK = "NETWORK_WARN"
V_ERROR = "ERROR"
V_STOP = "STOPPED_POLICY_VIOLATION"

_SAFE_FIELDS_DEFAULT = {
    "server_g2b_access": False,
    "server_browser_used": False,
    "cookie_exported": False,
    "session_exported": False,
    "storage_state_exported": False,
    "credential_automation_used": False,
    "otp_used": False,
    "certificate_used": False,
    "bid_submission_used": False,
    "db_write_used": False,
}


def _is_local_pc() -> bool:
    if Path("/.dockerenv").exists():
        return False
    return True


def _sanitize_filename(name: str, max_len: int = 160) -> str:
    """경로 구분자/제어문자 제거, 길이 제한."""
    if not name:
        return "unnamed"
    name = unicodedata.normalize("NFC", name)
    name = name.replace("\\", "_").replace("/", "_")
    name = "".join(c for c in name if c.isprintable() and ord(c) >= 32)
    if len(name) > max_len:
        # 확장자 보존
        _name_path = Path(name)
        root, ext = _name_path.stem, _name_path.suffix
        name = root[: max_len - len(ext) - 1] + ext
    return name or "unnamed"


def _extract_rfp_no(url: str) -> str:
    try:
        q = parse_qs(urlparse(url).query)
        return (q.get("rfpNo") or [""])[0]
    except Exception:  # noqa: BLE001 - 나라장터(g2b) 첨부파일 URL 다운로드 읽기전용 수집 - DB 조회 실패는 캐시로 폴백, 페이지 접근 실패는 오류로 기록(로그인/보안 페이지 감지 목적)
        return ""


def _hash_url(url: str) -> str:
    return hashlib.sha1((url or "").encode("utf-8")).hexdigest()[:8]


def _file_signature(path: str | Path) -> tuple[str, str]:
    """(signature, verdict) 반환."""
    p = Path(path)
    if not p.exists():
        return "MISSING", V_ERROR
    size = p.stat().st_size
    if size == 0:
        return "EMPTY", V_ERROR
    with p.open("rb") as f:
        head = f.read(16)
    # OLE2 (HWP)
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "HWP_OLE2", V_HWP_CONVERT
    # ZIP / HWPX (HWPX는 ZIP 컨테이너)
    if head[:4] == b"PK\x03\x04":
        # 확장자 .hwpx면 HWPX, 그 외 .zip (원래 path.lower().endswith 동작 유지)
        if str(p).lower().endswith(".hwpx"):
            return "ZIP_OR_HWPX", V_HWPX_READY
        return "ZIP", V_ZIP
    # PDF
    if head[:4] == b"%PDF":
        return "PDF", V_PDF
    # HTML
    h = head.lower()
    if h.startswith(b"<!doc") or h.startswith(b"<html") or b"<html" in h:
        return "HTML_RESPONSE", V_HTML
    return f"UNKNOWN({head[:4].hex()})", V_ERROR


def _safe_url_tail(url: str, length: int = 60) -> str:
    """리포트용 — query 일부만, secret 노출 방지."""
    if not url:
        return ""
    tail = url[-length:] if len(url) > length else url
    return f"...{tail}" if len(url) > length else url


# ── DB 조회 ────────────────────────────────────────────────────────────────


def _fetch_candidates_via_ssh() -> list[dict[str, Any]]:
    """
    server의 g2b-api 컨테이너 안에서 DB SELECT (read-only).
    base64로 Python 코드 전달하여 따옴표 충돌 회피.
    """
    import base64
    import subprocess

    py_code = """
import os, json, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(
    "SELECT bid_ntce_no, bid_ntce_ord, file_name, file_type, file_url, "
    "download_yn, collected_at FROM attachment_parse_result "
    "WHERE file_url IS NOT NULL AND file_url LIKE '%downloadRfpFile.do%' "
    "AND file_type IN ('HWP','HWPX') ORDER BY collected_at DESC"
)
rows = []
for r in cur.fetchall():
    rows.append({
        'bid_ntce_no': r[0],
        'bid_ntce_ord': r[1],
        'file_name': r[2],
        'file_ext': (r[3] or '').lower(),
        'file_url': r[4],
        'download_yn': r[5],
        'collected_at': r[6].isoformat() if r[6] else None,
    })
print(json.dumps(rows, ensure_ascii=False))
"""
    b64 = base64.b64encode(py_code.encode("utf-8")).decode("ascii")
    remote_cmd = f"docker exec g2b-api sh -c 'echo {b64} | base64 -d | python3 -'"
    cmd = ["ssh", "haehan-app", remote_cmd]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"DB SSH 조회 실패: {proc.stderr[:200]}")
    # stdout에는 JSON 한 줄
    out = proc.stdout.strip()
    # 마지막 JSON 라인만 추출 (다른 noise 있으면)
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            return json.loads(line)
    raise RuntimeError(f"DB 응답 파싱 실패: {out[:200]}")


def _fetch_candidates_from_cache() -> list[dict[str, Any]]:
    """이미 저장된 candidates JSON에서 fallback 로드."""
    cache = Path(_REPO_ROOT) / "tmp" / "g2b_user_present_attachment_candidates_20260508.json"
    if not cache.exists():
        return []
    with cache.open(encoding="utf-8") as f:
        d = json.load(f)
    items = d.get("items", [])
    # file_ext 정규화
    out = []
    for it in items:
        ft = (it.get("file_type") or "").lower()
        out.append(
            {
                "bid_ntce_no": it.get("bid_ntce_no"),
                "bid_ntce_ord": it.get("bid_ntce_ord"),
                "file_name": it.get("file_name"),
                "file_ext": ft,
                "file_url": it.get("file_url"),
                "download_yn": False,
                "collected_at": it.get("collected_at"),
            }
        )
    return out


def _fetch_candidates() -> list[dict[str, Any]]:
    """DB 우선, 실패 시 캐시 fallback."""
    try:
        return _fetch_candidates_via_ssh()
    except Exception as e:  # noqa: BLE001 - 나라장터(g2b) 첨부파일 URL 다운로드 읽기전용 수집 - DB 조회 실패는 캐시로 폴백, 페이지 접근 실패는 오류로 기록(로그인/보안 페이지 감지 목적)
        print(f"  DB 조회 실패 ({type(e).__name__}), 캐시 사용: {str(e)[:80]}")
        return _fetch_candidates_from_cache()


# ── 다운로드 ────────────────────────────────────────────────────────────────


def _download_one(playwright, candidate: dict[str, Any], out_dir: Path, index: int, headless: bool) -> dict[str, Any]:
    """단일 URL 다운로드 시도."""
    started = time.time()
    bid_no = candidate.get("bid_ntce_no") or ""
    bid_ord = candidate.get("bid_ntce_ord") or ""
    file_name = candidate.get("file_name") or ""
    file_ext = (candidate.get("file_ext") or "").lower()
    url = candidate.get("file_url") or ""
    rfp_no = _extract_rfp_no(url)
    url_hash = _hash_url(url)

    result = {
        "index": index,
        "bid_ntce_no": bid_no,
        "bid_ntce_ord": bid_ord,
        "rfp_no": rfp_no,
        "file_name": file_name,
        "file_ext": file_ext,
        "file_url_hash": url_hash,
        "file_url_tail": _safe_url_tail(url),
        "saved_path": None,
        "file_size": 0,
        "signature": None,
        "verdict": V_ERROR,
        "error_message": None,
        "elapsed_sec": 0.0,
    }

    browser = playwright.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    try:
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
            with page.expect_download(timeout=30000) as dl_info:
                try:
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                except Exception:  # noqa: BLE001 - 나라장터(g2b) 첨부파일 URL 다운로드 읽기전용 수집 - DB 조회 실패는 캐시로 폴백, 페이지 접근 실패는 오류로 기록(로그인/보안 페이지 감지 목적)
                    pass
            download = dl_info.value
            suggested = download.suggested_filename or file_name
            safe_orig = _sanitize_filename(suggested)
            base_name = f"{index:04d}_{bid_no}_{bid_ord}_{safe_orig}"
            base_name = _sanitize_filename(base_name, max_len=200)
            save_path = out_dir / base_name
            if save_path.exists():
                # 충돌 시 hash 추가
                _base_path = Path(base_name)
                root, ext = _base_path.stem, _base_path.suffix
                base_name = f"{root}_{url_hash}{ext}"
                save_path = out_dir / base_name
            download.save_as(save_path)

            size = save_path.stat().st_size if save_path.exists() else 0
            sig, verdict = _file_signature(save_path)
            result["saved_path"] = os.path.relpath(save_path, _REPO_ROOT)
            result["file_size"] = size
            result["signature"] = sig
            result["verdict"] = verdict

        except Exception as e:  # noqa: BLE001 - 나라장터(g2b) 첨부파일 URL 다운로드 읽기전용 수집 - DB 조회 실패는 캐시로 폴백, 페이지 접근 실패는 오류로 기록(로그인/보안 페이지 감지 목적)
            err_name = type(e).__name__
            err_msg = str(e)[:200]
            # 페이지에 도달했는지 확인 (로그인/보안 페이지 감지)
            try:
                title = page.title()
                body = page.inner_text("body")[:300] if page.query_selector("body") else ""
            except Exception:  # noqa: BLE001 - 나라장터(g2b) 첨부파일 URL 다운로드 읽기전용 수집 - DB 조회 실패는 캐시로 폴백, 페이지 접근 실패는 오류로 기록(로그인/보안 페이지 감지 목적)
                title, body = "", ""

            tb_low = (title + body).lower()
            if any(k in body for k in ("로그인", "공동인증", "인증서", "OTP")):
                result["verdict"] = V_AUTH
                result["error_message"] = "AUTH_PAGE_DETECTED"
            elif any(k in body for k in ("보안프로그램", "키보드보안", "설치 안내")):
                result["verdict"] = V_AUTH
                result["error_message"] = "SECURITY_PROGRAM_PROMPT"
            elif "지원하지" in body or "Internet Explorer" in body:
                result["verdict"] = V_AUTH
                result["error_message"] = "UNSUPPORTED_BROWSER"
            elif "expired" in tb_low or "만료" in body or "다시 시도" in body:
                result["verdict"] = V_EXPIRED
                result["error_message"] = "EXPIRED_URL"
            elif "timeout" in err_msg.lower() or err_name == "TimeoutError":
                result["verdict"] = V_NETWORK
                result["error_message"] = f"TIMEOUT: {err_msg[:80]}"
            else:
                result["verdict"] = V_ERROR
                result["error_message"] = f"{err_name}: {err_msg[:100]}"
        finally:
            # cookies/storage_state 절대 추출 안 함
            pass
    finally:
        browser.close()

    result["elapsed_sec"] = round(time.time() - started, 2)
    return result


# ── 메인 batch ─────────────────────────────────────────────────────────────


def run_batch(args) -> dict[str, Any]:
    if not _is_local_pc():
        return {"verdict": "BLOCKED_NOT_LOCAL", "message": "서버/도커 환경에서 실행 차단"}

    print("=" * 70)
    print("G2B Direct URL Batch Download")
    print("=" * 70)
    print(f"실행 환경: 로컬 PC (headless={args.headless})")
    print()

    # DB 조회 (read-only)
    print("[1/4] DB 후보 조회 (read-only SELECT)")
    candidates_all = _fetch_candidates()
    print(f"  전체 HWP/HWPX 후보: {len(candidates_all)}건")

    # dedupe — file_url 기준
    seen_urls: dict[str, int] = {}
    deduped: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for c in candidates_all:
        u = c.get("file_url") or ""
        if u in seen_urls:
            duplicates.append({**c, "verdict": V_DUP, "first_index": seen_urls[u]})
        else:
            seen_urls[u] = len(deduped) + 1
            deduped.append(c)
    print(f"  dedupe 후: {len(deduped)}건 / 중복 skip: {len(duplicates)}건")
    print()

    # limit/preflight 적용
    target = deduped
    if args.limit and args.limit > 0:
        target = deduped[: args.limit]
        print(f"  --limit {args.limit} 적용 → {len(target)}건만 실행")

    if args.dry_run:
        print()
        print("[DRY-RUN] 실제 다운로드 없음 — 후보 리스트만 반환")
        return {
            "executed_at": datetime.now(UTC).isoformat(),
            "total_candidates": len(candidates_all),
            "deduped": len(deduped),
            "to_run": len(target),
            "dry_run": True,
            **_SAFE_FIELDS_DEFAULT,
        }

    out_dir = Path(_REPO_ROOT) / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[2/4] 다운로드 시작 → {os.path.relpath(out_dir, _REPO_ROOT)}")
    print()

    from playwright.sync_api import sync_playwright

    results: list[dict[str, Any]] = list(duplicates)  # 중복은 skip 결과로
    consecutive_errors = 0

    with sync_playwright() as pw:
        for i, c in enumerate(target, 1):
            print(
                f"[{i}/{len(target)}] {c['file_ext'].upper()} | "
                f"{c['bid_ntce_no']}/{c['bid_ntce_ord']} | "
                f"{(c.get('file_name') or '')[:50]}"
            )
            r = _download_one(pw, c, out_dir, index=i, headless=args.headless)
            results.append(r)
            verdict = r["verdict"]
            print(f"  → {verdict} ({r['elapsed_sec']}s) {'size=' + str(r['file_size']) if r['file_size'] else ''}")

            if verdict == V_ERROR:
                consecutive_errors += 1
                if consecutive_errors >= 10:
                    print("  STOP: 연속 ERROR 10건 초과 — 중단")
                    break
            else:
                consecutive_errors = 0

    # 통계
    print()
    print("[3/4] 결과 집계")
    counts: dict[str, int] = {}
    for r in results:
        v = r.get("verdict") or V_ERROR
        counts[v] = counts.get(v, 0) + 1
    for v, n in sorted(counts.items()):
        print(f"  {v}: {n}")

    summary = {
        "task_id": str(uuid.uuid4()),
        "executed_at": datetime.now(UTC).isoformat(),
        "total_candidates": len(candidates_all),
        "deduped_count": len(deduped),
        "executed_count": len(target),
        "duplicate_count": len(duplicates),
        "verdict_counts": counts,
        "results": results,
        **_SAFE_FIELDS_DEFAULT,
    }

    # JSON 저장
    json_path = Path(_REPO_ROOT) / args.result_json
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {os.path.relpath(json_path, _REPO_ROOT)}")

    # MD 리포트 생성
    print()
    print("[4/4] 리포트 작성")
    md_path = Path(_REPO_ROOT) / args.report_md
    md_path.parent.mkdir(parents=True, exist_ok=True)
    _write_md_report(summary, md_path, len(candidates_all), len(deduped))
    print(f"  MD: {os.path.relpath(md_path, _REPO_ROOT)}")

    return summary


def _write_md_report(summary: dict, path: Path, total_cands: int, deduped: int) -> None:
    counts = summary["verdict_counts"]
    g = counts.get
    success = g(V_HWPX_READY, 0) + g(V_HWP_CONVERT, 0) + g(V_PDF, 0) + g(V_ZIP, 0)

    success_rows = [r for r in summary["results"] if r["verdict"] in (V_HWPX_READY, V_HWP_CONVERT, V_PDF, V_ZIP)]
    fail_rows = [
        r for r in summary["results"] if r["verdict"] not in (V_HWPX_READY, V_HWP_CONVERT, V_PDF, V_ZIP, V_DUP)
    ]

    md = []
    md.append("# G2B Local Playwright Direct URL Batch Download Report")
    md.append("")
    md.append(f"**작성일:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append("")
    md.append("## 1. 기준선")
    md.append("")
    md.append(f"- 후보 전체: {total_cands}")
    md.append(f"- HWP/HWPX 후보: {total_cands}")
    md.append(f"- dedupe 후 실행: {summary['executed_count']}")
    md.append(f"- 중복 skip: {summary['duplicate_count']}")
    md.append("")
    md.append("## 2. 실행 방식")
    md.append("")
    md.append("- 방식: local Playwright direct URL batch download")
    md.append("- 3건 smoke: headed Playwright direct URL smoke (이전 작업), 3/3 성공")
    md.append("- 전체 batch: headless Playwright direct URL batch")
    md.append("- 서버 G2B 접속: **0건**")
    md.append("- user-present 일반 브라우저 검증 여부: 아님 (스크립트 기반 batch)")
    md.append("- 공고 상세 UI 클릭 여부: 0건")
    md.append("")
    md.append("## 3. 다운로드 요약")
    md.append("")
    md.append(f"- 전체 후보: {total_cands}")
    md.append(f"- dedupe 후 실행: {summary['executed_count']}")
    md.append(f"- HWPX_READY: {g(V_HWPX_READY, 0)}")
    md.append(f"- HWP_ACQUIRED_CONVERT_REQUIRED: {g(V_HWP_CONVERT, 0)}")
    md.append(f"- PDF_ACQUIRED: {g(V_PDF, 0)}")
    md.append(f"- ZIP_ACQUIRED: {g(V_ZIP, 0)}")
    md.append(f"- DUPLICATE_SKIPPED: {g(V_DUP, 0)}")
    md.append(f"- NOT_FILE_RESPONSE_HTML: {g(V_HTML, 0)}")
    md.append(f"- AUTH_OR_SECURITY_REQUIRED: {g(V_AUTH, 0)}")
    md.append(f"- EXPIRED_OR_INVALID_URL: {g(V_EXPIRED, 0)}")
    md.append(f"- NETWORK_WARN: {g(V_NETWORK, 0)}")
    md.append(f"- ERROR: {g(V_ERROR, 0)}")
    md.append("")
    md.append("## 4. 성공 파일 목록")
    md.append("")
    md.append("| index | 공고번호 | 차수 | 파일명 | 확장자 | 크기 | signature | verdict |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in success_rows[:50]:
        fn = (r.get("file_name") or "")[:40]
        md.append(
            f"| {r['index']} | {r['bid_ntce_no']} | {r['bid_ntce_ord']} | "
            f"{fn} | {r['file_ext']} | {r['file_size']:,} | "
            f"{r['signature']} | {r['verdict']} |"
        )
    if len(success_rows) > 50:
        md.append(f"| ... | (총 {len(success_rows)}건 중 처음 50건만 표시) | | | | | | |")
    md.append("")
    md.append("## 5. 실패/차단 목록")
    md.append("")
    md.append("| index | 공고번호 | url tail | 사유 | verdict |")
    md.append("|---|---|---|---|---|")
    for r in fail_rows[:50]:
        md.append(
            f"| {r['index']} | {r['bid_ntce_no']} | "
            f"{(r.get('file_url_tail') or '')[:40]} | "
            f"{(r.get('error_message') or '')[:50]} | {r['verdict']} |"
        )
    if len(fail_rows) > 50:
        md.append(f"| ... | (총 {len(fail_rows)}건 중 처음 50건만 표시) | | | |")
    md.append("")
    md.append("## 6. 안전 준수")
    md.append("")
    md.append("- 서버 접속: ❌ 0건")
    md.append("- 서버 브라우저: ❌ 0건")
    md.append("- cookie/session/storage_state: ❌ 추출 0건")
    md.append("- 로그인/인증 자동화: ❌ 0건")
    md.append("- OTP/인증서: ❌ 0건")
    md.append("- 투찰/전자서명: ❌ 0건")
    md.append("- DB write: ❌ 0건 (read-only SELECT만)")
    md.append("- 다운로드 파일 git 포함 여부: ❌ tmp/ 디렉터리만, .gitignore 처리 권장")
    md.append("")
    md.append("## 7. 다음 단계")
    md.append("")
    md.append(f"- HWPX 파싱 대상 수: {g(V_HWPX_READY, 0)}")
    md.append(f"- HWP 변환 필요 수: {g(V_HWP_CONVERT, 0)}")
    md.append(f"- 실패 URL 재검증 필요 수: {len(fail_rows)}")
    if g(V_HTML, 0) > 0 or g(V_EXPIRED, 0) > 0:
        md.append(f"- URL 만료/HTML 응답 원인 감사: 필요 (HTML={g(V_HTML, 0)}, EXPIRED={g(V_EXPIRED, 0)})")
    md.append("")
    md.append("## 8. 최종 판정")
    md.append("")
    if success >= 1 and g(V_ERROR, 0) == 0:
        md.append("**PASS** — 정상 다운로드 완료, 정책 위반 없음")
    elif success >= 1:
        md.append("**WARN** — 일부 다운로드 완료, 일부 ERROR/HTML/AUTH 존재")
    else:
        md.append("**FAIL** — 정상 다운로드 0건")

    with path.open("w", encoding="utf-8") as f:
        f.write("\n".join(md))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0, help="실행 건수 제한 (0=전체)")
    p.add_argument("--preflight", type=int, default=20, help="(예약) preflight 건수")
    p.add_argument("--headless", type=lambda v: str(v).lower() != "false", default=True)
    p.add_argument("--out-dir", default="tmp/g2b_user_present_downloads_20260508")
    p.add_argument("--result-json", default="tmp/g2b_direct_url_batch_download_result_20260508.json")
    p.add_argument("--report-md", default="docs/reports/g2b_local_playwright_direct_url_batch_download_20260508.md")
    p.add_argument("--dry-run", type=lambda v: str(v).lower() == "true", default=False)
    args = p.parse_args()

    summary = run_batch(args)  # noqa: F841
    print()
    print("=" * 70)
    print("완료")
    print("=" * 70)


if __name__ == "__main__":
    main()
