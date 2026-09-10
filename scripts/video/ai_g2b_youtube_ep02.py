"""AI 나라장터 입찰 2편 — 동고양세무서 청사신축(소방) 실제 분석."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.instagram.kotara_ctc_reel import (
    FONT_BOLD,
    FONT_REG,
    GOLD,
    INK,
    WHITE,
    H,
    W,
    _font,
    _gradient_band,
    _phone_pill,
)

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "data" / "youtube_g2b_series" / "ep_live"
OUT_DIR = ROOT / "data" / "youtube_g2b_series" / "ep02_real"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TTS_RATE = "+25%"


def _fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    ratio = min(max_w / img.width, max_h / img.height)
    return img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)


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
    f_title = _font(FONT_BOLD, 60)
    f_sub = _font(FONT_REG, 30)
    total_h = len(lines) * 78 + (48 if sub else 0)
    y = (H - total_h) // 2
    for ln in lines:
        tw = draw.textlength(ln, font=f_title)
        draw.text(((W - tw) / 2, y), ln, font=f_title, fill=WHITE)
        y += 78
    if sub:
        y += 10
        tw = draw.textlength(sub, font=f_sub)
        draw.text(((W - tw) / 2, y), sub, font=f_sub, fill=(200, 194, 185))
    return frame


def _stat_card(number: str, caption: str, footnote: str = "") -> Image.Image:
    frame = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(frame, "RGBA")
    _gradient_band(frame, int(H * 0.30), int(H * 0.70), from_alpha=0, to_alpha=50, color=(80, 70, 50))
    f_num = _font(FONT_BOLD, 110)
    f_cap = _font(FONT_BOLD, 42)
    f_foot = _font(FONT_REG, 28)
    tw = draw.textlength(number, font=f_num)
    y = H * 0.36
    draw.text(((W - tw) / 2, y), number, font=f_num, fill=GOLD)
    y += 140
    tw = draw.textlength(caption, font=f_cap)
    draw.text(((W - tw) / 2, y), caption, font=f_cap, fill=WHITE)
    if footnote:
        y += 70
        tw = draw.textlength(footnote, font=f_foot)
        draw.text(((W - tw) / 2, y), footnote, font=f_foot, fill=(180, 175, 168))
    return frame


def _cta_card() -> Image.Image:
    frame = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(frame, "RGBA")
    f_kicker = _font(FONT_REG, 34)
    f_site = _font(FONT_BOLD, 78)
    f_desc = _font(FONT_REG, 30)
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
    _phone_pill(draw, W // 2, int(y), "010-7387-6635", size=46, big=True)
    return frame


SCENES = [
    {
        "narr": "이번엔 경쟁이 훨씬 치열한 공고로 AI에게 투찰가 분석을 시켜봤습니다. 동고양세무서 청사신축 소방공사, 예상 참여업체 678개사입니다.",
        "render": lambda: _text_card(
            ["이번엔 경쟁 678개사", "초고경쟁 공고로 테스트했습니다"], "동고양세무서 청사신축(소방)"
        ),
    },
    {
        "narr": "기초금액 10억 1천7백만원, 낙찰하한율 89.745%, 제한경쟁 방식입니다.",
        "render": lambda: _caption_frame(
            SRC_DIR / "ep2_detail.jpg", ["실제 공고 상세 화면"], "기초금액 1,017,479,000원 · 낙찰하한율 89.745%"
        ),
    },
    {
        "narr": "AI에게 물어봤습니다. 이번엔 카드 형식이 아니라 단계별 서술로 답이 나왔습니다. 예정가격 추정부터 시작합니다.",
        "render": lambda: _caption_frame(
            SRC_DIR / "ep2_step_01.jpg",
            ["AI 실시간 답변"],
            "1~4단계: 예정가격 추정 → 이론적 하한가 → 경쟁강도 → 안전마진",
        ),
    },
    {
        "narr": "핵심은 3단계입니다. 678개사가 전부 같은 공식으로 계산해서 몰려들기 때문에, 이론값 그대로 쓰면 동일가 근접 경쟁에서 순위가 밀릴 위험이 있다고 짚었습니다.",
        "render": lambda: _text_card(
            ["678개사가 전부", "같은 공식으로 계산합니다"], "이론값 그대로 쓰면 순위가 밀릴 수 있습니다"
        ),
    },
    {
        "narr": "그래서 AI가 제시한 최종 추천 투찰가는 9억 1천3백42만원이었습니다.",
        "render": lambda: _stat_card(
            "913,420,000원", "AI 최종 추천 투찰가", "이론적 하한가(913,136,528원)에 안전마진 반영"
        ),
    },
    {
        "narr": "같은 공고로 저희 사이트의 정밀 시뮬레이션을 돌려보니, 승률 최고 구간 투찰가는 9억 1천2백67만원이 나왔습니다.",
        "render": lambda: _caption_frame(
            SRC_DIR / "ep2_sim_final.jpg",
            ["사이트 정밀 시뮬레이션 결과"],
            "승률 최고 투찰금액 912,678,663원 (투찰률 89.70%)",
        ),
    },
    {
        "narr": "이번엔 완전히 일치하지는 않았습니다. AI는 913,420,000원, 사이트는 912,678,663원으로 약 74만원, 0.08퍼센트 정도 차이가 났습니다.",
        "render": lambda: _text_card(
            ["이번엔 완전히 일치하지 않았습니다"], "AI 913,420,000원 vs 시뮬레이션 912,678,663원 (0.08% 차이)"
        ),
    },
    {
        "narr": "지난 편에서 말씀드렸듯이, AI 추론과 정밀 시뮬레이션은 항상 일치하지 않습니다. 경쟁이 치열한 공고일수록 실측 데이터 기반 정밀 계산의 가치가 더 커집니다.",
        "render": lambda: _text_card(
            ["경쟁이 치열할수록", "정밀 검증의 가치가 커집니다"], "실측 데이터 vs 일반 추론의 차이"
        ),
    },
    {
        "narr": "저희가 실제로 운영 중인 AI 나라장터 입찰분석 플랫폼 해한 에이아이에서, 우리 회사 공고로 직접 확인해보실 수 있습니다.",
        "render": _cta_card,
    },
]


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    return float(out.stdout.strip())


async def _tts(text: str, out_path: Path, rate: str) -> None:
    import edge_tts

    comm = edge_tts.Communicate(text=text, voice="ko-KR-InJoonNeural", rate=rate)
    await comm.save(str(out_path))


def build_video(frames: list[Path], durations: list[float], out_path: Path, fade: float = 0.4) -> Path:
    n = len(frames)
    inputs: list[str] = []
    for f, d in zip(frames, durations):
        inputs += ["-loop", "1", "-t", str(d + fade), "-i", str(f)]
    scale_filters = [
        f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]"
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
    proc = subprocess.run(cmd, capture_output=True, text=True)
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
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"오디오 믹싱 실패: {proc.stderr[-2000:]}")
    return out_path


def main() -> None:
    audio_dir = OUT_DIR / "audio"
    frame_dir = OUT_DIR / "frames"
    audio_dir.mkdir(parents=True, exist_ok=True)
    frame_dir.mkdir(parents=True, exist_ok=True)
    durations, frame_paths, audio_paths = [], [], []
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
        print(f"scene {i}: {dur:.1f}s")
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
    final_out = OUT_DIR / "ai_g2b_ep02_real.mp4"
    mux_audio(video_silent, full_audio, final_out)
    total_sec = sum(durations)
    print(f"\n완료: {final_out} (총 {total_sec:.0f}초)")


if __name__ == "__main__":
    main()
