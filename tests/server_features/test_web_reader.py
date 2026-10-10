"""core.agent_runtime.browser.web_reader 검증 (read-only Stage 1).

HTML 문자열 기반 테스트만 사용한다. 실제 외부 사이트 접속은 하지 않는다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ─── 공용 샘플 HTML ────────────────────────────────────────────────────────

_HTML_BASIC = """
<html>
  <head>
    <title>  기성 청구 상세 조회  </title>
    <meta name="description" content="기성 청구 리스트 페이지">
    <meta name="csrf-token" content="SECRET_TOKEN_9999">
  </head>
  <body>
    <h1>기성 청구 목록</h1>
    <h2>필터</h2>
    <a href="/list?page=1">목록 보기</a>
    <a href="/list?page=2">다음</a>
    <a href="/admin/delete?id=3">삭제</a>
    <a href="/download.xlsx">엑셀 다운로드</a>
    <button>조회</button>
    <button type="submit">저장</button>
    <button>삭제</button>
    <button>검색</button>
    <form method="post" action="/payments/submit">
      <input name="invoice_id" type="text" placeholder="청구서 번호">
      <input name="password" type="password" value="SUPER_SECRET_PW">
      <input name="csrf_token" type="hidden" value="HIDDEN_CSRF_VALUE_ABCDEF">
      <input name="session_id" type="hidden" value="SESSION_XYZ">
      <select name="status" multiple>
        <option>대기</option>
        <option>완료</option>
      </select>
      <textarea name="memo" placeholder="비고">SECRET_MEMO_CONTENT</textarea>
      <input type="submit" value="제출">
    </form>
    <table>
      <thead>
        <tr><th>기성 차수</th><th>청구 금액</th><th>상태</th></tr>
      </thead>
      <tbody>
        <tr><td>1</td><td>1,000</td><td>대기</td></tr>
        <tr><td>2</td><td>2,000</td><td>완료</td></tr>
      </tbody>
    </table>
  </body>
