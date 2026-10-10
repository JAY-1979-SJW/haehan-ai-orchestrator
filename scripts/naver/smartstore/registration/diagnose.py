"""상품 등록 시 발생하는 문제를 자동 탐색 + 진단.

진단 항목:
  1. 필수 필드 확인 (label에 '*' 또는 required)
  2. 이미지 업로드 영역 구조 (file input ↔ 용도 매핑)
  3. SmartEditor ONE iframe 진입 가능성
  4. 저장하기 클릭 시 발생 에러 메시지 수집
  5. 가격/재고/배송 등 누락 필드 탐지
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.browser.popup.popup_detector import close_popup_windows, handle_page_popups  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402
from scripts.naver.common.auth import ensure_naver_login  # noqa: E402
from scripts.naver.smartstore.product.product import REGISTER_URL, ProductRegister  # noqa: E402

_log = get_logger(__name__)


DIAGNOSE_JS = r"""
() => {
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };

    const result = {};

    // 1. 필수 표시(*) 또는 required 가진 필드들
    const required_fields = [];
    document.querySelectorAll('input, select, textarea').forEach(el => {
        if (!isVisible(el)) return;
        const type = (el.type || el.tagName).toLowerCase();
        if (type === 'hidden') return;
        const req = el.required || el.getAttribute('aria-required') === 'true' || el.hasAttribute('required');
        // 부모에서 * 또는 '필수' 텍스트
        let nearText = '';
        let parent = el.parentElement;
        for (let i = 0; i < 3 && parent; i++) {
            const t = (parent.innerText || '').substring(0, 200);
            if (/[*★]|필수/.test(t)) {
                nearText = t.replace(/\n+/g, ' ').substring(0, 100);
                break;
            }
            parent = parent.parentElement;
        }
        if (req || nearText) {
            required_fields.push({
                type, name: el.name || '', id: el.id || '',
                placeholder: el.placeholder || '',
                required_attr: req,
                near_text: nearText,
            });
        }
    });
    result.required_fields = required_fields;

    // 2. 모든 file input + 주변 컨텍스트
    const file_inputs = [];
    document.querySelectorAll('input[type="file"]').forEach((el, i) => {
        let parent = el.parentElement;
        let nearText = '';
        for (let j = 0; j < 5 && parent; j++) {
            const t = (parent.innerText || '').substring(0, 200);
            if (t && t.length > 5) {
                nearText = t.replace(/\n+/g, ' ').substring(0, 150);
                break;
            }
            parent = parent.parentElement;
        }
        const r = el.getBoundingClientRect();
        file_inputs.push({
            idx: i,
            accept: el.accept || '',
            multiple: el.multiple,
            name: el.name || '',
            id: el.id || '',
            visible: isVisible(el),
            position: {x: Math.round(r.x), y: Math.round(r.y + window.scrollY)},
            near_text: nearText,
        });
    });
    result.file_inputs = file_inputs;

    // 3. SmartEditor iframe 후보
    const iframes = [];
    document.querySelectorAll('iframe').forEach(f => {
        iframes.push({
            id: f.id || '',
            name: f.name || '',
            src: (f.src || '').substring(0, 150),
            cls: (f.className || '').substring(0, 80),
        });
    });
    result.iframes = iframes;

    // 4. 에러/검증 메시지 수집
    const errors = [];
    document.querySelectorAll(
        '[class*="error"]:not([class*="no-error"]), [class*="invalid"], ' +
        '[class*="warning"], .ng-invalid + [class*="message"], ' +
        '.form-error, [role="alert"]'
    ).forEach(el => {
        if (!isVisible(el)) return;
        const text = (el.innerText || '').trim();
        if (text && text.length < 200) {
            errors.push({
                text: text,
                cls: (el.className || '').substring(0, 60),
            });
        }
    });
    result.error_messages = errors;

    // 5. 모든 라벨 (각 입력 옆에 있는 텍스트)
    const labels = [];
    document.querySelectorAll('label, .label, dt, [class*="label-text"]').forEach(el => {
        if (!isVisible(el)) return;
        const text = (el.innerText || '').trim();
        if (text && text.length >= 2 && text.length < 30) {
            const r = el.getBoundingClientRect();
            labels.push({text: text, y: Math.round(r.y + window.scrollY)});
        }
    });
    // 중복 제거
    const seenLabel = new Set();
    result.labels = labels.filter(l => {
        if (seenLabel.has(l.text)) return false;
        seenLabel.add(l.text);
        return true;
    }).slice(0, 80);

    return result;
}
"""


def _enter_register_page(page) -> None:
    """등록 페이지 진입 + 전체 스크롤."""
    print("[1] 등록 페이지 진입")
    page.goto(REGISTER_URL, timeout=20000, wait_until="domcontentloaded")
    time.sleep(5)
    try:
        handle_page_popups(page, timeout_s=2.0)
        close_popup_windows(page)
    except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 필드 진단 스크립트(읽기전용 분석, 실제 저장 클릭 없음) — 팝업처리/스크롤/버튼탐색 실패는 무시하거나 진단결과에 오류 메시지만 기록
        pass

    # 페이지 전체 스크롤
    print("[2] 페이지 전체 스크롤 (필드 로드)")
    for y in range(0, 7000, 800):
        page.evaluate(f"window.scrollTo(0, {y})")
        time.sleep(0.5)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)


def _print_diag(diag) -> None:
    """진단 결과 출력."""
    # 출력
    print(f"\n=== 필수 필드 ({len(diag['required_fields'])}개) ===")
    for f in diag["required_fields"][:20]:
        print(f"  {f['type']:<10} name={f['name'][:25]:<27} id={f['id'][:20]:<22} req={f['required_attr']}")
        if f.get("near_text"):
            print(f"     주변: {f['near_text'][:80]}")

    print(f"\n=== 이미지 업로드 file input ({len(diag['file_inputs'])}개) ===")
    for fi in diag["file_inputs"]:
        v = "✓" if fi["visible"] else "✗"
        print(f"  [{fi['idx']}] {v} accept={fi['accept'][:30]:<32} multiple={fi['multiple']}")
        print(f"     id={fi['id']}, name={fi['name']}")
        print(f"     주변: {fi['near_text'][:100]}")

    print(f"\n=== iframe ({len(diag['iframes'])}개) ===")
    for f in diag["iframes"]:
        print(f"  id={f['id']:<20} name={f['name']:<20} src={f['src'][:80]}")

    print(f"\n=== 현재 에러 메시지 ({len(diag['error_messages'])}개) ===")
    for e in diag["error_messages"][:10]:
        print(f"  - {e['text']}")
        print(f"    cls={e['cls']}")

    print(f"\n=== 페이지 라벨 ({len(diag['labels'])}개 — 60자 이내) ===")
    for lb in diag["labels"][:40]:
        print(f"  y={lb['y']:>5}  {lb['text']}")


def _probe_save_button(page) -> None:
    """저장하기 버튼 위치 확인 (실제 클릭 없음)."""
    # 저장 시도 → 에러 발생 시킨 후 추가 진단
    print("\n[4] 저장하기 클릭으로 검증 에러 발생 시도 (실제 저장 X)")
    # fixed bar 보이게
    pr = ProductRegister(page)
    pr._show_fixed_bar()
    time.sleep(1)

    try:
        # 저장하기 버튼 hover만 (실제 클릭은 위험)
        page.locator('button:has-text("저장하기")').first.scroll_into_view_if_needed(timeout=3000)
        time.sleep(0.5)
        print("  저장하기 버튼 화면에 위치 — 클릭하면 어떤 검증 오류 발생할지 다음 단계에서 확인")
    except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 필드 진단 스크립트(읽기전용 분석, 실제 저장 클릭 없음) — 팝업처리/스크롤/버튼탐색 실패는 무시하거나 진단결과에 오류 메시지만 기록
        print(f"  저장하기 버튼 위치 찾기 실패: {e}")


def main():
    page = get_page()
    print(f"\n{'=' * 70}")
    print("  상품 등록 페이지 문제 진단")
    print(f"{'=' * 70}\n")

    r = ensure_naver_login(page)
    if not r.get("ok"):
        print("✗ 로그인 실패")
        return

    _enter_register_page(page)

    print("[3] 진단 데이터 수집")
    diag = page.evaluate(DIAGNOSE_JS)

    _print_diag(diag)

    _probe_save_button(page)

    # 결과 저장
    out = ROOT / "data" / "smartstore_product_diagnosis.json"
    out.write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ 진단 결과 저장: {out.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 필드 진단 스크립트(읽기전용 분석, 실제 저장 클릭 없음) — 팝업처리/스크롤/버튼탐색 실패는 무시하거나 진단결과에 오류 메시지만 기록
        import traceback

        traceback.print_exc()
