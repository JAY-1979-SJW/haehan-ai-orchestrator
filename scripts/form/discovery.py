"""범용 폼 탐색 — 사이트별 selector 없이 의미 기반 매핑.

핵심 아이디어:
  - 페이지의 input/select/textarea 를 모두 수집
  - 각 필드의 name/type/placeholder/autocomplete/label/aria-label/주변 텍스트 분석
  - 정규 역할(role)로 매핑 + 신뢰도(score)

사용:
    from scripts.form.discovery import discover_form
    result = discover_form(page)
    # result.fields: [{role, selector, score, raw}, ...]
    # result.intent: "login" | "signup" | "search" | "unknown"

역할 (role):
    id, email, phone, password, password_confirm,
    name_full, name_first, name_last,
    birth_year, birth_month, birth_day, birth_full,
    zipcode, address, address_detail, gender,
    agree_terms, agree_privacy, agree_marketing, agree_age,
    captcha_text, sms_code, email_code,
    submit, search_query, other
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scripts.common.logger import get_logger

log = get_logger(__name__)


# 역할별 키워드 — name/id/placeholder/label 매칭
_ROLE_KEYWORDS: dict[str, list[str]] = {
    "id": [
        "userid",
        "user_id",
        "loginid",
        "login_id",
        "memberid",
        "member_id",
        "username",
        "user_name",
        "id",
        "아이디",
        "회원id",
    ],
    "email": ["email", "mail", "e-mail", "이메일", "메일주소"],
    "phone": ["phone", "mobile", "cellphone", "tel", "hp", "휴대폰", "전화", "핸드폰"],
    "password": ["password", "passwd", "pw", "pwd", "비밀번호", "패스워드"],
    "password_confirm": [
        "password_confirm",
        "passwd_confirm",
        "pw_confirm",
        "password2",
        "pw2",
        "confirm_password",
        "passwordcheck",
        "비밀번호 확인",
        "비밀번호확인",
        "재입력",
    ],
    "name_full": ["fullname", "full_name", "name", "성명", "이름"],
    "name_first": ["firstname", "first_name", "givenname"],
    "name_last": ["lastname", "last_name", "familyname", "surname"],
    "birth_year": ["birthyear", "birth_year", "year", "출생년도", "생년"],
    "birth_month": ["birthmonth", "birth_month", "month", "출생월", "생월"],
    "birth_day": ["birthday", "birth_day", "day", "출생일", "생일"],
    "birth_full": ["birth", "birthdate", "birth_date", "dob", "생년월일"],
    "zipcode": ["zip", "zipcode", "postcode", "postal_code", "우편번호"],
    "address": ["address", "addr", "주소"],
    "address_detail": ["address2", "addr2", "address_detail", "addrdetail", "상세주소", "나머지주소"],
    "gender": ["gender", "sex", "성별"],
    "agree_terms": ["agree_terms", "terms", "tos", "service_agree", "이용약관", "서비스약관"],
    "agree_privacy": ["agree_privacy", "privacy", "personal_info", "개인정보", "개인정보처리"],
    "agree_marketing": ["agree_marketing", "marketing", "promotion", "광고", "마케팅", "수신동의", "이벤트"],
    "agree_age": ["agree_age", "over14", "age_confirm", "14세", "성인", "만14"],
    "captcha_text": ["captcha", "보안문자", "자동입력", "robot"],
    "sms_code": ["sms_code", "phone_code", "auth_code_sms", "인증번호", "smsauth"],
    "email_code": ["email_code", "mail_code", "auth_code_email", "이메일인증"],
    "search_query": ["search", "query", "keyword", "검색어"],
}

# input type 우선 신호
_TYPE_HINTS: dict[str, str] = {
    "email": "email",
    "tel": "phone",
    "password": "password",
    "search": "search_query",
}

# autocomplete 표준 값 매핑
_AUTOCOMPLETE_MAP: dict[str, str] = {
    "username": "id",
    "email": "email",
    "tel": "phone",
    "current-password": "password",
    "new-password": "password",
    "new-password-confirm": "password_confirm",
    "name": "name_full",
    "given-name": "name_first",
    "family-name": "name_last",
    "bday": "birth_full",
    "bday-year": "birth_year",
    "bday-month": "birth_month",
    "bday-day": "birth_day",
    "postal-code": "zipcode",
    "street-address": "address",
    "address-line1": "address",
    "address-line2": "address_detail",
    "sex": "gender",
    "one-time-code": "sms_code",
}


@dataclass
class FormField:
    role: str
    selector: str
    score: float  # 0~1
    element_type: str  # input/select/textarea
    raw: dict[str, Any]  # 원본 속성

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "selector": self.selector,
            "score": self.score,
            "element_type": self.element_type,
            "raw": self.raw,
        }


@dataclass
class FormDiscovery:
    fields: list[FormField] = field(default_factory=list)
    intent: str = "unknown"  # login | signup | search | unknown
    submit_selector: str | None = None
    notes: list[str] = field(default_factory=list)

    def get(self, role: str) -> FormField | None:
        best = None
        for f in self.fields:
            if f.role == role and (best is None or f.score > best.score):
                best = f
        return best

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "submit_selector": self.submit_selector,
            "fields": [f.to_dict() for f in self.fields],
            "notes": self.notes,
        }


# 페이지에서 필드 메타데이터 추출하는 JS
_EXTRACT_JS = r"""
() => {
  const out = [];
  const sels = ['input', 'select', 'textarea'];
  sels.forEach(tag => {
    document.querySelectorAll(tag).forEach((el, idx) => {
      const r = el.getBoundingClientRect();
      const visible = r.width > 0 && r.height > 0 && el.offsetParent !== null;
      const type = (el.type || '').toLowerCase();
      if (['hidden','submit','button','reset','image'].includes(type)) return;
      // 라벨 후보 수집
      let label = '';
      if (el.id) {
        const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (l) label = (l.innerText || '').trim();
      }
      if (!label) {
        const parentL = el.closest('label');
        if (parentL) label = (parentL.innerText || '').trim();
      }
      // 주변 텍스트
      let near = '';
      const prev = el.previousElementSibling;
      if (prev && !prev.querySelector('input,select,textarea')) {
        near = (prev.innerText || '').trim().slice(0, 60);
      }
      // selector 생성
      let selector = '';
      if (el.id) {
        selector = `#${CSS.escape(el.id)}`;
      } else if (el.name) {
        selector = `${tag}[name="${el.name}"]`;
      } else {
        // 위치 기반 (마지막 수단)
        selector = `${tag}:nth-of-type(${idx + 1})`;
      }
      out.push({
        tag, type,
        name: el.name || '',
        id: el.id || '',
        placeholder: el.placeholder || '',
        autocomplete: el.autocomplete || '',
        ariaLabel: el.getAttribute('aria-label') || '',
        label, near,
        required: el.required || false,
        visible,
        selector,
        value_present: !!el.value,
      });
    });
  });
  // 제출 후보
  const submits = [];
  document.querySelectorAll('button, input[type="submit"], a').forEach(el => {
    const txt = (el.innerText || el.value || '').trim();
    if (/로그인|회원가입|가입|sign\s*in|sign\s*up|login|submit|확인|다음|next/i.test(txt)) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) {
        let sel = '';
        if (el.id) sel = `#${CSS.escape(el.id)}`;
        else if (el.type === 'submit') sel = `button[type="submit"]`;
        else sel = `${el.tagName.toLowerCase()}:has-text("${txt.slice(0,20)}")`;
        submits.push({selector: sel, text: txt, tag: el.tagName.toLowerCase()});
      }
    }
  });
  // 약관 체크박스
  const checks = [];
  document.querySelectorAll('input[type="checkbox"]').forEach((el, idx) => {
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) return;
    let label = '';
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) label = (l.innerText || '').trim();
    }
    if (!label) {
      const parentL = el.closest('label');
      if (parentL) label = (parentL.innerText || '').trim();
    }
    if (!label) {
      // 부모 li/div 텍스트
      const p = el.closest('li, div, p');
      if (p) label = (p.innerText || '').trim().slice(0, 200);
    }
    let selector = el.id ? `#${CSS.escape(el.id)}` : (el.name ? `input[name="${el.name}"]` : `input[type="checkbox"]:nth-of-type(${idx+1})`);
    checks.push({selector, label, name: el.name, id: el.id, checked: el.checked});
  });
  return {fields: out, submits, checkboxes: checks, url: location.href};
}
"""


def _score_field(attrs: dict) -> tuple[str, float]:
    """필드 속성 dict → (role, score). score 0~1."""
    name = (attrs.get("name") or "").lower()
    el_id = (attrs.get("id") or "").lower()
    ph = (attrs.get("placeholder") or "").lower()
    ac = (attrs.get("autocomplete") or "").lower()
    aria = (attrs.get("ariaLabel") or "").lower()
    label = (attrs.get("label") or "").lower()
    near = (attrs.get("near") or "").lower()
    t = (attrs.get("type") or "").lower()

    # 1) autocomplete 표준 — 가장 강력
    if ac in _AUTOCOMPLETE_MAP:
        return _AUTOCOMPLETE_MAP[ac], 0.95

    # 2) type hint — 단, placeholder/label에 더 명확한 역할 키워드가 있으면 override
    if t in _TYPE_HINTS:
        return _score_by_type_hint(_TYPE_HINTS[t], name, el_id, ph, label, aria)

    # 3) 키워드 매칭 (name > id > autocomplete > placeholder > label > aria > near)
    sources = [(name, 0.9), (el_id, 0.85), (ph, 0.75), (label, 0.7), (aria, 0.65), (near, 0.55)]
    return _score_by_keywords(sources)


def _score_by_type_hint(base_role: str, name: str, el_id: str, ph: str, label: str, aria: str) -> tuple[str, float]:
    """type 속성 힌트 기반 (role, score). 속성 키워드가 더 명확하면 override."""
    # type=password 인데 confirm/재입력 → password_confirm
    if base_role == "password":
        for src in (name, el_id, ph, label, aria):
            if any(k in src for k in ["confirm", "check", "재입력", "확인", "2"]):
                return "password_confirm", 0.88
    # type=search 이지만 placeholder/label/aria에 "아이디"/"id"/"user" 가 있으면 id 로 override
    if base_role == "search_query":
        for src in (ph, label, aria, name, el_id):
            if any(k in src for k in ["아이디", "userid", "user_id", "loginid", "login_id", "username", "user_name"]):
                return "id", 0.92
            if any(k in src for k in ["이메일", "메일주소", "email"]):
                return "email", 0.92
    return base_role, 0.85


def _score_by_keywords(sources: list[tuple[str, float]]) -> tuple[str, float]:
    """속성 문자열별 가중치로 키워드 매칭 (role, score)."""
    best_role = "other"
    best_score = 0.0
    for src, weight in sources:
        if not src:
            continue
        for role, kws in _ROLE_KEYWORDS.items():
            for kw in kws:
                if kw in src:
                    # 길이 가중치 — 매칭된 키워드가 길수록 신뢰도 ↑
                    s = weight * min(1.0, len(kw) / 8 + 0.4)
                    if s > best_score:
                        best_score = s
                        best_role = role
    return best_role, round(best_score, 2)


def _classify_checkbox(chk: dict) -> FormField:
    """체크박스 라벨 키워드로 동의 역할을 분류."""
    lab = (chk.get("label") or "").lower()
    role = "other"
    score = 0.5
    # 마케팅이 먼저 (더 구체적)
    for keyword_role in ("agree_marketing", "agree_privacy", "agree_terms", "agree_age"):
        for kw in _ROLE_KEYWORDS[keyword_role]:
            if kw in lab:
                role = keyword_role
                score = 0.85
                break
        if role != "other":
            break
    return FormField(
        role=role,
        selector=chk.get("selector", ""),
        score=score,
        element_type="checkbox",
        raw=chk,
    )


def _select_submit(result: FormDiscovery, submits: list[dict]) -> None:
    """제출 버튼 선택 (가장 의미있는 텍스트 우선) + intent 설정."""
    # 회원가입 우선순위 추정
    for s in submits:
        txt = s.get("text", "")
        if any(k in txt for k in ["회원가입", "Sign up", "Sign Up", "가입"]):
            result.submit_selector = s["selector"]
            result.intent = "signup"
            break
    if not result.submit_selector:
        for s in submits:
            txt = s.get("text", "")
            if any(k in txt for k in ["로그인", "Sign in", "Sign In", "Log in"]):
                result.submit_selector = s["selector"]
                result.intent = "login"
                break
    if not result.submit_selector:
        result.submit_selector = submits[0]["selector"]


def _infer_intent(result: FormDiscovery) -> None:
    """필드 구성으로 intent 추가 추론."""
    has_pw_confirm = any(f.role == "password_confirm" for f in result.fields)
    has_email = any(f.role == "email" for f in result.fields)
    has_phone = any(f.role == "phone" for f in result.fields)
    has_birth = any(f.role.startswith("birth") for f in result.fields)
    if has_pw_confirm or (has_email and has_phone) or has_birth:
        result.intent = "signup"
    elif any(f.role == "id" for f in result.fields) and any(f.role == "password" for f in result.fields):
        result.intent = "login"
    elif any(f.role == "search_query" for f in result.fields):
        result.intent = "search"


def discover_form(page) -> FormDiscovery:
    """현재 페이지의 폼을 자동 탐색 + 의미 매핑."""
    try:
        data = page.evaluate(_EXTRACT_JS)
    except Exception as e:  # noqa: BLE001 - 폼 필드 discovery용 page.evaluate 실패를 로그로 남기고 notes에 실패 사유를 담아 반환 - 읽기전용 폼 탐색, 제출/입력 동작 없음
        log.warning("[form-discovery] evaluate 실패: %s", e)
        return FormDiscovery(notes=[f"evaluate_failed: {str(e)[:100]}"])

    result = FormDiscovery()
    for attrs in data.get("fields", []):
        if not attrs.get("visible"):
            continue
        role, score = _score_field(attrs)
        result.fields.append(
            FormField(
                role=role,
                selector=attrs.get("selector", ""),
                score=score,
                element_type=attrs.get("tag", "input"),
                raw=attrs,
            )
        )

    # 체크박스도 별도로 분류
    for chk in data.get("checkboxes", []):
        result.fields.append(_classify_checkbox(chk))

    # 제출 버튼 선택 (가장 의미있는 텍스트 우선)
    submits = data.get("submits", [])
    if submits:
        _select_submit(result, submits)

    # intent 추가 추론 (없으면)
    if result.intent == "unknown":
        _infer_intent(result)

    log.info(
        "[form-discovery] intent=%s fields=%d submit=%s",
        result.intent,
        len(result.fields),
        result.submit_selector or "-",
    )
    return result
