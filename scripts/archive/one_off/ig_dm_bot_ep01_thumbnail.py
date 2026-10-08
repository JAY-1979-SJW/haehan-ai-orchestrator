"""인스타 DM 봇 1편 — 유튜브 썸네일 제작.

"만든 방법"이 아니라 "누구에게 왜 필요한가"(자영업자·홍보담당자의 고객문의 응대 부담)를
1초 안에 읽히게 하는 썸네일. 1280x720, YouTube 썸네일 규격.

실행: python scripts/archive/one_off/ig_dm_bot_ep01_thumbnail.py
출력: data/video/ig_dm_bot_ep01/thumbnail.jpg (+ OneDrive 로컬 데이터 디렉터리)
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from ai_orchestrator.core.config import get_local_data_dir  # noqa: E402
from scripts.archive.one_off.kotara_ctc_reel import _cover, _font  # noqa: E402

OUT_DIR = get_local_data_dir() / "video" / "ig_dm_bot_ep01"
DEMO_DIR = OUT_DIR / "demo_frames"

W, H = 1280, 720
FONT_BOLD = str(Path(os.environ.get("WINDIR", "")) / "Fonts" / "malgunbd.ttf")
FONT_REG = str(Path(os.environ.get("WINDIR", "")) / "Fonts" / "malgun.ttf")

INK = (24, 22, 20)
GOLD = (196, 164, 108)
WHITE = (255, 255, 255)
RED = (214, 78, 64)


def build() -> Image.Image:
    bg_path = DEMO_DIR / "02_dm_received.png"
    photo = Image.open(bg_path).convert("RGB")
    img = _cover(photo, W, H, focus_y=0.3)
    overlay = Image.new("RGBA", (W, H), (10, 9, 8, 195))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    # 타겟 배지 (좌상단)
    badge_font = _font(FONT_BOLD, 30)
    badge_text = "자영업자 · 홍보담당자 필독"
    bw = draw.textlength(badge_text, font=badge_font) + 50
    draw.rounded_rectangle([40, 40, 40 + bw, 96], radius=28, fill=RED)
    draw.text((65, 52), badge_text, font=badge_font, fill=WHITE)

    # 메인 헤드라인 — 통증 포인트
    f_head = _font(FONT_BOLD, 78)
    lines = ["댓글 답장,", "밤새 놓치고 계신가요?"]
    y = 150
    for ln in lines:
        draw.text((60, y), ln, font=f_head, fill=WHITE)
        y += 92

    # 서브 헤드라인 — 해결책
    f_sub = _font(FONT_BOLD, 46)
    sub = "AI가 대신 DM 보내드립니다"
    draw.text((60, y + 20), sub, font=f_sub, fill=GOLD)

    # 하단 우측 강조 텍스트
    f_small = _font(FONT_BOLD, 34)
    small = "툴 없이 직접 만든 방법 공개"
    tw = draw.textlength(small, font=f_small)
    draw.rounded_rectangle([W - tw - 90, H - 90, W - 30, H - 30], radius=16, fill=(255, 255, 255, 230))
    draw.text((W - tw - 65, H - 80), small, font=f_small, fill=INK)

    return img


def main() -> None:
    img = build()
    out = OUT_DIR / "thumbnail.jpg"
    img.save(out, quality=92)
    print(f"썸네일 저장: {out}")


if __name__ == "__main__":
    main()
