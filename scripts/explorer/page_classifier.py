"""페이지 자동 분류기 — DOM 분석으로 페이지 타입 추정.

타입:
    login | signup | list_table | detail_view | form_input |
    modal_popup | pagination_list | landing | unknown

사용:
    from scripts.explorer.page_classifier import classify_page
    info = classify_page(page)
    # info: {type, confidence, signals, suggested_handlers, snapshot}
"""
from __future__ import annotations

from scripts.logger import get_logger
from scripts.form.discovery import discover_form

log = get_logger(__name__)


_CLASSIFY_JS = r"""
() => {
  const out = {
    url: location.href,
    title: document.title || '',
    forms: document.querySelectorAll('form').length,
    inputs_visible: 0,
    password_inputs: 0,
    submit_buttons: 0,
    tables: [],
    pagination_signs: [],
    modal_signs: [],
    interactive_elements: 0,
    headings: [],
    body_chars: 0,
  };
  // visible inputs (password 도 visible 한 것만 — hidden 다중 폼 오분류 방지)
  document.querySelectorAll('input').forEach(el => {
    const r = el.getBoundingClientRect();
    const visible = el.offsetParent !== null && r.width > 0;
    if (visible) out.inputs_visible++;
    if (visible && el.type === 'password') out.password_inputs++;
  });
  // submit buttons
  document.querySelectorAll('button, input[type=submit]').forEach(el => {
    const txt = (el.innerText || el.value || '').trim();
    if (/로그인|회원가입|가입|sign\s*in|sign\s*up|submit|확인|등록|저장/i.test(txt)) {
      out.submit_buttons++;
    }
  });
  // tables (data-bearing)
  document.querySelectorAll('table').forEach(t => {
    const rows = t.querySelectorAll('tr').length;
    const cols = t.querySelector('tr') ? t.querySelector('tr').children.length : 0;
    if (rows > 1 && cols > 1) {
      const head = Array.from(t.querySelectorAll('tr:first-child th, tr:first-child td'))
                          .map(c => (c.innerText || '').trim().slice(0, 30));
      out.tables.push({rows, cols, header: head.slice(0, 10)});
    }
  });
  // pagination
  document.querySelectorAll('a, button, li').forEach(el => {
    const txt = (el.innerText || '').trim();
    if (/^다음$|^이전$|^next$|^prev|페이지\s*\d/i.test(txt)) {
      out.pagination_signs.push(txt.slice(0, 20));
    }
  });
  // modal indicators
  document.querySelectorAll('[role=dialog], [class*=modal], [class*=popup], [class*=overlay]').forEach(el => {
    const r = el.getBoundingClientRect();
    if (el.offsetParent !== null && r.width > 100 && r.height > 50 && r.width < window.innerWidth - 50) {
      out.modal_signs.push({class: el.className.slice(0, 50), w: Math.round(r.width), h: Math.round(r.height)});
    }
  });
  // interactive (buttons, links visible)
  document.querySelectorAll('button, a[href]').forEach(el => {
    const r = el.getBoundingClientRect();
    if (el.offsetParent !== null && r.width > 0) out.interactive_elements++;
  });
  // headings (top h1/h2)
  document.querySelectorAll('h1, h2').forEach(h => {
    const txt = (h.innerText || '').trim();
    if (txt) out.headings.push(txt.slice(0, 80));
  });
  out.body_chars = (document.body.innerText || '').length;
  return out;
}
"""


