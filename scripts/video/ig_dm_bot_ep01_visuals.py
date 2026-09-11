"""인스타 DM 봇 소개 영상 1편 — 비주얼 카드 제작 + 최종 조립.

나레이션(TTS)은 scripts/video/ig_dm_bot_ep01.py 에서 이미 생성됨.
이 스크립트는 그 길이에 맞춰 롱폼(1920x1080) 카드/다이어그램을 만들고,
실제 데모 캡처 스크린샷(data/video/ig_dm_bot_ep01/demo_frames/)과 합쳐
최종 mp4를 만든다. 코드/레포는 화면에 노출하지 않는다(비공개 원칙).

실행:
  python scripts/video/ig_dm_bot_ep01_visuals.py
출력: data/video/ig_dm_bot_ep01/final.mp4
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ai_orchestrator.config import get_local_data_dir  # noqa: E402
from scripts.instagram.kotara_ctc_reel import _font, _gradient_band, _letterbox, _wrap  # noqa: E402

OUT_DIR = get_local_data_dir() / "video" / "ig_dm_bot_ep01"
NARRATION_DIR = OUT_DIR / "narration"
DEMO_DIR = OUT_DIR / "demo_frames"
FRAME_DIR = OUT_DIR / "frames"
FRAME_DIR.mkdir(parents=True, exist_ok=True)

W, H = 1920, 1080
FONT_BOLD = r"C:\Windows\Fonts\malgunbd.ttf"
FONT_REG = r"C:\Windows\Fonts\malgun.ttf"

INK = (24, 22, 20)
CREAM = (247, 243, 236)
WHITE = (255, 255, 255)
GOLD = (196, 164, 108)
BLUE = (90, 140, 210)


def _title_card(lines: list[str], sub: str = "") -> Image.Image:
    img = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(img, "RGBA")
    _gradient_band(img, int(H * 0.30), int(H * 0.70), from_alpha=0, to_alpha=45, color=(60, 55, 48))
    f_title = _font(FONT_BOLD, 84)
    f_sub = _font(FONT_REG, 40)
    total_h = len(lines) * 104 + (60 if sub else 0)
    y = (H - total_h) // 2
    for ln in lines:
        tw = draw.textlength(ln, font=f_title)
        draw.text(((W - tw) / 2, y), ln, font=f_title, fill=WHITE)
        y += 104
    if sub:
        y += 16
        tw = draw.textlength(sub, font=f_sub)
        draw.text(((W - tw) / 2, y), sub, font=f_sub, fill=(200, 194, 185))
    return img


def _step_card(step_no: int, total: int, title: str, desc: str) -> Image.Image:
    """아키텍처 단계 카드 — 좌측 큰 숫자 + 우측 설명."""
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img, "RGBA")

    # 좌측 패널
    panel_w = int(W * 0.32)
    draw.rectangle([0, 0, panel_w, H], fill=INK)
    f_step = _font(FONT_REG, 36)
    f_no = _font(FONT_BOLD, 220)
    step_txt = f"STEP {step_no}/{total}"
    draw.text((80, 120), step_txt, font=f_step, fill=GOLD)
    draw.text((80, 190), str(step_no), font=f_no, fill=WHITE)

    # 진행 바 (하단)
    bar_y = H - 100
    seg_w = (panel_w - 160) / total
    for i in range(total):
        x0 = 80 + i * seg_w
        color = GOLD if i < step_no else (80, 76, 70)
        draw.rectangle([x0, bar_y, x0 + seg_w - 12, bar_y + 10], fill=color)

    # 우측 텍스트
    f_title = _font(FONT_BOLD, 64)
    f_desc = _font(FONT_REG, 38)
    tx = panel_w + 100
    ty = 300
    for ln in _wrap(draw, title, f_title, W - tx - 100):
        draw.text((tx, ty), ln, font=f_title, fill=INK)
        ty += 84
    ty += 30
    for ln in _wrap(draw, desc, f_desc, W - tx - 100):
        draw.text((tx, ty), ln, font=f_desc, fill=(70, 66, 60))
        ty += 58
    return img


def _demo_card(shot_path: Path, caption: str) -> Image.Image:
    """실제 캡처 스크린샷을 카드에 합성."""
    img = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(img, "RGBA")
    shot = Image.open(shot_path).convert("RGB")
    inner = _letterbox(shot, W - 160, H - 220, bg=(40, 38, 35))
    img.paste(inner, (80, 60))
    f_cap = _font(FONT_BOLD, 44)
    tw = draw.textlength(caption, font=f_cap)
    draw.text(((W - tw) / 2, H - 110), caption, font=f_cap, fill=GOLD)
    return img


def _cta_card(lines: list[str], sub: str = "") -> Image.Image:
    return _title_card(lines, sub)


STEPS = [
    (1, "웹훅", "댓글이 달리면 메타 서버가\n우리 서버로 실시간 전달"),
    (2, "댓글 감지", "가격, 문의 같은 반응 키워드가\n있는지 확인"),
    (3, "규칙 매칭", "계정·게시물별로 정해둔\n규칙과 대조"),
    (4, "프라이빗 리플라이", "매칭된 메시지를\nDM으로 자동 발송"),
]


def render_frames() -> list[tuple[Path, float]]:
    """(프레임경로, 노출시간초) 리스트. 노출시간은 나레이션 길이에서 역산."""
    import json

    durations = json.loads((OUT_DIR / "scene_durations.json").read_text(encoding="utf-8"))

    frames: list[tuple[Path, float]] = []

    # scene 0: hook
    p = FRAME_DIR / "s0_hook.png"
    _title_card(["인스타 팔로우·DM,", "자동으로 될까?"], "댓글 하나로 DM 자동발송 — 툴 없이 직접 만들었습니다").save(p)
    frames.append((p, durations["hook"]))

    # scene 1: architecture — 4단계를 나레이션 길이 안에서 균등 분할
    arch_total = durations["architecture"]
    per_step = arch_total / len(STEPS)
    for no, title, desc in STEPS:
        p = FRAME_DIR / f"s1_step{no}.png"
        _step_card(no, len(STEPS), title, desc).save(p)
        frames.append((p, per_step))

    # scene 2: demo — 실제 캡처 2장
    demo_total = durations["demo"]
    shots = [
        (DEMO_DIR / "01_comment_posted.png", '① 댓글 게시 — "가격이 얼마에요?"'),
        (DEMO_DIR / "02_dm_received.png", "② 1분 만에 자동 DM 도착"),
    ]
    for shot_path, cap in shots:
        p = FRAME_DIR / f"s2_{shot_path.stem}.png"
        _demo_card(shot_path, cap).save(p)
        frames.append((p, demo_total / len(shots)))

    # scene 3: cta
    p = FRAME_DIR / "s3_cta.png"
    _cta_card(["직접 만들어보세요"], "구축 문의는 채널 링크로 · 세부 구현은 다음 영상에서").save(p)
    frames.append((p, durations["cta"]))

    return frames


def build_video(frames: list[tuple[Path, float]], out_path: Path, fade: float = 0.4) -> Path:
    paths = [f for f, _ in frames]
    durations = [d for _, d in frames]
    n = len(paths)
    inputs: list[str] = []
    for f, d in zip(paths, durations):
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
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {proc.stderr[-3000:]}")
    return out_path


def concat_narration(out_path: Path) -> Path:
    """4개 나레이션 mp3를 하나로 이어붙인다(장면 순서대로)."""
    names = ["scene_00_hook.mp3", "scene_01_architecture.mp3", "scene_02_demo.mp3", "scene_03_cta.mp3"]
    list_file = OUT_DIR / "narration_concat.txt"
    list_file.write_text("\n".join(f"file '{(NARRATION_DIR / n).as_posix()}'" for n in names), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"나레이션 병합 실패: {proc.stderr[-2000:]}")
    return out_path


def mux(video_no_audio: Path, narration: Path, out_path: Path) -> Path:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_no_audio),
        "-i",
        str(narration),
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"mux 실패: {proc.stderr[-2000:]}")
    return out_path


def main() -> None:
    frames = render_frames()
    print(f"프레임 {len(frames)}개 생성 완료, 총 {sum(d for _, d in frames):.1f}초")

    silent = OUT_DIR / "silent.mp4"
    build_video(frames, silent)
    print(f"무음 비디오 조립 완료: {silent}")

    narration = OUT_DIR / "narration_full.mp3"
    concat_narration(narration)
    print(f"나레이션 병합 완료: {narration}")

    final = OUT_DIR / "final.mp4"
    mux(silent, narration, final)
    print(f"최종 영상 완성: {final}")


if __name__ == "__main__":
    main()
