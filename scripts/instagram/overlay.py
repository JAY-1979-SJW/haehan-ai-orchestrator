"""캐러셀 이미지에 장별 안내 문구를 얹는다 (정보성 슬라이드).

인스타 캐러셀은 캡션이 하나뿐이라, 장마다 다른 정보를 주려면 이미지 자체에
텍스트를 합성해야 한다. 주부·셀프인테리어 관심층이 실제로 궁금해하는 것을
장별로 하나씩 답해주는 구성으로 쓴다.

비율은 4:5(1080x1350) — 인스타 피드에서 세로 화면을 가장 많이 차지한다.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_BOLD = r"C:\Windows\Fonts\malgunbd.ttf"
FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
W, H = 1080, 1350

ACCENT = (255, 214, 102)  # 따뜻한 조명색 포인트


def fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """w×h 캔버스를 꽉 채우도록 리사이즈 후 중앙 크롭(캐러셀 4:5·릴스 9:16 공용 — reel_overlay 도 사용)."""
    src_ratio = img.width / img.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:
        nh = h
        nw = int(nh * src_ratio)
    else:
        nw = w
        nh = int(nw / src_ratio)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _fit_cover(img: Image.Image) -> Image.Image:
    """4:5 캔버스를 꽉 채우도록 리사이즈 후 중앙 크롭."""
    return fit_cover(img, W, H)


def wrap_text(draw, text: str, font, max_w: int) -> list[str]:
    """글자 단위로 max_w(픽셀)를 넘기 전에 줄을 나눈다(줄바꿈 문자는 강제 줄바꿈). reel_overlay 도 사용."""
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        test = cur + ch
        if draw.textlength(test, font=font) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


_wrap = wrap_text


def render_slide(
    src: Path,
    dst: Path,
    title: str,
    body: str = "",
    badge: str = "",
    position: str = "bottom",
) -> Path:
    img = _fit_cover(Image.open(src).convert("RGB"))
    draw = ImageDraw.Draw(img, "RGBA")

    f_badge = ImageFont.truetype(FONT_BOLD, 34)
    f_title = ImageFont.truetype(FONT_BOLD, 62)
    f_body = ImageFont.truetype(FONT_REG, 40)

    margin = 70
    max_w = W - margin * 2
    title_lines = _wrap(draw, title, f_title, max_w)
    body_lines = _wrap(draw, body, f_body, max_w) if body else []

    block_h = len(title_lines) * 80 + (len(body_lines) * 56 if body_lines else 0)
    if badge:
        block_h += 70
    block_h += 90

    if position == "top":
        y0 = 0
        grad_from, grad_to = 235, 0
    else:
        y0 = H - block_h
        grad_from, grad_to = 0, 235

    # 가독성용 그라데이션 오버레이 — 픽셀 단위 마스크로 만들어 밴딩(줄무늬) 방지
    grad = Image.new("L", (1, block_h))
    for yy in range(block_h):
        t = yy / max(block_h - 1, 1)
        grad.putpixel((0, yy), int(grad_from + (grad_to - grad_from) * t))
    mask = grad.resize((W, block_h))
    shade = Image.new("RGB", (W, block_h), (0, 0, 0))
    img.paste(shade, (0, y0), mask)
    draw = ImageDraw.Draw(img, "RGBA")

    y = y0 + 45
    if badge:
        bw = draw.textlength(badge, font=f_badge)
        draw.rounded_rectangle([margin, y, margin + bw + 44, y + 56], radius=28, fill=ACCENT)
        draw.text((margin + 22, y + 10), badge, font=f_badge, fill=(30, 30, 30))
        y += 74

    for ln in title_lines:
        draw.text((margin, y), ln, font=f_title, fill=(255, 255, 255))
        y += 80

    if body_lines:
        y += 10
        for ln in body_lines:
            draw.text((margin, y), ln, font=f_body, fill=(235, 235, 235))
            y += 56

    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, quality=92)
    return dst
