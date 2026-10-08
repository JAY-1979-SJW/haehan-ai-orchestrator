"""인스타 DM 봇 소개 영상 1편 — 비주얼 카드 제작 + 최종 조립.

나레이션(TTS)은 scripts/archive/one_off/ig_dm_bot_ep01.py 에서 이미 생성됨.
이 스크립트는 그 길이에 맞춰 롱폼(1920x1080) 카드/다이어그램을 만들고,
실제 데모 캡처 스크린샷(data/video/ig_dm_bot_ep01/demo_frames/)과 합쳐
최종 mp4를 만든다. 코드/레포는 화면에 노출하지 않는다(비공개 원칙).

실행:
  python scripts/archive/one_off/ig_dm_bot_ep01_visuals.py
출력: data/video/ig_dm_bot_ep01/final.mp4
"""

from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from ai_orchestrator.core.config import get_local_data_dir  # noqa: E402
from scripts.archive.one_off.kotara_ctc_reel import _cover, _font, _gradient_band, _letterbox, _wrap  # noqa: E402

OUT_DIR = get_local_data_dir() / "video" / "ig_dm_bot_ep01"
NARRATION_DIR = OUT_DIR / "narration"
DEMO_DIR = OUT_DIR / "demo_frames"
FRAME_DIR = OUT_DIR / "frames"
FRAME_DIR.mkdir(parents=True, exist_ok=True)

W, H = 1920, 1080
FONT_BOLD = str(Path(os.environ.get("WINDIR", "")) / "Fonts" / "malgunbd.ttf")
FONT_REG = str(Path(os.environ.get("WINDIR", "")) / "Fonts" / "malgun.ttf")

INK = (24, 22, 20)
CREAM = (247, 243, 236)
WHITE = (255, 255, 255)
GOLD = (196, 164, 108)
BLUE = (90, 140, 210)


def _title_card(lines: list[str], sub: str = "", bubble: str = "", bg_photo: Path | None = None) -> Image.Image:
    """검은 배경만으로는 지루하다는 피드백 반영 — bg_photo가 있으면 실제 사진을 어둡게 깔고 그 위에 텍스트."""
    if bg_photo and bg_photo.exists():
        photo = Image.open(bg_photo).convert("RGB")
        img = _cover(photo, W, H, focus_y=0.35)
        overlay = Image.new("RGBA", (W, H), (10, 9, 8, 175))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    else:
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
    if bubble:
        bubble_top = 120
        _speech_bubble(
            draw, bubble, center_x=W - 380, top_y=bubble_top, tail_x=W - 480, tail_y=bubble_top + 190, fill=GOLD
        )
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


def _speech_bubble(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수/CLI 인자 보존)
    draw: ImageDraw.ImageDraw,
    text: str,
    center_x: int,
    top_y: int,
    tail_x: int,
    tail_y: int,
    font_size: int = 34,
    fill=WHITE,
    text_color=INK,
    max_width: int = 520,
) -> None:
    """만화풍 말풍선 — (center_x, top_y) 근처에 텍스트를 담은 풍선을 그리고 (tail_x, tail_y)를 가리키는 꼬리를 단다."""
    font = _font(FONT_BOLD, font_size)
    lines = _wrap(draw, text, font, max_width - 60)
    line_h = font_size + 14
    box_w = min(max_width, max(draw.textlength(ln, font=font) for ln in lines) + 60)
    box_h = len(lines) * line_h + 40
    x0 = center_x - box_w / 2
    y0 = top_y
    x1 = center_x + box_w / 2
    y1 = top_y + box_h

    draw.rounded_rectangle([x0, y0, x1, y1], radius=22, fill=fill, outline=INK, width=3)
    tail_base_x = min(max(tail_x, x0 + 30), x1 - 30)
    draw.polygon(
        [(tail_base_x - 18, y1 - 2), (tail_base_x + 18, y1 - 2), (tail_x, tail_y)],
        fill=fill,
        outline=INK,
    )
    draw.line([(tail_base_x - 18, y1 - 2), (tail_x, tail_y)], fill=INK, width=3)
    draw.line([(tail_base_x + 18, y1 - 2), (tail_x, tail_y)], fill=INK, width=3)

    ty = y0 + 20
    for ln in lines:
        tw = draw.textlength(ln, font=font)
        draw.text((center_x - tw / 2, ty), ln, font=font, fill=text_color)
        ty += line_h


