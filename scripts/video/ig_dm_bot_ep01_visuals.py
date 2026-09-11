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

    def _spread(total: float, weights: list[float]) -> list[float]:
        s = sum(weights)
        return [total * w / s for w in weights]

    # scene 0: hook — 정지 화면이 너무 길지 않도록 5단계로 잘게 쪼개 계속 바뀌게 한다.
    hook_total = durations["hook"]
    hook_states = [
        (["인스타 팔로우·DM,"], ""),
        (["인스타 팔로우·DM,", "자동으로 될까?"], ""),
        (["인스타 팔로우·DM,", "자동으로 될까?"], "❌ 팔로우·좋아요·댓글 자동화는 안 됩니다"),
        (["인스타 팔로우·DM,", "자동으로 될까?"], "✅ 댓글→DM 자동발송은 공식 지원됩니다"),
        (["인스타 팔로우·DM,", "자동으로 될까?"], "댓글 하나로 DM 자동발송 — 툴 없이 직접 만들었습니다"),
    ]
    for i, (dur, (lines, sub)) in enumerate(zip(_spread(hook_total, [1, 1, 1.2, 1.2, 1.3]), hook_states)):
        p = FRAME_DIR / f"s0_hook_{i}.png"
        _title_card(lines, sub).save(p)
        frames.append((p, dur))

    # scene 1: architecture — 다이어그램은 화면에 고정, 진행 박스만 누적 강조.
    # 각 단계를 (박스 강조만) → (+설명 텍스트) → (+실제 캡처, 있으면) 3단계로 쪼개
    # 한 화면이 오래 머물지 않게 한다.
    arch_total = durations["architecture"]
    per_step_total = arch_total / len(STEPS)
    for no, desc, inset_path, inset_caption in STEPS:
        sub_states: list[tuple[str, Path | None, str]] = [("", None, "")]
        sub_states.append((desc, None, ""))
        if inset_path:
            sub_states.append((desc, inset_path, inset_caption))
        weights = [0.8] + [1.2] * (len(sub_states) - 1)
        for j, (dur, (d, ip, ic)) in enumerate(zip(_spread(per_step_total, weights), sub_states)):
            p = FRAME_DIR / f"s1_step{no}_{j}.png"
            _diagram_card(no, d, ip, ic).save(p)
            frames.append((p, dur))

    # scene 2: demo — 실제 캡처 2장, 각각 (이미지만) → (+캡션)으로 쪼갠다.
    demo_total = durations["demo"]
    shots = [
        (DEMO_DIR / "01_comment_posted.png", '① 댓글 게시 — "가격이 얼마에요?"'),
        (DEMO_DIR / "02_dm_received.png", "② 1분 만에 자동 DM 도착"),
    ]
    per_shot_total = demo_total / len(shots)
    for shot_path, cap in shots:
        p_a = FRAME_DIR / f"s2_{shot_path.stem}_a.png"
        _demo_card(shot_path, "").save(p_a)
        p_b = FRAME_DIR / f"s2_{shot_path.stem}_b.png"
        _demo_card(shot_path, cap).save(p_b)
        for dur, p in zip(_spread(per_shot_total, [0.8, 1.2]), [p_a, p_b]):
            frames.append((p, dur))

    # scene 3: cta — 4단계로 나눠 정지감을 줄인다.
    cta_total = durations["cta"]
    cta_states = [
        ("직접 만들어보세요", ""),
        ("직접 만들어보세요", "구축 문의는 채널 링크로"),
        ("직접 만들어보세요", "구축 문의는 채널 링크로 · 세부 구현은 다음 영상에서"),
        ("직접 만들어보세요", "구축 문의는 채널 링크로 · 세부 구현은 다음 영상에서 · 구독하기 🔔"),
    ]
    for i, (dur, (line, sub)) in enumerate(zip(_spread(cta_total, [1, 1, 1, 1.2]), cta_states)):
        p = FRAME_DIR / f"s3_cta_{i}.png"
        _cta_card([line], sub).save(p)
        frames.append((p, dur))

    return frames


def _kenburns_clip(path: Path, duration: float, zoom_in: bool, k: float = 0.12):
    """정지 이미지에 실제로 동작하는 줌 효과를 입힌 moviepy 클립.

    NOTE(2026-09-11): ffmpeg zoompan/time-crop 필터로 먼저 시도했으나 이 환경
    ffmpeg(8.1)에서 누적 zoom이 매 프레임 리셋되는 버그로 실제로는 전혀 줌이
    진행되지 않음을 여러 방식으로 실측 확인함. moviepy(파이썬에서 프레임 단위로
    직접 리사이즈)는 같은 조건에서 실제 줌이 프레임마다 진행되는 것을 확인했다
    (frame shape이 시간에 따라 실제로 커짐) — 이후 이 효과가 필요하면 ffmpeg
    zoompan을 다시 시도하지 말고 바로 moviepy를 쓸 것.
    """
    from moviepy import ImageClip

    clip = ImageClip(str(path)).with_duration(duration)

    def zoom(t: float) -> float:
        frac = min(t / duration, 1) if duration > 0 else 1
        return 1 + k * frac if zoom_in else 1 + k * (1 - frac)

    clip = clip.resized(zoom)

    def crop_center(get_frame, t):
        frame = get_frame(t)
        h, w = frame.shape[0], frame.shape[1]
        x0 = max(0, (w - W) // 2)
        y0 = max(0, (h - H) // 2)
        return frame[y0 : y0 + H, x0 : x0 + W]

    return clip.transform(crop_center)


def build_video(frames: list[tuple[Path, float]], out_path: Path, fade: float = 0.4) -> Path:
    """카드마다 Ken Burns 줌(moviepy) + xfade로 잇는다. 짝/홀 인덱스로 줌 방향을 번갈아 단조로움을 줄인다."""
    from moviepy import concatenate_videoclips, vfx

    n = len(frames)
    clips = [_kenburns_clip(p, d + fade, i % 2 == 0) for i, (p, d) in enumerate(frames)]
    faded = []
    for i, c in enumerate(clips):
        effects = []
        if i > 0:
            effects.append(vfx.CrossFadeIn(fade))
        if i < n - 1:
            effects.append(vfx.CrossFadeOut(fade))
        faded.append(c.with_effects(effects) if effects else c)

    final = concatenate_videoclips(faded, method="compose", padding=-fade)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(str(out_path), fps=30, codec="libx264", audio=False, logger=None)
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
