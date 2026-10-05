"""AI 나라장터 입찰 1편 — 실제 스크린샷(claude.ai 답변 + bid.haehan-ai.kr 시뮬레이션) 기반 영상.

가로 16:9. 각 장면 = 실제 스크린샷 + 하단 자막바 + TTS 나레이션.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "data" / "youtube_g2b_series" / "ep_live"
OUT_DIR = ROOT / "data" / "youtube_g2b_series" / "ep01_real"
OUT_DIR.mkdir(parents=True, exist_ok=True)

W, H = 1920, 1080
FONT_BOLD = r"C:\Windows\Fonts\malgunbd.ttf"
FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
INK = (18, 17, 16)
WHITE = (255, 255, 255)
GOLD = (196, 164, 108)

TTS_RATE = "+25%"


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    ratio = min(max_w / img.width, max_h / img.height)
    new_size = (int(img.width * ratio), int(img.height * ratio))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _caption_frame(screenshot_path: Path | None, caption_lines: list[str], caption_sub: str = "") -> Image.Image:
    frame = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(frame, "RGBA")

    cap_h = 210 if caption_sub else 170
    img_area_h = H - cap_h

    if screenshot_path is not None:
        shot = Image.open(screenshot_path).convert("RGB")
        shot = _fit_image(shot, W - 80, img_area_h - 40)
        x = (W - shot.width) // 2
        y = (img_area_h - shot.height) // 2 + 20
        # subtle border
        draw.rectangle([x - 4, y - 4, x + shot.width + 4, y + shot.height + 4], outline=(70, 65, 58), width=2)
        frame.paste(shot, (x, y))

    draw.rectangle([0, img_area_h, W, H], fill=(12, 11, 10))
    f_cap = _font(FONT_BOLD, 40)
    f_sub = _font(FONT_REG, 26)
    y = img_area_h + 24
    for ln in caption_lines:
        tw = draw.textlength(ln, font=f_cap)
        draw.text(((W - tw) / 2, y), ln, font=f_cap, fill=WHITE)
        y += 52
    if caption_sub:
        tw = draw.textlength(caption_sub, font=f_sub)
        draw.text(((W - tw) / 2, y + 4), caption_sub, font=f_sub, fill=GOLD)
    return frame


def _text_card(lines: list[str], sub: str = "") -> Image.Image:
    frame = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(frame, "RGBA")
    f_title = _font(FONT_BOLD, 62)
    f_sub = _font(FONT_REG, 32)
    total_h = len(lines) * 80 + (50 if sub else 0)
    y = (H - total_h) // 2
    for ln in lines:
        tw = draw.textlength(ln, font=f_title)
        draw.text(((W - tw) / 2, y), ln, font=f_title, fill=WHITE)
        y += 80
    if sub:
        y += 10
        tw = draw.textlength(sub, font=f_sub)
        draw.text(((W - tw) / 2, y), sub, font=f_sub, fill=(200, 194, 185))
    return frame


def _cta_card() -> Image.Image:
    frame = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(frame, "RGBA")
    f_kicker = _font(FONT_REG, 34)
    f_site = _font(FONT_BOLD, 78)
    f_desc = _font(FONT_REG, 30)
    f_phone = _font(FONT_BOLD, 46)

    kicker = "AI 나라장터 입찰분석, 무료로 확인해보세요"
    tw = draw.textlength(kicker, font=f_kicker)
    y = H * 0.28
    draw.text(((W - tw) / 2, y), kicker, font=f_kicker, fill=(210, 205, 196))

    y += 90
    site = "bid.haehan-ai.kr"
    tw = draw.textlength(site, font=f_site)
    draw.text(((W - tw) / 2, y), site, font=f_site, fill=GOLD)

    y += 120
    desc = "우리 회사 낙찰 데이터, 지금 무료로 확인"
    tw = draw.textlength(desc, font=f_desc)
    draw.text(((W - tw) / 2, y), desc, font=f_desc, fill=WHITE)

    y += 90
    phone = "010-7387-6635"
    tw = draw.textlength(phone, font=f_phone)
    draw.rectangle([(W - tw) / 2 - 30, y - 10, (W + tw) / 2 + 30, y + 60], fill=(30, 28, 25))
    draw.text(((W - tw) / 2, y), phone, font=f_phone, fill=WHITE)
    return frame


# ──────────────────────────────────────────────────────────
# 장면 구성
# ──────────────────────────────────────────────────────────

SCENES: list[dict[str, Any]] = [
    {
        "narr": "나라장터 공고 하나를 골라서, AI에게 실제로 투찰가 분석을 시켜봤습니다. 화성여자교도소 신축공사 소방공사, 기초금액 31억원짜리 공고입니다.",
        "render": lambda: _text_card(
            ["AI에게 실제로", "투찰가 분석을 시켜봤습니다"], "화성여자교도소 신축공사 소방공사"
        ),
    },
    {
        "narr": "이게 실제 공고 상세 화면입니다. 기초금액 31억 8백만원, 마감은 9월 11일입니다.",
        "render": lambda: _caption_frame(
            SRC_DIR / "bid_detail.jpg", ["실제 공고 상세 화면"], "기초금액 3,108,559,000원 · 낙찰하한율 88.745%"
        ),
    },
    {
        "narr": "이 정보를 그대로 클로드에게 물어봤습니다. 이 공고 투찰가를 어떻게 분석해야 하는지 단계별로 설명해달라고 했습니다.",
        "render": lambda: _caption_frame(
            SRC_DIR / "step_01_initial.jpg", ["1단계: 예정가격 범위 추정"], "AI가 실제로 답변한 화면"
        ),
    },
    {
        "narr": "두 번째 단계, 낙찰하한율 88.745%를 적용해서 낙찰 가능한 하한금액을 계산합니다.",
        "render": lambda: _caption_frame(SRC_DIR / "step_02.jpg", ["2단계: 낙찰하한금액 산출"]),
    },
    {
        "narr": "세 번째, 최근 1~2년 유사한 규모의 교정시설, 관공서 소방공사 낙찰 사례를 수집합니다.",
        "render": lambda: _caption_frame(SRC_DIR / "step_03.jpg", ["3단계: 유사 소방공사 낙찰사례 수집"]),
    },
    {
        "narr": "네 번째, 예상 참여업체 294개사라는 경쟁 강도를 반영합니다. 참여사가 많을수록 낙찰선이 하한율에 가까워지는 경향이 있습니다.",
        "render": lambda: _caption_frame(SRC_DIR / "step_04.jpg", ["4단계: 경쟁강도(참여 294개사) 반영"]),
    },
    {
        "narr": "다섯 번째, 너무 낮게 쓰면 저가심의 대상이 될 수 있다는 리스크까지 짚어줍니다.",
        "render": lambda: _caption_frame(SRC_DIR / "step_05.jpg", ["5단계: 저가심의·하자이행 리스크 점검"]),
    },
    {
        "narr": "마지막 여섯 번째 단계에서 최종 투찰률 구간을 확정합니다.",
        "render": lambda: _caption_frame(SRC_DIR / "step_06.jpg", ["6단계: 최종 투찰율 구간 확정"]),
    },
    {
        "narr": "그래서 최종 금액이 얼마냐고 딱 하나만 찍어달라고 다시 물어봤습니다. 답은 27억 5천7백만원이었습니다.",
        "render": lambda: _caption_frame(SRC_DIR / "final_recommend.jpg", ["최종 추천 투찰가"], "2,757,291,833원"),
    },
    {
        "narr": "그런데 저희가 실제로 운영하는 사이트에서 같은 공고로 몬테카를로 시뮬레이션을 5천 번 돌려본 결과도 똑같이 2,757,291,833원이 나왔습니다.",
        "render": lambda: _caption_frame(
            SRC_DIR / "bid_simulation_final.jpg",
            ["사이트 정밀 시뮬레이션 결과"],
            "AI 답변과 완전히 일치: 2,757,291,833원",
        ),
    },
    {
        "narr": "이 과정, 사실 누구나 따라할 수 있습니다. 공고문에서 기초금액과 하한율만 확인해서, 클로드에게 그대로 물어보면 됩니다.",
        "render": lambda: _text_card(
            ["누구나 따라할 수 있습니다"], "①공고정보 확인 → ②AI에게 질문 → ③필요하면 정밀검증"
        ),
    },
    {
        "narr": "다만 AI의 답변은 일반적인 추론이고, 저희 사이트는 실제 축적된 데이터로 정밀하게 검증한다는 차이가 있습니다. 이번엔 우연히 숫자가 일치했지만, 매번 그런 건 아닙니다.",
        "render": lambda: _text_card(
            ["AI 추론 vs 정밀 시뮬레이션", "이번엔 일치했지만 매번은 아닙니다"], "정직하게 말씀드립니다"
        ),
    },
    {
        "narr": "저희가 실제로 운영 중인 AI 나라장터 입찰분석 플랫폼 해한 에이아이에서, 우리 회사 낙찰 데이터를 무료로 확인해보실 수 있습니다.",
        "render": _cta_card,
    },
]


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return float(out.stdout.strip())


async def _tts(text: str, out_path: Path, rate: str) -> None:
    import edge_tts  # type: ignore[import-not-found]  # 선택적 의존성(docs_registry.toml 등록)

    comm = edge_tts.Communicate(text=text, voice="ko-KR-InJoonNeural", rate=rate)
    await comm.save(str(out_path))


def build_video(frames: list[Path], durations: list[float], out_path: Path, fade: float = 0.4) -> Path:
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


def mux_audio(video_no_audio: Path, narration: Path, out_path: Path) -> Path:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_no_audio),
        "-i",
        str(narration),
        "-c:v",
        "copy",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"오디오 믹싱 실패: {proc.stderr[-2000:]}")
    return out_path


def main() -> None:
    audio_dir = OUT_DIR / "audio"
    frame_dir = OUT_DIR / "frames"
    audio_dir.mkdir(parents=True, exist_ok=True)
    frame_dir.mkdir(parents=True, exist_ok=True)

    durations: list[float] = []
    frame_paths: list[Path] = []
    audio_paths: list[Path] = []

    for i, scene in enumerate(SCENES):
        audio_path = audio_dir / f"scene_{i:02d}.mp3"
        asyncio.run(_tts(scene["narr"], audio_path, TTS_RATE))
        dur = _probe_duration(audio_path)
        audio_paths.append(audio_path)
        durations.append(dur + 0.4)

        frame = scene["render"]()
        frame_path = frame_dir / f"scene_{i:02d}.png"
        frame.save(frame_path)
        frame_paths.append(frame_path)
        print(f"scene {i}: {dur:.1f}s  {scene['narr'][:30]}...")

    concat_list = audio_dir / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in audio_paths), encoding="utf-8")
    full_audio = audio_dir / "full_narration.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(full_audio)],
        check=True,
        capture_output=True,
    )

    video_silent = OUT_DIR / "video_silent.mp4"
    build_video(frame_paths, durations, video_silent)

    final_out = OUT_DIR / "ai_g2b_ep01_real.mp4"
    mux_audio(video_silent, full_audio, final_out)

    total_sec = sum(durations)
    print(f"\n완료: {final_out}  (총 {total_sec:.0f}초 ≈ {total_sec / 60:.1f}분)")


if __name__ == "__main__":
    main()
