"""루씨에어 코타라 커넥트 CTC 판매 릴스 제작 — 세로 9:16 사진 기반 광고.

제공된 실제 제품/상세페이지 사진(gonobi/렉시움 원본, [[gonobi-lexium-authorized-supplier]]
메모리로 사용 허가됨)만 사용한다. AI 이미지 생성 없음 — 부족한 그래픽은
PIL(HTML/CSS 대신 파이썬 도형·텍스트)로 보완한다.

출력: data/instagram_reels/kotara_ctc/
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from scripts.app_paths import repo_root

ROOT = repo_root()
SRC_DIR = ROOT / "data" / "naver_blog_images" / "gonobi_224362505769"
OUT_DIR = ROOT / "data" / "instagram_reels" / "kotara_ctc"
OUT_DIR.mkdir(parents=True, exist_ok=True)

W, H = 1080, 1920

FONT_BOLD = r"C:\Windows\Fonts\malgunbd.ttf"
FONT_REG = r"C:\Windows\Fonts\malgun.ttf"

# 뉴트럴/프리미엄 팔레트
INK = (26, 24, 22)
CREAM = (245, 240, 232)
WHITE = (255, 255, 255)
GOLD = (196, 164, 108)  # 우드톤과 어울리는 차분한 골드 포인트 (원본 팬 색상에서 추출)
PHONE_BG = (20, 18, 17)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _cover(img: Image.Image, w: int, h: int, focus_y: float = 0.5) -> Image.Image:
    """w x h 캔버스를 꽉 채우도록 리사이즈 후 크롭. focus_y로 세로 크롭 위치 조절(0=위쪽 고정)."""
    src_ratio = img.width / img.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:
        nh = h
        nw = int(nh * src_ratio)
    else:
        nw = w
        nh = int(nw / src_ratio)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = int((nw - w) * 0.5)
    top = int((nh - h) * focus_y)
    top = max(0, min(top, nh - h))
    return img.crop((left, top, left + w, top + h))


def _letterbox(img: Image.Image, w: int, h: int, bg=CREAM) -> Image.Image:
    """원본 비율을 유지한 채 캔버스 안에 맞추고 나머지는 배경색으로 채운다(찌그러짐 방지)."""
    src_ratio = img.width / img.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:
        nw = w
        nh = int(nw / src_ratio)
    else:
        nh = h
        nw = int(nh * src_ratio)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (w, h), bg)
    canvas.paste(img, ((w - nw) // 2, (h - nh) // 2))
    return canvas


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
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


def _gradient_band(img: Image.Image, y0: int, y1: int, from_alpha: int, to_alpha: int, color=(0, 0, 0)) -> None:
    band_h = y1 - y0
    if band_h <= 0:
        return
    grad = Image.new("L", (1, band_h))
    for yy in range(band_h):
        t = yy / max(band_h - 1, 1)
        grad.putpixel((0, yy), int(from_alpha + (to_alpha - from_alpha) * t))
    mask = grad.resize((img.width, band_h))
    shade = Image.new("RGB", (img.width, band_h), color)
    img.paste(shade, (0, y0), mask)


def _location_badge(
    draw: ImageDraw.ImageDraw, x: int, y: int, text: str = "반딧불 전파사 · 다산 현대프리미엄캠퍼스", size: int = 27
) -> None:
    """좌상단 지역 타겟팅 배지 — 가격 위계(1순위)를 침범하지 않도록 작고 옅게."""
    font = _font(FONT_BOLD, size)
    pad_x, pad_y = 24, 12
    tw = draw.textlength(text, font=font)
    bw, bh = tw + pad_x * 2, size + pad_y * 2
    draw.rounded_rectangle([x, y, x + bw, y + bh], radius=bh / 2, fill=(255, 255, 255, 235))
    draw.text((x + pad_x, y + pad_y - 2), text, font=font, fill=INK)


def _phone_pill(draw: ImageDraw.ImageDraw, cx: int, y: int, text: str, size: int = 36, big: bool = False) -> int:
    """전화번호 CTA 알약 배지. 반환값: 배지 높이."""
    font = _font(FONT_BOLD, size)
    pad_x, pad_y = 34, 18
    tw = draw.textlength(text, font=font)
    bw, bh = tw + pad_x * 2, size + pad_y * 2
    x0 = cx - bw / 2
    draw.rounded_rectangle([x0, y, x0 + bw, y + bh], radius=bh / 2, fill=GOLD if big else INK)
    fill = INK if big else WHITE
    draw.text((cx - tw / 2, y + pad_y - 2), text, font=font, fill=fill)
    return int(bh)


# ──────────────────────────────────────────────────────────
# 썸네일 (A/B/C)
# ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────
# 장면 프레임
# ──────────────────────────────────────────────────────────


def _base_frame(src_name: str, focus_y: float = 0.5, mode: str = "letterbox") -> Image.Image:
    src = Image.open(SRC_DIR / src_name).convert("RGB")
    if mode == "cover":
        return _cover(src, W, H, focus_y=focus_y)

    # 블러 채움 배경 + 선명한 원본을 중앙에 얹는 방식 — 위아래 여백을 크림색
    # 평면으로 비우지 않고 이미지 자체의 확대·블러본으로 채워 화면을 꽉 채운다.
    bg = _cover(src, W, H, focus_y=focus_y).filter(ImageFilter.GaussianBlur(40))
    dark = Image.new("RGB", (W, H), (10, 9, 8))
    bg = Image.blend(bg, dark, 0.45)

    fg = _letterbox_transparent(src, int(W * 0.92))
    canvas = bg.convert("RGBA")
    fx = (W - fg.width) // 2
    fy = (H - fg.height) // 2
    canvas.alpha_composite(fg, (fx, fy))
    return canvas.convert("RGB")


def _letterbox_transparent(img: Image.Image, target_w: int) -> Image.Image:
    """원본 비율을 유지한 채 target_w 너비로 리사이즈 (알파 채널 포함, 배경 없음)."""
    ratio = img.height / img.width
    nh = int(target_w * ratio)
    resized = img.resize((target_w, nh), Image.Resampling.LANCZOS).convert("RGBA")
    return resized


def _bottom_cta(draw: ImageDraw.ImageDraw, img: Image.Image, phone_text: str = "설치문의 010-7387-6635") -> None:
    """중간 장면 공통 하단 소형 CTA — 고정 위치, 제품 가리지 않게 작게."""
    band_h = 130
    _gradient_band(img, H - band_h, H, from_alpha=0, to_alpha=190, color=(15, 13, 12))
    f = _font(FONT_BOLD, 34)
    tw = draw.textlength(phone_text, font=f)
    draw.text(((W - tw) / 2, H - 74), phone_text, font=f, fill=WHITE)


def _top_caption(draw: ImageDraw.ImageDraw, img: Image.Image, title_lines: list[str], sub: str = "") -> None:
    f_title = _font(FONT_BOLD, 62)
    f_sub = _font(FONT_REG, 34)
    band_h = 56 + len(title_lines) * 74 + (56 if sub else 0) + 20
    # 텍스트가 걸치는 구간은 항상 충분한 대비를 유지하고(최소 alpha 175),
    # 그 아래로만 이미지 쪽으로 자연스럽게 사라지도록 여유를 둬 가독성을 지킨다.
    _gradient_band(img, 0, band_h, from_alpha=225, to_alpha=175, color=(15, 13, 12))
    _gradient_band(img, band_h, band_h + 60, from_alpha=175, to_alpha=0, color=(15, 13, 12))
    y = 56
    for ln in title_lines:
        tw = draw.textlength(ln, font=f_title)
        draw.text(((W - tw) / 2, y), ln, font=f_title, fill=WHITE)
        y += 74
    if sub:
        tw = draw.textlength(sub, font=f_sub)
        draw.text(((W - tw) / 2, y + 6), sub, font=f_sub, fill=(225, 220, 212))


def scene_1(dst: Path) -> Path:
    """0~3초 — 썸네일과 거의 동일한 첫 화면."""
    img = _cover(Image.open(SRC_DIR / "01.png").convert("RGB"), W, H, focus_y=0.12)
    draw = ImageDraw.Draw(img, "RGBA")
    band_y0 = int(H * 0.52)
    _gradient_band(img, band_y0, H, from_alpha=0, to_alpha=215, color=(15, 13, 12))
    _location_badge(draw, 48, 48)
    f_sub = _font(FONT_BOLD, 52)
    f_price = _font(FONT_BOLD, 132)
    f_name = _font(FONT_REG, 40)
    margin = 72
    y = band_y0 + 60
    draw.text((margin, y), "실링팬 설치까지", font=f_sub, fill=WHITE)
    y += 78
    draw.text((margin, y), "64.9만원", font=f_price, fill=GOLD)
    y += 158
    draw.text((margin, y), "루씨에어 코타라 CTC", font=f_name, fill=(225, 220, 212))
    y += 80
    _phone_pill(draw, W // 2, y, "010-7387-6635", size=38, big=True)
    img.save(dst, quality=95)
    return dst


def scene_2(dst: Path) -> Path:
    """3~6초 — 03.png 규격 카드."""
    img = _base_frame("03.png", mode="letterbox")
    draw = ImageDraw.Draw(img, "RGBA")
    _top_caption(draw, img, ["137cm 대형 사이즈", "높이 18.5cm"], sub="적정 층고 2.3m 이상")
    _bottom_cta(draw, img)
    img.save(dst, quality=95)
    return dst


def scene_3(dst: Path) -> Path:
    """6~10초 — 05.png IoT 앱."""
    img = _base_frame("05.png", mode="letterbox")
    draw = ImageDraw.Draw(img, "RGBA")
    _top_caption(draw, img, ["스마트폰으로 제어"], sub="Lucci Connect IoT · 전원·풍속·타이머")
    _bottom_cta(draw, img)
    img.save(dst, quality=95)
    return dst


def scene_4(dst: Path) -> Path:
    """10~14초 — 13.png BLDC 모터."""
    img = _base_frame("13.png", mode="letterbox")
    draw = ImageDraw.Draw(img, "RGBA")
    _top_caption(draw, img, ["BLDC 모터", "6단계 풍속"])
    _bottom_cta(draw, img)
    img.save(dst, quality=95)
    return dst


def scene_5(dst: Path) -> Path:
    """14~18초 — 16.png 소음 시험자료. '무소음' 표현 사용 금지."""
    img = _base_frame("16.png", mode="letterbox")
    draw = ImageDraw.Draw(img, "RGBA")
    _top_caption(draw, img, ["1단 운전 18.1dB"], sub="TÜV Rheinland 시험 기준")
    _bottom_cta(draw, img)
    img.save(dst, quality=95)
    return dst


def scene_6(dst: Path) -> Path:
    """18~21초 — 공기순환. 사용자 지시는 18.png를 지정했으나 실제 그 이미지는
    '과전력 보호·동작 감지' 안전기능 카드였고, 218㎥/min 공기순환 다이어그램은
    19.png였다. 내용 정확성을 위해 19.png로 교정해서 사용한다(재생성 없음,
    소재 재배치만).
    """
    img = _base_frame("19.png", mode="letterbox")
    draw = ImageDraw.Draw(img, "RGBA")
    _top_caption(draw, img, ["에어컨과 함께", "실내 공기순환"])
    _bottom_cta(draw, img)
    img.save(dst, quality=95)
    return dst


def scene_7(dst: Path) -> Path:
    """21~24초 — 14.png 보증."""
    img = _base_frame("14.png", mode="letterbox")
    draw = ImageDraw.Draw(img, "RGBA")
    _top_caption(draw, img, ["제품 최대 2년 A/S", "모터 최대 4년 보증"], sub="제품별 보증조건 확인")
    _bottom_cta(draw, img)
    img.save(dst, quality=95)
    return dst


def scene_8_final(dst: Path) -> Path:
    """24~30초 — 마지막 판매 장면. 01.png 재사용, 가격+CTA+추가공사 고지."""
    img = _cover(Image.open(SRC_DIR / "01.png").convert("RGB"), W, H, focus_y=0.12)
    draw = ImageDraw.Draw(img, "RGBA")
    band_y0 = int(H * 0.40)
    _gradient_band(img, band_y0, H, from_alpha=0, to_alpha=225, color=(15, 13, 12))
    _location_badge(draw, 48, 48)

    f_label = _font(FONT_BOLD, 46)
    f_price = _font(FONT_BOLD, 108)
    f_name = _font(FONT_REG, 38)
    f_cta = _font(FONT_BOLD, 70)
    f_phone = _font(FONT_BOLD, 76)
    f_tail = _font(FONT_REG, 32)
    f_note = _font(FONT_REG, 24)

    margin = 72
    y = band_y0 + 40
    draw.text((margin, y), "제품 + 기본설치", font=f_label, fill=WHITE)
    y += 62
    draw.text((margin, y), "649,000원", font=f_price, fill=GOLD)
    y += 130
    draw.text((margin, y), "루씨에어 코타라 CTC 137cm", font=f_name, fill=(225, 220, 212))
    y += 54

    # "전국 최저가" 등 단정적 최상급 표현은 쓰지 않는다(입증 불가·표시광고법
    # 리스크, 블로그 원고와 동일 원칙). 대신 "설치비 포함 총액 비교"로
    # 우위를 유도한다.
    f_edge = _font(FONT_BOLD, 34)
    draw.text((margin, y), "설치비까지 포함하면 더 유리합니다", font=f_edge, fill=GOLD)
    y += 62

    draw.line([(margin, y), (W - margin, y)], fill=(120, 112, 100), width=1)
    y += 34

    draw.text((margin, y), "설치문의", font=f_cta, fill=WHITE)
    y += 88
    draw.text((margin, y), "010-7387-6635", font=f_phone, fill=GOLD)
    y += 96

    draw.text((margin, y), "반딧불 전파사 · 다산 현대프리미엄캠퍼스", font=f_tail, fill=(225, 220, 212))
    y += 46
    draw.text((margin, y), "설치할 천장 사진을 보내주세요", font=f_tail, fill=(220, 214, 205))
    y += 50

    note = "천장보강 · 신규배선 · 고소작업 · 특수천장 등 추가공사 별도"
    draw.text((margin, y), note, font=f_note, fill=(180, 174, 165))

    img.save(dst, quality=95)
    return dst


SCENES: list[dict] = [
    {"name": "scene_1", "fn": scene_1, "dur": 3.0, "caption": "실링팬 설치까지 64.9만원 — 루씨에어 코타라 CTC"},
    {"name": "scene_2", "fn": scene_2, "dur": 3.0, "caption": "137cm 대형 사이즈, 높이 18.5cm, 적정 층고 2.3m 이상"},
    {"name": "scene_3", "fn": scene_3, "dur": 4.0, "caption": "스마트폰으로 제어 — Lucci Connect IoT"},
    {"name": "scene_4", "fn": scene_4, "dur": 4.0, "caption": "BLDC 모터, 6단계 풍속"},
    {"name": "scene_5", "fn": scene_5, "dur": 4.0, "caption": "1단 운전 18.1dB, TÜV Rheinland 시험 기준"},
    {"name": "scene_6", "fn": scene_6, "dur": 3.0, "caption": "에어컨과 함께 실내 공기순환"},
    {"name": "scene_7", "fn": scene_7, "dur": 3.0, "caption": "제품 최대 2년 A/S, 모터 최대 4년 보증"},
    {"name": "scene_8", "fn": scene_8_final, "dur": 6.0, "caption": "제품+기본설치 649,000원. 설치문의 010-7387-6635"},
]


# ──────────────────────────────────────────────────────────
# ffmpeg 조립 (가변 길이 xfade)
# ──────────────────────────────────────────────────────────


def build_video(frames: list[Path], durations: list[float], out_path: Path, fade: float = 0.5) -> Path:
    n = len(frames)
    inputs: list[str] = []
    for f, d in zip(frames, durations):
        inputs += ["-loop", "1", "-t", str(d + fade), "-i", str(f)]

    scale_filters = [
        f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]"
        for i in range(n)
    ]
    xfade_parts = []
    cur = "v0"
    offset = durations[0]
    for i in range(1, n):
        nxt = f"x{i}"
        xfade_parts.append(f"[{cur}][v{i}]xfade=transition=fade:duration={fade}:offset={offset:.2f}[{nxt}]")
        cur = nxt
        offset += durations[i]

    filter_complex = ";".join(scale_filters + xfade_parts)
    total = sum(durations)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-f",
        "lavfi",
        "-t",
        f"{total:.2f}",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-filter_complex",
        filter_complex,
        "-map",
        f"[{cur}]",
        "-map",
        f"{n}:a",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-t",
        f"{total:.2f}",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {proc.stderr[-2000:]}")
    return out_path


def mux_audio(
    video_no_audio_src: Path, tts_path: Path, bgm_path: Path | None, out_path: Path, bgm_volume: float = 0.18
) -> Path:
    """무음(anullsrc) 비디오에 나레이션(TTS) + (선택)배경음악을 믹싱한다."""
    if bgm_path and bgm_path.exists():
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_no_audio_src),
            "-i",
            str(tts_path),
            "-stream_loop",
            "-1",
            "-i",
            str(bgm_path),
            "-filter_complex",
            (
                f"[2:a]volume={bgm_volume}[bgm];"
                "[1:a][bgm]amix=inputs=2:duration=first:dropout_transition=2,"
                "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[aout]"
            ),
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(out_path),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_no_audio_src),
            "-i",
            str(tts_path),
            "-filter_complex",
            "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[aout]",
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(out_path),
        ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 오디오 믹싱 실패: {proc.stderr[-2000:]}")
    return out_path


