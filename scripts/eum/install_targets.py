"""Verify EUM install-target rows from the live screen and optional Excel download."""

from __future__ import annotations

import contextlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.common.app_paths import repo_root
from scripts.eum.menu_actions import open_menu_page
from scripts.eum.sales_mail import DEFAULT_SOURCE, load_new_site_projects

ROOT = repo_root()


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


DATA_DIR = _eum_dir()
DOWNLOAD_DIR = DATA_DIR / "eum_downloads"
DEFAULT_EXCEL_PASSWORD = "Haehan2026!"

_TABLE_ROWS_JS = """
() => {
  const textOf = (el) => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
  const tables = Array.from(document.querySelectorAll('table'));
  return tables.map((table, tableIndex) => {
    const headers = Array.from(table.querySelectorAll('th')).map(textOf).filter(Boolean);
    const rows = Array.from(table.querySelectorAll('tbody tr')).map((tr) =>
      Array.from(tr.querySelectorAll('td')).map(textOf)
    ).filter((cells) => cells.some(Boolean));
    return {tableIndex, headers, rows};
  });
}
"""

INSTALL_TARGET_HEADERS = [
    "NO",
    "공사번호",
    "공제가입번호",
    "공사명",
    "현장주소",
    "업체명",
    "단말기설치 예정일",
    "단말기설치 예정대수",
    "시범사업장 여부",
    "관할지사",
    "담당자",
    "연락처",
    "이메일",
    "등록일",
    "공사시작일",
    "공사종료일",
]


def _row_to_dict(headers: list[str], cells: list[str]) -> dict[str, str]:
    return {
        str(headers[idx] if idx < len(headers) else f"col_{idx + 1}"): str(value) for idx, value in enumerate(cells)
    }


def run_default_search(page) -> dict[str, Any]:
    """Set broad date filters and click the search button."""
    actions: list[str] = []
    # EUM 신규현장 설치대상 전 페이지 읽기전용 수집 + 엑셀 다운로드 - 실패시 False/빈 문자열/ok:False 반환, 삭제/제출 없음
    with contextlib.suppress(Exception):
        page.locator("#__loading__").wait_for(state="hidden", timeout=10000)
    for selector in (
        "input[name='WEBMAN370M00_regDateRadio'][value='thisYear']",
        "input[name='WEBMAN370M00_planDateRadio'][value='thisYear']",
    ):
        locator = page.locator(selector).first
        if locator.count() > 0:
            try:
                locator.check(timeout=3000)
            except Exception:  # noqa: BLE001 - EUM 신규현장 설치대상 전 페이지 읽기전용 수집 + 엑셀 다운로드 - 실패시 False/빈 문자열/ok:False 반환, 삭제/제출 없음
                page.evaluate(
                    """(selector) => {
                      const el = document.querySelector(selector);
                      if (el) {
                        el.checked = true;
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                      }
                    }""",
                    selector,
                )
            actions.append(f"checked {selector}")

    button = page.get_by_role("button", name="조회", exact=True)
    if button.count() == 0:
        button = page.locator("button").filter(has_text="조회").last
    button.click(timeout=5000)
    page.wait_for_timeout(2500)
    return {"actions": actions, "clicked_search": True}


def extract_screen_rows(page) -> dict[str, Any]:
    """Extract visible install-target table rows from the current page."""
    tables = page.evaluate(_TABLE_ROWS_JS)
    candidates = []
    for table in tables:
        headers = table.get("headers") or []
        if "공사명" in headers and "이메일" in headers:
            candidates.append(table)
    table = candidates[-1] if candidates else (tables[-1] if tables else {"headers": [], "rows": []})
    raw_headers = table.get("headers") or []
    raw_rows = table.get("rows", [])
    headers = INSTALL_TARGET_HEADERS if len(raw_headers) == len(INSTALL_TARGET_HEADERS) else raw_headers
    usable_rows = [
        row for row in raw_rows if len(row) > 1 and not any("조회된" in cell and "없" in cell for cell in row)
    ]
    if headers == INSTALL_TARGET_HEADERS and usable_rows and all(len(row) < len(headers) for row in usable_rows[:4]):
        merged_rows = []
        pending: list[str] = []
        for row in usable_rows:
            pending.extend(row)
            if len(pending) >= len(headers):
                merged_rows.append(pending[: len(headers)])
                pending = pending[len(headers) :]
        usable_rows = merged_rows
    rows = [_row_to_dict(headers, row) for row in usable_rows]
    return {
        "headers": headers,
        "raw_headers": raw_headers,
        "visible_count": len(rows),
        "rows": rows,
    }


