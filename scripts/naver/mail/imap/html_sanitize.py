"""메일 HTML 정제 — 허용 목록 방식. 서식 편집기의 결과를 보내기 전에, 받은 메일을 답장/전달 인용으로 쓰기 전에 거친다.

기준서: docs/specs/2026-10-01_naver_mailbox_tab.md 10-1. 표준 라이브러리만 사용한다(네트워크 없음).
- 태그·속성·CSS 속성은 허용 목록에 있는 것만 남긴다. script/style/iframe/form 등은 내용까지 지운다.
- 링크는 http/https/mailto 만. 이미지는 `data:image/(png|jpeg|gif|webp);base64` 와 `cid:` 만 — 외부 이미지 주소는 추적(읽음 확인) 위험이라 제거한다.
- 앱 화면의 편집기(contentEditable)에는 이 모듈을 거친 HTML 만 넣는다.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

ALLOWED_TAGS = frozenset(
    {
        "a", "b", "strong", "i", "em", "u", "s", "strike", "del", "ins", "sub", "sup", "br", "p", "div", "span",
        "ul", "ol", "li", "blockquote", "h1", "h2", "h3", "h4", "pre", "code", "hr",
        "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "img", "font",
    }
)  # fmt: skip
VOID_TAGS = frozenset({"br", "hr", "img"})
# 닫는 태그가 없는 요소(<meta>, <link> 처럼) — 지우기만 하고 "내용 건너뛰기" 상태로 들어가면 뒤쪽 본문이 전부 사라진다
NO_END_TAGS = frozenset(
    {"meta", "link", "base", "input", "embed", "area", "col", "param", "source", "track", "wbr", "frame"}
)
# 내용까지 통째로 버리는 태그
DROP_WITH_CONTENT = frozenset(
    {"script", "style", "iframe", "object", "embed", "form", "head", "title", "noscript", "template", "svg", "math", "textarea", "select", "button", "link", "meta", "base", "applet", "frame", "frameset"}
)  # fmt: skip
ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "title"}),
    "img": frozenset({"src", "alt", "width", "height"}),
    "td": frozenset({"colspan", "rowspan", "align"}),
    "th": frozenset({"colspan", "rowspan", "align"}),
    "font": frozenset({"color", "size", "face"}),
    "div": frozenset({"align"}),
    "p": frozenset({"align"}),
}
ALLOWED_STYLE_PROPS = frozenset(
    {
        "color", "background-color", "background", "font-size", "font-family", "font-weight", "font-style",
        "text-decoration", "text-align", "line-height", "margin", "margin-left", "margin-right", "margin-top",
        "margin-bottom", "padding", "padding-left", "padding-right", "padding-top", "padding-bottom",
        "border", "border-left", "border-collapse", "width", "text-indent", "white-space",
    }
)  # fmt: skip
_STYLE_VALUE = re.compile(r"^[#\w\s%.,()'\"-]+$")
_STYLE_FORBIDDEN = re.compile(r"url\s*\(|expression|javascript|@import|behavior|-moz-binding", re.IGNORECASE)
_SAFE_DATA_IMAGE = re.compile(r"^data:image/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=\s]+$", re.IGNORECASE)
_SAFE_CID = re.compile(r"^cid:[\w.@+-]{1,120}$", re.IGNORECASE)
_NUM = re.compile(r"^\d{1,4}%?$")
_SAFE_SCHEMES = frozenset({"http", "https", "mailto"})
MAX_HTML_CHARS = 600_000
MAX_INLINE_IMAGE_BYTES = 5 * 1024 * 1024
MAX_INLINE_TOTAL_BYTES = 10 * 1024 * 1024


def _clean_style(value: str) -> str:
    out = []
    for decl in value.split(";"):
        prop, sep, val = decl.partition(":")
        prop, val = prop.strip().lower(), val.strip()
        if not sep or prop not in ALLOWED_STYLE_PROPS or not val:
            continue
        if _STYLE_FORBIDDEN.search(val) or not _STYLE_VALUE.match(val):
            continue
        out.append(f"{prop}: {val}")
    return "; ".join(out)


def _clean_href(value: str) -> str | None:
    value = value.strip()
    if not value or re.search(r"[\x00-\x20]", value[:8]):  # 앞쪽 공백·제어문자로 스킴을 숨기는 우회 차단
        return None
    return value if urlparse(value).scheme.lower() in _SAFE_SCHEMES else None


def _clean_img_src(value: str, max_data_bytes: int | None) -> str | None:
    value = value.strip()
    if _SAFE_CID.match(value):
        return value
    if _SAFE_DATA_IMAGE.match(value):
        if max_data_bytes is not None and len(value) * 3 // 4 > max_data_bytes:
            return None
        return re.sub(r"\s+", "", value)
    return None  # 외부 주소(http/https)는 추적 위험으로 제거


class _Sanitizer(HTMLParser):
    def __init__(self, max_data_bytes: int | None) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []
        self.skip_depth = 0
        self.max_data_bytes = max_data_bytes

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in NO_END_TAGS:
            return  # 속성만 있는 요소는 통째로 버리고 상태를 바꾸지 않는다
        if self.skip_depth:
            if tag in DROP_WITH_CONTENT:
                self.skip_depth += 1
            return
        if tag in DROP_WITH_CONTENT:
            self.skip_depth = 1
            return
        if tag not in ALLOWED_TAGS:
            return  # 감싸는 태그만 풀고 내용은 유지
        rendered = self._attrs(tag, attrs)
        if tag == "img" and not any(a.startswith(" src=") for a in rendered):
            return  # 주소가 제거된 이미지는 통째로 뺀다
        self.out.append(f"<{tag}{''.join(rendered)}>")
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and not self.skip_depth:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in NO_END_TAGS:
            return
        if self.skip_depth:
            if tag in DROP_WITH_CONTENT:
                self.skip_depth -= 1
            return
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS and tag in self.stack:
            while self.stack:  # 열린 태그를 안쪽부터 닫아 짝을 맞춘다
                top = self.stack.pop()
                self.out.append(f"</{top}>")
                if top == tag:
                    break

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.out.append(html.escape(data, quote=False))

    def _attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> list[str]:
        allowed = ALLOWED_ATTRS.get(tag, frozenset())
        out: list[str] = []
        for name, raw in attrs:
            name, value = name.lower(), (raw or "")
            if name == "style":
                style = _clean_style(value)
                if style:
                    out.append(f' style="{html.escape(style, quote=True)}"')
            elif name in allowed:
                cleaned = self._attr_value(tag, name, value)
                if cleaned is not None:
                    out.append(f' {name}="{html.escape(cleaned, quote=True)}"')
        if tag == "a" and any(a.startswith(" href=") for a in out):
            out.append(' target="_blank" rel="noopener noreferrer"')
        return out

    def _attr_value(self, tag: str, name: str, value: str) -> str | None:
        if name == "href":
            return _clean_href(value)
        if name == "src":
            return _clean_img_src(value, self.max_data_bytes)
        if name in {"width", "height", "colspan", "rowspan", "size"}:
            return value.strip() if _NUM.match(value.strip()) else None
        if name == "align":
            return value.strip().lower() if value.strip().lower() in {"left", "right", "center", "justify"} else None
        if name in {"color", "face", "alt", "title"}:
            return value[:200] if _STYLE_VALUE.match(value) or name in {"alt", "title"} else None
        return None

    def result(self) -> str:
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)


def sanitize_html(raw: str, *, max_data_image_bytes: int | None = None) -> str:
    """허용 목록으로 정제한 HTML. `max_data_image_bytes` 를 주면 그보다 큰 내장 이미지는 뺀다(인용용)."""
    parser = _Sanitizer(max_data_image_bytes)
    parser.feed(raw[:MAX_HTML_CHARS])
    parser.close()
    return parser.result()


_BLOCK_TAGS = frozenset({"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "blockquote", "pre", "table", "hr"})


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.href: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in NO_END_TAGS:
            return
        if tag in DROP_WITH_CONTENT:
            self.skip += 1
        elif tag == "br" or tag in _BLOCK_TAGS:
            self.parts.append("\n")
            if tag == "li":
                self.parts.append("- ")
        elif tag == "a":
            self.href.append(dict(attrs).get("href"))

    def handle_endtag(self, tag: str) -> None:
        if tag in NO_END_TAGS:
            return
        if tag in DROP_WITH_CONTENT:
            self.skip = max(0, self.skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag == "a" and self.href:
            link = self.href.pop()
            text = "".join(self.parts[-20:])
            if link and link not in text and link.startswith(("http://", "https://")):
                self.parts.append(f" ({link})")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    """텍스트 대체본(multipart/alternative 의 plain 부분) — 줄바꿈을 살리고 빈 줄은 한 줄로 줄인다."""
    parser = _TextExtractor()
    parser.feed(raw[:MAX_HTML_CHARS])
    parser.close()
    text = "".join(parser.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def text_to_html(text: str) -> str:
    """평문 본문을 인용용 HTML 로 — 줄바꿈 유지, 특수문자 이스케이프."""
    return "<br>".join(html.escape(line, quote=False) for line in text.rstrip("\n").split("\n"))


@dataclass(frozen=True)
class InlineImage:
    cid: str
    subtype: str  # png | jpeg | gif | webp
    data: bytes


_DATA_IMG_ATTR = re.compile(r'src="data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=]+)"', re.IGNORECASE)


def split_inline_images(clean_html: str) -> tuple[str, list[InlineImage]]:
    """정제된 HTML 의 `data:` 이미지를 본문 속 첨부(cid)로 바꾸고 이미지 목록을 돌려준다. 크기 초과·깨진 이미지는 ValueError."""
    images: list[InlineImage] = []
    total = 0

    def _swap(match: re.Match[str]) -> str:
        nonlocal total
        subtype, payload = match.group(1).lower(), match.group(2)
        try:
            data = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as e:
            raise ValueError("본문 이미지를 해석하지 못했습니다") from e
        if len(data) > MAX_INLINE_IMAGE_BYTES:
            raise ValueError("본문 이미지 하나는 5MB 이하여야 합니다")
        total += len(data)
        if total > MAX_INLINE_TOTAL_BYTES:
            raise ValueError("본문 이미지 합계는 10MB 이하여야 합니다")
        cid = f"img{len(images) + 1}.{hashlib.sha256(payload.encode()).hexdigest()[:10]}@haehan"
        images.append(InlineImage(cid, subtype, data))
        return f'src="cid:{cid}"'

    return _DATA_IMG_ATTR.sub(_swap, clean_html), images
