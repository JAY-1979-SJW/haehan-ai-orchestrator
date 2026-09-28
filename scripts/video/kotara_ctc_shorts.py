"""루씨에어 코타라 CTC 사진형 YouTube Shorts 3편 제작.

기존 릴스 제작 헬퍼(scripts.instagram.kotara_ctc_reel)의 폰트·색상·이미지
크롭·오디오 믹싱 로직을 그대로 재사용한다(중복 구현 금지 원칙). 이 모듈은
3개 대본(가격후킹/낮은천장/제품만사면안되는이유)에 맞는 장면 텍스트만 새로
정의하고, 프레임 렌더링·비디오 조립은 기존 함수를 호출한다.

출력: data/instagram_reels/kotara_ctc_shorts/{variant}/
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.instagram.kotara_ctc_reel import (
    CREAM,
    FONT_BOLD,
    FONT_REG,
    GOLD,
    INK,
    SRC_DIR,
    WHITE,
    H,
    W,
    _base_frame,
    _cover,
    _font,
    _gradient_band,
    _phone_pill,
    build_video,
    mux_audio,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT / "data" / "instagram_reels" / "kotara_ctc_shorts"
OUT_ROOT.mkdir(parents=True, exist_ok=True)


def _top_caption_lines(img: Image.Image, lines: list[str], sub: str = "") -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    f_title = _font(FONT_BOLD, 60)
    f_sub = _font(FONT_REG, 32)
    band_h = 56 + len(lines) * 72 + (54 if sub else 0) + 20
    _gradient_band(img, 0, band_h, from_alpha=225, to_alpha=175, color=(15, 13, 12))
    _gradient_band(img, band_h, band_h + 60, from_alpha=175, to_alpha=0, color=(15, 13, 12))
    y = 54
    for ln in lines:
        tw = draw.textlength(ln, font=f_title)
        draw.text(((W - tw) / 2, y), ln, font=f_title, fill=WHITE)
        y += 72
    if sub:
        tw = draw.textlength(sub, font=f_sub)
        draw.text(((W - tw) / 2, y + 4), sub, font=f_sub, fill=(225, 220, 212))


def _photo_card(image_name: str, lines: list[str], sub: str = "") -> Image.Image:
    img = _base_frame(image_name, mode="letterbox")
    _top_caption_lines(img, lines, sub)
    return img


def _photo_full(
    image_name: str, headline: list[str], price: str = "", phone: str = "", footer: str = "", focus_y: float = 0.12
) -> Image.Image:
    """01.png 전체화면 크롭 + 하단 그라데이션 텍스트 (썸네일/오프닝/클로징용)."""
    img = _cover(Image.open(SRC_DIR / image_name).convert("RGB"), W, H, focus_y=focus_y)
    draw = ImageDraw.Draw(img, "RGBA")
    band_y0 = int(H * 0.50)
    _gradient_band(img, band_y0, H, from_alpha=0, to_alpha=225, color=(15, 13, 12))

    f_h = _font(FONT_BOLD, 56)
    f_price = _font(FONT_BOLD, 96)
    f_foot = _font(FONT_REG, 30)

    margin = 72
    y = band_y0 + 50
    for ln in headline:
        draw.text((margin, y), ln, font=f_h, fill=WHITE)
        y += 68
    if price:
        y += 6
        draw.text((margin, y), price, font=f_price, fill=GOLD)
        y += 118
    if phone:
        _phone_pill(draw, W // 2, y, phone, size=40, big=True)
        y += 40 + 36 + 30
    if footer:
        tw = draw.textlength(footer, font=f_foot)
        draw.text(((W - tw) / 2, y), footer, font=f_foot, fill=(210, 205, 196))
    return img


def _text_card(lines: list[str], sub: str = "") -> Image.Image:
    """사진 없이 순수 텍스트 카드 — 뉴트럴 배경(블러 없음, 차분한 잉크톤)."""
    img = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(img, "RGBA")
    # 은은한 대각 그라데이션 느낌을 주기 위해 살짝 밝은 밴드
    _gradient_band(img, int(H * 0.35), int(H * 0.65), from_alpha=0, to_alpha=40, color=(60, 55, 48))

    f_title = _font(FONT_BOLD, 64)
    f_sub = _font(FONT_REG, 34)
    total_h = len(lines) * 82 + (52 if sub else 0)
    y = (H - total_h) // 2
    for ln in lines:
        tw = draw.textlength(ln, font=f_title)
        draw.text(((W - tw) / 2, y), ln, font=f_title, fill=WHITE)
        y += 82
    if sub:
        y += 10
        tw = draw.textlength(sub, font=f_sub)
        draw.text(((W - tw) / 2, y), sub, font=f_sub, fill=(200, 194, 185))
    return img


def _compare_card() -> Image.Image:
    """가격 비교 카드 — 블로그 원고 실측 근거(2026-08-25 확인)와 동일 수치."""
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img, "RGBA")

    f_title = _font(FONT_BOLD, 52)
    f_label = _font(FONT_REG, 36)
    f_price = _font(FONT_BOLD, 38)
    f_price_us = _font(FONT_BOLD, 46)

    margin = 80
    rows = [
        ("정상 판매가격", "약 670,000원", False),
        ("오늘의집 공개 판매가", "약 603,000원", False),
        ("LG 홈스타일 판매가", "약 636,500원", False),
        ("일부 회원·프로모션가", "약 591,950원", False),
        ("저희 제품+기본설치", "649,000원", True),
    ]
    row_h = 108
    title_block_h = 66 * 2 + 60
    table_h = row_h * len(rows)
    total_h = title_block_h + table_h
    y = (H - total_h) // 2

    title = "제품만 비교하지 말고"
    title2 = "설치 총액을 보세요"
    for ln in (title, title2):
        tw = draw.textlength(ln, font=f_title)
        draw.text(((W - tw) / 2, y), ln, font=f_title, fill=INK)
        y += 66

    y += 60
    box_top = y
    box_bottom = y + row_h * len(rows)
    draw.rounded_rectangle(
        [margin - 20, box_top - 20, W - margin + 20, box_bottom + 20], radius=24, fill=(255, 255, 255)
    )
    for label, price, highlight in rows:
        if highlight:
            draw.rounded_rectangle([margin - 10, y, W - margin + 10, y + row_h - 10], radius=14, fill=(255, 244, 224))
        draw.text((margin + 10, y + 34), label, font=f_label, fill=INK if highlight else (90, 85, 78))
        pf = f_price_us if highlight else f_price
        pw = draw.textlength(price, font=pf)
        draw.text(
            (W - margin - 10 - pw, y + (28 if highlight else 32)),
            price,
            font=pf,
            fill=GOLD if highlight else (90, 85, 78),
        )
        y += row_h

    return img


# ──────────────────────────────────────────────────────────
# 공통 클로징 (모든 영상 마지막 2초)
# ──────────────────────────────────────────────────────────


def closing_scene() -> Image.Image:
    return _photo_full(
        "01.png",
        headline=["설치문의"],
        price="",
        phone="010-7387-6635",
        footer="설치할 천장 사진을 보내주세요 · 추가공사 별도",
    )


# ──────────────────────────────────────────────────────────
# 대본 정의
# ──────────────────────────────────────────────────────────

SCRIPT_1 = {
    "id": "01_price_hook",
    "title_ko": "가격 후킹형",
    "youtube_title": "실링팬 설치까지 64.9만원｜루씨에어 코타라 CTC",
    "scenes": [
        {
            "dur": 3,
            "narr": "실링팬, 제품만 보지 마세요. 설치까지 64만 9천원입니다.",
            "render": lambda: _photo_full("01.png", ["실링팬 설치까지"], "64.9만원", "", "루씨에어 코타라 CTC"),
        },
        {
            "dur": 3,
            "narr": "루씨에어 코타라 커넥트 CTC 실링팬입니다.",
            "render": lambda: _photo_card("03.png", ["루씨에어", "코타라 CTC"]),
        },
        {
            "dur": 4,
            "narr": "137센티 대형 사이즈에 높이는 18.5센티로 깔끔합니다.",
            "render": lambda: _photo_card("03.png", ["137cm 대형 사이즈"], "높이 18.5cm"),
        },
        {
            "dur": 4,
            "narr": "스마트폰으로 전원과 풍속, 타이머까지 제어할 수 있습니다.",
            "render": lambda: _photo_card("05.png", ["스마트폰 제어"], "Lucci Connect IoT"),
        },
        {
            "dur": 4,
            "narr": "BLDC 모터 적용으로 조용하고 효율적으로 사용할 수 있습니다.",
            "render": lambda: _photo_card("13.png", ["BLDC 모터"], "저소음 운전"),
        },
        {
            "dur": 5,
            "narr": "코타라 CTC, 제품과 기본설치까지 64만 9천원. 설치할 천장 사진을 보내주시면 먼저 확인해드립니다.",
            "render": lambda: _photo_full(
                "01.png", ["제품 + 기본설치"], "649,000원", "010-7387-6635", "천장사진 보내주세요"
            ),
        },
        {
            "dur": 2,
            "narr": "추가공사는 현장 확인 후 미리 안내드립니다.",
            "render": lambda: _text_card(["천장보강 · 신규배선", "고소작업 · 특수천장"], "등 추가공사 별도"),
        },
    ],
}

SCRIPT_2 = {
    "id": "02_low_ceiling",
    "title_ko": "낮은 천장 고민 해결형",
    "youtube_title": "천장 낮아도 실링팬 가능할까요? 코타라 CTC 18.5cm",
    "scenes": [
        {
            "dur": 3,
            "narr": "천장이 낮아서 실링팬 설치를 망설이고 계신가요?",
            "render": lambda: _photo_full("01.png", ["천장 낮아서"], "", "", "실링팬 고민되시나요?"),
        },
        {
            "dur": 4,
            "narr": "루씨에어 코타라 CTC는 높이 18.5센티의 슬림한 타입입니다.",
            "render": lambda: _photo_card("03.png", ["코타라 CTC"], "높이 18.5cm"),
        },
        {
            "dur": 4,
            "narr": "137센티 실링팬이고, 제조사 권장 적정 층고는 2.3미터 이상입니다.",
            "render": lambda: _photo_card("03.png", ["137cm / 54인치"], "적정 층고 2.3m 이상"),
        },
        {
            "dur": 4,
            "narr": "다만 설치는 층고만 보는 게 아니라 천장보강과 전원 위치도 함께 확인해야 합니다.",
            "render": lambda: _text_card(["설치 전 확인"], "천장보강 · 우물천장 · 전원위치"),
        },
        {
            "dur": 5,
            "narr": "그래서 설치 전에는 천장 사진을 먼저 보내주시는 게 가장 정확합니다.",
            "render": lambda: _photo_full("01.png", ["설치할 천장 사진"], "", "", "먼저 보내주세요"),
        },
        {
            "dur": 5,
            "narr": "코타라 CTC는 제품과 기본설치 포함 64만 9천원입니다. 문의는 010-7387-6635로 주세요.",
            "render": lambda: _photo_full("01.png", ["제품 + 기본설치"], "649,000원", "010-7387-6635", "추가공사 별도"),
        },
    ],
}

SCRIPT_3 = {
    "id": "03_not_just_product",
    "title_ko": "제품만 사면 안 되는 이유형",
    "youtube_title": "실링팬 제품만 사면 끝일까요? 설치까지 64.9만원 비교",
    "scenes": [
        {
            "dur": 4,
            "narr": "실링팬은 제품만 사면 끝나는 게 아닙니다.",
            "render": lambda: _photo_full("01.png", ["실링팬"], "", "", "제품만 사면 끝일까요?"),
        },
        {
            "dur": 4,
            "narr": "천장에 안전하게 설치하고 작동까지 확인해야 제대로 사용할 수 있습니다.",
            "render": lambda: _text_card(["실링팬은"], "설치가 중요합니다"),
        },
        {
            "dur": 4,
            "narr": "그래서 제품 가격만 보지 말고 설치까지 포함한 총액을 봐야 합니다.",
            "render": lambda: _compare_card(),
        },
        {
            "dur": 5,
            "narr": "루씨에어 코타라 CTC는 137센티 사이즈에 IoT 제어와 BLDC 모터를 적용한 모델입니다.",
            "render": lambda: _photo_card("13.png", ["루씨에어 코타라 CTC"], "137cm / IoT / BLDC"),
        },
        {
            "dur": 6,
            "narr": "이 제품은 기본설치 포함 64만 9천원으로 안내드리고 있습니다.",
            "render": lambda: _photo_full("01.png", ["제품 + 기본설치"], "649,000원"),
        },
        {
            "dur": 5,
            "narr": "설치할 천장 사진을 보내주시면 추가공사 여부부터 먼저 확인해드립니다. 문의는 010-7387-6635입니다.",
            "render": lambda: _photo_full(
                "01.png", ["설치할 천장 사진"], "", "010-7387-6635", "보내주세요 · 추가공사 별도"
            ),
        },
    ],
}

SCRIPTS = [SCRIPT_1, SCRIPT_2, SCRIPT_3]


# ──────────────────────────────────────────────────────────
# 조립
# ──────────────────────────────────────────────────────────


async def _tts(text: str, out_path: Path, rate: str = "+15%") -> None:
    import edge_tts

    comm = edge_tts.Communicate(text=text, voice="ko-KR-InJoonNeural", rate=rate)
    await comm.save(str(out_path))


def _tts_fit(text: str, target_seconds: float, out_dir: Path, idx: int) -> Path:
    """대본에 명시된 장면 길이(target_seconds)에 맞춰 내레이션 속도를 조절한다.

    영상 길이를 내레이션에 맞추는 대신(이전 방식), 대본이 지정한 타이밍을
    그대로 지키고 내레이션 쪽을 압축한다 — 쇼츠는 대본 타이밍 자체가
    홍보 설계라는 사용자 지시(2026-08-26)에 따름.
    """
    baseline = out_dir / f"scene_{idx:02d}_base.mp3"
    asyncio.run(_tts(text, baseline, rate="+0%"))
    d0 = _probe_duration(baseline)

    buffer = 0.15
    target_speech = max(0.5, target_seconds - buffer)
    if d0 <= target_speech:
        return baseline

    needed_factor = d0 / target_speech
    rate_pct = min(round((needed_factor - 1) * 100) + 2, 100)
    sped = out_dir / f"scene_{idx:02d}_sped.mp3"
    asyncio.run(_tts(text, sped, rate=f"+{rate_pct}%"))
    return sped


def _pad_to(src: Path, dst: Path, seconds: float) -> None:
    """오디오를 정확히 seconds 길이로 맞춘다(무음 패딩 또는 트림)."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-af",
        "apad",
        "-t",
        f"{seconds:.3f}",
        "-ar",
        "48000",
        "-ac",
        "2",
        str(dst),
    ]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)