def _set_page_size_max(page) -> bool:
    """표시개수 select 를 100개(최대)로 설정. 화면 행이 20개로 제한되던 문제 해결."""
    try:
        ok = page.evaluate(
            """() => {
              for (const s of document.querySelectorAll('select')) {
                const o = [...s.options].find(o => /100/.test(o.text || ''));
                if (o) { s.value = o.value; s.dispatchEvent(new Event('change', {bubbles: true})); return true; }
              }
              return false;
            }"""
        )
        page.wait_for_timeout(1500)
        return bool(ok)
    except Exception:  # noqa: BLE001 - EUM 신규현장 설치대상 전 페이지 읽기전용 수집 + 엑셀 다운로드 - 실패시 False/빈 문자열/ok:False 반환, 삭제/제출 없음
        return False


def _click_page_button(page, num: int) -> bool:
    """페이지네이션 '번호' 버튼 클릭 (데이터 td 제외 — button 요소만)."""
    try:
        return bool(
            page.evaluate(
                """(n) => {
              const bs = [...document.querySelectorAll('button')]
                .filter(b => (b.textContent || '').trim() === String(n));
              if (bs.length) { bs[bs.length - 1].click(); return true; }
              const nx = [...document.querySelectorAll('button,a')]
                .find(e => /다음|next/i.test((e.textContent || '') + (e.getAttribute('title') || '')));
              if (nx) { nx.click(); return true; }
              return false;
            }""",
                num,
            )
        )
    except Exception:  # noqa: BLE001 - EUM 신규현장 설치대상 전 페이지 읽기전용 수집 + 엑셀 다운로드 - 실패시 False/빈 문자열/ok:False 반환, 삭제/제출 없음
        return False


def _accumulate_rows(page, seen: dict[str, dict[str, str]]) -> int:
    """현재 화면 행을 공사번호 기준으로 seen 에 누적하고 신규 추가 건수를 반환."""
    added = 0
    for row in extract_screen_rows(page).get("rows", []):
        key = row.get("공사번호") or row.get("공제가입번호")
        if key and key not in seen:
            seen[key] = row
            added += 1
    return added


def _first_row_text(page) -> str:
    try:
        return page.evaluate(
            "() => { const r = document.querySelector('tbody tr'); return r ? (r.innerText || '').slice(0, 40) : ''; }"
        )
    except Exception:  # noqa: BLE001 - EUM 신규현장 설치대상 전 페이지 읽기전용 수집 + 엑셀 다운로드 - 실패시 False/빈 문자열/ok:False 반환, 삭제/제출 없음
        return ""


def collect_all_install_targets(page, *, max_pages: int = 50, save: bool = True) -> dict[str, Any]:
    """WEBMAN370M00 신규현장 설치대상 '전 페이지' 전수 수집 (상시 수집).

    extract_screen_rows 는 현재 화면(보이는 1페이지, 기본 20개)만 추출하므로,
    표시개수를 100개로 키우고 페이지 버튼을 순회하며 공사번호 기준 dedup 누적한다.
    수집 결과를 DEFAULT_SOURCE(영업메일 소스)에 저장한다.
    """
    opened = open_menu_page(page, "WEBMAN370M00")
    if isinstance(opened, dict) and opened.get("ok") is False:
        return {"ok": False, "open": opened}
    run_default_search(page)
    _set_page_size_max(page)

    seen: dict[str, dict[str, str]] = {}

    _accumulate_rows(page, seen)  # 1페이지
    target = 2
    pages_visited = 1
    for _ in range(max_pages):
        prev = _first_row_text(page)
        if not _click_page_button(page, target):
            break
        # EUM 신규현장 설치대상 전 페이지 읽기전용 수집 + 엑셀 다운로드 - 실패시 False/빈 문자열/ok:False 반환, 삭제/제출 없음
        with contextlib.suppress(Exception):
            page.wait_for_function(
                "(prev) => { const r = document.querySelector('tbody tr'); return r && (r.innerText || '').slice(0, 40) !== prev; }",
                arg=prev,
                timeout=8000,
            )
        page.wait_for_timeout(800)
        if _accumulate_rows(page, seen) == 0:  # 같은 페이지 재추출(더 이상 진행 안 됨) → 종료
            break
        pages_visited = target
        target += 1

    rows = list(seen.values())
    result: dict[str, Any] = {"ok": True, "total": len(rows), "pages_visited": pages_visited}
    if save:
        DEFAULT_SOURCE.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_SOURCE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        result["saved_path"] = str(DEFAULT_SOURCE)
    return result