def classify_page(page) -> dict:
    """현재 페이지의 타입을 분류 + 권장 핸들러.

    Returns:
        {
          type: str,
          confidence: float,
          signals: [...],
          suggested_handlers: [...],
          discovery: {...},   # form discovery 결과 요약
          snapshot: {...},    # 원본 신호 (DEBUG용)
        }
    """
    try:
        snap = page.evaluate(_CLASSIFY_JS)
    except Exception as e:
        log.debug("[classify] evaluate 실패: %s", e)
        return {"type": "unknown", "confidence": 0.0, "signals": ["evaluate_failed"],
                "suggested_handlers": [], "discovery": {}, "snapshot": {}}

    # discovery 결과 (intent + 폼 필드)
    try:
        disc = discover_form(page).to_dict()
    except Exception:
        disc = {"intent": "unknown", "fields": []}

    signals: list[str] = []
    suggestions: list[str] = []
    page_type = "unknown"
    confidence = 0.0

    # --- 분류 규칙 (우선순위 순) ---

    # 1) 로그인
    if disc.get("intent") == "login" and snap["password_inputs"] >= 1:
        page_type = "login"
        confidence = 0.95
        signals.append("intent=login")
        signals.append(f"password_inputs={snap['password_inputs']}")
        suggestions.append("scripts.form.orchestrator.universal_login")

    # 2) 회원가입
    elif disc.get("intent") == "signup":
        page_type = "signup"
        confidence = 0.9
        signals.append("intent=signup")
        suggestions.append("scripts.form.orchestrator (signup intent — F4~F8 필요)")

    # 3) 모달/팝업 (페이지 내 작은 박스만)
    elif snap["modal_signs"] and snap["body_chars"] < 800:
        page_type = "modal_popup"
        confidence = 0.85
        signals.append(f"modal_signs={len(snap['modal_signs'])}")
        suggestions.append("scripts.popup_watcher / popup_classifier")

    # 4) 데이터 리스트 + 페이지네이션
    elif snap["tables"] and snap["pagination_signs"]:
        page_type = "list_table"
        confidence = 0.9
        biggest = max(snap["tables"], key=lambda t: t["rows"])
        signals.append(f"table_rows={biggest['rows']}")
        signals.append(f"pagination={len(snap['pagination_signs'])}")
        suggestions.append(f"테이블 추출 + 페이지네이션 (헤더: {biggest['header'][:5]})")

    # 5) 데이터 리스트 (페이지네이션 없음)
    elif snap["tables"]:
        biggest = max(snap["tables"], key=lambda t: t["rows"])
        if biggest["rows"] >= 5:
            page_type = "list_table"
            confidence = 0.75
            signals.append(f"table_rows={biggest['rows']}")
            suggestions.append(f"테이블 추출 (헤더: {biggest['header'][:5]})")

    # 6) 일반 입력 폼 (로그인/검색 외)
    elif disc.get("intent") not in ("login", "signup") and snap["forms"] >= 1 and snap["inputs_visible"] >= 3:
        page_type = "form_input"
        confidence = 0.7
        signals.append(f"inputs_visible={snap['inputs_visible']}")
        signals.append(f"submit_buttons={snap['submit_buttons']}")
        suggestions.append("scripts.form.discovery + form/orchestrator 응용")

    # 7) 상세 뷰 (큰 콘텐츠 + 액션 버튼)
    elif snap["body_chars"] > 500 and snap["submit_buttons"] >= 1:
        page_type = "detail_view"
        confidence = 0.6
        signals.append(f"body_chars={snap['body_chars']}")
        suggestions.append("페이지 콘텐츠 추출 (제목/본문/메타)")

    # 8) 랜딩 (큰 콘텐츠 + 링크 다수)
    elif snap["interactive_elements"] > 30 and snap["body_chars"] > 500:
        page_type = "landing"
        confidence = 0.6
        signals.append(f"links={snap['interactive_elements']}")
        suggestions.append("BFS 진입점 — 메뉴/네비게이션 매핑")

    # 9) 미설계
    else:
        page_type = "unknown"
        confidence = 0.3
        signals.append(f"forms={snap['forms']}, inputs={snap['inputs_visible']}, "
                       f"tables={len(snap['tables'])}, body={snap['body_chars']}")
        suggestions.append("data/discovered/<host>/<page>.json 에 스냅샷 저장 — 수동 핸들러 추가 필요")

    return {
        "type": page_type,
        "confidence": confidence,
        "signals": signals,
        "suggested_handlers": suggestions,
        "discovery": {
            "intent": disc.get("intent", "unknown"),
            "fields_count": len(disc.get("fields", [])),
            "submit": disc.get("submit_selector"),
        },
        "snapshot": snap,
    }
