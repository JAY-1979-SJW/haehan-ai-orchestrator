"""릴스 슬라이드에 장별 자막을 얹은 뒤 ffmpeg로 이어붙인다.

overlay.py는 캐러셀용 4:5(1080x1350) 캔버스라, 릴스용 9:16(1080x1920)
캔버스로 같은 로직을 재사용한다. 자막은 화면 하단 그라데이션 위에 표시.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from scripts.instagram.overlay import fit_cover, wrap_text

FONT_BOLD = r"C:\Windows\Fonts\malgunbd.ttf"
FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
W, H = 1080, 1920


def _fit_cover(img: Image.Image) -> Image.Image:
    return fit_cover(img, W, H)


_wrap = wrap_text


def render_reel_slide(src: Path, dst: Path, text: str) -> Path:
    img = _fit_cover(Image.open(src).convert("RGB"))
    draw = ImageDraw.Draw(img, "RGBA")

    f_title = ImageFont.truetype(FONT_BOLD, 66)
    margin = 70
    max_w = W - margin * 2
    lines = _wrap(draw, text, f_title, max_w)
    block_h = len(lines) * 84 + 100

    y0 = H - block_h
    grad = Image.new("L", (1, block_h))
    for yy in range(block_h):
        t = yy / max(block_h - 1, 1)
        grad.putpixel((0, yy), int(220 * t))
    mask = grad.resize((W, block_h))
    shade = Image.new("RGB", (W, block_h), (0, 0, 0))
    img.paste(shade, (0, y0), mask)
    draw = ImageDraw.Draw(img, "RGBA")

    y = y0 + 50
    for ln in lines:
        draw.text((margin, y), ln, font=f_title, fill=(255, 255, 255))
        y += 84

    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, quality=92)
    return dst
