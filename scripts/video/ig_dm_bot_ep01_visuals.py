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


DIAGRAM_STEPS = [
    (1, "웹훅"),
    (2, "댓글 감지"),
    (3, "규칙 매칭"),
    (4, "프라이빗 리플라이"),
]


def _draw_diagram(draw: ImageDraw.ImageDraw, active: int, top: int = 90) -> None:
    """상단 고정 화이트보드 다이어그램 — 4개 박스 + 화살표, active까지 누적 강조."""
    n = len(DIAGRAM_STEPS)
    box_w, box_h = 380, 200
    gap = 76
    total_w = n * box_w + (n - 1) * gap
    x0 = (W - total_w) // 2
    f_no = _font(FONT_BOLD, 56)
    f_label = _font(FONT_REG, 32)

    for i, (no, label) in enumerate(DIAGRAM_STEPS):
        bx = x0 + i * (box_w + gap)
        by = top
        done = no < active
        cur = no == active
        if cur:
            fill, edge, txt_color = GOLD, GOLD, INK
        elif done:
            fill, edge, txt_color = (60, 56, 50), (120, 112, 100), WHITE
        else:
            fill, edge, txt_color = CREAM, (200, 194, 184), (150, 144, 134)
        draw.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=18, fill=fill, outline=edge, width=4)
        tw = draw.textlength(str(no), font=f_no)
        draw.text((bx + box_w / 2 - tw / 2, by + 36), str(no), font=f_no, fill=txt_color)
        lw = draw.textlength(label, font=f_label)
        draw.text((bx + box_w / 2 - lw / 2, by + 130), label, font=f_label, fill=txt_color)

        if i < n - 1:
            ax0 = bx + box_w + 10
            ax1 = ax0 + gap - 20
            ay = by + box_h / 2
            arrow_color = GOLD if no < active else (170, 164, 154)
            draw.line([ax0, ay, ax1, ay], fill=arrow_color, width=5)
            draw.polygon([(ax1 + 14, ay), (ax1 - 6, ay - 12), (ax1 - 6, ay + 12)], fill=arrow_color)


def _diagram_card(active: int, desc: str, inset_path: Path | None = None, inset_caption: str = "") -> Image.Image:
    """전체 다이어그램(상단 고정) + 하단에 설명 텍스트 또는 실제 캡처 인서트."""
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img, "RGBA")

    f_title = _font(FONT_BOLD, 46)
    title = "핵심 구조 — 댓글이 DM이 되기까지"
    tw = draw.textlength(title, font=f_title)
    draw.text(((W - tw) / 2, 24), title, font=f_title, fill=INK)

    _draw_diagram(draw, active)

    bottom_y = 90 + 200 + 70  # 다이어그램 하단 여백

    if inset_path and inset_path.exists():
        # 실제 화면 캡처를 우측에, 설명 텍스트를 좌측에 배치
        inset_w, inset_h = 760, H - bottom_y - 60
        shot = Image.open(inset_path).convert("RGB")
        inner = _letterbox(shot, inset_w, inset_h, bg=(235, 230, 220))
        ix = W - inset_w - 120
        img.paste(inner, (ix, bottom_y))
        draw.rectangle([ix, bottom_y, ix + inset_w, bottom_y + inset_h], outline=(210, 204, 192), width=3)
        f_cap = _font(FONT_BOLD, 30)
        cw = draw.textlength(inset_caption, font=f_cap)
        draw.text((ix + inset_w / 2 - cw / 2, bottom_y + inset_h + 14), inset_caption, font=f_cap, fill=GOLD)
        desc_w = ix - 160
    else:
        desc_w = W - 240

    f_desc = _font(FONT_BOLD, 48)
    ty = bottom_y + 30
    for ln in _wrap(draw, desc, f_desc, desc_w):
        draw.text((120, ty), ln, font=f_desc, fill=(60, 56, 50))
        ty += 68
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
    (1, "댓글이 달리면 메타 서버가 우리 서버로 실시간 전달합니다.", None, ""),
    (
        2,
        "가격, 문의 같은 반응 키워드가 있는지 확인합니다.",
        DEMO_DIR / "01_comment_posted.png",
        '실제 화면 — "가격이 얼마에요?" 댓글',
    ),
    (3, "계정·게시물별로 정해둔 규칙과 대조합니다.", None, ""),
    (
        4,
        "매칭된 메시지를 DM으로 자동 발송합니다.",
        DEMO_DIR / "02_dm_received.png",
        "실제 화면 — 1분 만에 도착한 자동 DM",
    ),
]


def render_frames() -> list[tuple[Path, float]]:
    """(프레임경로, 노출시간초) 리스트. 노출시간은 나레이션 길이에서 역산."""
    import json

    durations = json.loads((OUT_DIR / "scene_durations.json").read_text(encoding="utf-8"))

    frames: list[tuple[Path, float]] = []

    # scene 0: hook — 질문만 먼저 던지고, 답(훅 문구)이 뒤이어 등장하도록 2단계로 쪼갠다.
    hook_total = durations["hook"]
    p0a = FRAME_DIR / "s0_hook_a.png"
    _title_card(["인스타 팔로우·DM,", "자동으로 될까?"]).save(p0a)
    frames.append((p0a, hook_total * 0.45))
    p0b = FRAME_DIR / "s0_hook_b.png"
    _title_card(["인스타 팔로우·DM,", "자동으로 될까?"], "댓글 하나로 DM 자동발송 — 툴 없이 직접 만들었습니다").save(
        p0b
    )
    frames.append((p0b, hook_total * 0.55))

    # scene 1: architecture — 다이어그램은 화면에 고정, 진행 박스만 누적 강조.
    # 2·4단계는 실제 캡처를 인서트해 추상 설명과 실제 화면을 교차 노출한다.
    arch_total = durations["architecture"]
    per_step = arch_total / len(STEPS)
    for no, desc, inset_path, inset_caption in STEPS:
        p = FRAME_DIR / f"s1_step{no}.png"
        _diagram_card(no, desc, inset_path, inset_caption).save(p)
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

    # scene 3: cta — 마찬가지로 2단계 등장(문구 → 문구+안내)으로 정지감을 줄인다.
    cta_total = durations["cta"]
    p3a = FRAME_DIR / "s3_cta_a.png"
    _cta_card(["직접 만들어보세요"]).save(p3a)
    frames.append((p3a, cta_total * 0.45))
    p3b = FRAME_DIR / "s3_cta_b.png"
    _cta_card(["직접 만들어보세요"], "구축 문의는 채널 링크로 · 세부 구현은 다음 영상에서").save(p3b)
    frames.append((p3b, cta_total * 0.55))

    return frames


def build_video(frames: list[tuple[Path, float]], out_path: Path, fade: float = 0.4) -> Path:
    """정지 카드를 xfade로 잇는다.

    NOTE(2026-09-11): zoompan/time-crop 기반 Ken Burns 효과를 시도했으나 이 ffmpeg
    빌드(8.1)에서 실제로는 전혀 줌이 진행되지 않는 것을 여러 방식으로 실측 확인함
    (누적 zoom 표현식이 매 프레임 리셋되는 것으로 추정). 검증 안 되는 효과에 시간을
    더 쓰지 않고, 확실히 작동하는 xfade+프레임 수 증가(텍스트 단계적 등장 등)로
    생동감을 준다 — render_frames()에서 카드당 프레임 수를 늘려서 해결.
    """
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
