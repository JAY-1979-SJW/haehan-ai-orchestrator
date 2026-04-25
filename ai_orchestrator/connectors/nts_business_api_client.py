"""TAX-API-1 — 국세청 사업자등록정보 API client (PoC).

본 모듈은 공공데이터포털 (api.odcloud.kr/api/nts-businessman/v1) 의
"사업자등록정보 진위확인 및 상태조회" API 를 호출한다.

원칙:
  - stdlib ``urllib`` 만 사용. ``requests`` 신규 의존성 추가 금지.
  - serviceKey 는 URL query 로 전달하지만, repr/log/예외 메시지에는 절대
    원문 노출 금지 (``redacted_url`` 만 표면화).
  - 사업자번호는 숫자만 남기는 normalize 함수 제공.
  - 1회 최대 100건 (``MAX_BATCH_SIZE``) 제한 검사.
  - 빈 값 / 형식 오류는 API 호출 전 차단.
  - 응답 에러는 요약 dict 로 반환 (예외를 호출자에게 던지지 않는다).
  - live_enabled=False 또는 service_key 누락 시 ``mode="mock_or_disabled"``
    로 응답 형식만 갖춘 dict 를 반환한다 (실제 호출 안 함).

본 모듈은 어떤 경우에도:
  - 홈택스 화면, 쿠키, storage_state, localStorage 에 접근하지 않는다.
  - 사용자 ID/PW/인증서 비밀번호/OTP 를 다루지 않는다.
  - 캡차/보안 우회를 시도하지 않는다.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional
from urllib import error as _urlerror
from urllib import parse as _urlparse
from urllib import request as _urlrequest

from .nts_business_api_config import (
    MAX_BATCH_SIZE,
    NtsBusinessApiConfig,
    load_nts_business_api_config,
)

logger = logging.getLogger(__name__)


# ─── 공개 상수 ─────────────────────────────────────────────────────────────

STATUS_PATH = "/status"
VALIDATE_PATH = "/validate"

MODE_LIVE = "live"
MODE_MOCK_OR_DISABLED = "mock_or_disabled"

KIND_STATUS = "status"
KIND_VALIDATE = "validate"


# ─── normalize ────────────────────────────────────────────────────────────

_DIGIT_RE = re.compile(r"\D+")


def normalize_business_number(value: Any) -> str:
    """사업자번호에서 숫자만 남긴 10자리 문자열을 반환.

    10자리가 아니면 빈 문자열을 반환한다 (호출자 측에서 invalid 판정).
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:  # noqa: BLE001
            return ""
    digits = _DIGIT_RE.sub("", value)
    if len(digits) != 10:
        return ""
    return digits


def _normalize_business_numbers(
    values: Any,
) -> tuple[list[str], list[str]]:
    """입력 리스트를 정규화하고 (정상, 무효 원문) 두 리스트로 분리."""
    normalized: list[str] = []
    invalid_raws: list[str] = []
    if not isinstance(values, list):
        return normalized, invalid_raws
    for item in values:
        n = normalize_business_number(item)
        if n:
            if n not in normalized:
                normalized.append(n)
        else:
            raw = "" if item is None else str(item)
            invalid_raws.append(raw[:40])
    return normalized, invalid_raws


# ─── 요청 페이로드 빌더 ─────────────────────────────────────────────────────

def build_status_payload(business_numbers: list[str]) -> dict[str, Any]:
    """status API 요청 본문. 사업자번호는 이미 normalize 되어 있다고 가정."""
    return {"b_no": list(business_numbers)}


def _coerce_validate_item(item: Any) -> Optional[dict[str, str]]:
    """validate API item 정규화. 필수 필드 누락 시 None.

    공공데이터 API 의 validate 표준 필드:
      - b_no: 사업자번호 (10자리 숫자)
      - start_dt: 개업일자 (YYYYMMDD)
      - p_nm: 대표자명 (외국인의 경우 p_nm2 가능)
      - p_nm2 (옵션): 대표자명2
      - b_nm (옵션): 상호
      - corp_no (옵션): 법인등록번호
      - b_sector (옵션), b_type (옵션), b_adr (옵션)
    """
    if not isinstance(item, dict):
        return None
    b_no_raw = item.get("b_no") or item.get("business_number") or ""
    b_no = normalize_business_number(b_no_raw)
    if not b_no:
        return None
    start_dt = item.get("start_dt") or item.get("opening_date") or ""
    if not isinstance(start_dt, str):
        start_dt = str(start_dt) if start_dt is not None else ""
    start_dt = re.sub(r"\D+", "", start_dt)
    if len(start_dt) != 8:
        return None
    p_nm = item.get("p_nm") or item.get("ceo_name") or ""
    if not isinstance(p_nm, str) or not p_nm.strip():
        return None
    out: dict[str, str] = {
        "b_no": b_no,
        "start_dt": start_dt,
        "p_nm": p_nm.strip(),
    }
    optional_keys = ("p_nm2", "b_nm", "corp_no", "b_sector", "b_type", "b_adr")
    for k in optional_keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def build_validate_payload(items: list[dict]) -> dict[str, Any]:
    """validate API 요청 본문. 각 item 은 ``_coerce_validate_item`` 통과본."""
    return {"businesses": list(items)}