def _silence(dst: Path, seconds: float) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t",
        f"{seconds:.3f}",
        str(dst),
    ]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)


def _concat_audio(segments: list[Path], dst: Path) -> None:
    inputs: list[str] = []
    for s in segments:
        inputs += ["-i", str(s)]
    n = len(segments)
    filt = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[aout]"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filt, "-map", "[aout]", str(dst)]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)


def build_short(script: dict) -> Path:
    out_dir = OUT_ROOT / script["id"]
    frame_dir = out_dir / "frames"
    audio_dir = out_dir / "audio"
    frame_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    frames: list[Path] = []
    durations: list[float] = []
    audio_segments: list[Path] = []

    for i, scene in enumerate(script["scenes"]):
        img = scene["render"]()
        p = frame_dir / f"scene_{i:02d}.png"
        img.convert("RGB").save(p, quality=95)

        scene_dur = float(scene["dur"])  # 대본에 명시된 길이를 그대로 지킨다
        tts_src = _tts_fit(scene["narr"], scene_dur, audio_dir, i)

        seg = audio_dir / f"scene_{i:02d}_seg.wav"
        _pad_to(tts_src, seg, scene_dur)

        frames.append(p)
        durations.append(scene_dur)
        audio_segments.append(seg)

    # 공통 클로징 2초 추가 (내레이션 없음, 무음)
    closing = closing_scene()
    cp = frame_dir / f"scene_{len(script['scenes']):02d}_closing.png"
    closing.convert("RGB").save(cp, quality=95)
    closing_dur = 2.0
    closing_seg = audio_dir / "closing_silence.wav"
    _silence(closing_seg, closing_dur)
    frames.append(cp)
    durations.append(closing_dur)
    audio_segments.append(closing_seg)

    total = sum(durations)
    print(f"[{script['id']}] 장면 {len(frames)}개, 총 {total:.1f}초 (대본 타이밍 그대로)")

    video_noaudio = out_dir / "_video_noaudio.mp4"
    build_video(frames, durations, video_noaudio)

    narration_path = out_dir / "narration.wav"
    _concat_audio(audio_segments, narration_path)

    bgm = ROOT / "data" / "instagram_reels" / "bgm" / "candidate.mp3"
    final_path = out_dir / f"kotara_ctc_short_{script['id']}.mp4"
    mux_audio(video_noaudio, narration_path, bgm if bgm.exists() else None, final_path, bgm_volume=0.15)

    return final_path


def _probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return float(proc.stdout.strip() or 0)


if __name__ == "__main__":
    for s in SCRIPTS:
        out = build_short(s)
        print(f"완료: {out}")
