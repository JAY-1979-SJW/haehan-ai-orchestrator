"""제품 상세페이지 6장 생성 템플릿 (v2) — 채팅에서 검증한 디자인을 이 저장소 환경으로 이식.

원본은 리눅스 샌드박스 기준(폰트 /usr/share/fonts/..., 이미지 /home/claude/...)이라
이 프로젝트에서 그대로 실행 불가. 아래로 교체:
  - 폰트: Windows 맑은고딕 (C:/Windows/Fonts/malgun*.ttf)
  - 제품 사진: data/mk_catalog/crops/{code}_*.png (카탈로그 페이지에서 크롭)
  - 출력: data/mk_catalog/detail/{code}/
  - 소재 한계: 카탈로그엔 제품당 45도 컷 1장뿐 → 색상별 컷은 그 사진을 좌우 분할한
    근사치이며 렌즈 클로즈업 원본이 없어 4페이지(컬러 옵션)는 클로즈업 없이 구성.

사용:
    from scripts.mk_catalog.detail_page_template import build_detail_pages
    build_detail_pages(
        name="COB 원통 레일 ∅55", code="422-001-019-800",
        size="∅55×H100", led="LED COB 3W", color_temp="전구색(3000K)",
        color="블랙 / 화이트", features="플리커프리",
        crop_both="data/mk_catalog/crops/422-001-019-800_both.png",
        crop_black="data/mk_catalog/crops/422-001-019-800_black.png",
        crop_white="data/mk_catalog/crops/422-001-019-800_white.png",
        out_dir="data/mk_catalog/detail/422-001-019-800",
    )
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W = 860
NAVY = (26, 34, 51)
RED = (214, 40, 57)
GOLD = (196, 154, 88)
GOLD_L = (224, 190, 130)
GRAY_BG = (245, 245, 247)
GRAY_TXT = (110, 114, 122)
LINE = (225, 226, 230)
WHITE = (255, 255, 255)
CREAM = (250, 246, 238)

FONT_DIR = Path("C:/Windows/Fonts")
_FONT_FILES = {
    "black": "malgunbd.ttf",
    "bold": "malgunbd.ttf",
    "medium": "malgun.ttf",
    "regular": "malgun.ttf",
    "light": "malgunsl.ttf",
}


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / _FONT_FILES[weight]), size)


def _new_canvas(h: int, bg=WHITE):
    img = Image.new("RGB", (W, h), bg)
    return img, ImageDraw.Draw(img)


def _center_text(d, text, y, f, fill=NAVY):
    bbox = d.textbbox((0, 0), text, font=f)
    tw = bbox[2] - bbox[0]
    d.text(((W - tw) / 2, y), text, font=f, fill=fill)
    return bbox[3] - bbox[1]


def _wrap_and_draw(d, text, x, y, f, max_width, fill, line_gap=10, center=False):
    lines, cur = [], ""
    for ch in text:
        test = cur + ch
        bbox = d.textbbox((0, 0), test, font=f)
        if bbox[2] - bbox[0] > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    yy = y
    for ln in lines:
        bbox = d.textbbox((0, 0), ln, font=f)
        xx = (W - (bbox[2] - bbox[0])) / 2 if center else x
        d.text((xx, yy), ln, font=f, fill=fill)
        yy += (bbox[3] - bbox[1]) + line_gap
    return yy


def _paste_fit(path, box_w, box_h):
    p = Image.open(path).convert("RGBA")
    ratio = min(box_w / p.width, box_h / p.height)
    nw, nh = int(p.width * ratio), int(p.height * ratio)
    return p.resize((nw, nh), Image.LANCZOS), nw, nh


def _same_image_bytes(path_a: str, path_b: str) -> bool:
    """두 이미지 파일이 (경로가 달라도) 같은 사진인지 바이트 단위로 비교."""
    a, b = Path(path_a), Path(path_b)
    if not a.exists() or not b.exists():
        return False
    return a.read_bytes() == b.read_bytes()


def _rounded_photo(path, box_w, box_h, radius=20):
    p, nw, nh = _paste_fit(path, box_w, box_h)
    mask = Image.new("L", (nw, nh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, nw, nh], radius=radius, fill=255)
    out = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
    out.paste(p, (0, 0), mask)
    return out, nw, nh


def build_detail_pages(
    *,
    name: str,
    code: str,
    size: str,
    led: str,
    color_temp: str,
    color: str,
    features: str,
    crop_both: str,
    crop_black: str,
    crop_white: str,
    out_dir: str,
) -> list[str]:
    """제품 상세페이지 6장(PNG) 생성. 저장된 파일 경로 리스트 반환."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    # ── 1. 커버 ──────────────────────────────────────────────
    img, d = _new_canvas(1050, bg=NAVY)
    d.polygon([(0, 650), (W, 520), (W, 1050), (0, 1050)], fill=WHITE)
    d.rectangle([0, 0, W, 8], fill=RED)
    _center_text(d, "MK LIGHTING", 70, font("medium", 22), fill=GOLD_L)
    _center_text(d, name, 120, font("black", 44), fill=WHITE)
    _center_text(d, f"제품코드 {code}", 190, font("regular", 22), fill=(180, 188, 205))

    hero, hw, hh = _paste_fit(crop_both, 700, 480)
    img.paste(hero, (int((W - hw) / 2), 280), hero)
    d = ImageDraw.Draw(img)

    y2 = 280 + hh + 50
    d.line([(80, y2), (W - 80, y2)], fill=LINE, width=2)
    y2 += 40
    _center_text(d, "군더더기 없는 심플한 실루엣", y2, font("bold", 28), fill=NAVY)
    y2 += 50
    y2 = _wrap_and_draw(
        d, f"{led} · {features} · 국제규격 3선 레일 전용", 80, y2, font("regular", 21), W - 160, GRAY_TXT, center=True
    )
    img = img.crop((0, 0, W, int(y2) + 40))
    p1 = str(out / "01_cover.png")
    img.save(p1)
    saved.append(p1)

    # ── 2. 치수 도면 ──────────────────────────────────────────
    img, d = _new_canvas(900, bg=NAVY)
    d.rectangle([0, 0, W, 8], fill=RED)
    y = 70
    _center_text(d, "DIMENSION", y, font("medium", 22), fill=GOLD_L)
    y += 55
    _center_text(d, "치수 정보", y, font("black", 38), fill=WHITE)
    y += 130

    cx = W // 2
    cyl_w, cyl_h = 160, 300
    left, right = cx - cyl_w // 2, cx + cyl_w // 2
    top_y = y
    d.ellipse([left, top_y, right, top_y + 40], outline=GOLD, width=4)
    d.line([(left, top_y + 20), (left, top_y + 20 + cyl_h)], fill=GOLD, width=4)
    d.line([(right, top_y + 20), (right, top_y + 20 + cyl_h)], fill=GOLD, width=4)
    d.arc([left, top_y + cyl_h, right, top_y + cyl_h + 40], 0, 180, fill=GOLD, width=4)

    dim_y = top_y - 45
    d.line([(left, dim_y), (right, dim_y)], fill=(150, 158, 175), width=2)
    d.line([(left, dim_y - 12), (left, dim_y + 12)], fill=(150, 158, 175), width=2)
    d.line([(right, dim_y - 12), (right, dim_y + 12)], fill=(150, 158, 175), width=2)
    f_dim = font("bold", 24)
    lab = size.split("×")[0] if "×" in size else size
    bbox = d.textbbox((0, 0), lab, font=f_dim)
    d.rectangle(
        [cx - (bbox[2] - bbox[0]) / 2 - 10, dim_y - 20, cx + (bbox[2] - bbox[0]) / 2 + 10, dim_y + 2], fill=NAVY
    )
    d.text((cx - (bbox[2] - bbox[0]) / 2, dim_y - 18), lab, font=f_dim, fill=WHITE)

    dim_x = right + 55
    d.line([(dim_x, top_y), (dim_x, top_y + cyl_h + 20)], fill=(150, 158, 175), width=2)
    lab2 = size.split("×")[1] if "×" in size else ""
    d.text((dim_x + 15, top_y + cyl_h / 2 - 12), lab2, font=f_dim, fill=WHITE)

    y_end = top_y + cyl_h + 100
    d.line([(80, y_end), (W - 80, y_end)], fill=(70, 78, 95), width=1)
    y_end += 35
    _center_text(d, "단위: mm · 실측 기준 (오차 ±1~2mm)", y_end, font("regular", 18), fill=(160, 168, 185))
    img = img.crop((0, 0, W, y_end + 70))
    p2 = str(out / "02_dimension.png")
    img.save(p2)
    saved.append(p2)

    # ── 3. 특장점 ────────────────────────────────────────────
    img, d = _new_canvas(950, bg=GRAY_BG)
    d.rectangle([0, 0, W, 8], fill=RED)
    y = 70
    _center_text(d, "FEATURE", y, font("medium", 22), fill=GOLD)
    y += 55
    _center_text(d, "이런 점이 다릅니다", y, font("black", 36), fill=NAVY)
    y += 90

    cards = [
        (led, "선명한 집광, 포인트 조명", NAVY),
        (features, "안정적인 사용감", RED),
        ("3선 레일 전용", "국제 규격 레일에 바로 장착", GOLD),
        (color, "공간에 맞게 선택", (70, 110, 130)),
    ]
    card_w = (W - 120 - 30) // 2
    card_h = 200
    for i, (title, desc, c) in enumerate(cards):
        cx0 = 60 + (i % 2) * (card_w + 30)
        cy0 = y + (i // 2) * (card_h + 30)
        d.rounded_rectangle([cx0, cy0, cx0 + card_w, cy0 + card_h], radius=18, fill=WHITE)
        d.rounded_rectangle([cx0, cy0, cx0 + card_w, cy0 + 10], radius=5, fill=c)
        ic = 50
        d.ellipse([cx0 + 25, cy0 + 30, cx0 + 25 + ic, cy0 + 30 + ic], outline=c, width=4)
        d.text((cx0 + 25, cy0 + 100), title, font=font("bold", 21), fill=NAVY)
        _wrap_and_draw(d, desc, cx0 + 25, cy0 + 140, font("regular", 17), card_w - 50, GRAY_TXT)

    y_end = y + 2 * (card_h + 30)
    img = img.crop((0, 0, W, y_end + 30))
    p3 = str(out / "03_feature.png")
    img.save(p3)
    saved.append(p3)

    # ── 4. 컬러 옵션 ─────────────────────────────────────────
    # ⚠️ 소재 한계: 카탈로그엔 제품당 컬러별 실사진이 없는 경우가 많음(45도 컷 1장뿐).
    # crop_black == crop_white(같은 파일)면 실제 촬영본이 1장뿐이라는 뜻 —
    # 없는 색상 사진을 지어내면 허위광고 리스크이므로, 이 경우 촬영된 색상만 정직하게 표시.
    single_photo = _same_image_bytes(crop_black, crop_white)

    if single_photo:
        img, d = _new_canvas(950, bg=WHITE)
        d.rectangle([0, 0, W, 8], fill=RED)
        y = 70
        _center_text(d, "COLOR", y, font("medium", 22), fill=GOLD)
        y += 55
        _center_text(d, color, y, font("black", 34), fill=NAVY)
        y += 90

        card_w = W - 120
        card_h = 560
        d.rounded_rectangle([60, y, 60 + card_w, y + card_h], radius=18, fill=GRAY_BG)
        main, mw, _mh = _paste_fit(crop_black, card_w - 80, card_h - 40)
        img.paste(main, (60 + int((card_w - mw) / 2), y + 20), main)
        d = ImageDraw.Draw(img)

        y_end = y + card_h + 40
        y_end = _wrap_and_draw(
            d,
            f"실제 촬영 사진 기준 색상이며, {color} 동일 구조로 제작됩니다.",
            80,
            y_end,
            font("regular", 20),
            W - 160,
            GRAY_TXT,
            center=True,
        )
        img = img.crop((0, 0, W, int(y_end) + 40))
        p4 = str(out / "04_color.png")
        img.save(p4)
        saved.append(p4)
    else:
        img, d = _new_canvas(1150, bg=WHITE)
        d.rectangle([0, 0, W, 8], fill=RED)
        y = 70
        _center_text(d, "COLOR", y, font("medium", 22), fill=GOLD)
        y += 55
        _center_text(d, color, y, font("black", 36), fill=NAVY)
        y += 90

        half = (W - 100) // 2
        card_h = 660
        for i, (label, path, bg) in enumerate([("BLACK", crop_black, NAVY), ("WHITE", crop_white, (225, 227, 232))]):
            x0 = 40 + i * (half + 20)
            d.rounded_rectangle([x0, y, x0 + half, y + card_h], radius=18, fill=bg)
            main, mw, _mh = _paste_fit(path, half - 60, card_h - 120)
            img.paste(main, (x0 + int((half - mw) / 2), y + 30), main)
            d = ImageDraw.Draw(img)
            txt_color = WHITE if i == 0 else NAVY
            tb = d.textbbox((0, 0), label, font=font("bold", 26))
            d.text((x0 + (half - (tb[2] - tb[0])) / 2, y + card_h - 55), label, font=font("bold", 26), fill=txt_color)

        y_end = y + card_h + 40
        _wrap_and_draw(
            d, "공간 분위기에 맞춰 컬러를 선택하세요.", 80, y_end, font("regular", 22), W - 160, GRAY_TXT, center=True
        )
        img = img.crop((0, 0, W, y_end + 70))
        p4 = str(out / "04_color.png")
        img.save(p4)
        saved.append(p4)

    # ── 5. 설치 안내 ─────────────────────────────────────────
    img, d = _new_canvas(1250, bg=WHITE)
    d.rectangle([0, 0, W, 8], fill=RED)
    y = 70
    _center_text(d, "INSTALLATION", y, font("medium", 22), fill=GOLD)
    y += 55
    _center_text(d, "레일 하나로 끝내는 설치", y, font("black", 34), fill=NAVY)
    y += 90

    items = [
        ("01", "국제 규격 3선 레일 호환", "시중 대부분의 트랙 레일에 별도 부속 없이 바로 장착됩니다."),
        ("02", "각도 조절 헤드", "설치 후에도 원하는 방향으로 빛의 각도를 자유롭게 조절할 수 있습니다."),
        ("03", "전문 시공 연계 가능", "제품 구매와 함께 현장 실측·배선·설치까지 진행해 드립니다."),
    ]
    for i, (num, title, desc) in enumerate(items):
        by = y + i * 210
        d.rounded_rectangle([60, by, W - 60, by + 170], radius=16, fill=GRAY_BG if i % 2 == 0 else CREAM)
        d.text((90, by + 25), num, font=font("black", 54), fill=(GOLD if i % 2 == 0 else RED))
        d.text((210, by + 30), title, font=font("bold", 24), fill=NAVY)
        _wrap_and_draw(d, desc, 210, by + 72, font("regular", 19), W - 210 - 80, GRAY_TXT, line_gap=6)

    y_final = y + len(items) * 210 + 10
    d.rounded_rectangle([60, y_final, W - 60, y_final + 160], radius=16, fill=NAVY)
    _center_text(d, "시공 문의는 채널톡·카카오톡으로", y_final + 45, font("medium", 22), fill=WHITE)
    _center_text(
        d,
        "구매 전 상담 시 현장 조건에 맞는 제품을 추천해 드립니다",
        y_final + 90,
        font("regular", 18),
        fill=(210, 215, 225),
    )
    img = img.crop((0, 0, W, y_final + 160 + 40))
    p5 = str(out / "05_install.png")
    img.save(p5)
    saved.append(p5)

    # ── 6. 사양표 + 배송/AS ──────────────────────────────────
    img, d = _new_canvas(1300, bg=WHITE)
    d.rectangle([0, 0, W, 8], fill=RED)
    y = 70
    _center_text(d, "SPEC & GUIDE", y, font("medium", 22), fill=GOLD)
    y += 55
    _center_text(d, "제품 사양 · 배송 안내", y, font("black", 34), fill=NAVY)
    y += 90

    rows = [
        ("규격", size),
        ("광원", led),
        ("색온도", color_temp),
        ("컬러", color),
        ("특징", features),
        ("제품코드", code),
    ]
    table_x, table_w = 70, W - 140
    row_h = 76
    for i, (label, val) in enumerate(rows):
        ry = y + i * row_h
        bg = GRAY_BG if i % 2 == 0 else WHITE
        d.rectangle([table_x, ry, table_x + table_w, ry + row_h], fill=bg)
        d.rectangle([table_x, ry, table_x + 190, ry + row_h], fill=NAVY)
        lb = d.textbbox((0, 0), label, font=font("medium", 22))
        d.text(
            (table_x + (190 - (lb[2] - lb[0])) / 2, ry + (row_h - 22) / 2 - 4),
            label,
            font=font("medium", 22),
            fill=WHITE,
        )
        d.text((table_x + 215, ry + (row_h - 22) / 2 - 4), val, font=font("regular", 22), fill=NAVY)
    for i in range(len(rows) + 1):
        d.line([(table_x, y + i * row_h), (table_x + table_w, y + i * row_h)], fill=LINE, width=1)
    d.rectangle([table_x, y, table_x + table_w, y + len(rows) * row_h], outline=LINE, width=2)

    y2 = y + len(rows) * row_h + 60
    d.line([(60, y2), (W - 60, y2)], fill=LINE, width=4)
    y2 += 35
    guide = [
        ("배송", "결제 후 2~3일 이내 출고 (공휴일 제외)"),
        ("교환/반품", "수령일로부터 7일 이내, 하자 시 가능"),
        ("A/S", "시공 후 하자는 현장 A/S로 대응"),
    ]
    for title, desc in guide:
        d.rectangle([60, y2, 68, y2 + 26], fill=RED)
        d.text((90, y2 - 4), title, font=font("bold", 22), fill=NAVY)
        d.text((230, y2), desc, font=font("regular", 18), fill=GRAY_TXT)
        y2 += 55

    y2 += 25
    d.rectangle([0, y2, W, y2 + 110], fill=NAVY)
    _center_text(d, "MK LIGHTING", y2 + 32, font("medium", 20), fill=GOLD)
    _center_text(d, f"제품코드 {code}", y2 + 68, font("regular", 16), fill=(190, 196, 210))
    img = img.crop((0, 0, W, y2 + 110))
    p6 = str(out / "06_spec.png")
    img.save(p6)
    saved.append(p6)

    return saved
