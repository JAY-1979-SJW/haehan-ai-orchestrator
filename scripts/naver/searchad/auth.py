"""네이버 검색광고 API 인증 헤더 생성 — HMAC-SHA256 서명.

공식 스펙: X-Timestamp(ms) + "." + HTTP method + "." + URI 를
secret key로 HMAC-SHA256 서명 후 base64 인코딩 → X-Signature.

자격증명은 scripts.auth.credentials(암호화 저장, "naver_searchad" 사이트)에서 읽는다.
원문 값은 어떤 경우에도 로그/출력하지 않는다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time


def _sign(secret_key: str, timestamp: str, method: str, uri: str) -> str:
    message = f"{timestamp}.{method}.{uri}"
    digest = hmac.new(secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def build_headers(*, method: str, uri: str, access_license: str, secret_key: str, customer_id: str) -> dict[str, str]:
    """요청 1건에 필요한 인증 헤더를 생성. 매 요청마다 새 timestamp로 새로 만들어야 한다."""
    timestamp = str(int(time.time() * 1000))
    signature = _sign(secret_key, timestamp, method, uri)
    return {
        "X-Timestamp": timestamp,
        "X-API-KEY": access_license,
        "X-Customer": customer_id,
        "X-Signature": signature,
        "Content-Type": "application/json; charset=UTF-8",
    }


def load_credentials() -> dict[str, str]:
    """저장된 naver_searchad 자격증명을 로드. 없으면 빈 값."""
    from scripts.auth.credentials import get_cred

    cred = get_cred("naver_searchad")
    return {
        "customer_id": cred.get("id", ""),
        "secret_key": cred.get("pw", ""),
        "access_license": cred.get("access_license", ""),
    }