def _demo_card(shot_path: Path, caption: str, bubble: str = "") -> Image.Image:
    """실제 캡처 스크린샷을 카드에 합성 + 재미 요소로 말풍선을 얹는다."""
    img = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(img, "RGBA")
    shot = Image.open(shot_path).convert("RGB")
    inner = _letterbox(shot, W - 160, H - 220, bg=(40, 38, 35))
    img.paste(inner, (80, 60))
    f_cap = _font(FONT_BOLD, 44)
    tw = draw.textlength(caption, font=f_cap)
    draw.text(((W - tw) / 2, H - 110), caption, font=f_cap, fill=GOLD)
    if bubble:
        _speech_bubble(draw, bubble, center_x=W - 420, top_y=90, tail_x=W - 560, tail_y=300, fill=GOLD)
    return img


def _cta_card(lines: list[str], sub: str = "", bg_photo: Path | None = None) -> Image.Image:
    return _title_card(lines, sub, bg_photo=bg_photo)


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


def render_frames() -> tuple[list[tuple[Path, float]], int]:
    """(프레임경로, 노출시간초) 리스트 + hook 프레임 개수(그 뒤에 Manim 아키텍처 클립을 끼워넣을 위치).

    아키텍처 장면은 정지 카드가 아니라 별도 렌더링된 Manim 애니메이션(DiagramScene.mp4)을
    쓰므로 이 리스트에는 포함되지 않는다 — build_video()에서 hook 다음, demo 앞에 splice한다.
    """
    import json

    durations = json.loads((OUT_DIR / "scene_durations.json").read_text(encoding="utf-8"))

    frames: list[tuple[Path, float]] = []

    def _spread(total: float, weights: list[float]) -> list[float]:
        s = sum(weights)
        return [total * w / s for w in weights]

    # scene -1: teaser — "진짜 되나?"부터 콜드오픈으로 맨 앞에 배치(피드백 반영, 2026-09-11).
    teaser_total = durations["teaser"]
    teaser_states = [
        (DEMO_DIR / "01_comment_posted.png", '"가격이 얼마에요?" 라고 댓글을 달아봅니다', ""),
        (DEMO_DIR / "02_dm_received.png", "몇 초 뒤 — 자동으로 DM이 도착했습니다", "저는 아무것도 안 했어요"),
        (DEMO_DIR / "02_dm_received.png", "이걸, AI 에이전트로 직접 만들었습니다", ""),
    ]
    for i, (dur, (shot, cap, bubble)) in enumerate(zip(_spread(teaser_total, [1, 1, 1]), teaser_states)):
        p = FRAME_DIR / f"sT_teaser_{i}.png"
        _demo_card(shot, cap, bubble).save(p)
        frames.append((p, dur))

    # scene 0: hook — 정지 화면이 너무 길지 않도록 5단계로 잘게 쪼개 계속 바뀌게 한다.
    hook_total = durations["hook"]
    bg_manychat = OUT_DIR / "bg_manychat_pricing.png"
    bg_meta = OUT_DIR / "bg_meta_docs.png"
    hook_states = [
        (["인스타 팔로우·DM,"], "", "", bg_manychat),
        (["인스타 팔로우·DM,", "자동으로 될까?"], "", "음... 되려나?", bg_manychat),
        (
            ["인스타 팔로우·DM,", "자동으로 될까?"],
            "X  팔로우·좋아요·댓글 자동화는 안 됩니다",
            "역시 안 되는구나",
            bg_meta,
        ),
        (["인스타 팔로우·DM,", "자동으로 될까?"], "O  댓글→DM 자동발송은 공식 지원됩니다", "어? 이건 되네?", bg_meta),
        (["인스타 팔로우·DM,", "자동으로 될까?"], "댓글 하나로 DM 자동발송 — 툴 없이 직접 만들었습니다", "", None),
    ]
    for i, (dur, (lines, sub, bubble, bg)) in enumerate(zip(_spread(hook_total, [1, 1, 1.2, 1.2, 1.3]), hook_states)):
        p = FRAME_DIR / f"s0_hook_{i}.png"
        _title_card(lines, sub, bubble, bg_photo=bg).save(p)
        frames.append((p, dur))
    hook_frame_count = len(frames)

    # scene 1: architecture — 정지 카드가 아니라 진짜 애니메이션(Manim)으로 별도 렌더링됨.
    # scripts/video/manim_diagram_scene.py 참조. hook_frame_count 뒤에 build_video()가 끼워넣는다.

    # scene 2: demo — 실제 캡처 2장, 각각 (이미지만) → (+캡션)으로 쪼갠다.
    demo_total = durations["demo"]
    shots = [
        (DEMO_DIR / "01_comment_posted.png", '① 댓글 게시 — "가격이 얼마에요?"', "저요 저요! 궁금해요~"),
        (DEMO_DIR / "02_dm_received.png", "② 1분 만에 자동 DM 도착", "어? 벌써 답장이 왔네?"),
    ]
    per_shot_total = demo_total / len(shots)
    for shot_path, cap, bubble in shots:
        p_a = FRAME_DIR / f"s2_{shot_path.stem}_a.png"
        _demo_card(shot_path, "", bubble).save(p_a)
        p_b = FRAME_DIR / f"s2_{shot_path.stem}_b.png"
        _demo_card(shot_path, cap, bubble).save(p_b)
        for dur, p in zip(_spread(per_shot_total, [0.8, 1.2]), [p_a, p_b]):
            frames.append((p, dur))

    # scene 3: cta — 4단계로 나눠 정지감을 줄인다.
    cta_total = durations["cta"]
    cta_bg = DEMO_DIR / "02_dm_received.png"
    cta_states = [
        ("직접 만들어보세요", ""),
        ("직접 만들어보세요", "구축 문의는 채널 링크로"),
        ("직접 만들어보세요", "구축 문의는 채널 링크로 · 세부 구현은 다음 영상에서"),
        ("직접 만들어보세요", "구축 문의는 채널 링크로 · 세부 구현은 다음 영상에서 · 구독하기"),
    ]
    for i, (dur, (line, sub)) in enumerate(zip(_spread(cta_total, [1, 1, 1, 1.2]), cta_states)):
        p = FRAME_DIR / f"s3_cta_{i}.png"
        _cta_card([line], sub, bg_photo=cta_bg).save(p)
        frames.append((p, dur))

    return frames, hook_frame_count


