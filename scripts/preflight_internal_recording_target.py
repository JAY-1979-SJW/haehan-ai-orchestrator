"""내부 URL 녹화 대상 preflight 점검 스크립트.

동작:
  - 후보 URL 목록을 받아 stdlib urllib로 접근 가능 여부 확인
  - 외부 host 기본 차단 (localhost / 127.0.0.1 / ::1 / 추가 allow-host만 허용)
  - 응답 body 일부에서 login/password/form/input 신호 감지
  - HTML 원문은 저장하지 않음
  - 첫 번째 reachable + login_required=False URL을 추천

사용 예:
  python scripts/preflight_internal_recording_target.py \\
    --url http://127.0.0.1:3000 \\
    --url http://127.0.0.1:8765 \\
    --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import urllib.request
import urllib.error

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "::1")

_FORBIDDEN_EXTERNAL_HOSTS = (
    "naver.com", "youtube.com", "youtu.be", "google.com",
    "hometax.go.kr", "instagram.com", "facebook.com", "tiktok.com",
    "kakao.com", "daum.net",
)

# HTML 구조적 로그인 신호 — 단순 텍스트 언급이 아닌 form/input 요소 기반
_LOGIN_SIGNALS = (
    "type=\"password\"",
    "type='password'",
    "name=\"password\"",
    "name='password'",
    "id=\"password\"",
    "id='password'",
)

# form action 에 login 경로가 포함될 때만 추가 감지
_LOGIN_FORM_PATTERNS = (
    "action=\"/login",
    "action='/login",
    "action=\"/signin",
    "action='/signin",
    "action=\"/auth",
    "action='/auth",
)

PEEK_BYTES = 4096


def _coerce_allow_hosts(allow_hosts: Any) -> tuple:
    base = set(DEFAULT_ALLOWED_HOSTS)
    if allow_hosts:
        for h in allow_hosts:
            if isinstance(h, str) and h.strip():
                base.add(h.strip().lower())
    return tuple(base)


def _is_internal_host(url: str, allow_hosts: tuple) -> bool:
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    for fh in _FORBIDDEN_EXTERNAL_HOSTS:
        if host == fh or host.endswith("." + fh):
            return False
    return host in allow_hosts


def _detect_login(body_snippet: str) -> bool:
    """HTML 구조 기반 로그인 화면 감지.

    단순 텍스트 언급(예: "로그인 없음", "login policy")은 무시하고
    실제 password input 요소 또는 login form action 이 있을 때만 True.
    """
    lower = body_snippet.lower()
    if any(sig in lower for sig in _LOGIN_SIGNALS):
        return True
    if any(pat in lower for pat in _LOGIN_FORM_PATTERNS):
        return True
    return False


def check_url(url: str, allow_hosts: tuple, timeout: float = 3.0) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "url": url,
        "internal_host": False,
        "reachable": False,
        "status_code": None,
        "login_required": False,
        "skip_reason": None,
    }

    if not _is_internal_host(url, allow_hosts):
        result["skip_reason"] = "external_host_blocked"
        return result
    result["internal_host"] = True

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result["status_code"] = resp.status
            result["reachable"] = True
            raw = resp.read(PEEK_BYTES)
            try:
                snippet = raw.decode("utf-8", errors="replace")
            except Exception:
                snippet = ""
            result["login_required"] = _detect_login(snippet)
    except urllib.error.HTTPError as e:
        result["status_code"] = e.code
        result["reachable"] = e.code < 500
        if e.code in (401, 403):
            result["login_required"] = True
        try:
            raw = e.read(PEEK_BYTES)
            snippet = raw.decode("utf-8", errors="replace")
            if _detect_login(snippet):
                result["login_required"] = True
        except Exception:
            pass
    except Exception as exc:
        result["skip_reason"] = f"connection_error:{type(exc).__name__}"

    return result


def run_preflight(
    urls: List[str],
    allow_hosts: Optional[List[str]] = None,
    timeout: float = 3.0,
) -> Dict[str, Any]:
    hosts = _coerce_allow_hosts(allow_hosts)
    candidates = []
    recommended: Optional[str] = None

    for url in urls:
        r = check_url(url, hosts, timeout=timeout)
        candidates.append(r)
        if (
            recommended is None
            and r["reachable"]
            and not r["login_required"]
            and not r["skip_reason"]
        ):
            recommended = url

    return {
        "candidates": candidates,
        "recommended_url": recommended,
        "allow_hosts": list(hosts),
        "note": (
            "recommended_url 이 None 이면 접근 가능한 내부 URL 없음 — smoke SKIP"
            if recommended is None
            else "recommended_url 로 smoke 실행 가능"
        ),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="내부 URL 녹화 대상 preflight")
    parser.add_argument("--url", action="append", dest="urls", metavar="URL", default=[])
    parser.add_argument("--allow-host", action="append", dest="allow_hosts", metavar="HOST", default=None)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.urls:
        print("ERROR: --url 을 하나 이상 지정하세요", file=sys.stderr)
        return 1

    result = run_preflight(args.urls, allow_hosts=args.allow_hosts, timeout=args.timeout)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for c in result["candidates"]:
            mark = "OK " if (c["reachable"] and not c["login_required"]) else "ERR"
            login = " [LOGIN]" if c["login_required"] else ""
            skip = f" skip={c['skip_reason']}" if c["skip_reason"] else ""
            print(f"{mark}  {c['url']}  status={c['status_code']}{login}{skip}")
        print(f"recommended: {result['recommended_url']}")
        print(result["note"])

    return 0 if result["recommended_url"] else 2


if __name__ == "__main__":
    sys.exit(main())
