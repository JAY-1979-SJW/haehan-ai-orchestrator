"""네이버 메일 자동화

지원 작업:
  - inbox: 받은메일함 전체 추출 (페이지네이션 순회)
  - compose: 메일 작성 준비 (수신인/참조/제목/본문 입력, 발송은 별도 승인 필요)

발송(send) 정책:
  CLAUDE.md 규칙상 메일 전송은 매번 사용자 명시 승인이 필요한 비가역 작업.
  compose 단계는 자동 진행 가능하나, '보내기' 클릭은 send=True 명시 + 추가
  확인 절차를 거친다.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from contextlib import contextmanager

from .base import page_goto
from scripts.web_connector import get_page
from scripts.login_session import ensure_login
from scripts.logger import get_logger
from scripts import cdp_db
from scripts.gate import check as gate_check

_log = get_logger(__name__)

INBOX_URL = "https://mail.naver.com/v2/folders/0/all"
COMPOSE_URL = "https://mail.naver.com/v2/new"

# 검증된 셀렉터 (2026-05-11)
SEL_RECIPIENT = "#recipient_input_element"
SEL_REFERENCE = "#reference_input_element"
SEL_SUBJECT = "#subject_title"

_EXTRACT_INBOX_JS = r"""
() => {
    const items = document.querySelectorAll('[class*="mail_item"]');
    const out = [];
    items.forEach(it => {
        const cls = it.className || '';
        const m = cls.match(/mail-(\d+)/);
        const raw = (it.innerText || '').trim();
        const lines = raw.split(/[\r\n]+/).map(s => s.trim()).filter(Boolean);
        out.push({mid: m ? m[1] : '', lines: lines});
    });
    return out;
}
"""

_CLICK_NEXT_JS = r"""
() => {
    const pg = document.querySelector('[class*="pagination"]');
    if (!pg) return {clicked: false, reason: 'no pagination'};
    const btns = pg.querySelectorAll('button, a');
    for (const b of btns) {
        const t = (b.innerText || b.getAttribute('aria-label') || '').trim();
        if (t === '다음 페이지' || t.includes('다음 페이지')) {
            if (b.disabled || b.getAttribute('aria-disabled') === 'true') {
                return {clicked: false, reason: 'disabled'};
            }
            b.click();
            return {clicked: true};
        }
    }
    return {clicked: false, reason: 'not found'};
}
"""

_CLICK_FIRST_JS = r"""
() => {
    const pg = document.querySelector('[class*="pagination"]');
    if (!pg) return false;
    const btns = pg.querySelectorAll('button, a');
    for (const b of btns) {
        const t = (b.innerText || '').trim();
        if (t.includes('첫 페이지')) { b.click(); return true; }
    }
    return false;
}
"""


@contextmanager
def _mail_context(task: str, args: list[str], start_url: str):
    """메일 전용 컨텍스트 — 기존 탭 재사용 + 함수 종료 후 페이지 유지.

    site_base.task_context는 종료 시 close_page를 호출하므로 우회한다.
    작성 후 사용자가 페이지에서 직접 검토/발송 단계로 이어가도록 페이지를 닫지 않음.
    """
    _log.info("[naver] %s 시작 args=%s", task, args)
    page = get_page()
    if start_url:
        page.goto(start_url, timeout=30000)
    ensure_login(page, "naver")
    try:
        yield page
        _log.info("[naver] %s 완료 (페이지 유지)", task)
    except Exception as e:
        _log.error("[naver] %s 실패: %s", task, e)
        raise
    # finally에서 close_page 호출하지 않음 — 페이지 그대로 유지


def run(task: str, args: list[str]) -> None:
    """메일 작업 디스패처."""
    match task:
        case "inbox":
            _task_inbox(args)
        case "compose":
            _task_compose(args)
        case "attach" | "attachment":
            _task_attach(args)
        case "send":
            _task_send(args)
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")
            print("  사용 가능: inbox | compose | send")


def _parse_item(lines: list[str]) -> dict[str, str]:
    sender, subject, ts = "", "", ""
    for i, ln in enumerate(lines):
        if ln == "보낸 사람" and i + 1 < len(lines):
            sender = lines[i + 1]
        elif ln == "메일 제목" and i + 1 < len(lines):
            subject = lines[i + 1]
    for ln in reversed(lines):
        if re.match(r'^(오전|오후|\d{2}\.\d{2}\.\d{2}|\d{4}\.\d{2}\.\d{2}|\d{1,2}:\d{2}|\d+분 전|어제|오늘)', ln):
            ts = ln
            break
    return {"sender": sender, "subject": subject, "time": ts}


def list_inbox(page, max_pages: int = 8) -> list[dict[str, Any]]:
    """받은메일함 전체 메일을 페이지네이션으로 순회 수집.

    Args:
        page: Playwright Page (이미 로그인된 세션)
        max_pages: 최대 순회 페이지 수 (안전 상한)

    Returns:
        [{mid, sender, subject, time, lines}, ...]
    """
    if not page.url.startswith(INBOX_URL.rsplit("/", 1)[0]):
        page_goto(page, INBOX_URL)
    time.sleep(2.0)
    page.evaluate(_CLICK_FIRST_JS)
    time.sleep(1.5)

    seen: dict[str, dict[str, Any]] = {}
    for p in range(1, max_pages + 1):
        time.sleep(1.0)
        items = page.evaluate(_EXTRACT_INBOX_JS)
        new_count = 0
        for it in items:
            if it["mid"] and it["mid"] not in seen:
                parsed = _parse_item(it["lines"])
                seen[it["mid"]] = {"mid": it["mid"], **parsed, "lines": it["lines"]}
                new_count += 1
        print(f"  페이지 {p}: 추출 {len(items)}건 (신규 {new_count}), 누적 {len(seen)}건")
        if new_count == 0 and p > 1:
            break
        nxt = page.evaluate(_CLICK_NEXT_JS)
        if not nxt.get("clicked"):
            break
        time.sleep(1.5)

    return list(seen.values())


def _task_inbox(args: list[str]) -> None:
    """CLI: naver mail inbox [최대페이지]."""
    max_pages = int(args[0]) if args and args[0].isdigit() else 8
    print("\n[작업] 네이버 받은메일함 전체 추출")
    with _mail_context("mail-inbox", args, start_url=INBOX_URL) as page:
        mails = list_inbox(page, max_pages=max_pages)

    print(f"\n총 수집: {len(mails)}건")
    os.makedirs("data", exist_ok=True)
    out_path = "data/naver_mail_inbox.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(mails, f, ensure_ascii=False, indent=2)
    print(f"저장: {out_path}")

    print(f"\n{'#':>3} | {'발신자':<28} | {'시간':<10} | 제목")
    print("-" * 110)
    for i, m in enumerate(mails):
        s = (m.get("sender") or "")[:28]
        t = (m.get("time") or "")[:10]
        sub = (m.get("subject") or "")[:55]
        print(f"{i+1:>3} | {s:<28} | {t:<10} | {sub}")


def compose(
    page,
    to: str,
    cc: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    send: bool = False,
) -> dict[str, Any]:
    """메일 작성 페이지 진입 후 필드 채우기.

    Args:
        page: Playwright Page (이미 로그인)
        to: 수신인 이메일 (콤마로 다중 가능)
        cc: 참조 이메일
        subject: 제목
        body: 본문 (서명 위에 prepend, plain text)
        send: True여도 실제 발송은 별도 확인 필요. 본 함수는 prepare까지만 수행하고
              send=True인 경우 _click_send를 호출하는 별도 단계 분리 권장.

    Returns:
        {url, to_set, cc_set, subject_set, body_set, recipients_text}
    """
    # 항상 새 작성 페이지로 진입
    page_goto(page, COMPOSE_URL)
    time.sleep(3.0)
    main = page.frames[0]

    # 진입 직후 기존 칩(이전 임시저장 잔재) 제거.
    # DevTools 분석(2026-05-11) 결과 네이버 메일은 일반적으로 자동 복원하지 않고,
    # 임시저장된 작성 메일이 있던 경우에만 진입 시 칩이 함께 렌더됨.
    cleared = main.evaluate(
        r"""() => {
            const dels = document.querySelectorAll(
                'button[id^="mail_object_element_delete_button_"]'
            );
            let n = 0;
            dels.forEach(b => { try { b.click(); n++; } catch(e) {} });
            return n;
        }"""
    )
    if cleared:
        print(f"  진입 잔재 칩 제거: {cleared}개")
        time.sleep(0.6)

    result: dict[str, Any] = {"url": page.url, "cleared_chips": cleared}

    def _fill_chip(selector: str, value: str) -> bool:
        loc = main.locator(selector)
        loc.click()
        time.sleep(0.3)
        loc.fill(value)
        time.sleep(0.3)
        page.keyboard.press("Enter")
        time.sleep(1.0)
        return True

    # 수신인
    if to:
        to_list = [t.strip() for t in to.split(",") if t.strip()]
        for one in to_list:
            _fill_chip(SEL_RECIPIENT, one)
        result["to_set"] = to

    # 참조
    if cc:
        for one in [t.strip() for t in cc.split(",") if t.strip()]:
            _fill_chip(SEL_REFERENCE, one)
        result["cc_set"] = cc

    # 제목
    if subject:
        sub_loc = main.locator(SEL_SUBJECT)
        sub_loc.click()
        time.sleep(0.2)
        sub_loc.fill(subject)
        time.sleep(0.3)
        result["subject_set"] = subject

    # 본문: contenteditable이 있는 첫 iframe (메인 외)
    if body:
        try:
            editor_frame = None
            for f in page.frames:
                if f == main:
                    continue
                try:
                    has_ce = f.evaluate(
                        "() => document.querySelectorAll('[contenteditable=\"true\"]').length"
                    )
                    if has_ce:
                        editor_frame = f
                        break
                except Exception:
                    continue
            if editor_frame:
                editor_frame.evaluate(
                    """(text) => {
                        const ed = document.querySelector('[contenteditable="true"]');
                        if (!ed) return false;
                        ed.focus();
                        const p = document.createElement('p');
                        p.textContent = text;
                        ed.insertBefore(p, ed.firstChild);
                        return true;
                    }""",
                    body,
                )
                result["body_set"] = body
            else:
                result["body_set"] = "frame not found"
        except Exception as e:
            result["body_set"] = f"error: {e}"

    # 입력 후 최종 dedup 1회 — 의도하지 않은 중복/잔여 칩만 제거
    # (자동 복원은 일반적으로 없음. 만약 발송 직전에 또 발생하면 send() 단계에서 한번 더 처리)
    if to:
        to_list = [t.strip().lower() for t in to.split(",") if t.strip()]
        time.sleep(0.8)
        final_removed = main.evaluate(
            r"""(allowed) => {
                const allow = new Set(allowed);
                const seen = new Set();
                const wraps = document.querySelectorAll('[id^="mail_object_element_wrapper_to_"]');
                let removed = 0;
                wraps.forEach(w => {
                    const btn = w.querySelector('button[id^="mail_object_element_button_to_"]');
                    const val = btn ? (btn.innerText || '').trim().toLowerCase() : '';
                    const del = w.querySelector('button[id^="mail_object_element_delete_button_to_"]');
                    if (!val || !del) return;
                    if (!allow.has(val) || seen.has(val)) {
                        try { del.click(); removed++; } catch(e) {}
                    } else {
                        seen.add(val);
                    }
                });
                return removed;
            }""",
            to_list,
        )
        if final_removed:
            print(f"  중복/잔여 칩 제거: {final_removed}개")
        result["dedup_removed"] = final_removed

    # 최종 검증
    final_chips = main.evaluate(
        r"""() => {
            const wraps = document.querySelectorAll('[id^="mail_object_element_wrapper_to_"]');
            return Array.from(wraps).map(w => {
                const btn = w.querySelector('button[id^="mail_object_element_button_to_"]');
                return btn ? (btn.innerText || '').trim() : '';
            }).filter(Boolean);
        }"""
    )
    result["recipients_text"] = ", ".join(final_chips)
    result["final_chip_count"] = len(final_chips)

    return result


def send_mail(page) -> dict[str, Any]:
    """현재 작성 페이지에서 메일 발송 (사용자 승인 필수).

    Returns:
        {success, recipient, subject, error_msg}
    """
    gate_check("naver_mail_send")
    result: dict[str, Any] = {"success": False}
    main = page.frames[0]

    # 발송 전 최종 수신인 확인
    final_chips = main.evaluate(
        r"""() => {
            const wraps = document.querySelectorAll('[id^="mail_object_element_wrapper_to_"]');
            return Array.from(wraps).map(w => {
                const btn = w.querySelector('button[id^="mail_object_element_button_to_"]');
                return btn ? (btn.innerText || '').trim() : '';
            }).filter(Boolean);
        }"""
    )
    if not final_chips:
        result["error_msg"] = "수신인 없음"
        return result

    recipient = ", ".join(final_chips)
    result["recipient"] = recipient

    # 제목 확인
    subject = main.evaluate(
        f"""() => {{
            const el = document.querySelector('{SEL_SUBJECT}');
            return el ? (el.value || el.innerText || '').trim() : '';
        }}"""
    )
    result["subject"] = subject

    # DB에 발송 시작 기록
    mail_id = cdp_db.log_mail_send(
        site_name="naver",
        recipient=recipient,
        subject=subject,
        status="pending",
    )

    try:
        # 발송 버튼 클릭
        send_btn = main.evaluate(
            r"""() => {
                const btn = Array.from(document.querySelectorAll('button')).find(
                    b => (b.innerText || '').includes('보내기') || (b.getAttribute('aria-label') || '').includes('보내')
                );
                if (!btn) return {found: false};
                btn.click();
                return {found: true};
            }"""
        )
        if not send_btn.get("found"):
            cdp_db.update_mail_send(mail_id, "fail", error_msg="발송 버튼을 찾을 수 없음")
            result["error_msg"] = "발송 버튼을 찾을 수 없음"
            return result

        time.sleep(2.0)

        # 확인 팝업 처리 (있으면)
        confirmed = main.evaluate(
            r"""() => {
                const dialogs = document.querySelectorAll('[role="dialog"], .modal, .popup');
                let found = false;
                dialogs.forEach(d => {
                    const buttons = d.querySelectorAll('button');
                    buttons.forEach(b => {
                        if ((b.innerText || '').includes('확인') || (b.innerText || '').includes('확')
                            || (b.getAttribute('aria-label') || '').includes('확')) {
                            b.click();
                            found = true;
                        }
                    });
                });
                return found;
            }"""
        )
        if confirmed:
            time.sleep(1.5)

        # 발송 성공 확인 (받은편지함으로 이동 또는 완료 메시지)
        time.sleep(1.0)
        current_url = page.url
        is_sent = "folders" in current_url or "inbox" in current_url or current_url.endswith("/")

        if is_sent:
            cdp_db.update_mail_send(mail_id, "success")
            result["success"] = True
            _log.info("[naver] 메일 발송 완료: %s → %s", subject, recipient)
        else:
            cdp_db.update_mail_send(mail_id, "fail", error_msg="발송 확인 실패")
            result["error_msg"] = "발송 확인 실패"
            _log.warning("[naver] 메일 발송 확인 불가: %s", current_url)

    except Exception as e:
        cdp_db.update_mail_send(mail_id, "fail", error_msg=str(e))
        result["error_msg"] = str(e)
        _log.error("[naver] 메일 발송 중 오류: %s", e)

    return result


def _mail_option_value(args: list[str], prefix: str) -> str | None:
    for arg in args:
        text = str(arg)
        if text.startswith(prefix):
            return text.split("=", 1)[1]
    return None


def _mail_flag(args: list[str], name: str) -> bool:
    return name in args


def _parse_attach_files(args: list[str]) -> list[Path]:
    raw_values: list[str] = []
    file_one = _mail_option_value(args, "--file=")
    file_many = _mail_option_value(args, "--files=")
    if file_one:
        raw_values.append(file_one)
    if file_many:
        raw_values.extend(part for part in re.split(r"[;,]", file_many) if part.strip())
    raw_values.extend(str(arg) for arg in args if not str(arg).startswith("--"))
    seen: set[str] = set()
    paths: list[Path] = []
    for raw in raw_values:
        path = Path(raw).expanduser()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def attach_files(page, file_paths: list[str | Path]) -> dict[str, Any]:
    """Attach files to the current Naver Mail compose page without sending."""
    paths = [Path(p).expanduser() for p in file_paths]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        return {"ok": False, "error": "file_not_found", "missing": missing}
    if not page.url.startswith("https://mail.naver.com/v2/new"):
        return {"ok": False, "error": "compose_page_required", "url": page.url}

    selectors = [
        'input[type="file"]',
        'input[accept]',
    ]
    last_error = ""
    for frame in page.frames:
        for selector in selectors:
            try:
                loc = frame.locator(selector).first
                loc.set_input_files([str(p) for p in paths], timeout=5000)
                time.sleep(2.0)
                return {
                    "ok": True,
                    "attached_count": len(paths),
                    "files": [{"name": p.name, "size": p.stat().st_size} for p in paths],
                    "url": page.url,
                }
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)[:200]
                continue

    try:
        main = page.frames[0]
        clicked = main.evaluate(
            r"""() => {
                const buttons = Array.from(document.querySelectorAll('button, a, label'));
                const target = buttons.find(el => {
                    const text = (el.innerText || el.getAttribute('aria-label') || el.title || '').trim();
                    return text.includes('첨부') || text.toLowerCase().includes('attach');
                });
                if (!target) return false;
                target.click();
                return true;
            }"""
        )
        if clicked:
            time.sleep(1.0)
            for frame in page.frames:
                try:
                    loc = frame.locator('input[type="file"]').first
                    loc.set_input_files([str(p) for p in paths], timeout=5000)
                    time.sleep(2.0)
                    return {
                        "ok": True,
                        "attached_count": len(paths),
                        "files": [{"name": p.name, "size": p.stat().st_size} for p in paths],
                        "url": page.url,
                    }
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)[:200]
    except Exception as exc:  # noqa: BLE001
        last_error = str(exc)[:200]

    return {"ok": False, "error": "file_input_not_found", "detail": last_error}


def _save_attach_record(record: dict[str, Any]) -> Path:
    out = Path("data") / "naver_mail_attach_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _task_attach(args: list[str]) -> None:
    """CLI: naver mail attach --file=<path> [--execute --approved --confirm=NAVER_APPROVED_ATTACH]."""
    paths = _parse_attach_files(args)
    dry_run = _mail_flag(args, "--dry-run") or not _mail_flag(args, "--execute")
    approved = _mail_flag(args, "--approved")
    confirm = _mail_option_value(args, "--confirm=") or ""

    if not paths:
        raise SystemExit("mail attach requires --file=PATH or --files=A.xlsx;B.pdf")
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise SystemExit(f"attachment file not found: {missing[0]}")
    if not dry_run and (not approved or confirm != "NAVER_APPROVED_ATTACH"):
        raise SystemExit("mail attach execute requires --approved --confirm=NAVER_APPROVED_ATTACH")

    plan = {
        "workflow": "naver_mail_attach",
        "dry_run": dry_run,
        "approval_required": True,
        "files": [{"name": p.name, "size": p.stat().st_size} for p in paths],
    }

    if dry_run:
        record = {**plan, "ok": True, "note": "dry-run only; no browser file attachment"}
        path = _save_attach_record(record)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        print(f"saved: {path}")
        return

    from scripts.gate import check as gate_check
    gate_check("browser.attach_file", risk="approve", force=approved, files=",".join(p.name for p in paths))
    page = get_page()
    result = attach_files(page, paths)
    record = {**plan, "ok": bool(result.get("ok")), "result": result}
    path = _save_attach_record(record)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    print(f"saved: {path}")


def _task_send(args: list[str]) -> None:
    """CLI: naver mail send.

    현재 열려 있는 작성 페이지의 메일을 발송.
    """
    print("\n[작업] 네이버 메일 발송")
    page = get_page()
    if not page.url.startswith("https://mail.naver.com/v2/new"):
        print("  ✗ 에러: 메일 작성 페이지가 열려있지 않습니다")
        return

    r = send_mail(page)
    if r.get("success"):
        print("\n✓ 발송 완료")
        print(f"  수신인: {r.get('recipient', '?')}")
        print(f"  제목: {r.get('subject', '(제목 없음)')}")
    else:
        print("\n✗ 발송 실패")
        print(f"  오류: {r.get('error_msg', '알 수 없는 오류')}")


def _task_compose(args: list[str]) -> None:
    """CLI: naver mail compose <수신인> [제목] [본문...].

    실제 발송은 하지 않음. 발송하려면 별도 명시 승인 + send 옵션이 필요.
    """
    if not args:
        print("  사용법: cdp_client.py naver mail compose <수신인> [제목] [본문...]")
        return
    to = args[0]
    subject = args[1] if len(args) > 1 else None
    body = " ".join(args[2:]) if len(args) > 2 else None

    print("\n[작업] 네이버 메일 작성 준비")
    print(f"  수신인: {to}")
    if subject:
        print(f"  제목: {subject}")
    if body:
        print(f"  본문: {body[:60]}...")

    with _mail_context("mail-compose", args, start_url=COMPOSE_URL) as page:
        r = compose(page, to=to, subject=subject, body=body, send=False)

    print("\n=== 작성 준비 완료 ===")
    print(f"  URL: {r.get('url')}")
    print(f"  최종 수신인 칩({r.get('final_chip_count', '?')}개): {r.get('recipients_text', '')}")
    if subject:
        print(f"  제목 입력: {r.get('subject_set')}")
    if body:
        print(f"  본문 입력: {r.get('body_set')}")
    print("\n⚠ 발송은 사용자 명시 승인 후 별도 단계에서 수행 (현재는 준비 단계).")


# ════════════════════════════════════════════════════════════════════════
# 신규: NaverMail 클래스 (NaverServices 통합 API용 wrapper)
# 기존 inbox/compose 함수와 별도. 기존 코드 보존.
# ════════════════════════════════════════════════════════════════════════

import time as _time_v2

try:
    from playwright.sync_api import Page as _Page_v2
except Exception:
    _Page_v2 = None


class NaverMail:
    """네이버 메일 wrapper (NaverServices 통합 API)."""

    MAIL_URL = "https://mail.naver.com/"

    def __init__(self, page):
        self.page = page

    def open(self) -> bool:
        from scripts.naver.auth import ensure_naver_login
        from scripts.popup_detector import handle_page_popups
        r = ensure_naver_login(self.page, return_url=self.MAIL_URL)
        if not r.get("ok"):
            return False
        self.page.goto(self.MAIL_URL, timeout=20000, wait_until="domcontentloaded")
        _time_v2.sleep(2.5)
        try:
            handle_page_popups(self.page, timeout_s=1.5)
        except Exception:
            pass
        return True

    def list_inbox(self, limit: int = 20) -> list:
        if not self.open():
            return []
        try:
            return self.page.evaluate("""
            (limit) => {
                const rows = document.querySelectorAll('.mail_list li, [class*="MailList"] li, .list_mail tr, tbody tr');
                const out = [];
                for (let i = 0; i < Math.min(rows.length, limit); i++) {
                    const r = rows[i];
                    const subject = r.querySelector('.subject, [class*="subject"]')?.innerText?.trim() || '';
                    const sender = r.querySelector('.from, .sender, [class*="sender"]')?.innerText?.trim() || '';
                    const date = r.querySelector('.date, .time, [class*="date"]')?.innerText?.trim() || '';
                    const unread = r.classList.contains('unread') || r.querySelector('.unread') !== null;
                    if (subject || sender) out.push({subject, sender, date, unread});
                }
                return out;
            }
            """, limit)
        except Exception:
            return []

    def search(self, query: str, limit: int = 20) -> list:
        if not self.open():
            return []
        try:
            self.page.locator('input[type="search"], input[placeholder*="검색"]').first.fill(query, timeout=3000)
            self.page.keyboard.press("Enter")
            _time_v2.sleep(2.5)
            return self.list_inbox(limit=limit)
        except Exception:
            return []

    def compose(self, to: str, subject: str, body: str, send: bool = False) -> dict:
        """메일 작성 (기본 임시저장, send=True 시 발송)."""
        from scripts.critical_logger import log_critical
        if not self.open():
            return {"ok": False, "error": "open_failed"}
        try:
            self.page.locator('a:has-text("메일쓰기"), .btn_write').first.click(timeout=5000)
            _time_v2.sleep(2)
            self.page.locator('input[name="to"], input[placeholder*="받는사람"]').first.fill(to, timeout=3000)
            _time_v2.sleep(0.3)
            self.page.locator('input[name="subject"], input[placeholder*="제목"]').first.fill(subject, timeout=3000)
            _time_v2.sleep(0.3)
            body_el = self.page.locator('iframe.iframe_body, [contenteditable="true"]').first
            body_el.click(timeout=3000)
            _time_v2.sleep(0.5)
            self.page.keyboard.type(body, delay=10)
            _time_v2.sleep(0.5)
            if send:
                gate_check("naver_mail_send")
                self.page.locator('button:has-text("보내기"), .btn_send').first.click(timeout=3000)
                _time_v2.sleep(3)
                log_critical("MAIL_SEND", f"네이버 메일 발송: {subject[:30]}", to=to)
                return {"ok": True, "mode": "sent"}
            else:
                self.page.locator('button:has-text("임시저장"), .btn_temp_save').first.click(timeout=3000)
                _time_v2.sleep(2)
                return {"ok": True, "mode": "draft"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
