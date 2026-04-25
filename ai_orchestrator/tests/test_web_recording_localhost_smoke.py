"""F-4S-8c 정적 검사 테스트 — 실제 브라우저 실행 없음.

검증 항목:
  - demo HTML에 form/input/password/button 없음
  - demo HTML에 외부 script/img/css URL 없음
  - serve script가 127.0.0.1 기본값인지
  - smoke script에 외부 URL 없음
  - smoke script에 click/fill/type/press 없음
  - smoke script에 cookie/storage/evaluate 없음
  - smoke script에 upload/OAuth/LTX 호출 없음
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_DEMO_HTML = _ROOT / "samples" / "web_recording_demo" / "index.html"
_SERVE_SCRIPT = _ROOT / "scripts" / "serve_web_recording_demo.py"
_SMOKE_SCRIPT = _ROOT / "scripts" / "smoke_web_recording_localhost.py"


# ---------------------------------------------------------------------------
# Demo HTML 정적 검사
# ---------------------------------------------------------------------------


def _html() -> str:
    return _DEMO_HTML.read_text(encoding="utf-8")


def test_demo_html_exists():
    assert _DEMO_HTML.exists(), f"demo HTML not found: {_DEMO_HTML}"


def test_demo_html_no_form():
    html = _html().lower()
    assert "<form" not in html, "demo HTML must not contain <form>"


def test_demo_html_no_input():
    html = _html().lower()
    # input 태그 없어야 함 (type="hidden" 포함)
    assert "<input" not in html, "demo HTML must not contain <input>"


def test_demo_html_no_password():
    html = _html().lower()
    assert "password" not in html, "demo HTML must not contain 'password'"


def test_demo_html_no_button():
    html = _html().lower()
    assert "<button" not in html, "demo HTML must not contain <button>"


def test_demo_html_no_external_script():
    html = _html()
    # <script src="..."> 가 있으면 안 됨 (인라인 <script> 는 허용하지 않지만 src= 만 체크)
    assert not re.search(r'<script\s[^>]*src\s*=', html, re.IGNORECASE), \
        "demo HTML must not contain external <script src=...>"


def test_demo_html_no_external_img():
    html = _html()
    # src="http..." 또는 src="https..." 인 img 없어야 함
    for m in re.finditer(r'<img\s[^>]*src\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        url = m.group(1)
        assert not url.startswith(("http://", "https://", "//")), \
            f"demo HTML must not contain external img src: {url}"


def test_demo_html_no_external_css():
    html = _html()
    # <link href="http..."> 없어야 함
    for m in re.finditer(r'<link\s[^>]*href\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
        url = m.group(1)
        assert not url.startswith(("http://", "https://", "//")), \
            f"demo HTML must not contain external CSS href: {url}"


def test_demo_html_no_cdn():
    html = _html().lower()
    cdn_patterns = ("cdn.jsdelivr", "cdnjs.cloudflare", "unpkg.com", "fonts.googleapis")
    for pat in cdn_patterns:
        assert pat not in html, f"demo HTML must not reference CDN: {pat}"


# ---------------------------------------------------------------------------
# serve 스크립트 정적 검사
# ---------------------------------------------------------------------------


def _serve_src() -> str:
    return _SERVE_SCRIPT.read_text(encoding="utf-8")


def test_serve_script_exists():
    assert _SERVE_SCRIPT.exists(), f"serve script not found: {_SERVE_SCRIPT}"


def test_serve_script_default_host_127():
    src = _serve_src()
    assert '127.0.0.1' in src, "serve script must default to 127.0.0.1"


def test_serve_script_no_0000():
    src = _serve_src()
    # 0.0.0.0 바인딩 없어야 함
    assert "0.0.0.0" not in src, "serve script must not bind to 0.0.0.0"


# ---------------------------------------------------------------------------
# smoke 스크립트 정적 검사
# ---------------------------------------------------------------------------


def _smoke_src() -> str:
    return _SMOKE_SCRIPT.read_text(encoding="utf-8")


def test_smoke_script_exists():
    assert _SMOKE_SCRIPT.exists(), f"smoke script not found: {_SMOKE_SCRIPT}"


def test_smoke_script_no_external_url():
    src = _smoke_src()
    # naver.com / youtube.com / google.com 등 외부 URL 없어야 함
    external_patterns = [
        "naver.com", "youtube.com", "youtu.be", "google.com",
        "instagram.com", "facebook.com", "tiktok.com",
    ]
    for pat in external_patterns:
        assert pat not in src.lower(), \
            f"smoke script must not reference external URL: {pat}"


def test_smoke_script_uses_localhost_target():
    src = _smoke_src()
    assert "127.0.0.1" in src, "smoke script must use 127.0.0.1 as target"


def test_smoke_script_no_click():
    src = _smoke_src()
    assert "page.click" not in src, "smoke script must not use page.click"


def test_smoke_script_no_fill():
    src = _smoke_src()
    assert "page.fill" not in src, "smoke script must not use page.fill"


def test_smoke_script_no_type():
    src = _smoke_src()
    assert "page.type" not in src, "smoke script must not use page.type"


def test_smoke_script_no_press():
    src = _smoke_src()
    assert "page.press" not in src, "smoke script must not use page.press"


def test_smoke_script_no_evaluate():
    # 실제 코드 호출 여부 검사 (docstring 언급은 허용)
    src = _smoke_src()
    assert "page.evaluate(" not in src, "smoke script must not call page.evaluate()"


def test_smoke_script_no_cookie():
    src = _smoke_src()
    assert "storage_state" not in src, "smoke script must not use storage_state"
    assert ".set_cookie(" not in src.lower(), "smoke script must not call set_cookie()"


def test_smoke_script_no_upload():
    # .upload( 또는 upload_file( 형태의 실제 호출 검사
    src = _smoke_src()
    assert ".upload(" not in src.lower(), "smoke script must not call .upload()"
    assert "upload_file(" not in src.lower(), "smoke script must not call upload_file()"


def test_smoke_script_no_oauth():
    # oauth 관련 실제 import/call 검사
    src = _smoke_src()
    assert "import oauth" not in src.lower(), "smoke script must not import oauth"
    assert "oauth2" not in src.lower(), "smoke script must not use oauth2"


def test_smoke_script_no_ltx():
    # ltx API 실제 호출 검사
    src = _smoke_src()
    assert "ltx_api" not in src.lower(), "smoke script must not call ltx_api"
    assert "import ltx" not in src.lower(), "smoke script must not import ltx"


def test_smoke_recording_steps_no_forbidden():
    src = _smoke_src()
    # recording_steps 정의에 forbidden step type 없어야 함
    forbidden = ["click", "fill", "type", "press", "submit", "login", "purchase"]
    # step 정의 블록만 추출 — "type": "..." 형태
    step_type_values = re.findall(r'"type"\s*:\s*"([^"]+)"', src)
    for sv in step_type_values:
        assert sv not in forbidden, \
            f"smoke recording_steps must not include forbidden step type: {sv}"
