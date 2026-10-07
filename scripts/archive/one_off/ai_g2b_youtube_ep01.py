"""AI 나라장터 입찰 시리즈 1편 유튜브 영상 제작 — 텍스트카드+TTS.

기존 렌더링/조립 헬퍼(scripts.archive.one_off.kotara_ctc_reel)를 재사용한다.
콘텐츠는 blog_drafts/ai_g2b_01_intro.json의 실측 데이터를 요약해 사용.
해한Ai(bid.haehan-ai.kr) + 010-7387-6635를 강조 카드로 별도 노출.

출력: data/youtube_g2b_series/ep01/
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from scripts.archive.one_off.kotara_ctc_reel import (
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
    build_video,
    mux_audio,
)

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "youtube_g2b_series" / "ep01"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TTS_RATE = "+25%"  # 사용자 지시: 말하기 속도 상향 (기존 쇼츠 기본 +15%보다 빠르게)

SITE = "bid.haehan-ai.kr"
PHONE = "010-7387-6635"


def _text_card(lines: list[str], sub: str = "") -> Image.Image:
    img = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(img, "RGBA")
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


def _stat_card(number: str, caption: str, footnote: str = "") -> Image.Image:
    """큰 숫자를 강조하는 카드 (실측 수치용)."""
    img = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(img, "RGBA")
    _gradient_band(img, int(H * 0.30), int(H * 0.70), from_alpha=0, to_alpha=50, color=(80, 70, 50))
    f_num = _font(FONT_BOLD, 150)
    f_cap = _font(FONT_BOLD, 46)
    f_foot = _font(FONT_REG, 30)

    tw = draw.textlength(number, font=f_num)
    num_y = H * 0.38
    draw.text(((W - tw) / 2, num_y), number, font=f_num, fill=GOLD)

    cap_y = num_y + 180
    # 캡션 줄바꿈(최대 14자 정도씩)
    words = caption
    tw2 = draw.textlength(words, font=f_cap)
    if tw2 > W - 120:
        mid = len(words) // 2
        # 가장 가까운 공백 기준 분리, 없으면 그냥 절반
        split_at = words.rfind(" ", 0, mid) or mid
        line1, line2 = words[:split_at].strip(), words[split_at:].strip()
        for i, ln in enumerate([line1, line2]):
            tw3 = draw.textlength(ln, font=f_cap)
            draw.text(((W - tw3) / 2, cap_y + i * 60), ln, font=f_cap, fill=WHITE)
        cap_y += 60
    else:
        draw.text(((W - tw2) / 2, cap_y), words, font=f_cap, fill=WHITE)

    if footnote:
        fy = cap_y + 90
        twf = draw.textlength(footnote, font=f_foot)
        draw.text(((W - twf) / 2, fy), footnote, font=f_foot, fill=(180, 175, 168))
    return img


def _cta_card() -> Image.Image:
    """사이트+전화번호를 크게 강조하는 클로징 카드."""
    img = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(img, "RGBA")
    _gradient_band(img, int(H * 0.20), int(H * 0.80), from_alpha=0, to_alpha=55, color=(70, 60, 40))

    f_kicker = _font(FONT_REG, 38)
    f_site = _font(FONT_BOLD, 84)
    f_desc = _font(FONT_REG, 34)

    kicker = "AI 나라장터 입찰분석, 무료로 확인해보세요"
    tw = draw.textlength(kicker, font=f_kicker)
    y = H * 0.30
    draw.text(((W - tw) / 2, y), kicker, font=f_kicker, fill=(210, 205, 196))

    y += 90
    tw = draw.textlength(SITE, font=f_site)
    draw.text(((W - tw) / 2, y), SITE, font=f_site, fill=GOLD)

    y += 140
    desc = "우리 회사 낙찰 데이터, 지금 무료로 확인"
    tw = draw.textlength(desc, font=f_desc)
    draw.text(((W - tw) / 2, y), desc, font=f_desc, fill=WHITE)

    y += 100
    _phone_pill(draw, W // 2, int(y), PHONE, size=54, big=True)
    return img


# ──────────────────────────────────────────────────────────
# 대본 (1편: 나라장터 입찰 처음이신 분 — 요약본, 3~4분 타깃)
# ──────────────────────────────────────────────────────────

SCENES: list[dict[str, Any]] = [
    {
        "narr": "나라장터 입찰, 처음이면 다들 여기서 막힙니다. 투찰금액을 얼마로 써야 할지, 감으로 정하고 계시지 않나요?",
        "render": lambda: _text_card(["나라장터 입찰", "처음이신 분"], "투찰금액, 감으로 쓰고 계신가요?"),
    },
    {
        "narr": "AI로 과거 낙찰 데이터를 분석하면, 감이 아니라 근거로 투찰가를 정할 수 있습니다. 오늘은 그 방법을 알려드립니다.",
        "render": lambda: _text_card(["AI로 분석하면", "근거가 생깁니다"], "저희가 실제로 검증한 방법"),
    },
    {
        "narr": "먼저 낙찰하한율입니다. 이 비율 밑으로 쓰면 바로 실격입니다. 공고문에서 가장 먼저 확인해야 할 숫자입니다.",
        "render": lambda: _text_card(["1. 낙찰하한율 확인", "이 밑으로 쓰면 실격"], "공고문에서 가장 먼저 볼 숫자"),
    },
    {
        "narr": "두 번째는 복수예비가격입니다. 예정가격 후보 15개 중 4개가 추첨으로 뽑혀 평균을 냅니다. 정확히 맞히는 게 아니라 범위를 넓게 봐야 합니다.",
        "render": lambda: _stat_card("15개 중 4개", "복수예비가격, 추첨으로 결정", "정확히 맞히기 아니라 범위로 접근"),
    },
    {
        "narr": "저희가 실제로 소방공사 251건을 분석했습니다. 낙찰된 투찰비율 중앙값은 90.335퍼센트였고, 90.25에서 90.5 구간에 17.1퍼센트가 몰려 있었습니다.",
        "render": lambda: _stat_card("90.335%", "251건 분석한 낙찰비율 중앙값", "90.25~90.50% 구간에 17.1% 집중"),
    },
    {
        "narr": "그런데 더 중요한 건 이겁니다. 실격선과 낙찰선 사이 간격이 8개월 사이 7.5배나 좁아졌습니다. 예전 방식은 지금 시장에서 통하기 어렵습니다.",
        "render": lambda: _stat_card(
            "7.5배", "실격선-낙찰선 간격, 8개월 새 압축", "예전 전략은 지금 시장에서 위험합니다"
        ),
    },
    {
        "narr": "적격심사 A값도 놓치면 안 됩니다. 낙찰하한율을 넘겨도 A값 감점으로 순위가 밀릴 수 있습니다. 두 기준을 같이 봐야 합니다.",
        "render": lambda: _text_card(["A값 감점 주의", "하한율 통과해도"], "A값 근접도에서 순위가 밀릴 수 있음"),
    },
    {
        "narr": "이 모든 계산, 사람이 매번 손으로 하기는 어렵습니다. 그래서 저희가 AI 나라장터 입찰분석 프로그램을 직접 만들고 있습니다.",
        "render": lambda: _text_card(["AI로 이렇게", "계산할 수 있습니다"], "과거 데이터 자동 수집 + 분포 계산"),
    },
    {
        "narr": "지금 실제로 운영 중인 해한 에이아이에서, 우리 회사 낙찰 데이터를 무료로 확인해보실 수 있습니다. 화면 아래 사이트와 번호로 바로 연락 주세요.",
        "render": _cta_card,
    },
]


def _probe_duration(path: Path) -> float:
    import subprocess

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
        durations.append(dur + 0.4)  # 장면 전환 여유

        frame = scene["render"]()
        frame_path = frame_dir / f"scene_{i:02d}.png"
        frame.save(frame_path)
        frame_paths.append(frame_path)
        print(f"scene {i}: {dur:.1f}s  {scene['narr'][:30]}...")

    # 오디오 전부 이어붙이기
    concat_list = audio_dir / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in audio_paths), encoding="utf-8")
    full_audio = audio_dir / "full_narration.mp3"
    import subprocess

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(full_audio)],
        check=True,
        capture_output=True,
    )

    video_no_audio = OUT_DIR / "video_silent.mp4"
    build_video(frame_paths, durations, video_no_audio, fade=0.4)

    final_out = OUT_DIR / "ai_g2b_ep01.mp4"
    mux_audio(video_no_audio, full_audio, None, final_out)

    total_sec = sum(durations)
    print(f"\n완료: {final_out}  (총 {total_sec:.0f}초 ≈ {total_sec / 60:.1f}분)")


if __name__ == "__main__":
    main()
