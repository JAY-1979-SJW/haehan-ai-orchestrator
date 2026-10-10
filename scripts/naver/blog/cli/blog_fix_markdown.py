"""기존 발행 글의 마크다운 소제목(##)을 대괄호 형식으로 일괄 수정.

배경: 네이버 블로그는 마크다운을 렌더링하지 않아 `## 도입부`가 독자 화면에
그대로 노출되고 있었다(2026-08-19 확인, 131개 글 전체). content.py 는 이미
대괄호 형식으로 고쳤지만, 이미 올라간 글은 따로 수정해야 한다.

방식: 본문 전체를 덮어쓰면 첨부 이미지가 사라지므로, 스마트에디터를 열어
**텍스트 문단만 찾아 치환**한다. 이미지·구조는 건드리지 않는다.

  "## 도입부"          → "[도입부]"
  "### AI 동작 순서"   → "· AI 동작 순서"
  "## [AI 자동화 활용]" → "[AI 자동화 활용]"

사용:
    python -m scripts.naver.blog.cli.blog_fix_markdown --limit 1        # 1건만(테스트)
    python -m scripts.naver.blog.cli.blog_fix_markdown --limit 1 --apply # 실제 저장
    python -m scripts.naver.blog.cli.blog_fix_markdown --all --apply     # 전체
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
import time
from pathlib import Path

from scripts.naver.blog.accounts import DEFAULT_ACCOUNT

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.common.logger import get_logger  # noqa: E402

_log = get_logger("scripts.naver.blog.cli.blog_fix_markdown")

BLOG_ID = DEFAULT_ACCOUNT
CDP_URL = "http://127.0.0.1:9222"
CACHE = _ROOT / "data" / "blog_topic_cache.json"
STATE = _ROOT / "data" / "blog_markdown_fix_state.json"


def convert_heading(text: str) -> str | None:
    """마크다운 소제목 한 줄을 대괄호/불릿 형식으로. 대상이 아니면 None."""
    t = text.strip()
    m3 = re.match(r"^###\s+(.+)$", t)
    if m3:
        return f"· {m3.group(1).strip().strip('[]')}"
    m2 = re.match(r"^##\s+(.+)$", t)
    if m2:
        inner = m2.group(1).strip()
        # CTA 블록(📌)은 소제목이 아니라 안내문이라 대괄호를 씌우지 않는다.
        if inner.startswith("📌"):
            return inner
        if inner.startswith("[") and inner.endswith("]"):
            return inner
        return f"[{inner}]"
    return None


def load_targets() -> list[dict]:
    data = json.loads(CACHE.read_text(encoding="utf-8"))
    seen: set[str] = set()
    out = []
    for p in data.get("posted", []):
        ln = str(p.get("log_no") or "")
        if ln and ln not in seen:
            seen.add(ln)
            out.append({"log_no": ln, "title": p.get("title", "")})
    return out


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"done": [], "skipped": [], "failed": []}


def save_state(st: dict) -> None:
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def fix_one(page, log_no: str, apply: bool) -> dict:
    """편집기를 열어 마크다운 소제목 문단만 치환한다."""
    # SmartEditor3 는 iframe 없이 메인 페이지에 렌더링되고,
    # PostWriteForm.naver 가 logNo 로 기존 글을 불러온다(writer.py 참조).
    url = f"https://blog.naver.com/PostWriteForm.naver?blogId={BLOG_ID}&logNo={log_no}"
    page.goto(url, timeout=40000, wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    frame = page

    found = frame.evaluate(
        """() => {
        const out = [];
        document.querySelectorAll('.se-text-paragraph').forEach((el, i) => {
            const t = (el.innerText || '').trim();
            if (/^#{2,3}\\s+/.test(t)) out.push({i, text: t.split('\\n')[0].slice(0, 60)});
        });
        return out;
    }"""
    )
    if not found:
        return {"ok": True, "changed": 0, "note": "마크다운 없음"}

    if not apply:
        return {"ok": True, "changed": 0, "preview": [f["text"] for f in found]}

    # ⚠️ DOM textContent 직접 수정은 저장되지 않는다(2026-08-19 실측).
    # 스마트에디터는 내부 모델로 문서를 관리해서, DOM만 바꾸면 발행 시
    # 원본이 그대로 올라간다. 실제 클릭 + 키보드 입력으로 고쳐야 한다.
    changed = 0
    for item in found:
        new = convert_heading(item["text"])
        if not new:
            continue
        try:
            el = page.locator(".se-text-paragraph").nth(item["i"])
            el.click(timeout=8000)
            page.wait_for_timeout(250)
            # 해당 줄만 선택해서 교체 (Home → Shift+End)
            page.keyboard.press("Home")
            page.keyboard.press("Shift+End")
            page.wait_for_timeout(120)
            page.keyboard.type(new, delay=15)
            page.wait_for_timeout(220)
            changed += 1
        except Exception as e:  # noqa: BLE001 - 네이버 블로그 기존 글의 마크다운 서식 일괄 수정 스크립트 — 문단 수정 실패는 개별 warning 로그 후 다음 문단으로 계속, 발행 확인 팝업 클릭 실패도 무시(팝업 없으면 그냥 넘어감), 건별 실패는 failed 리스트에 기록되어 은폐되지 않으며 --apply 플래그로만 실제 저장됨.
            _log.warning("[md-fix] 문단 %s 수정 실패: %s", item["i"], str(e)[:70])

    if changed:
        _save_post(page, frame)
    return {"ok": True, "changed": changed}


def _save_post(page, frame) -> None:
    """스마트에디터 저장(발행) 버튼 클릭."""
    for label in ("발행", "저장"):
        try:
            frame.get_by_text(label, exact=True).first.click(timeout=6000)
            page.wait_for_timeout(2500)
            break
        except Exception:  # noqa: BLE001 - 네이버 블로그 기존 글의 마크다운 서식 일괄 수정 스크립트 — 문단 수정 실패는 개별 warning 로그 후 다음 문단으로 계속, 발행 확인 팝업 클릭 실패도 무시(팝업 없으면 그냥 넘어감), 건별 실패는 failed 리스트에 기록되어 은폐되지 않으며 --apply 플래그로만 실제 저장됨.
            continue
    # 발행 확인 팝업 — 클릭 실패도 무시(팝업 없으면 그냥 넘어감), 건별 실패는 failed 리스트에 기록되어 은폐되지 않음
    with contextlib.suppress(Exception):
        frame.get_by_text("발행", exact=True).last.click(timeout=6000)
    page.wait_for_timeout(4000)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true", help="실제 저장(미지정 시 탐지만)")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    targets = load_targets()
    st = load_state()
    todo = [t for t in targets if t["log_no"] not in st["done"]]
    if not args.all:
        todo = todo[: args.limit]

    print(f"대상 {len(todo)}건 (전체 {len(targets)}, 완료 {len(st['done'])})")
    if not args.apply:
        print("※ 탐지 모드 — 실제 저장하려면 --apply\n")

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        page = browser.contexts[0].pages[0]
        for i, t in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] {t['log_no']} {t['title'][:34]}")
            try:
                r = fix_one(page, t["log_no"], args.apply)
                if r.get("preview"):
                    for p in r["preview"][:6]:
                        print(f"    발견: {p}")
                elif r["changed"]:
                    print(f"    ✅ {r['changed']}개 소제목 수정")
                    st["done"].append(t["log_no"])
                else:
                    print(f"    - {r.get('note', '변경 없음')}")
                    st["skipped"].append(t["log_no"])
            except Exception as e:  # noqa: BLE001 - 네이버 블로그 기존 글의 마크다운 서식 일괄 수정 스크립트 — 문단 수정 실패는 개별 warning 로그 후 다음 문단으로 계속, 발행 확인 팝업 클릭 실패도 무시(팝업 없으면 그냥 넘어감), 건별 실패는 failed 리스트에 기록되어 은폐되지 않으며 --apply 플래그로만 실제 저장됨.
                print(f"    ❌ {str(e)[:90]}")
                st["failed"].append(t["log_no"])
            if args.apply:
                save_state(st)
                time.sleep(3)

    print(f"\n완료 {len(st['done'])} / 건너뜀 {len(st['skipped'])} / 실패 {len(st['failed'])}")


if __name__ == "__main__":
    main()
