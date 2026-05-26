"""SmartStore draft-fill helpers.

These helpers may type test data into visible text/number fields, but never
click final state-changing controls such as save, submit, send, delete, issue,
approve, or settlement request buttons.
"""
from __future__ import annotations

import json
import struct
import time
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import websocket  # type: ignore

from scripts.naver.mail_read import cdp
from scripts.smartstore.live_probe import classify_probe, find_rendered_smartstore_target, select_smartstore_session
from scripts.smartstore.live_probe import _target_ws_url

ROOT = Path(__file__).resolve().parents[2]
LATEST_DRAFT_FILL_PATH = ROOT / "data" / "smartstore_draft_fill_latest.json"
TEST_ASSET_DIR = ROOT / "data" / "smartstore_test_assets"
TEST_CATEGORY = {
    "id": "50000966",
    "parentId": "50000108",
    "name": "앤틱소품(스마트스토어사용N)",
    "wholeCategoryId": "50000004>50000108>50000966",
    "wholeCategoryName": "가구/인테리어>인테리어소품>앤틱소품",
    "level": 3,
    "lastLevel": True,
    "deleted": False,
    "sellBlogUse": False,
    "sortOrder": 0,
    "juvenileHarmful": False,
}

PRODUCT_REGISTER_URL = "https://sell.smartstore.naver.com/#/products/standard-group-product/create"
PRODUCT_REGISTER_CANDIDATE_URLS = [
    "https://sell.smartstore.naver.com/#/products/regular/create",
    "https://sell.smartstore.naver.com/#/products/general/create",
    "https://sell.smartstore.naver.com/#/products/single/create",
    "https://sell.smartstore.naver.com/#/products/single-product/create",
    "https://sell.smartstore.naver.com/#/products/normal/create",
    "https://sell.smartstore.naver.com/#/products/individual-product/create",
    "https://sell.smartstore.naver.com/#/products/edit-new",
    "https://sell.smartstore.naver.com/#/products/create",
    PRODUCT_REGISTER_URL,
]
APPROVAL_CONFIRM_TEXT = "SMARTSTORE_APPROVED_SUBMIT"


@dataclass
class SmartStoreDraftFillReport:
    ok: bool
    code: str
    workflow: str
    port: int | None = None
    target_id: str = ""
    before_url: str = ""
    after_url: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    filled: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    blocked_controls: list[dict[str, Any]] = field(default_factory=list)
    final_submit_blocked: bool = True
    approval_required_for_submit: bool = True
    approval_confirm_text: str = APPROVAL_CONFIRM_TEXT
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sample_product_data() -> dict[str, Any]:
    return {
        "name": "AI 자동화 테스트 상품 - 저장 금지",
        "category": "생활/건강",
        "price": 12900,
        "stock": 7,
        "brand": "Haehan Test",
        "manufacturer": "Haehan AI Lab",
        "model_name": "TEST-AI-001",
        "description": "스마트스토어 자동화 입력 검증용 테스트 문구입니다. 최종 저장은 수행하지 않습니다.",
    }


