"""F-4C — Trusted automation secret reference 인터페이스 (스텁 단계).

본 모듈은 대표님 PC 에서만 동작하는 trusted browser automation 트랙의
**비밀값 처리 인터페이스** 를 정의한다.

핵심 원칙 (docs/design/trusted_browser_automation_policy.md):
  - AI/GPT/서버는 비밀값을 알지 않는다.
  - 오케스트레이터→로컬 에이전트 파라미터는 ``secret_id`` 만 전달한다.
  - 로컬 에이전트만 ``secret_id`` 를 OS 키 저장소에서 resolve 해 잠시
    메모리에 보유한다 (실제 OS 연동은 본 단계 미구현).
  - 평문 비밀값이 ActionResult / audit log / exception trace 에 절대
    노출되지 않게 한다.

본 단계에서 **구현하는** 것:
  - ``SecretRef`` (TypedDict) — secret_id 기반 reference 타입
  - ``validate_secret_ref(ref)``                     — 형식 검증
  - ``reject_raw_secret_params(params)``             — raw 비밀 키워드 차단
  - ``redact_for_log(payload)``                       — 로그/결과용 마스킹
  - ``resolve_secret(secret_id)``                     — NotImplemented 스텁

본 단계에서 **구현하지 않는** 것:
  - 실제 Windows Credential Manager 연동
  - 실제 홈택스 자동 로그인 클릭
  - 평문 비밀값 보유/저장
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, TypedDict


# ─── 정책 상수 ────────────────────────────────────────────────────────────

# raw 비밀값이 들어오면 거절해야 하는 파라미터 키 (lower-case 비교).
# 값이 빈 문자열/None 이면 무해로 보고, 값이 있으면 차단한다.
_RAW_SECRET_PARAM_KEYS: tuple[str, ...] = (
    "password",
    "passwd",
    "cert_password",
    "certificate_password",
    "otp",
    "token",
    "access_token",
    "refresh_token",
    "cookie",
    "session",
    "storage_state",
    "localstorage",
    "sessionstorage",
)

# secret_id 자체에 들어오면 안 되는 문자 — 보안 저장소에 매핑되는 식별자
# 만 허용한다. 공백/제어/슬래시/콜론 등은 거절.
_SECRET_ID_ALLOWED_CHARS_HINT = (
    "letters/digits/underscore/hyphen/dot only"
)

# secret_id 길이 제한.
_SECRET_ID_MIN_LEN = 3
_SECRET_ID_MAX_LEN = 128

# 로그 마스킹 시 노출할 secret_id 의 prefix 글자수.
_SECRET_ID_PREFIX_LEN = 4


# ─── 타입 ────────────────────────────────────────────────────────────────

class SecretRef(TypedDict, total=False):
    """secret_id 기반 reference. raw 값은 절대 보유하지 않는다.

    필드:
      site_key:           "hometax" 등 사이트 키 (lowercase, ASCII)
      login_method:       "certificate" / "id_password" 등
      user_id_secret_id:  사용자 ID 가 보안 저장소에 저장된 식별자
      password_secret_id: 비밀번호 식별자 (평문 값 아님)
    """
    site_key: str
    login_method: str
    user_id_secret_id: str
    password_secret_id: str


# ─── 검증 ────────────────────────────────────────────────────────────────

def is_valid_secret_id(value: Any) -> bool:
    """secret_id 식별자 형식 검증.

    - str 이어야 한다.
    - 길이 [3, 128].
    - 영문/숫자/_ - . 만 허용. 공백/슬래시/콜론/한글 등 불허.
    """
    if not isinstance(value, str):
        return False
    s = value.strip()
    if len(s) != len(value):  # 양옆 공백 자체를 허용하지 않음
        return False
    if not (_SECRET_ID_MIN_LEN <= len(s) <= _SECRET_ID_MAX_LEN):
        return False
    for ch in s:
        # ASCII 영숫자 + _-. 만 허용. 한글 등 비-ASCII 는 거절.
        if ch in ("_", "-", "."):
            continue
        if not (("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9")):
            return False
    return True


def validate_secret_ref(ref: Any) -> dict[str, Any]:
    """SecretRef dict 형식 검증.

    반환:
      {"ok": bool, "error_code": str, "warnings": [str, ...]}

    원칙:
      - dict / Mapping 만 허용.
      - 알려진 raw 비밀 키 (``password`` 등) 가 들어와 있으면 즉시 거절.
      - ``site_key`` 는 lowercase ASCII slug.
      - id 는 ``user_id_secret_id`` / ``password_secret_id`` 둘 다
        ``is_valid_secret_id`` 통과해야 한다.
      - 본 단계에서는 ``login_method`` 는 free-form (검증만, 거절 안 함).
    """
    if not isinstance(ref, Mapping):
        return _err("REF_NOT_MAPPING")

    raw_check = reject_raw_secret_params(ref)
    if not raw_check["ok"]:
        return raw_check

    site_key = ref.get("site_key")
    if not isinstance(site_key, str) or not site_key.strip():
        return _err("MISSING_SITE_KEY")
    if site_key != site_key.strip().lower():
        return _err("SITE_KEY_NOT_LOWERCASE")
    if not all(c.isalnum() or c in ("_", "-") for c in site_key):
        return _err("SITE_KEY_INVALID_CHARS")

    user_id = ref.get("user_id_secret_id")
    if not is_valid_secret_id(user_id):
        return _err("INVALID_USER_ID_SECRET_ID")

    password_id = ref.get("password_secret_id")
    if not is_valid_secret_id(password_id):
        return _err("INVALID_PASSWORD_SECRET_ID")

    if user_id == password_id:
        return _err("USER_AND_PASSWORD_SECRET_ID_COLLIDE")

    return {"ok": True, "error_code": "", "warnings": []}


def reject_raw_secret_params(params: Any) -> dict[str, Any]:
    """파라미터 dict 에 raw 비밀값이 들어왔는지 검사.

    - dict 가 아닌 입력은 ok=True 로 통과 (호출자가 별도 검증).
    - dict key 의 lowercase 가 ``_RAW_SECRET_PARAM_KEYS`` 에 포함되고,
      해당 value 가 비어있지 않으면 거절.
    - raw 비밀값을 거절할 때 **value 자체는 결과에 노출하지 않는다**.

    반환:
      {"ok": bool, "error_code": str, "warnings": [str, ...]}
    """
    if not isinstance(params, Mapping):
        return {"ok": True, "error_code": "", "warnings": []}

    bad_keys: list[str] = []
    for key, value in params.items():
        if not isinstance(key, str):
            continue
        if key.lower() not in _RAW_SECRET_PARAM_KEYS:
            continue
        if value is None:
            continue
        # 빈 문자열/빈 컨테이너는 무해.
        if isinstance(value, (str, bytes)) and len(value) == 0:
            continue
        if isinstance(value, (list, tuple, dict)) and len(value) == 0:
            continue
        bad_keys.append(key.lower())

    if bad_keys:
        # 키 이름은 노출 가능 (값은 절대 노출 금지).
        unique = sorted(set(bad_keys))
        return {
            "ok": False,
            "error_code": "RAW_SECRET_PARAM_REJECTED",
            "warnings": [f"raw_secret_param:{k}" for k in unique],
        }
    return {"ok": True, "error_code": "", "warnings": []}


# ─── 마스킹 ──────────────────────────────────────────────────────────────

def redact_for_log(payload: Any) -> Any:
    """로그/audit/ActionResult 용 sanitizer.

    - dict 는 동일 키를 유지하되, 위 raw 비밀 키워드의 값은 ``"***"`` 로
      치환. ``*_secret_id`` 같은 reference 식별자는 prefix 만 노출.
    - list/tuple 은 재귀.
    - 그 외 타입은 그대로.
    """
    if isinstance(payload, Mapping):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(key, str) and key.lower() in _RAW_SECRET_PARAM_KEYS:
                out[key] = "***"
                continue
            if (
                isinstance(key, str)
                and key.lower().endswith("_secret_id")
                and isinstance(value, str)
            ):
                out[key] = _mask_secret_id(value)
                continue
            out[key] = redact_for_log(value)
        return out
    if isinstance(payload, list):
        return [redact_for_log(v) for v in payload]
    if isinstance(payload, tuple):
        return tuple(redact_for_log(v) for v in payload)
    return payload


def _mask_secret_id(value: str) -> str:
    if not isinstance(value, str) or not value:
        return ""
    head = value[:_SECRET_ID_PREFIX_LEN]
    return f"{head}***"


# ─── resolve (스텁) ──────────────────────────────────────────────────────

def resolve_secret(
    secret_id: str,
    *,
    _backend: Optional[str] = None,
) -> str:
    """secret_id → 평문 비밀값. 본 단계에서는 NotImplementedError.

    실제 구현은 후속 단계에서 Windows Credential Manager 와 연동하며,
    그 때도:
      - 호출 결과는 지역 변수에서만 보유하고 함수 종료 시 폐기한다.
      - 반환값은 절대 로깅/audit/ActionResult 로 흘리지 않는다.
      - exception trace 에도 평문이 들어가지 않게 메시지에서 비밀값을
        제외한다.
    """
    if not is_valid_secret_id(secret_id):
        raise ValueError("invalid secret_id format")
    raise NotImplementedError(
        "trusted_secrets.resolve_secret is a stub in F-4C; "
        "Windows Credential Manager integration is a later step",
    )


# ─── helpers ─────────────────────────────────────────────────────────────

def _err(code: str, *warnings: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": code,
        "warnings": [code.lower(), *warnings],
    }


def raw_secret_param_keys() -> tuple[str, ...]:
    """테스트/문서용 — 차단 대상 키 목록을 노출."""
    return _RAW_SECRET_PARAM_KEYS


__all__ = [
    "SecretRef",
    "is_valid_secret_id",
    "validate_secret_ref",
    "reject_raw_secret_params",
    "redact_for_log",
    "resolve_secret",
    "raw_secret_param_keys",
]