def compare_with_source(screen_rows: list[dict[str, str]], source: str | Path = DEFAULT_SOURCE) -> dict[str, Any]:
    """Compare visible screen rows with the saved extraction source."""
    try:
        source_rows = load_new_site_projects(source)
    except FileNotFoundError:
        return {"source_exists": False, "matches": [], "missing": screen_rows}

    by_project_no = {str(row.get("공사번호") or ""): row for row in source_rows}
    matches = []
    missing = []
    for row in screen_rows:
        project_no = str(row.get("공사번호") or "")
        source_row = by_project_no.get(project_no)
        if not source_row:
            missing.append(row)
            continue
        matches.append(
            {
                "공사번호": project_no,
                "screen_email": row.get("이메일", ""),
                "source_email": source_row.get("이메일", ""),
                "email_match": row.get("이메일", "") == source_row.get("이메일", ""),
                "screen_project": row.get("공사명", ""),
                "source_project": source_row.get("공사명", ""),
                "project_match": row.get("공사명", "") == source_row.get("공사명", ""),
            }
        )

    return {
        "source_exists": True,
        "source_total": len(source_rows),
        "matches": matches,
        "missing": missing,
        "all_visible_rows_in_source": not missing,
        "all_matched_emails": all(item["email_match"] for item in matches) if matches else False,
    }


def try_excel_download(page) -> dict[str, Any]:
    """Try clicking the visible Excel button and saving the downloaded file."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    button = page.locator("button:has-text('엑셀저장'), a:has-text('엑셀저장')").first
    if button.count() == 0:
        return {"attempted": False, "ok": False, "error": "Excel button not found"}

    try:
        with page.expect_download(timeout=15000) as download_info:
            button.click(timeout=5000)
        download = download_info.value
        suggested = download.suggested_filename or "eum_install_targets.xlsx"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = DOWNLOAD_DIR / f"{stamp}_{suggested}"
        download.save_as(str(save_path))
        return {
            "attempted": True,
            "ok": True,
            "saved_path": str(save_path),
            "suggested_filename": suggested,
            "size": save_path.stat().st_size if save_path.exists() else None,
        }
    except Exception as exc:  # noqa: BLE001 - EUM 신규현장 설치대상 전 페이지 읽기전용 수집 + 엑셀 다운로드 - 실패시 False/빈 문자열/ok:False 반환, 삭제/제출 없음
        return {"attempted": True, "ok": False, "error": str(exc)}


def download_install_targets_excel(
    page,
    *,
    password: str | None = None,
    reason_selector: str = "#chk_a1",
    output_dir: str | Path = DOWNLOAD_DIR,
) -> dict[str, Any]:
    """Run the full EUM Excel download flow for WEBMAN370M00."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    password = password or os.getenv("EUM_EXCEL_PASSWORD") or DEFAULT_EXCEL_PASSWORD
    events: dict[str, list[dict[str, Any]]] = {"requests": [], "responses": [], "downloads": [], "console": []}

    def save_download(download) -> dict[str, Any]:
        suggested = download.suggested_filename or "eum_install_targets.xlsx"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = output_dir / f"{stamp}_{suggested}"
        download.save_as(str(save_path))
        row = {
            "suggested_filename": suggested,
            "saved_path": str(save_path),
            "size": save_path.stat().st_size if save_path.exists() else None,
        }
        events["downloads"].append(row)
        return row

    page.on(
        "request",
        lambda req: (
            events["requests"].append({"method": req.method, "url": req.url, "type": req.resource_type})
            if "eum.cw.or.kr/api/" in req.url
            else None
        ),
    )
    page.on(
        "response",
        lambda res: (
            events["responses"].append(
                {
                    "status": res.status,
                    "url": res.url,
                    "content_type": res.headers.get("content-type", ""),
                    "content_disposition": res.headers.get("content-disposition", ""),
                }
            )
            if "eum.cw.or.kr/api/" in res.url
            else None
        ),
    )
    page.on("console", lambda msg: events["console"].append({"type": msg.type, "text": msg.text[:500]}))

    page.evaluate(
        "document.querySelectorAll('#xlsDownRsnAlert,#excelPswdAlert,#modalConfirm0').forEach((el) => el.remove())"
    )
    opened = open_menu_page(page, "WEBMAN370M00")
    if not opened.get("ok"):
        return {"ok": False, "step": "open", "open": opened, "events": events}

    search = run_default_search(page)
    page.wait_for_timeout(2500)

    excel_button = page.locator("div.bot_area div.right button.btn_s.btn_ty02.line:has-text('엑셀저장')").first
    if excel_button.count() == 0:
        excel_button = page.locator("button:has-text('엑셀저장')").first
    if excel_button.count() == 0:
        return {
            "ok": False,
            "step": "excel_button",
            "error": "Excel button not found",
            "search": search,
            "events": events,
        }

    excel_button.scroll_into_view_if_needed(timeout=5000)
    excel_button.click(timeout=5000)
    page.locator("#xlsDownRsnAlert").wait_for(state="attached", timeout=10000)
    page.locator(reason_selector).check(timeout=5000)
    page.locator("#xlsDownRsnAlertClose").first.click(timeout=5000)

    page.locator("#excelPswdAlert").wait_for(state="attached", timeout=10000)
    page.locator("#excelFilePswd").fill(password, timeout=5000)
    page.locator("#excelPswdAlertClose").first.click(timeout=5000)

    confirm = page.locator("#modalConfirm0 button:has-text('확인')").last
    if confirm.count() == 0:
        confirm = page.locator(".popup:has-text('데이터 추출을 시작합니다') button:has-text('확인')").last
    if confirm.count() == 0:
        return {
            "ok": False,
            "step": "final_confirm",
            "error": "Final confirm button not found",
            "search": search,
            "events": events,
        }

    downloaded = None
    with page.expect_download(timeout=90000) as download_info:
        confirm.click(timeout=5000)
    downloaded = save_download(download_info.value)

    result = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "url": page.url,
        "search": search,
        "download": downloaded,
        "events": events,
        "password": password,
    }
    path = output_dir / f"eum_install_targets_excel_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["saved_path"] = str(path)
    return result


