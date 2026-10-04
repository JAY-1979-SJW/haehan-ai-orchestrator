"""하나팩스 전송결과 읽기 — 건별 최종 결과(전송 성공/실패)를 **읽기 전용**으로 가져온다.

기준서: docs/specs/2026-10-02_hanafax_auto_send.md §14·§15
- 로그인 후 전송결과 화면(`HanaFax_SendList_combin.asp`)의 표만 읽는다. 삭제·예약취소·저장 버튼은 누르지 않는다.
- 엔진과 같은 락을 써서 발송·미리보기와 동시에 사이트를 쓰지 않는다.
- 표는 중첩 표라 가장 안쪽 행의 셀 텍스트만 쓰고, 열 위치가 아닌 **셀 내용 패턴**으로 해석한다(화면 개편에 덜 민감).
- 수신번호는 한 건짜리 전송에서만 보이고 여러 명이면 `+` 와 "외 N명" 으로 표시된다(건 단위 결과만 확정 가능).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

log = logging.getLogger("hanafax.send_result")

_BASE_URL = "https://www.hanafax.com"
_RESULT_URL = f"{_BASE_URL}/HanaFax/HanaFax_SendList_combin.asp"
_RETENTION = re.compile(r"^~\d{4}\.\d{2}\.\d{2}$")
_DIGITS = re.compile(r"^\d{1,5}$")
_PHONE = re.compile(r"^\d{8,12}$")
_STATUS = re.compile(r"^전송\s*(성공|실패|중)|^예약")
_TODAY = re.compile(r"^오늘\s+(\d{1,2}):(\d{2})$")
_DATE_ONLY = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})$")
_EXTRA = re.compile(r"^외\s*(\d+)명$")
_JOB = re.compile(r"^#job=(\d+)$")


def _parse_when(text: str, now: datetime) -> tuple[datetime | None, bool]:
    """전송일 칸 → (시각, 분 단위까지 아는지). '오늘 08:59' 는 분까지, '2026.09.08' 은 날짜만 안다."""
    m = _TODAY.match(text)
    if m:
        return now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0), True
    m = _DATE_ONLY.match(text)
    if m:
        return now.replace(
            year=int(m.group(1)), month=int(m.group(2)), day=int(m.group(3)), hour=0, minute=0, second=0, microsecond=0
        ), False
    return None, False


def parse_rows(rows: list[list[str]], now: datetime) -> list[dict[str, Any]]:
    """안쪽 행의 셀 텍스트 목록 → 전송결과 레코드. 해석할 수 없는 행은 건너뛴다."""
    results: list[dict[str, Any]] = []
    for cells in rows:
        texts = [c.strip() for c in cells]
        if not any(_RETENTION.match(t) for t in texts):
            continue
        try:
            start = next(i for i, t in enumerate(texts) if _RETENTION.match(t))
            filled = [(i, t) for i, t in enumerate(texts) if t and i > start]
            title = filled[0][1]
            after_title = [t for i, t in filled if i > filled[0][0]]
            number = next((t for t in after_title if _PHONE.match(t) or t == "+"), "")
            tail = after_title[after_title.index(number) + 1 :] if number in after_title else after_title
            counts = [int(t) for t in tail if _DIGITS.match(t)][:3]
            status = next((t for t in tail if _STATUS.match(t)), "")
            when_text = next((t for t in reversed(texts) if _TODAY.match(t) or _DATE_ONLY.match(t)), "")
            extra = next((int(m.group(1)) for t in texts if (m := _EXTRA.match(t))), 0)
            job_id = next((m.group(1) for t in texts if (m := _JOB.match(t))), "")
        except (StopIteration, ValueError, IndexError):
            continue
        if len(counts) < 3 or not status:
            continue
        when, minute_known = _parse_when(when_text, now)
        results.append(
            {
                "title": title,
                "number": number if _PHONE.match(number) else "",  # 여러 명이면 '+' → 빈 값
                "total": counts[0],
                "success": counts[1],
                "failure": counts[2],
                "status": status,
                "extra_recipients": extra,
                "job_id": job_id,  # 세부내역 조회용 건 ID(없으면 빈 값)
                "when": when,
                "minute_known": minute_known,
            }
        )
    return results


# 데이터 행은 안쪽에 표(수신번호 펼침용)를 품고 있으므로 '가장 안쪽 행'이 아니라 **직계 셀에 보관기한(~YYYY.MM.DD)이 있는 행**을 읽는다
_JS_ROWS = r"""() => Array.from(document.querySelectorAll('tr')).map(tr => {
    const cells = Array.from(tr.querySelectorAll(':scope > td')).map(c => c.innerText.replace(/\s+/g, ' ').trim());
    const a = tr.querySelector('a[href*="detail("]');
    const m = a ? /detail\((\d+)/.exec(a.getAttribute('href') || '') : null;
    if (m) cells.push('#job=' + m[1]);
    return cells;
}).filter(r => r.some(t => /^~\d{4}\.\d{2}\.\d{2}$/.test(t)))"""


def fetch_results(page_size_label: str = "50개씩") -> list[dict[str, Any]]:
    """전송결과 첫 쪽을 읽어 레코드 목록을 돌려준다(최신순). 로그인 실패 등은 예외."""
    from scripts.hanafax import sender as engine
    from scripts.hanafax.auth import get_credentials

    uid, pwd = get_credentials()
    if not uid or not pwd:
        raise RuntimeError("하나팩스 자격증명이 없습니다")
    with engine._LOCK:
        return _read(uid, pwd, page_size_label)


def _read(uid: str, pwd: str, page_size_label: str) -> list[dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        try:
            context = browser.new_context(locale="ko-KR", viewport={"width": 1280, "height": 1000})
            page = context.new_page()
            page.on("dialog", lambda d: d.dismiss())
            page.goto(_BASE_URL, wait_until="domcontentloaded", timeout=20_000)
            page.fill('input[name="struid"]', uid)
            page.fill('input[name="strpwd"]', pwd)
            page.evaluate("document.querySelector('form').submit()")
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
            page.wait_for_timeout(1_500)
            if not any(c["name"] == "Login" for c in context.cookies()):
                raise RuntimeError("하나팩스 로그인 실패")
            page.goto(_RESULT_URL, wait_until="domcontentloaded", timeout=20_000)
            page.wait_for_timeout(2_000)
            try:  # 더 많이 보이게 50개씩(실패해도 첫 10건으로 진행)
                page.select_option('select[name="pagesize"]', label=page_size_label, timeout=3_000)
                page.wait_for_load_state("domcontentloaded", timeout=10_000)
                page.wait_for_timeout(1_500)
            except Exception as exc:  # noqa: BLE001 - 보조 동작
                log.info("페이지 크기 변경 생략: %s", type(exc).__name__)
            return parse_rows(page.evaluate(_JS_ROWS), datetime.now().astimezone())
        finally:
            browser.close()


def within(record_time: datetime, site_time: datetime, minutes: int = 10) -> bool:
    """앱 기록 시각과 사이트 전송 시각이 비슷한지(분 단위 표시·시계 차이를 감안)."""
    return abs(record_time - site_time) <= timedelta(minutes=minutes)


# ── 세부내역(번호별 결과) ───────────────────────────────────────────────────────────
# 건의 제목을 펼치면(`detail(건ID, 0)`) 기본정보(수신번호 전체)와 **사유별 인원** 표가 나온다. 인원 숫자 링크(`get_submitList(건ID, 구분)`)는
# `pop_sendDetail.asp` 팝업에 번호별 전송완료시간을 보여 준다 → 일부만 성공한 혼합 결과도 번호별로 확정할 수 있다.
_SUCCESS_LABELS = ("완료", "받음")  # '완료'·'일부 페이지 전송 완료'·'사람, 자동응답기 받음(참조)' — 발송완료(과금)
_PHONE_TEXT = re.compile(r"\b(0\d{1,2})-?(\d{3,4})-?(\d{4})\b")


def classify_label(label: str) -> str:
    """사유 구분 → 'success'(발송완료) | 'fail'(발송 미완료: 통화 중·잘못된 번호·응답 없음·수신거부·회선불량·기타)."""
    return "success" if any(key in label for key in _SUCCESS_LABELS) else "fail"


def parse_numbers(text: str) -> list[str]:
    """텍스트에서 전화번호를 숫자만 남겨 순서대로(중복 제거) 뽑는다."""
    seen: dict[str, None] = {}
    for m in _PHONE_TEXT.finditer(text):
        seen.setdefault("".join(m.groups()), None)
    return list(seen)


_JS_DETAIL = r"""() => {
    const cell = (label) => {
        const td = Array.from(document.querySelectorAll('td')).find(t => t.innerText.trim() === label);
        return td && td.nextElementSibling ? td.nextElementSibling.innerText.trim() : '';
    };
    const cats = Array.from(document.querySelectorAll('a')).map(a => {
        const m = /get_submitList\((\d+),\s*(\d+)\)/.exec(a.getAttribute('href') || '');
        if (!m) return null;
        const td = a.closest('td'); const tr = a.closest('tr');
        const cells = Array.from(tr.children).map(c => c.innerText.replace(/\s+/g, ' ').trim());
        const idx = Array.from(tr.children).indexOf(td);
        return {sub: parseInt(m[2], 10), count: parseInt(a.innerText, 10) || 0, label: idx > 0 ? cells[idx - 1] : ''};
    }).filter(Boolean);
    return {numbers: cell('수신번호'), status: cell('전송상태'), done_at: cell('완료일시'), categories: cats};
}"""


def fetch_job_detail(job_id: str) -> dict[str, Any]:
    """건 하나의 번호별 최종 결과를 읽는다 → {numbers, outcomes{번호: success|fail}, labels{번호: 사유}, status}. 읽기 전용."""
    from scripts.hanafax import sender as engine
    from scripts.hanafax.auth import get_credentials

    if not re.fullmatch(r"\d{1,12}", str(job_id)):
        raise ValueError("건 ID 가 올바르지 않습니다")
    uid, pwd = get_credentials()
    if not uid or not pwd:
        raise RuntimeError("하나팩스 자격증명이 없습니다")
    with engine._LOCK:
        return _read_detail(uid, pwd, str(job_id))


def _read_detail(uid: str, pwd: str, job_id: str) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context(locale="ko-KR", viewport={"width": 1280, "height": 1000})
            page = context.new_page()
            page.on("dialog", lambda d: d.dismiss())
            page.goto(_BASE_URL, wait_until="domcontentloaded", timeout=20_000)
            page.fill('input[name="struid"]', uid)
            page.fill('input[name="strpwd"]', pwd)
            page.evaluate("document.querySelector('form').submit()")
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
            page.wait_for_timeout(1_500)
            page.goto(_RESULT_URL, wait_until="domcontentloaded", timeout=20_000)
            page.wait_for_timeout(2_000)
            page.evaluate(f"detail({job_id}, 0)")  # 제목 클릭과 같은 사이트 함수(홍보 레이어에 가려져도 동작)
            page.wait_for_timeout(3_000)
            info = page.evaluate(_JS_DETAIL)
            outcomes: dict[str, str] = {}
            labels: dict[str, str] = {}
            for cat in info["categories"]:
                if cat["count"] <= 0:
                    continue
                with context.expect_page(timeout=8_000) as popup:
                    page.evaluate(f"get_submitList({job_id}, {cat['sub']})")
                detail = popup.value
                detail.wait_for_load_state("domcontentloaded")
                detail.wait_for_timeout(1_000)
                for number in parse_numbers(detail.inner_text("body")):
                    outcomes[number] = classify_label(cat["label"])
                    labels[number] = cat["label"]
                detail.close()
            return {"numbers": parse_numbers(info["numbers"]), "status": info["status"], "outcomes": outcomes, "labels": labels}
        finally:
            browser.close()