</html>
"""


# ─── 기본 추출 ─────────────────────────────────────────────────────────────


def test_title_and_headings_extracted() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    r = analyze_html_structure(_HTML_BASIC)
    assert r["ok"] is True
    assert r["page_title"] == "기성 청구 상세 조회"
    assert {"level": 1, "text": "기성 청구 목록"} in r["headings"]
    assert any(h["level"] == 2 for h in r["headings"])


def test_links_extracted_and_normalized() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    r = analyze_html_structure(_HTML_BASIC, base_url="https://example.com/proj/")
    hrefs = {link["text"]: link for link in r["links"]}
    assert "목록 보기" in hrefs
    assert hrefs["목록 보기"]["href"] == "/list?page=1"
    assert hrefs["목록 보기"]["normalized_href"] == "https://example.com/list?page=1"
    # danger 토큰이 있는 링크는 risk_hint=danger_write
    assert hrefs["삭제"]["risk_hint"] == "danger_write"
    # 다운로드는 medium
    assert hrefs["엑셀 다운로드"]["risk_hint"] == "medium"


def test_buttons_extracted() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    r = analyze_html_structure(_HTML_BASIC)
    texts = {b["text"] for b in r["buttons"]}
    # <button> 요소 + <input type="submit"> 모두 수집
    assert "저장" in texts
    assert "삭제" in texts
    assert "조회" in texts
    assert "검색" in texts
    assert any(b["text"] == "제출" and b["type"] == "submit" for b in r["buttons"])


# ─── 버튼 위험도 ───────────────────────────────────────────────────────────


def test_write_buttons_classified_danger_write() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    r = analyze_html_structure(_HTML_BASIC)
    by_text = {b["text"]: b for b in r["buttons"]}
    assert by_text["저장"]["risk_level"] == "danger_write"
    assert by_text["삭제"]["risk_level"] == "danger_write"
    assert by_text["제출"]["risk_level"] == "danger_write"


def test_read_buttons_classified_safe_read() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    r = analyze_html_structure(_HTML_BASIC)
    by_text = {b["text"]: b for b in r["buttons"]}
    assert by_text["조회"]["risk_level"] == "safe_read"
    assert by_text["검색"]["risk_level"] == "safe_read"


# ─── 민감정보 차단 ─────────────────────────────────────────────────────────


def test_password_value_not_in_result() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    r = analyze_html_structure(_HTML_BASIC)
    # 직렬화 결과에 password value 가 포함되어 있지 않아야 함
    serialized = json.dumps(r, ensure_ascii=False)
    assert "SUPER_SECRET_PW" not in serialized
    for item in r["inputs"]:
        assert "value" not in item  # value 키 자체가 없음


def test_hidden_csrf_value_not_in_result() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    r = analyze_html_structure(_HTML_BASIC)
    serialized = json.dumps(r, ensure_ascii=False)
    assert "HIDDEN_CSRF_VALUE_ABCDEF" not in serialized
    assert "SESSION_XYZ" not in serialized
    # meta name=csrf-token 의 content 도 드롭되어야 함
    assert "SECRET_TOKEN_9999" not in serialized


def test_form_has_password_and_hidden() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    r = analyze_html_structure(_HTML_BASIC)
    assert len(r["forms"]) == 1
    form = r["forms"][0]
    assert form["method"] == "post"
    assert form["has_password"] is True
    assert form["has_hidden"] is True
    assert form["field_count"] >= 4
    # password 또는 danger_write submit 이 있으므로 최소 medium
    assert form["risk_level"] in ("medium", "danger_write")


# ─── 표/키워드 ─────────────────────────────────────────────────────────────


def test_table_headers_rows_columns() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    r = analyze_html_structure(_HTML_BASIC)
    assert len(r["tables"]) == 1
    t = r["tables"][0]
    assert t["headers"] == ["기성 차수", "청구 금액", "상태"]
    # thead tr + tbody tr x 2 = 3 rows
    assert t["row_count"] == 3
    assert t["column_count"] == 3
    # 헤더에 "기성"·"청구" 키워드 → purpose_candidate 반영
    assert "기성" in t["purpose_candidate"]
    assert "청구" in t["purpose_candidate"]


def test_business_keyword_scoring_on_links() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    html = """
    <a href="/projects/contracts">계약 현황</a>
    <a href="/static/about.html">About</a>
    <a href="/invoices/기성정산">기성 정산 내역</a>
    """
    r = analyze_html_structure(html, keyword_hints=["기성", "청구", "정산", "계약"])
    by_text = {link["text"]: link for link in r["links"]}
    # 비즈니스 키워드 링크는 "About" 링크보다 점수가 높아야 함
    assert by_text["계약 현황"]["keyword_score"] > by_text["About"]["keyword_score"]
    assert by_text["기성 정산 내역"]["keyword_score"] >= by_text["About"]["keyword_score"] + 2


# ─── 경계/안전 ─────────────────────────────────────────────────────────────


def test_empty_html_returns_safe_empty_result() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    r = analyze_html_structure("")
    assert r["ok"] is True
    assert r["page_title"] == ""
    assert r["headings"] == []
    assert r["links"] == []
    assert r["buttons"] == []
    assert r["forms"] == []
    assert r["tables"] == []
    assert r["risky_elements"] == []


def test_recommended_actions_are_read_only() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    r = analyze_html_structure(_HTML_BASIC)
    recs = r["recommended_actions"]
    forbidden = {"click", "submit", "delete", "save", "press", "execute", "post", "remove"}
    for rec in recs:
        act = str(rec.get("action", "")).lower()
        assert act not in forbidden, f"recommended action must be read-only, got {act!r}"
        # 위험 동사 포함 여부도 검사
        for bad in ("click", "submit", "delete", "save", "post", "remove"):
            assert bad not in act, f"recommended action contains danger verb: {act!r}"


def test_full_html_body_not_in_result() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    unique_marker = "UNIQUE_PLAIN_TEXT_MARKER_ABCDEFG_12345"
    html = f"<html><body><div>preamble {unique_marker} tail</div><p>extra</p></body></html>"
    r = analyze_html_structure(html)
    serialized = json.dumps(r, ensure_ascii=False)
    # 원문 본문의 임의 마커가 결과에 포함되면 안 됨 (요약만 수집해야 함)
    assert unique_marker not in serialized


# ─── URL validator ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "file://C:/Windows/system.ini",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "about:blank",
        "chrome://settings",
        "edge://settings",
        "ftp://example.com/",
    ],
)
def test_validate_url_blocks_dangerous_schemes(url: str) -> None:
    from core.agent_runtime.browser.web_reader import validate_url_for_readonly_open

    r = validate_url_for_readonly_open(url)
    assert r["ok"] is False
    assert r["error_code"] in {"URL_SCHEME_BLOCKED", "URL_NO_HOST", "URL_PARSE_FAILED"}


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://localhost:8080/admin",
        "http://127.0.0.1/",
        "http://0.0.0.0/",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
    ],
)
def test_validate_url_blocks_internal_addresses(url: str) -> None:
    from core.agent_runtime.browser.web_reader import validate_url_for_readonly_open

    r = validate_url_for_readonly_open(url)
    assert r["ok"] is False
    assert r["error_code"] == "URL_HOST_BLOCKED"


def test_validate_url_accepts_public_https() -> None:
    from core.agent_runtime.browser.web_reader import validate_url_for_readonly_open

    r = validate_url_for_readonly_open("https://example.com/path?x=1")
    assert r["ok"] is True
    assert r["scheme"] == "https"
    assert r["host"] == "example.com"


def test_validate_url_allow_private_network_opt_in() -> None:
    from core.agent_runtime.browser.web_reader import validate_url_for_readonly_open

    blocked = validate_url_for_readonly_open("http://127.0.0.1/")
    assert blocked["ok"] is False
    ok = validate_url_for_readonly_open("http://127.0.0.1/", allow_private_network=True)
    assert ok["ok"] is True


# ─── action 통합 ───────────────────────────────────────────────────────────


def test_execute_action_web_analyze_html() -> None:
    from core.agent_runtime.connection.actions import execute_action

    result = execute_action(
        "web_analyze_html",
        {"html": _HTML_BASIC, "base_url": "https://example.com/"},
    )
    assert result.success is True
    assert "page_structure" in result.data
    page = result.data["page_structure"]
    assert page["ok"] is True
    assert page["counts"]["buttons"] >= 4


def test_execute_action_web_analyze_html_missing_html() -> None:
    from core.agent_runtime.connection.actions import execute_action

    result = execute_action("web_analyze_html", {})
    assert result.success is False
    assert result.error_code == "MISSING_HTML"


# ─── 민감 토큰 종합 스캔 ───────────────────────────────────────────────────


def test_result_contains_no_known_sensitive_tokens() -> None:
    from core.agent_runtime.browser.web_reader import analyze_html_structure

    html = """
    <html><body>
      <form action="/login" method="post">
        <input type="password" name="pw" value="TOP_SECRET_PW_1234">
        <input type="hidden" name="authorization" value="Bearer ABC.DEF.GHI">
        <input type="hidden" name="set-cookie" value="sid=123; HttpOnly">
        <input type="hidden" name="access_token" value="AT_9999">
        <input type="hidden" name="refresh_token" value="RT_9999">
      </form>
    </body></html>
    """
    r = analyze_html_structure(html)
    s = json.dumps(r, ensure_ascii=False)
    for token in (
        "TOP_SECRET_PW_1234",
        "Bearer ABC.DEF.GHI",
        "sid=123; HttpOnly",
        "AT_9999",
        "RT_9999",
    ):
        assert token not in s, f"sensitive token leaked: {token!r}"


# ─── 금지 API / 라이브러리 정적 검사 ───────────────────────────────────────


def test_no_browser_automation_or_mutation_apis() -> None:
    """web_reader / 새 action 코드에 클릭·입력·브라우저 자동화 호출이 없는지."""
    from pathlib import Path

    import core.agent_runtime.browser.web_reader as wr
    import core.agent_runtime.connection.actions as ac

    reader_src = Path(wr.__file__).read_text(encoding="utf-8")
    actions_src = Path(ac.__file__).read_text(encoding="utf-8")

    # web_reader 모듈에는 브라우저/자동화 라이브러리 import 나 호출이 없어야 함
    for token in (
        "playwright",
        "selenium",
        "pyppeteer",
        "webdriver",
        "ChromeDriver",
        "geckodriver",
        ".click(",
        "type_text",
        "submit_form",
        "send_keys",
    ):
        assert token not in reader_src, f"{token!r} found in web_reader.py"

    # actions.py 의 web_analyze_html 관련 블록 — 전체적으로도 브라우저 자동화 호출 없음
    for token in ("playwright", "selenium", "pyppeteer", "webdriver", "send_keys"):
        assert token not in actions_src, f"{token!r} found in actions.py"
