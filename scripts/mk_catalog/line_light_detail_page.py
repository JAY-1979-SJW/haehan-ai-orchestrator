"""라인조명(매입 라인등) 상세페이지 6장 생성 — 실제 사진 기반, 외부 AI 이미지 생성 없음.

detail_page_template.py의 공용 헬퍼(폰트/캔버스/텍스트래핑/사진맞춤)를 재사용하고,
레이아웃만 평평한 라인바 형태에 맞게 새로 구성한다(원통형 레일 전용 도면은 재사용 불가).

사용:
    from scripts.mk_catalog.line_light_detail_page import build_line_light_detail_pages
    build_line_light_detail_pages(
        name="이지라인 메타 (매입 라인조명)",
        brand="반딧불 조명 스튜디오",
        photos={
            "cover": "data/blog_uploads/linelight_01.png",
            "spec1": "data/blog_uploads/linelight_02.png",
            "spec2": "data/blog_uploads/linelight_12.png",
            "install_steps": "data/blog_uploads/linelight_17.png",
            "install_real": "data/blog_uploads/linelight_08.png",
            "case": "data/blog_uploads/linelight_06.png",
        },
        contact="010-7387-6635",
        out_dir="data/mk_catalog/detail/linelight_meta",
    )
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from scripts.mk_catalog.detail_page_template import (
    CREAM,
    GOLD,
    GOLD_L,
    GRAY_BG,
    GRAY_TXT,
    LINE,
    NAVY,
    WHITE,
    W,
    _center_text,
    _new_canvas,
    _paste_fit,
    _rounded_photo,
    _wrap_and_draw,
    font,
)

TEAL = (33, 150, 136)
TEAL_L = (178, 223, 219)


def _wrap_and_draw_boxcenter(d, text, box_x, box_w, y, f, fill, line_gap=8):
    """지정한 컬럼 폭(box_x~box_x+box_w) 안에서 줄바꿈 + 가운데정렬.

    공용 _wrap_and_draw(center=True)는 페이지 전체 폭(W) 기준으로 중앙정렬하기 때문에
    여러 컬럼을 나란히 놓을 때 텍스트가 서로 겹치는 문제가 있어 별도로 둔다.
    """
    lines, cur = [], ""
    for ch in text:
        test = cur + ch
        bbox = d.textbbox((0, 0), test, font=f)
        if bbox[2] - bbox[0] > box_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    yy = y
    for ln in lines:
        bbox = d.textbbox((0, 0), ln, font=f)
        xx = box_x + (box_w - (bbox[2] - bbox[0])) / 2
        d.text((xx, yy), ln, font=f, fill=fill)
        yy += (bbox[3] - bbox[1]) + line_gap
    return yy


def _photo_page(photo_path: str, eyebrow: str, title: str, body: str, *, bg=WHITE) -> Image.Image:
    """사진(위) + 제목/본문(아래) 기본 페이지."""
    img, d = _new_canvas(1100, bg=bg)
    d.rectangle([0, 0, W, 8], fill=TEAL)

    y = 55
    _center_text(d, eyebrow, y, font("medium", 20), fill=TEAL)
    y += 45
    _center_text(d, title, y, font("black", 36), fill=NAVY)
    y += 70

    photo, pw, ph = _rounded_photo(photo_path, W - 120, 560, radius=24)
    img.paste(photo, (int((W - pw) / 2), y), photo)
    y += ph + 45

    d = ImageDraw.Draw(img)
    y = _wrap_and_draw(d, body, 80, y, font("regular", 22), W - 160, GRAY_TXT, line_gap=12, center=True)
    y += 30

    img = img.crop((0, 0, W, int(y)))
    return img


def _wrap_lines(d, text, f, max_width) -> list[str]:
    """max_width 안에 들어가도록 줄바꿈한 라인 목록 반환."""
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        test = cur + ch
        if d.textbbox((0, 0), test, font=f)[2] > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def build_selection_criteria_page(
    *,
    brand: str,
    product_name: str,
    rows: list[dict[str, str]],
    out_path: str,
) -> str:
    """'라인조명 선택 기준' 비교표 1장 생성.

    경쟁사를 지목하지 않고 확인 항목 기준으로만 구성한다(허위 비교 방지).
    rows: [{"item":"① 매입 깊이", "why":"...", "how":"...", "ours":"9mm — ..."}, ...]
    """
    # (x, width) — 첫 열이 좁으면 "칩 방/식" 처럼 어절이 끊겨 가독성이 떨어진다.
    COL = [(40, 170), (210, 200), (410, 190), (600, 220)]
    HEAD = ["확인 항목", "왜 중요한가", "구매 전 확인 방법", product_name]

    f_head = font("bold", 19)
    f_item = font("bold", 19)
    f_body = font("regular", 17)
    f_ours = font("bold", 18)

    # 1차: 높이 계산
    img, d = _new_canvas(3000, bg=WHITE)
    y = 40
    y_title = y
    y += 130
    y_head = y
    y += 56
    row_ys = []
    for r in rows:
        cells = [
            _wrap_lines(d, r["item"], f_item, COL[0][1] - 20),
            _wrap_lines(d, r["why"], f_body, COL[1][1] - 20),
            _wrap_lines(d, r["how"], f_body, COL[2][1] - 20),
            _wrap_lines(d, r["ours"], f_ours, COL[3][1] - 20),
        ]
        h = max(len(c) for c in cells) * 26 + 30
        row_ys.append((y, h, cells))
        y += h
    total_h = y + 90

    # 2차: 실제 렌더
    img, d = _new_canvas(total_h, bg=WHITE)
    d.rectangle([0, 0, W, 8], fill=TEAL)

    _center_text(d, brand, y_title + 20, font("medium", 19), fill=TEAL)
    _center_text(d, "라인조명, 이것만 확인하세요", y_title + 58, font("black", 33), fill=NAVY)

    # 헤더
    d.rectangle([40, y_head, W - 40, y_head + 46], fill=NAVY)
    for (x, w), h in zip(COL, HEAD):
        bb = d.textbbox((0, 0), h, font=f_head)
        d.text((x + (w - (bb[2] - bb[0])) / 2, y_head + 12), h, font=f_head, fill=WHITE)

    # 본문 행
    for idx, (ry, rh, cells) in enumerate(row_ys):
        if idx % 2 == 1:
            d.rectangle([40, ry, W - 40, ry + rh], fill=GRAY_BG)
        d.line([(40, ry), (W - 40, ry)], fill=LINE, width=1)
        fonts = [f_item, f_body, f_body, f_ours]
        colors = [NAVY, GRAY_TXT, GRAY_TXT, TEAL]
        for (x, w), lines, fnt, col in zip(COL, cells, fonts, colors):
            yy = ry + 15
            for ln in lines:
                d.text((x + 10, yy), ln, font=fnt, fill=col)
                yy += 26

    last_y = row_ys[-1][0] + row_ys[-1][1] if row_ys else y_head + 46
    d.line([(40, last_y), (W - 40, last_y)], fill=LINE, width=1)

    _wrap_and_draw(
        d,
        "※ 위 항목은 제품 사양서 기준입니다. 구매 전 상세페이지에서 직접 확인하세요.",
        40,
        last_y + 26,
        font("regular", 15),
        W - 80,
        GRAY_TXT,
        center=True,
    )

    img = img.crop((0, 0, W, total_h))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def build_line_light_detail_pages(
    *,
    name: str,
    brand: str,
    photos: dict[str, str],
    contact: str,
    out_dir: str,
) -> list[str]:
    """라인조명 상세페이지 6장(PNG) 생성. 저장된 파일 경로 리스트 반환."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    # ── 1. 커버 ──────────────────────────────────────────────
    img, d = _new_canvas(1050, bg=NAVY)
    d.rectangle([0, 0, W, 8], fill=TEAL)
    _center_text(d, brand, 70, font("medium", 22), fill=TEAL_L)
    y = 120
    y += _wrap_and_draw(d, name, 80, y, font("black", 40), W - 160, WHITE, line_gap=8, center=True) - y
    y += 20
    _center_text(d, "9mm 초슬림 매입 · 이음새 없는 무광 확산커버", y, font("regular", 22), fill=(190, 196, 210))
    y += 60

    hero, hw, hh = _paste_fit(photos["cover"], 720, 480)
    img.paste(hero, (int((W - hw) / 2), y), hero)
    d = ImageDraw.Draw(img)
    y += hh + 50
    d.line([(80, y), (W - 80, y)], fill=LINE, width=2)
    y += 40
    _center_text(d, "드레스룸 · 주방 · 거실 어디든 라인 하나로", y, font("bold", 26), fill=WHITE)
    y += 60

    img = img.crop((0, 0, W, int(y)))
    p1 = str(out / "01_cover.png")
    img.save(p1)
    saved.append(p1)

    # ── 2. 설치 단면도 (평평한 라인바 — 원통형 아님) ──────────
    img, d = _new_canvas(820, bg=NAVY)
    d.rectangle([0, 0, W, 8], fill=TEAL)
    y = 70
    _center_text(d, "INSTALL SECTION", y, font("medium", 22), fill=TEAL_L)
    y += 55
    _center_text(d, "9mm 매입 단면도", y, font("black", 36), fill=WHITE)
    y += 90

    # 천장(석고) 라인
    ceiling_y = y
    d.rectangle([120, ceiling_y, W - 120, ceiling_y + 14], fill=(90, 96, 110))
    _center_text(d, "석고 마감천장 (10mm 재단)", ceiling_y - 34, font("regular", 18), fill=(170, 176, 190))

    # 매입 라인바 단면 (얇은 사다리꼴)
    bar_top = ceiling_y + 14
    bar_h = 26
    bar_left, bar_right = W // 2 - 220, W // 2 + 220
    d.polygon(
        [
            (bar_left, bar_top),
            (bar_right, bar_top),
            (bar_right - 30, bar_top + bar_h),
            (bar_left + 30, bar_top + bar_h),
        ],
        fill=GOLD,
    )
    d.rectangle([bar_left + 30, bar_top + 6, bar_right - 30, bar_top + bar_h - 4], fill=(255, 244, 214))

    dim_y = bar_top + bar_h + 40
    d.line([(bar_left, dim_y), (bar_right, dim_y)], fill=(150, 158, 175), width=2)
    d.line([(bar_left, dim_y - 12), (bar_left, dim_y + 12)], fill=(150, 158, 175), width=2)
    d.line([(bar_right, dim_y - 12), (bar_right, dim_y + 12)], fill=(150, 158, 175), width=2)
    lab = "9mm 매입 깊이"
    f_dim = font("bold", 22)
    bbox = d.textbbox((0, 0), lab, font=f_dim)
    d.text(((W - (bbox[2] - bbox[0])) / 2, dim_y + 20), lab, font=f_dim, fill=GOLD_L)

    y = dim_y + 90
    y = _wrap_and_draw(
        d,
        "까다로운 목작업 없이 석고 한 장만 재단해 보강목에 바로 고정 — 공사 범위와 비용을 크게 줄여줍니다.",
        80,
        y,
        font("regular", 21),
        W - 160,
        (190, 196, 210),
        center=True,
    )
    img = img.crop((0, 0, W, int(y) + 40))
    p2 = str(out / "02_install_section.png")
    img.save(p2)
    saved.append(p2)

    # ── 3. 색온도 비교 (실사진 없이 색 스와치) ─────────────────
    img, d = _new_canvas(760, bg=WHITE)
    d.rectangle([0, 0, W, 8], fill=TEAL)
    y = 60
    _center_text(d, "COLOR TEMPERATURE", y, font("medium", 20), fill=TEAL)
    y += 50
    _center_text(d, "공간에 맞는 색온도 선택", y, font("black", 34), fill=NAVY)
    y += 80

    swatches = [
        ("3000K", "전구색", (255, 200, 120), "침실 · 거실 — 아늑한 분위기"),
        ("4000K", "주백색", (255, 244, 214), "주방 · 드레스룸 — 무난하고 선명"),
        ("6500K", "주광색", (220, 235, 255), "작업공간 — 밝기 최우선"),
    ]
    box_w, box_h, gap = 220, 220, 30
    total_w = box_w * 3 + gap * 2
    start_x = (W - total_w) // 2
    for i, (k, label, color, desc) in enumerate(swatches):
        x = start_x + i * (box_w + gap)
        d.rounded_rectangle([x, y, x + box_w, y + box_h], radius=18, fill=color, outline=LINE, width=2)
        f_k = font("black", 28)
        bbox = d.textbbox((0, 0), k, font=f_k)
        d.text((x + (box_w - (bbox[2] - bbox[0])) / 2, y + box_h + 16), k, font=f_k, fill=NAVY)
        f_l = font("bold", 20)
        bbox = d.textbbox((0, 0), label, font=f_l)
        d.text((x + (box_w - (bbox[2] - bbox[0])) / 2, y + box_h + 56), label, font=f_l, fill=TEAL)
        _wrap_and_draw_boxcenter(d, desc, x, box_w, y + box_h + 90, font("regular", 17), GRAY_TXT)

    y2 = y + box_h + 160
    img = img.crop((0, 0, W, int(y2)))
    p3 = str(out / "03_color_temp.png")
    img.save(p3)
    saved.append(p3)

    # ── 4. 좋은 제품 판별 기준 ────────────────────────────────
    img = _photo_page(
        photos["spec2"],
        "PRODUCT CHECK",
        "좋은 라인조명 vs 안 좋은 라인조명",
        "① 커버 이음새 처리(빛 끊김 여부)  ② COB칩 vs SMD칩(도트·고장률)\n"
        "③ 매입 깊이(공사 범위)  ④ 소등 후 커버 반사 여부\n"
        "네 가지만 확인해도 시공 후 후회를 크게 줄일 수 있습니다.",
        bg=GRAY_BG,
    )
    p4 = str(out / "04_product_check.png")
    img.save(p4)
    saved.append(p4)

    # ── 5. 시공 과정 ────────────────────────────────────────
    img = _photo_page(
        photos["install_steps"],
        "INSTALL PROCESS",
        "실제 시공은 이렇게 진행됩니다",
        "치수 측정 → 석고 10mm 재단 → 제품·전원 확인 → 전선 연결 → 고정 → 커버 마감\n"
        "전기 배선이 포함되는 작업이라 전문 시공을 권장드립니다.",
        bg=WHITE,
    )
    p5 = str(out / "05_install_process.png")
    img.save(p5)
    saved.append(p5)

    # ── 6. 마무리 / 브랜드 소개 ───────────────────────────────
    img, d = _new_canvas(960, bg=CREAM)
    d.rectangle([0, 0, W, 8], fill=TEAL)
    y = 60
    _center_text(d, brand, y, font("medium", 22), fill=TEAL)
    y += 55
    _center_text(d, "20년 현장 경험을 담은 조명 제안", y, font("black", 32), fill=NAVY)
    y += 70

    photo, pw, ph = _rounded_photo(photos["case"], W - 160, 460, radius=22)
    img.paste(photo, (int((W - pw) / 2), y), photo)
    y += ph + 45

    d = ImageDraw.Draw(img)
    y = _wrap_and_draw(
        d,
        "전기 시공 현장을 20년 넘게 관리해온 대표가 밝기·배선·시공성까지 직접 검토해서 조명을 제안합니다.",
        80,
        y,
        font("regular", 22),
        W - 160,
        GRAY_TXT,
        center=True,
    )
    y += 30
    d.rounded_rectangle([W // 2 - 220, y, W // 2 + 220, y + 70], radius=35, fill=TEAL)
    f_cta = font("bold", 26)
    cta = f"상담문의 {contact}"
    bbox = d.textbbox((0, 0), cta, font=f_cta)
    d.text((W // 2 - (bbox[2] - bbox[0]) / 2, y + 20), cta, font=f_cta, fill=WHITE)
    y += 70 + 40

    img = img.crop((0, 0, W, int(y)))
    p6 = str(out / "06_closing.png")
    img.save(p6)
    saved.append(p6)

    return saved
