"""메일 HTML 정제(html_sanitize) — 서식 편집기 결과·받은 메일 인용을 안전하게 만드는 허용 목록 규칙."""

from __future__ import annotations

import base64

import pytest

from scripts.naver.mail.imap import html_sanitize as hs

PNG = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000000020001e221bc330000000049454e44ae426082"
    )
).decode()


def clean(raw, **kw):
    return hs.sanitize_html(raw, **kw)


def test_basic_formatting_is_kept():
    out = clean(
        '<p style="color: #c00; text-align:center">안녕 <b>굵게</b> <i>기울임</i> <u>밑줄</u></p><ul><li>하나</li></ul>'
    )
    assert 'style="color: #c00; text-align: center"' in out and "<b>굵게</b>" in out and "<ul><li>하나</li></ul>" in out


@pytest.mark.parametrize(
    "attack",
    [
        "<script>alert(1)</script>x",
        "<img src=x onerror=alert(1)>",
        '<a href="javascript:alert(1)">클릭</a>',
        '<a href=" javascript:alert(1)">클릭</a>',
        '<a href="JaVaScRiPt:alert(1)">클릭</a>',
        '<a href="data:text/html,<script>alert(1)</script>">x</a>',
        "<iframe src='https://evil.example'></iframe>",
        "<object data=x></object><embed src=x>",
        '<form action="https://evil.example"><input name=p></form>',
        "<svg onload=alert(1)><circle/></svg>",
        '<p onclick="alert(1)">x</p>',
        '<div style="background:url(https://evil.example/a.png)">x</div>',
        '<div style="width:expression(alert(1))">x</div>',
        "<style>body{background:url(https://evil.example)}</style>x",
        '<meta http-equiv="refresh" content="0;url=https://evil.example">',
        '<base href="https://evil.example/">',
    ],
)
def test_dangerous_markup_is_removed(attack):
    out = clean(attack).lower()
    for bad in (
        "<script",
        "onerror",
        "onclick",
        "onload",
        "javascript:",
        "<iframe",
        "<object",
        "<embed",
        "<form",
        "<input",
        "<svg",
        "<style",
        "url(",
        "expression",
        "<meta",
        "<base",
        "data:text",
    ):
        assert bad not in out, (attack, out)


def test_links_keep_only_safe_schemes_and_open_safely():
    out = clean(
        '<a href="https://example.com/a?b=1&c=2">사이트</a> <a href="mailto:a@example.com">메일</a> <a href="/relative">상대</a>'
    )
    assert 'href="https://example.com/a?b=1&amp;c=2" target="_blank" rel="noopener noreferrer"' in out
    assert 'href="mailto:a@example.com"' in out and "/relative" not in out


def test_external_images_are_removed_but_embedded_ones_stay():
    assert "<img" not in clean('<img src="https://tracker.example/pixel.gif">')
    assert "<img" not in clean('<img src="http://tracker.example/pixel.gif">')
    assert "<img" not in clean('<img src="//tracker.example/p.gif">')
    ok = clean(f'<img src="data:image/png;base64,{PNG}" alt="로고">')
    assert f"data:image/png;base64,{PNG}" in ok and 'alt="로고"' in ok
    assert "<img" not in clean('<img src="data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=">')
    assert 'src="cid:logo1@x"' in clean('<img src="cid:logo1@x">')


def test_void_elements_in_head_do_not_swallow_the_body():
    """실제 메일 회귀: <meta>(닫는 태그 없음)를 '내용 제거 태그'로 취급해 본문 전체가 사라지던 문제."""
    page = '<html><head><meta charset="utf-8"><link rel="stylesheet" href="x.css"><title>t</title></head><body><p>본문</p><input name=a><p>둘째</p></body></html>'
    assert clean(page) == "<p>본문</p><p>둘째</p>"
    assert hs.html_to_text(page) == "본문\n\n둘째"


def test_big_embedded_images_can_be_dropped_for_quotes():
    assert "<img" not in clean(f'<img src="data:image/png;base64,{PNG}">', max_data_image_bytes=10)


def test_unknown_tags_are_unwrapped_and_unbalanced_tags_are_closed():
    assert clean("<custom>글자</custom>") == "글자"
    assert clean("<div><p><b>끝") == "<div><p><b>끝</b></p></div>"
    assert clean("</b>고아 닫힘") == "고아 닫힘"


def test_nested_dropped_tags_and_text_escaping():
    # 브라우저와 같이 첫 </script> 에서 스크립트가 끝난다 — 남는 글자 "y" 는 일반 텍스트라 안전하다
    out = clean("<script><script>alert(1)</script>y</script>보임")
    assert "alert" not in out and "<script" not in out and out.endswith("보임")
    assert clean("1 < 2 & 3 > 2") == "1 &lt; 2 &amp; 3 &gt; 2"
    assert "&lt;script&gt;" in clean("&lt;script&gt;alert(1)&lt;/script&gt;")


def test_style_values_are_validated():
    out = clean(
        "<span style=\"color:red;font-size:14px;position:fixed;font-family:'Malgun Gothic', sans-serif\">x</span>"
    )
    assert "position" not in out and "color: red" in out and "font-size: 14px" in out and "Malgun Gothic" in out
    assert "style" not in clean('<span style="color:red;;background:url(x)">y</span>'.replace("color:red;;", ""))


def test_html_to_text_keeps_line_structure_and_links():
    text = hs.html_to_text(
        '<p>첫 줄</p><p>둘째 <b>줄</b></p><ul><li>가</li><li>나</li></ul><a href="https://example.com">링크</a><script>SCRIPTBODY</script>'
    )
    assert text.splitlines()[0] == "첫 줄" and "둘째 줄" in text and "- 가" in text and "- 나" in text
    assert "https://example.com" in text and "SCRIPTBODY" not in text


def test_text_to_html_escapes_and_keeps_newlines():
    assert hs.text_to_html("a<b>\n둘째 & 셋째") == "a&lt;b&gt;<br>둘째 &amp; 셋째"


def test_inline_images_become_cid_parts():
    html_in = hs.sanitize_html(
        f'<p>사진</p><img src="data:image/png;base64,{PNG}"><img src="data:image/png;base64,{PNG}">'
    )
    out, images = hs.split_inline_images(html_in)
    assert len(images) == 2 and all(i.subtype == "png" and i.data[:4] == b"\x89PNG" for i in images)
    assert "data:image" not in out and out.count('src="cid:') == 2 and images[0].cid in out
    assert images[0].cid != images[1].cid


def test_inline_image_limits(monkeypatch):
    monkeypatch.setattr(hs, "MAX_INLINE_IMAGE_BYTES", 10)
    with pytest.raises(ValueError, match="5MB"):
        hs.split_inline_images(f'<img src="data:image/png;base64,{PNG}">')
    monkeypatch.setattr(hs, "MAX_INLINE_IMAGE_BYTES", 10_000)
    monkeypatch.setattr(hs, "MAX_INLINE_TOTAL_BYTES", 100)
    with pytest.raises(ValueError, match="10MB"):
        hs.split_inline_images(f'<img src="data:image/png;base64,{PNG}"><img src="data:image/png;base64,{PNG}">')