def verify_install_targets(page, *, download: bool = True) -> dict[str, Any]:
    """Open WEBMAN370M00, verify visible rows, and optionally download Excel."""
    opened = open_menu_page(page, "WEBMAN370M00")
    if not opened.get("ok"):
        return {"ok": False, "open": opened}

    page.wait_for_timeout(1500)
    search = run_default_search(page)
    screen = extract_screen_rows(page)
    comparison = compare_with_source(screen["rows"])
    excel = try_excel_download(page) if download else {"attempted": False, "ok": False, "skipped": True}

    result = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "url": page.url,
        "search": search,
        "screen": screen,
        "comparison": comparison,
        "excel": excel,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"eum_install_targets_verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["saved_path"] = str(path)
    return result


def print_summary(result: dict[str, Any]) -> None:
    print("=" * 60)
    print("EUM install targets verification")
    print("=" * 60)
    print(f"ok: {result.get('ok')}")
    print(f"url: {result.get('url')}")
    screen = result.get("screen") or {}
    print(f"visible rows: {screen.get('visible_count', 0)}")
    print(f"headers: {', '.join((screen.get('headers') or [])[:20])}")
    comparison = result.get("comparison") or {}
    if comparison:
        print(f"source total: {comparison.get('source_total')}")
        print(f"visible rows in source: {comparison.get('all_visible_rows_in_source')}")
        print(f"emails matched: {comparison.get('all_matched_emails')}")
    excel = result.get("excel") or {}
    print(f"excel attempted: {excel.get('attempted')}")
    print(f"excel ok: {excel.get('ok')}")
    if excel.get("saved_path"):
        print(f"excel saved: {excel.get('saved_path')}")
    elif excel.get("error"):
        print(f"excel error: {excel.get('error')}")
    if result.get("saved_path"):
        print(f"saved: {result['saved_path']}")
    for row in (screen.get("rows") or [])[:3]:
        print(f"- {row.get('공사번호', '')} {row.get('공사명', '')} {row.get('이메일', '')}")


def print_excel_download_summary(result: dict[str, Any]) -> None:
    print("=" * 60)
    print("EUM install targets Excel download")
    print("=" * 60)
    print(f"ok: {result.get('ok')}")
    if result.get("step"):
        print(f"failed step: {result.get('step')}")
    if result.get("error"):
        print(f"error: {result.get('error')}")
    download = result.get("download") or {}
    if download:
        print(f"file: {download.get('saved_path')}")
        print(f"size: {download.get('size')}")
    password_masked = (
        "***" if (result.get("password") or os.getenv("EUM_EXCEL_PASSWORD") or DEFAULT_EXCEL_PASSWORD) else ""
    )
    print(f"password: {password_masked}")
    if result.get("saved_path"):
        print(f"log: {result.get('saved_path')}")