MELT_EXE = Path.home() / "AppData" / "Local" / "Programs" / "Shotcut" / "melt.exe"
MELT_PROFILE = "atsc_1080p_30"
_MELT_CACHE_DIR = FRAME_DIR / "_melt_cache"
_MELT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _melt_kenburns_render(path: Path, duration: float, zoom_in: bool, k: float = 0.12) -> Path:
    """MLT(melt.exe)의 affine 필터로 실제 Ken Burns 줌을 렌더링한다.

    NOTE(2026-09-11): ffmpeg zoompan은 이 환경에서 누적 zoom이 매 프레임 리셋되는
    버그로 전혀 줌이 진행되지 않음을 확인(실측). moviepy(파이썬 프레임 단위
    resize)는 실제로 줌이 되지만 ImageClip의 "고정 크기" 최적화 경로를 못 타서
    매 프레임 풀HD 리사이즈를 반복 — 240초 분량에 20분+ 소요로 비현실적.
    MLT(melt.exe, C++ 엔진, Shotcut 번들)의 affine 트랜지션은 같은 4초 분량을
    3.5초에 렌더링(실측) — 이후 Ken Burns 필요하면 항상 이걸 쓸 것, 위 두 가지
    재시도 금지.
    """
    fps = 30
    out_frames = max(1, round(duration * fps))
    out_path = _MELT_CACHE_DIR / f"{path.stem}_{'in' if zoom_in else 'out'}_{out_frames}.mp4"
    if out_path.exists():
        return out_path
    if zoom_in:
        rect = f"0=0%/0%:100%x100%;{out_frames - 1}=-{k * 100:.0f}%/-{k * 100:.0f}%:{100 + k * 100:.0f}%x{100 + k * 100:.0f}%"
    else:
        rect = f"0=-{k * 100:.0f}%/-{k * 100:.0f}%:{100 + k * 100:.0f}%x{100 + k * 100:.0f}%;{out_frames - 1}=0%/0%:100%x100%"
    cmd = [
        str(MELT_EXE),
        "-profile",
        MELT_PROFILE,
        str(path),
        "in=0",
        f"out={out_frames - 1}",
        "-attach",
        "affine",
        f"transition.rect={rect}",
        "transition.valign=middle",
        "transition.halign=middle",
        "-consumer",
        f"avformat:{out_path}",
        "width=1920",
        "height=1080",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"melt 렌더 실패: {proc.stderr[-2000:]}")
    return out_path