def load_product_data(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return sample_product_data()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("draft-fill data must be a JSON object")
    return data


def sample_test_product_data(product_type: str = "individual") -> dict[str, Any]:
    suffix = "개별상품" if product_type == "individual" else "그룹상품"
    return {
        "name": f"AI TEST {suffix} - delete after validation",
        "category": "생활/건강",
        "price": 12900,
        "stock": 7,
        "brand": "Haehan Test",
        "manufacturer": "Haehan AI Lab",
        "model_name": "TEST-AI-001",
        "description": "스마트스토어 자동화 입력 검증용 테스트 상품입니다. 등록 후 삭제 예정입니다.",
    }


def _page_summary_expr() -> str:
    return r"""JSON.stringify((() => {
      const body = String(document.body ? document.body.innerText : '').replace(/\s+/g, ' ').trim();
      return {
        href: location.href,
        host: location.host,
        title: document.title || '',
        markers: {
          naverLogin: /nid\.naver\.com|로그인|sign in/i.test(`${location.href} ${document.title} ${body}`),
          logout: /로그아웃|logout|sign out/i.test(`${location.href} ${document.title} ${body}`),
          accountUser: /내정보|마이비즈|account/i.test(`${location.href} ${document.title} ${body}`),
          storeNavigation: /상품관리|판매관리|정산관리|문의\/리뷰관리|스토어관리/i.test(body),
          smartstore: /스마트스토어|스마트스토어센터|상품관리|판매관리/i.test(body),
          sellerCenter: /sell\.smartstore\.naver\.com|판매자센터/i.test(`${location.href} ${body}`),
          challenge: /보안|captcha|자동입력|로봇|인증번호|비정상|차단/i.test(body)
        },
        bodyLength: body.length,
        bodySample: body.slice(0, 600)
      };
    })())"""


def _fill_product_expr(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, ensure_ascii=False)
    return f"""JSON.stringify((() => {{
      const data = {encoded};
      const clean = (value) => String(value ?? '').trim();
      const visible = (el) => {{
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      }};
      const blockedType = (el) => {{
        const type = String(el.getAttribute('type') || '').toLowerCase();
        return ['hidden','file','password','checkbox','radio','submit','button','reset'].includes(type);
      }};
      const setValue = (el, value) => {{
        el.scrollIntoView({{block: 'center', inline: 'nearest'}});
        el.focus();
        const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
        if (descriptor && descriptor.set) descriptor.set.call(el, String(value));
        else el.value = String(value);
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        el.dispatchEvent(new Event('blur', {{bubbles: true}}));
      }};
      const fieldSpecs = [
        {{key:'name', selectors:['input[name="product.name"]','input[name*="product.name"]','input[placeholder*="상품명"]','input[aria-label*="상품명"]']}},
        {{key:'category', selectors:['input[placeholder*="카테고리"]:not([type="radio"]):not([type="checkbox"])','input[aria-label*="카테고리"]']}},
        {{key:'price', selectors:['input[name="product.salePrice"]','input[name*="salePrice"]','input[name*="sellPrice"]','input[placeholder*="판매가"]','input[aria-label*="판매가"]']}},
        {{key:'stock', selectors:['input[name="product.stockQuantity"]','input[name*="stockQuantity"]','input[name*="stock"]','input[placeholder*="재고"]','input[aria-label*="재고"]']}},
        {{key:'brand', selectors:['input[placeholder*="브랜드"]','input[aria-label*="브랜드"]','input[name*="brand"]']}},
        {{key:'manufacturer', selectors:['input[placeholder*="제조사"]','input[aria-label*="제조사"]','input[name*="manufacturer"]']}},
        {{key:'model_name', selectors:['input[placeholder*="모델"]','input[aria-label*="모델"]','input[name*="model"]']}},
        {{key:'description', selectors:['textarea[placeholder*="상세"]','textarea[aria-label*="상세"]','textarea','[contenteditable="true"]']}},
      ];
      const filled = [];
      const skipped = [];
      const used = new Set();
      for (const spec of fieldSpecs) {{
        const value = data[spec.key];
        if (value === undefined || value === null || value === '') {{
          skipped.push({{key: spec.key, reason: 'no_value'}});
          continue;
        }}
        let matched = null;
        let selector = '';
        for (const candidate of spec.selectors) {{
          const nodes = Array.from(document.querySelectorAll(candidate));
          matched = nodes.find((el) => !used.has(el) && visible(el) && !blockedType(el));
          if (matched) {{ selector = candidate; break; }}
        }}
        if (!matched) {{
          skipped.push({{key: spec.key, reason: 'field_not_found'}});
          continue;
        }}
        try {{
          if (matched.isContentEditable) {{
            matched.scrollIntoView({{block: 'center', inline: 'nearest'}});
            matched.focus();
            matched.innerText = String(value);
            matched.dispatchEvent(new InputEvent('input', {{bubbles: true, inputType: 'insertText', data: String(value)}}));
            matched.dispatchEvent(new Event('blur', {{bubbles: true}}));
          }} else {{
            setValue(matched, value);
          }}
          used.add(matched);
          filled.push({{
            key: spec.key,
            selector,
            value_preview: String(value).slice(0, 80),
            tag: matched.tagName.toLowerCase(),
            type: matched.getAttribute('type') || ''
          }});
        }} catch (error) {{
          skipped.push({{key: spec.key, reason: 'fill_failed', error: String(error).slice(0, 120)}});
        }}
      }}
      const finalTokens = /저장|등록|발송|삭제|신청|승인|취소|정산요청|save|submit|send|delete|apply|approve|cancel/i;
      const blocked_controls = Array.from(document.querySelectorAll('button,a,[role="button"],input[type="button"],input[type="submit"]'))
        .filter(visible)
        .map((el) => ({{
          text: clean(el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || ''),
          tag: el.tagName.toLowerCase(),
          type: el.getAttribute('type') || ''
        }}))
        .filter((item) => finalTokens.test(`${{item.text}} ${{item.type}}`))
        .slice(0, 80);
      return {{
        href: location.href,
        title: document.title || '',
        filled,
        skipped,
        blocked_controls,
        final_submit_blocked: true
      }};
    }})())"""


def create_test_image(path: str | Path | None = None, *, label: str = "SMARTSTORE TEST") -> Path:
    TEST_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(path) if path else TEST_ASSET_DIR / "smartstore_test_product.png"
    width = height = 800
    rows = []
    label_bytes = label.encode("ascii", errors="ignore")[:32] or b"TEST"
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            stripe = (x // 40 + y // 40) % 2
            r, g, b = (28, 96, 160) if stripe else (240, 244, 248)
            if 230 < x < 570 and 320 < y < 480:
                r, g, b = (255, 255, 255)
            if 350 < y < 450 and 260 < x < 540:
                idx = ((x - 260) // 8) % len(label_bytes)
                bit = (label_bytes[idx] >> ((x // 2) % 8)) & 1
                if bit:
                    r, g, b = (20, 20, 20)
            row.extend((r, g, b))
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(rows)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    out.write_bytes(png)
    return out


def select_test_category(target_id: str, *, port: int, category: dict[str, Any] | None = None) -> dict[str, Any]:
    data = category or TEST_CATEGORY
    encoded = json.dumps(data, ensure_ascii=False)
    return cdp.evaluate(
        target_id,
        f"""JSON.stringify((() => {{
          const category = {encoded};
          const jq = window.jQuery || window.$;
          const input = Array.from(document.querySelectorAll('input'))
            .find((el) => el.type === 'text' && el.name === 'category');
          if (!input || !jq) return {{ok: false, reason: 'category_selectize_missing'}};
          const selectize = jq(input).data('selectize');
          if (!selectize) return {{ok: false, reason: 'selectize_missing'}};
          selectize.addOption(category);
          selectize.refreshOptions(false);
          selectize.clear(true);
          selectize.addItem(category.id, false);
          selectize.setValue(category.id, false);
          selectize.refreshItems();
          input.dispatchEvent(new Event('input', {{bubbles: true}}));
          input.dispatchEvent(new Event('change', {{bubbles: true}}));
          try {{
            const scope = jq(input).scope && jq(input).scope();
            if (scope && scope.$applyAsync) scope.$applyAsync();
          }} catch (error) {{}}
          const confirm = Array.from(document.querySelectorAll('button,a,[role="button"]'))
            .find((el) => String(el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim() === '확인');
          if (confirm) confirm.click();
          return {{
            ok: true,
            id: category.id,
            name: category.wholeCategoryName,
            value: input.value,
            items: selectize.items.slice()
          }};
        }})())""",
        timeout=10.0,
        port=port,
    ) or {"ok": False, "reason": "category_select_failed"}


def upload_first_product_image(target_id: str, *, port: int, image_path: str | Path) -> dict[str, Any]:
    path = str(Path(image_path).resolve())
    existing = cdp.evaluate(
        target_id,
        "JSON.stringify({count: document.querySelectorAll('input[type=file]').length, representativeImages: document.querySelectorAll('#representImage img').length})",
        timeout=5.0,
        port=port,
    ) or {}
    if int((existing or {}).get("representativeImages") or 0) > 0:
        return {"ok": True, "reason": "representative_image_already_present", "file": path, "opener": {"ok": False, "reason": "not_needed", "existing": existing}}
    cdp.evaluate(
        target_id,
        r"""JSON.stringify((() => {
          const text = String(document.body ? document.body.innerText : '');
          const targets = ['대표이미지', '상품이미지', '이미지 등록', '사진 등록'];
          for (const token of targets) {
            const el = Array.from(document.querySelectorAll('body *')).find((node) => {
              const value = String(node.innerText || node.textContent || '');
              if (!value.includes(token)) return false;
              const style = window.getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            });
            if (el) {
              el.scrollIntoView({block: 'center', inline: 'nearest'});
              return {ok: true, token, href: location.href, seen: text.includes(token)};
            }
          }
          window.scrollTo(0, Math.max(window.scrollY, document.body.scrollHeight * 0.35));
          return {ok: false, reason: 'image_section_not_visible', href: location.href};
        })())""",
        timeout=8.0,
        port=port,
    )
    time.sleep(1.0)
    opener: dict[str, Any] = {"ok": False, "reason": "not_needed", "existing": existing}
    if int((existing or {}).get("count") or 0) <= 0:
        opener = cdp.evaluate(
            target_id,
            r"""JSON.stringify((() => {
              const button = document.querySelector('#representImage a.btn-add-img');
              if (!button) return {ok: false, reason: 'represent_image_button_missing'};
              button.scrollIntoView({block: 'center', inline: 'nearest'});
              button.click();
              return {ok: true, text: String(button.innerText || button.textContent || '').replace(/\s+/g, ' ').trim(), selector: '#representImage a.btn-add-img'};
            })())""",
            timeout=8.0,
            port=port,
        ) or {}
        time.sleep(2.0)
    ws_url = _target_ws_url(target_id, port=port)
    if not ws_url:
        return {"ok": False, "reason": "target_websocket_url_missing", "file": path, "opener": opener}
    ws = websocket.create_connection(ws_url, timeout=10)
    try:
        doc = cdp._send(ws, 9101, "DOM.getDocument", {"depth": -1, "pierce": True}, timeout=10.0)
        root_id = ((doc.get("result") or {}).get("root") or {}).get("nodeId")
        if not root_id:
            return {"ok": False, "reason": "dom_root_missing", "file": path, "opener": opener, "dom_error": doc.get("error")}
        query = cdp._send(
            ws,
            9102,
            "DOM.querySelectorAll",
            {"nodeId": root_id, "selector": "input[type='file']"},
            timeout=10.0,
        )
        node_ids = ((query.get("result") or {}).get("nodeIds") or [])
        if not node_ids:
            return {"ok": False, "reason": "file_input_not_found", "file": path, "opener": opener, "query_error": query.get("error")}
        results = []
        for index, node_id in enumerate(node_ids[:8], start=1):
            ev = cdp._send(
                ws,
                9102 + index,
                "DOM.setFileInputFiles",
                {"nodeId": node_id, "files": [path]},
                timeout=15.0,
            )
            results.append({"node_id": node_id, "ok": "error" not in ev, "error": ev.get("error")})
    finally:
        ws.close()
    return {"ok": any(item["ok"] for item in results), "file": path, "opener": opener, "file_input_count": len(node_ids), "results": results}


def _wait_for_product_page(target_id: str, *, port: int, wait_seconds: float) -> dict[str, Any]:
    deadline = time.time() + max(2.0, wait_seconds)
    payload: dict[str, Any] = {}
    while time.time() < deadline:
        payload = cdp.evaluate(target_id, _page_summary_expr(), timeout=5.0, port=port) or {}
        if isinstance(payload, dict) and "sell.smartstore.naver.com" in str(payload.get("href") or ""):
            field_ready = cdp.evaluate(
                target_id,
                """JSON.stringify((() => ({
                  productName: !!document.querySelector('input[name="product.name"]'),
                  visibleInputs: Array.from(document.querySelectorAll('input,textarea,select')).filter((el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                  }).length
                }))())""",
                timeout=5.0,
                port=port,
            ) or {}
            if (
                "standard-group-product/create" in str(payload.get("href") or "")
                and isinstance(field_ready, dict)
                and (field_ready.get("productName") or int(field_ready.get("visibleInputs") or 0) > 8)
            ):
                break
        time.sleep(0.5)
    return payload if isinstance(payload, dict) else {}


def _field_probe(target_id: str, *, port: int) -> dict[str, Any]:
    payload = cdp.evaluate(
        target_id,
        r"""JSON.stringify((() => {
          const visible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
          };
          return {
            href: location.href,
            title: document.title || '',
            productName: !!document.querySelector('input[name="product.name"]'),
            price: !!document.querySelector('input[name="product.salePrice"],input[name*="salePrice"],input[name*="sellPrice"]'),
            stock: !!document.querySelector('input[name="product.stockQuantity"],input[name*="stockQuantity"],input[name*="stock"]'),
            visibleInputs: Array.from(document.querySelectorAll('input,textarea,select')).filter(visible).length,
            bodySample: String(document.body ? document.body.innerText : '').replace(/\s+/g, ' ').trim().slice(0, 500)
          };
        })())""",
        timeout=6.0,
        port=port,
    ) or {}
    return payload if isinstance(payload, dict) else {}


def _navigate_to_best_product_page(
    target_id: str,
    *,
    port: int,
    wants_price_stock: bool,
    wait_seconds: float,
) -> dict[str, Any]:
    best: dict[str, Any] = {"url": PRODUCT_REGISTER_URL, "probe": {}, "score": -1}
    per_candidate_wait = max(2.0, min(5.0, wait_seconds / max(1, len(PRODUCT_REGISTER_CANDIDATE_URLS))))
    for url in PRODUCT_REGISTER_CANDIDATE_URLS:
        cdp.navigate(target_id, url, port=port)
        _wait_for_product_page(target_id, port=port, wait_seconds=per_candidate_wait)
        probe = _field_probe(target_id, port=port)
        score = int(bool(probe.get("productName"))) * 5
        score += int(bool(probe.get("price"))) * 10
        score += int(bool(probe.get("stock"))) * 10
        score += min(int(probe.get("visibleInputs") or 0), 20)
        if score > int(best.get("score") or -1):
            best = {"url": url, "probe": probe, "score": score}
        if probe.get("productName") and (not wants_price_stock or (probe.get("price") and probe.get("stock"))):
            return best
    if best.get("url"):
        cdp.navigate(target_id, str(best["url"]), port=port)
        _wait_for_product_page(target_id, port=port, wait_seconds=per_candidate_wait)
    return best


def fill_product_draft(
    data: dict[str, Any] | None = None,
    *,
    allow_mixed_readonly: bool = False,
    wait_seconds: float = 12.0,
) -> SmartStoreDraftFillReport:
    data = data or sample_product_data()
    session, selection = select_smartstore_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return SmartStoreDraftFillReport(
            ok=False,
            code=selection.code,
            workflow="product_draft_fill",
            data=data,
            messages=list(selection.messages),
            selection=selection.to_dict(),
        )
    target_id, raw = find_rendered_smartstore_target(port=session.port)
    if not target_id or not raw:
        return SmartStoreDraftFillReport(
            ok=False,
            code="no_rendered_smartstore_tab",
            workflow="product_draft_fill",
            port=session.port,
            data=data,
            messages=["No rendered SmartStore tab was found."],
            selection=selection.to_dict(),
        )
    verdict = classify_probe(raw)
    if not verdict.get("logged_in"):
        return SmartStoreDraftFillReport(
            ok=False,
            code=str(verdict.get("code") or "login_required"),
            workflow="product_draft_fill",
            port=session.port,
            target_id=target_id,
            before_url=str(verdict.get("url") or ""),
            data=data,
            messages=["SmartStore tab is not logged in or not fully rendered."],
            selection=selection.to_dict(),
        )

    before_url = str(verdict.get("url") or "")
    wants_price_stock = data.get("price") not in (None, "") or data.get("stock") not in (None, "")
    page_choice = _navigate_to_best_product_page(
        target_id,
        port=session.port,
        wants_price_stock=bool(wants_price_stock),
        wait_seconds=wait_seconds,
    )
    payload = cdp.evaluate(target_id, _fill_product_expr(data), timeout=12.0, port=session.port) or {}
    if not isinstance(payload, dict):
        payload = {}
    filled = list(payload.get("filled") or [])
    skipped = list(payload.get("skipped") or [])
    return SmartStoreDraftFillReport(
        ok=bool(filled),
        code="ok" if filled else "no_fields_filled",
        workflow="product_draft_fill",
        port=session.port,
        target_id=target_id,
        before_url=before_url,
        after_url=str(payload.get("href") or PRODUCT_REGISTER_URL),
        data=data,
        filled=filled,
        skipped=skipped,
        blocked_controls=list(payload.get("blocked_controls") or []),
        final_submit_blocked=True,
        approval_required_for_submit=True,
        messages=[
            "Typed product draft data into available non-final fields.",
            "No final save/register/submit/send/delete/apply/approve control was clicked.",
            "File upload, password, checkbox, radio, hidden, and submit controls are skipped.",
            f"Product page candidate selected: {page_choice.get('url')}; probe={page_choice.get('probe')}",
        ],
        selection=selection.to_dict(),
    )


def save_draft_fill_report(report: SmartStoreDraftFillReport, output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_DRAFT_FILL_PATH
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