# ─── HTTP 호출 ─────────────────────────────────────────────────────────────

def _build_request_url(
    base_url: str, path: str, service_key: str,
) -> tuple[str, str]:
    """(실제 URL, redacted URL) 두 개를 반환. redacted 는 키를 `***` 로 가린다."""
    base = (base_url or "").rstrip("/")
    real = f"{base}{path}?serviceKey={_urlparse.quote(service_key, safe='')}"
    redacted = f"{base}{path}?serviceKey=***"
    return real, redacted


def _redact_text(text: str, service_key: Optional[str]) -> str:
    """에러 응답 본문에 service_key 가 echo 되어 들어오는 경우 마스킹."""
    if not text or not isinstance(text, str):
        return ""
    if service_key:
        return text.replace(service_key, "***")
    return text


def _do_post_json(
    *,
    url_real: str,
    url_redacted: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    service_key: Optional[str],
    opener: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """POST JSON 요청. 결과 dict 반환. 예외는 dict 로 변환."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = _urlrequest.Request(
        url_real,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    open_fn = opener if opener is not None else _urlrequest.urlopen
    try:
        with open_fn(req, timeout=timeout_seconds) as resp:
            status = getattr(resp, "status", 0) or 0
            try:
                raw = resp.read() or b""
            except Exception as e:  # noqa: BLE001
                return _http_error("RESPONSE_READ_FAILED", url_redacted, str(e))
            return _decode_response(status, raw, service_key, url_redacted)
    except _urlerror.HTTPError as e:
        try:
            err_body = e.read() or b""
        except Exception:  # noqa: BLE001
            err_body = b""
        return _decode_response(
            getattr(e, "code", 0) or 0, err_body, service_key, url_redacted,
        )
    except _urlerror.URLError as e:
        return _http_error(
            "URL_ERROR", url_redacted, _redact_text(str(e.reason), service_key),
        )
    except Exception as e:  # noqa: BLE001 - 마지막 안전망
        logger.debug("nts_business_api unexpected error", exc_info=True)
        return _http_error(
            "UNEXPECTED_ERROR",
            url_redacted,
            _redact_text(f"{type(e).__name__}", service_key),
        )


def _http_error(
    error_code: str, url_redacted: str, detail: str = "",
) -> dict[str, Any]:
    return {
        "ok": False,
        "status_code": 0,
        "error_code": error_code,
        "url": url_redacted,
        "detail": (detail or "")[:300],
        "data": None,
    }


def _decode_response(
    status_code: int,
    raw: bytes,
    service_key: Optional[str],
    url_redacted: str,
) -> dict[str, Any]:
    text = ""
    try:
        text = raw.decode("utf-8")
    except Exception:  # noqa: BLE001
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            text = ""
    text = _redact_text(text, service_key)

    data: Any = None
    if text:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None

    if 200 <= int(status_code) < 300 and isinstance(data, dict):
        return {
            "ok": True,
            "status_code": int(status_code),
            "error_code": "",
            "url": url_redacted,
            "detail": "",
            "data": data,
        }
    return {
        "ok": False,
        "status_code": int(status_code),
        "error_code": f"HTTP_{int(status_code) or 0}",
        "url": url_redacted,
        "detail": text[:300],
        "data": data if isinstance(data, dict) else None,
    }


# ─── 응답 어댑터 ────────────────────────────────────────────────────────────

def _build_disabled_result(
    *,
    kind: str,
    count: int,
    invalid_raws: list[str],
    extra_warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    if not extra_warnings:
        warnings.append("live_disabled_or_no_service_key")
    else:
        warnings.extend(extra_warnings)
    for raw in invalid_raws:
        warnings.append(f"invalid_input:{raw}")
    return {
        "success": True,  # disabled 는 실패가 아니라 비활성.
        "mode": MODE_MOCK_OR_DISABLED,
        "kind": kind,
        "count": int(count),
        "items": [],
        "warnings": warnings,
    }


def _build_live_result(
    *,
    kind: str,
    count: int,
    invalid_raws: list[str],
    http: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = [f"invalid_input:{raw}" for raw in invalid_raws]
    if not http.get("ok"):
        warnings.append(http.get("error_code") or "HTTP_ERROR")
        return {
            "success": False,
            "mode": MODE_LIVE,
            "kind": kind,
            "count": int(count),
            "items": [],
            "warnings": warnings,
            "status_code": int(http.get("status_code") or 0),
            "url": http.get("url") or "",
            "detail": http.get("detail") or "",
        }
    data = http.get("data") or {}
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        items = []
    return {
        "success": True,
        "mode": MODE_LIVE,
        "kind": kind,
        "count": int(count),
        "items": items,
        "warnings": warnings,
        "status_code": int(http.get("status_code") or 0),
        "url": http.get("url") or "",
    }


# ─── 외부 API ──────────────────────────────────────────────────────────────

def _ensure_config(
    config: Optional[NtsBusinessApiConfig],
) -> NtsBusinessApiConfig:
    return config if config is not None else load_nts_business_api_config()


def check_status(
    business_numbers: list[str],
    *,
    config: Optional[NtsBusinessApiConfig] = None,
    live: bool = True,
    _opener: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """사업자등록 상태조회.

    - ``live=False`` 이면 disabled 모드로 반환 (HTTP 호출 없음).
    - ``config.live_enabled=False`` 또는 키 누락 시도 disabled.
    - 입력은 1~100건. 100건 초과 시 ``BATCH_TOO_LARGE`` 로 disabled 결과 반환.
    - 빈/형식 오류 사업자번호는 호출 전에 제거하고 warning 으로 기록.
    """
    cfg = _ensure_config(config)
    normalized, invalid_raws = _normalize_business_numbers(business_numbers)

    # 입력 0건 — 호출 안 함.
    if not normalized:
        return _build_disabled_result(
            kind=KIND_STATUS,
            count=0,
            invalid_raws=invalid_raws,
            extra_warnings=["empty_input"],
        )

    # 100건 초과 — 호출 안 함.
    if len(normalized) > MAX_BATCH_SIZE:
        return _build_disabled_result(
            kind=KIND_STATUS,
            count=len(normalized),
            invalid_raws=invalid_raws,
            extra_warnings=[f"batch_too_large:{len(normalized)}"],
        )

    if not live or not cfg.live_enabled or not cfg.service_key:
        return _build_disabled_result(
            kind=KIND_STATUS,
            count=len(normalized),
            invalid_raws=invalid_raws,
        )

    real, redacted = _build_request_url(
        cfg.base_url, STATUS_PATH, cfg.service_key,
    )
    http = _do_post_json(
        url_real=real,
        url_redacted=redacted,
        payload=build_status_payload(normalized),
        timeout_seconds=cfg.timeout_seconds,
        service_key=cfg.service_key,
        opener=_opener,
    )
    return _build_live_result(
        kind=KIND_STATUS,
        count=len(normalized),
        invalid_raws=invalid_raws,
        http=http,
    )


def validate_businesses(
    items: list[dict],
    *,
    config: Optional[NtsBusinessApiConfig] = None,
    live: bool = True,
    _opener: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """사업자등록 진위확인. ``items`` 는 b_no/start_dt/p_nm 필수.

    동작은 ``check_status`` 와 동일한 가드 (입력 0건/100건 초과/disabled).
    """
    cfg = _ensure_config(config)

    coerced: list[dict[str, str]] = []
    invalid_raws: list[str] = []
    if isinstance(items, list):
        for item in items:
            c = _coerce_validate_item(item)
            if c is None:
                if isinstance(item, dict):
                    invalid_raws.append(
                        str(item.get("b_no") or item.get("business_number") or "")[:40]
                    )
                else:
                    invalid_raws.append(str(item)[:40])
                continue
            coerced.append(c)

    if not coerced:
        return _build_disabled_result(
            kind=KIND_VALIDATE,
            count=0,
            invalid_raws=invalid_raws,
            extra_warnings=["empty_input"],
        )

    if len(coerced) > MAX_BATCH_SIZE:
        return _build_disabled_result(
            kind=KIND_VALIDATE,
            count=len(coerced),
            invalid_raws=invalid_raws,
            extra_warnings=[f"batch_too_large:{len(coerced)}"],
        )

    if not live or not cfg.live_enabled or not cfg.service_key:
        return _build_disabled_result(
            kind=KIND_VALIDATE,
            count=len(coerced),
            invalid_raws=invalid_raws,
        )

    real, redacted = _build_request_url(
        cfg.base_url, VALIDATE_PATH, cfg.service_key,
    )
    http = _do_post_json(
        url_real=real,
        url_redacted=redacted,
        payload=build_validate_payload(coerced),
        timeout_seconds=cfg.timeout_seconds,
        service_key=cfg.service_key,
        opener=_opener,
    )
    return _build_live_result(
        kind=KIND_VALIDATE,
        count=len(coerced),
        invalid_raws=invalid_raws,
        http=http,
    )


__all__ = [
    "MODE_LIVE",
    "MODE_MOCK_OR_DISABLED",
    "KIND_STATUS",
    "KIND_VALIDATE",
    "STATUS_PATH",
    "VALIDATE_PATH",
    "normalize_business_number",
    "build_status_payload",
    "build_validate_payload",
    "check_status",
    "validate_businesses",
]