def build_video(
    frames: list[tuple[Path, float]],
    hook_frame_count: int,
    manim_path: Path,
    out_path: Path,
    fade: float = 0.4,
) -> Path:
    """hook(정지카드+Ken Burns) → architecture(Manim 실애니메이션) → demo/cta(정지카드+Ken Burns) 순으로 이어붙인다.

    NOTE(2026-09-11): moviepy의 concatenate_videoclips(method="compose")+write_videofile은
    소스가 이미 렌더링된 mp4여도 프레임 단위로 재합성하느라 5개 클립(41초)에만 2분+ 소요돼
    비현실적임을 실측 확인(120초 타임아웃 내 완료 못함). ffmpeg xfade(비디오 대 비디오)로
    직접 이어붙이면 스트림 레벨 처리라 훨씬 빠름 — 카드 조립은 항상 이 방식을 쓸 것.
    """
    hook_frames = frames[:hook_frame_count]
    rest_frames = frames[hook_frame_count:]

    def _card_paths(sub_frames: list[tuple[Path, float]], start_idx: int) -> list[tuple[Path, float]]:
        out = []
        for i, (p, d) in enumerate(sub_frames):
            mp4 = _melt_kenburns_render(p, d + fade, (start_idx + i) % 2 == 0)
            out.append((mp4, d + fade))
        return out

    # (클립경로, xfade용 클립 자체 길이) — melt 카드는 d+fade로 렌더됐고, manim은 자연 길이 그대로.
    clip_list = _card_paths(hook_frames, 0)
    manim_duration = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(manim_path)],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        ).stdout.strip()
    )
    clip_list.append((manim_path, manim_duration))
    clip_list += _card_paths(rest_frames, len(hook_frames) + 1)

    n = len(clip_list)
    inputs: list[str] = []
    for p, _ in clip_list:
        inputs += ["-i", str(p)]

    # xfade offset은 "겹치기 전 화면에 온전히 보이는 시간" 기준이라 fade만큼 뺀 길이를 누적한다.
    visible = [d - fade for _, d in clip_list]
    scale_filters = [f"[{i}:v]scale={W}:{H},fps=30,setsar=1[v{i}]" for i in range(n)]
    xfade_parts = []
    cur = "v0"
    offset = visible[0]
    for i in range(1, n):
        nxt = f"x{i}"
        xfade_parts.append(f"[{cur}][v{i}]xfade=transition=fade:duration={fade}:offset={offset:.2f}[{nxt}]")
        cur = nxt
        offset += visible[i]

    filter_complex = ";".join(scale_filters + xfade_parts)
    total = sum(visible) + fade  # 마지막 클립은 겹치지 않은 꼬리까지 포함

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-map",
        f"[{cur}]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-t",
        f"{total:.2f}",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg xfade 조립 실패: {proc.stderr[-3000:]}")
    return out_path


def concat_narration(out_path: Path) -> Path:
    """4개 나레이션 mp3를 하나로 이어붙인다(장면 순서대로)."""
    names = [
        "scene_04_teaser.mp3",
        "scene_00_hook.mp3",
        "scene_01_architecture.mp3",
        "scene_02_demo.mp3",
        "scene_03_cta.mp3",
    ]
    list_file = OUT_DIR / "narration_concat.txt"
    list_file.write_text("\n".join(f"file '{(NARRATION_DIR / n).as_posix()}'" for n in names), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
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
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"mux 실패: {proc.stderr[-2000:]}")
    return out_path


MANIM_ARCHITECTURE_MP4 = ROOT / "media" / "videos" / "manim_diagram_scene" / "1080p30" / "DiagramScene_trimmed.mp4"


def main() -> None:
    frames, hook_frame_count = render_frames()
    print(f"프레임 {len(frames)}개 생성 완료 (hook {hook_frame_count}개 + demo/cta {len(frames) - hook_frame_count}개)")
    if not MANIM_ARCHITECTURE_MP4.exists():
        raise FileNotFoundError(
            f"Manim 아키텍처 애니메이션이 없습니다: {MANIM_ARCHITECTURE_MP4}\n"
            "먼저 렌더링하세요: python -m manim -qh --fps 30 -r 1920,1080 "
            "scripts/video/manim_diagram_scene.py DiagramScene "
            "(VS Build Tools 설치된 PowerShell 개발자 셸에서 실행)"
        )

    silent = OUT_DIR / "silent.mp4"
    build_video(frames, hook_frame_count, MANIM_ARCHITECTURE_MP4, silent)
    print(f"무음 비디오 조립 완료: {silent}")

    narration = OUT_DIR / "narration_full.mp3"
    concat_narration(narration)
    print(f"나레이션 병합 완료: {narration}")

    final = OUT_DIR / "final.mp4"
    mux(silent, narration, final)
    print(f"최종 영상 완성: {final}")


if __name__ == "__main__":
    main()
