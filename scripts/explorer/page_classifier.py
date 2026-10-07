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

from scripts.form.discovery import discover_form
from scripts.common.logger import get_logger

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


def _rule_login(snap: dict, disc: dict):
    # 1) 로그인
    if disc.get("intent") == "login" and snap["password_inputs"] >= 1:
        return (
            "login",
            0.95,
            ["intent=login", f"password_inputs={snap['password_inputs']}"],
            ["scripts.form.orchestrator.universal_login"],
        )
    return None


def _rule_signup(snap: dict, disc: dict):
    # 2) 회원가입
    if disc.get("intent") == "signup":
        return "signup", 0.9, ["intent=signup"], ["scripts.form.orchestrator (signup intent — F4~F8 필요)"]
    return None


def _rule_modal(snap: dict, disc: dict):
    # 3) 모달/팝업 (페이지 내 작은 박스만)
    if snap["modal_signs"] and snap["body_chars"] < 800:
        return (
            "modal_popup",
            0.85,
            [f"modal_signs={len(snap['modal_signs'])}"],
            ["scripts.browser.navigator.popup_watcher / popup_classifier"],
        )
    return None


def _rule_tables(snap: dict, disc: dict):
    # 4) 데이터 리스트 + 페이지네이션 / 5) 데이터 리스트 (페이지네이션 없음)
    if snap["tables"] and snap["pagination_signs"]:
        biggest = max(snap["tables"], key=lambda t: t["rows"])
        return (
            "list_table",
            0.9,
            [f"table_rows={biggest['rows']}", f"pagination={len(snap['pagination_signs'])}"],
            [f"테이블 추출 + 페이지네이션 (헤더: {biggest['header'][:5]})"],
        )
    if snap["tables"]:
        biggest = max(snap["tables"], key=lambda t: t["rows"])
        if biggest["rows"] >= 5:
            return (
                "list_table",
                0.75,
                [f"table_rows={biggest['rows']}"],
                [f"테이블 추출 (헤더: {biggest['header'][:5]})"],
            )
        # 표는 있으나 5행 미만 — 이후 규칙으로 넘어가지 않고 기본값 유지
        return "unknown", 0.0, [], []
    return None


def _rule_form_input(snap: dict, disc: dict):
    # 6) 일반 입력 폼 (로그인/검색 외)
    if disc.get("intent") not in ("login", "signup") and snap["forms"] >= 1 and snap["inputs_visible"] >= 3:
        return (
            "form_input",
            0.7,
            [f"inputs_visible={snap['inputs_visible']}", f"submit_buttons={snap['submit_buttons']}"],
            ["scripts.form.discovery + form/orchestrator 응용"],
        )
    return None


def _rule_detail_view(snap: dict, disc: dict):
    # 7) 상세 뷰 (큰 콘텐츠 + 액션 버튼)
    if snap["body_chars"] > 500 and snap["submit_buttons"] >= 1:
        return "detail_view", 0.6, [f"body_chars={snap['body_chars']}"], ["페이지 콘텐츠 추출 (제목/본문/메타)"]
    return None


def _rule_landing(snap: dict, disc: dict):
    # 8) 랜딩 (큰 콘텐츠 + 링크 다수)
    if snap["interactive_elements"] > 30 and snap["body_chars"] > 500:
        return "landing", 0.6, [f"links={snap['interactive_elements']}"], ["BFS 진입점 — 메뉴/네비게이션 매핑"]
    return None


_CLASSIFY_RULES = (
    _rule_login,
    _rule_signup,
    _rule_modal,
    _rule_tables,
    _rule_form_input,
    _rule_detail_view,
    _rule_landing,
)


def _apply_rules(snap: dict, disc: dict) -> tuple[str, float, list[str], list[str]]:
    """분류 규칙을 우선순위 순으로 적용해 (type, confidence, signals, suggestions) 반환."""
    for rule in _CLASSIFY_RULES:
        matched = rule(snap, disc)
        if matched is not None:
            return matched
    # 9) 미설계
    return (
        "unknown",
        0.3,
        [
            f"forms={snap['forms']}, inputs={snap['inputs_visible']}, "
            f"tables={len(snap['tables'])}, body={snap['body_chars']}"
        ],
        ["data/discovered/<host>/<page>.json 에 스냅샷 저장 — 수동 핸들러 추가 필요"],
    )


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
    except Exception as e:  # noqa: BLE001 - 페이지 분류기(읽기 전용 탐색) -- JS 평가 실패 시 unknown 분류로 폴백, 폼 discovery 실패도 unknown/빈 필드로 폴백(판정을 과장하지 않는 방향)
        log.debug("[classify] evaluate 실패: %s", e)
        return {
            "type": "unknown",
            "confidence": 0.0,
            "signals": ["evaluate_failed"],
            "suggested_handlers": [],
            "discovery": {},
            "snapshot": {},
        }

    # discovery 결과 (intent + 폼 필드)
    try:
        disc = discover_form(page).to_dict()
    except Exception:  # noqa: BLE001 - 페이지 분류기(읽기 전용 탐색) -- JS 평가 실패 시 unknown 분류로 폴백, 폼 discovery 실패도 unknown/빈 필드로 폴백(판정을 과장하지 않는 방향)
        disc = {"intent": "unknown", "fields": []}

    # --- 분류 규칙 (우선순위 순) ---
    page_type, confidence, signals, suggestions = _apply_rules(snap, disc)

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
