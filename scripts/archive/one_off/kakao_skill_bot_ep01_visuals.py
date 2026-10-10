"""카카오톡 챗봇 자동상담 소개 영상 1편 v2 — 비주얼 카드 제작 + 최종 조립.

v1 피드백 반영: 콜드오픈 데모를 맨 앞으로, 함정 3개 카운트 일관성, 관리화면 장면 추가.
나레이션(TTS)은 scripts/archive/one_off/kakao_skill_bot_ep01.py 에서 생성됨.
[[video-production-pipeline-standard]] 표준 적용.

실행:
  python scripts/archive/one_off/kakao_skill_bot_ep01_visuals.py
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

OUT_DIR = get_local_data_dir() / "video" / "kakao_skill_bot_ep01"
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
KAKAO_GOLD = (196, 164, 108)
GREEN = (110, 180, 110)


def _title_card(lines: list[str], sub: str = "", bubble: str = "", bg_photo: Path | None = None) -> Image.Image:
    if bg_photo and bg_photo.exists():
        photo = Image.open(bg_photo).convert("RGB")
        img = _cover(photo, W, H, focus_y=0.3)
        overlay = Image.new("RGBA", (W, H), (10, 9, 8, 180))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    else:
        img = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(img, "RGBA")
    _gradient_band(img, int(H * 0.30), int(H * 0.70), from_alpha=0, to_alpha=45, color=(60, 55, 48))
    f_title = _font(FONT_BOLD, 80)
    f_sub = _font(FONT_REG, 36)
    total_h = len(lines) * 100 + (56 if sub else 0)
    y = (H - total_h) // 2
    for ln in lines:
        tw = draw.textlength(ln, font=f_title)
        draw.text(((W - tw) / 2, y), ln, font=f_title, fill=WHITE)
        y += 100
    if sub:
        y += 16
        for sln in _wrap(draw, sub, f_sub, W - 240):
            tw = draw.textlength(sln, font=f_sub)
            draw.text(((W - tw) / 2, y), sln, font=f_sub, fill=(200, 194, 185))
            y += 48
    if bubble:
        _speech_bubble(draw, bubble, center_x=W - 380, top_y=110, tail_x=W - 480, tail_y=300, fill=KAKAO_GOLD)
    return img


def _speech_bubble(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수/CLI 인자 보존)
    draw: ImageDraw.ImageDraw,
    text: str,
    center_x: int,
    top_y: int,
    tail_x: int,
    tail_y: int,
    font_size: int = 32,
    fill=WHITE,
    text_color=INK,
    max_width: int = 500,
) -> None:
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
    draw.polygon([(tail_base_x - 18, y1 - 2), (tail_base_x + 18, y1 - 2), (tail_x, tail_y)], fill=fill, outline=INK)
    draw.line([(tail_base_x - 18, y1 - 2), (tail_x, tail_y)], fill=INK, width=3)
    draw.line([(tail_base_x + 18, y1 - 2), (tail_x, tail_y)], fill=INK, width=3)
    ty = y0 + 20
    for ln in lines:
        tw = draw.textlength(ln, font=font)
        draw.text((center_x - tw / 2, ty), ln, font=font, fill=text_color)
        ty += line_h


def _demo_card(shot_path: Path, caption: str, bubble: str = "") -> Image.Image:
    img = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(img, "RGBA")
    shot = Image.open(shot_path).convert("RGB")
    inner = _letterbox(shot, W - 160, H - 220, bg=(40, 38, 35))
    img.paste(inner, (80, 60))
    f_cap = _font(FONT_BOLD, 42)
    tw = draw.textlength(caption, font=f_cap)
    draw.text(((W - tw) / 2, H - 110), caption, font=f_cap, fill=KAKAO_GOLD)
    if bubble:
        _speech_bubble(draw, bubble, center_x=W - 420, top_y=90, tail_x=W - 560, tail_y=280, fill=KAKAO_GOLD)
    return img


def _cta_card(lines: list[str], sub: str = "", bg_photo: Path | None = None) -> Image.Image:
    return _title_card(lines, sub, bg_photo=bg_photo)


def _spread(total: float, weights: list[float]) -> list[float]:
    s = sum(weights)
    return [total * w / s for w in weights]


def _make_telegram_mock() -> Image.Image:
    img = Image.new("RGB", (1400, 900), (23, 33, 43))
    draw = ImageDraw.Draw(img)
    f_head = _font(FONT_BOLD, 34)
    f_body = _font(FONT_REG, 28)
    draw.rounded_rectangle([0, 0, 1400, 90], fill=(36, 47, 61))
    draw.text((40, 25), "해한AI 알림봇", font=f_head, fill=WHITE)
    bubble = [60, 140, 1150, 340]
    draw.rounded_rectangle(bubble, radius=24, fill=(43, 55, 70))
    draw.text((90, 170), "[카카오톡 문의] 카테고리: support", font=f_body, fill=(140, 220, 140))
    draw.text((90, 220), "문의 감사합니다. 담당자가 확인 후", font=f_body, fill=WHITE)
    draw.text((90, 260), "빠르게 답변드리겠습니다.", font=f_body, fill=WHITE)
    return img


def _make_admin_mock() -> Image.Image:
    """실제 문의함 화면 대신, 개인정보 없는 안전한 목업으로 대체."""
    img = Image.new("RGB", (1600, 1000), (250, 250, 248))
    draw = ImageDraw.Draw(img)
    f_head = _font(FONT_BOLD, 36)
    f_body = _font(FONT_REG, 26)
    f_badge = _font(FONT_BOLD, 22)
    draw.rectangle([0, 0, 1600, 90], fill=(255, 255, 255))
    draw.text((40, 25), "문의함 — 카카오톡 채널", font=f_head, fill=INK)
    rows = [
        ("영업/견적", (255, 244, 214), "30평 매장 견적 문의드립니다"),
        ("입찰/조달", (222, 236, 255), "공공기관 납품 가능 여부 문의"),
        ("기술/개발", (226, 245, 226), "설치 후 연동 방법 문의"),
        ("일반", (240, 240, 240), "영업시간이 어떻게 되나요"),
    ]
    y = 130
    for badge, color, text in rows:
        draw.rounded_rectangle(
            [40, y, 1560, y + 160], radius=16, fill=(255, 255, 255), outline=(225, 225, 220), width=2
        )
        draw.rounded_rectangle([70, y + 30, 240, y + 80], radius=14, fill=color)
        bw = draw.textlength(badge, font=f_badge)
        draw.text((70 + (170 - bw) / 2, y + 42), badge, font=f_badge, fill=INK)
        draw.text((70, y + 100), text, font=f_body, fill=(60, 58, 54))
        y += 190
    return img


def render_frames() -> tuple[list[tuple[Path, float]], int, int]:
    """(프레임경로, 노출시간초) 리스트 + [pitfalls 삽입 시작 인덱스, pitfalls 삽입 종료 인덱스(=다음 정지카드 시작)].

    pitfalls 장면은 Manim 애니메이션으로 별도 렌더링돼 두 인덱스 사이에 build_video()가 끼워넣는다.
    """
    import json

    durations = json.loads((OUT_DIR / "scene_durations.json").read_text(encoding="utf-8"))
    frames: list[tuple[Path, float]] = []

    real_shot = DEMO_DIR / "01_skilldata_fallback.png"
    tg_mock = DEMO_DIR / "02_telegram_mock.png"
    admin_mock = DEMO_DIR / "03_admin_mock.png"
    _make_telegram_mock().save(tg_mock)
    _make_admin_mock().save(admin_mock)

    # ── scene 0: cold_open — 데모를 맨 앞에 (문의 → 자동응답 → 텔레그램 알림) ──
    co_total = durations["cold_open"]
    co_states = [
        (real_shot, "① 카카오톡 문의 → 자동응답 (스킬데이터)", ""),
        (tg_mock, "② 동시에 텔레그램 알림 도착", "사람은 아무것도 안 했어요"),
    ]
    per = co_total / len(co_states)
    for shot_path, cap, bubble in co_states:
        p = FRAME_DIR / f"s0_co_{shot_path.stem}.png"
        _demo_card(shot_path, cap, bubble).save(p)
        frames.append((p, per))

    # ── scene 1: hook — 통증포인트, 3단계 ──────────────────────────
    hook_total = durations["hook"]
    hook_states = [
        (["왜 만들었는지부터"], "", ""),
        (["카톡 문의, 퇴근하면", "놓치고 계신가요?"], "", "저도 그랬어요..."),
        (["카톡 문의, 퇴근하면", "놓치고 계신가요?"], "상담직원 비용 부담 · 개인번호 노출 부담", ""),
    ]
    for i, (dur, (lines, sub, bubble)) in enumerate(zip(_spread(hook_total, [0.8, 1.1, 1.1]), hook_states)):
        p = FRAME_DIR / f"s1_hook_{i}.png"
        _title_card(lines, sub, bubble, bg_photo=real_shot).save(p)
        frames.append((p, dur))

    # ── scene 2: solution_overview — 구조 개요, 2단계 (비용 문구 정확화) ──
    ov_total = durations["solution_overview"]
    ov_states = [
        (["카톡 → 오픈빌더", "→ 우리 서버 → 답변"], "", ""),
        (
            ["카톡 → 오픈빌더", "→ 우리 서버 → 답변"],
            "카카오 챗봇은 무료 · 추가 AI API 비용 0원",
            "서버비는 기존 서버 그대로 사용",
        ),
    ]
    for i, (dur, (lines, sub, bubble)) in enumerate(zip(_spread(ov_total, [1, 1.4]), ov_states)):
        p = FRAME_DIR / f"s2_ov_{i}.png"
        _title_card(lines, sub, bubble, bg_photo=real_shot).save(p)
        frames.append((p, dur))
    pitfalls_start_index = len(frames)

    # scene 3: pitfalls — Manim 애니메이션(manim_kakao_diagram_scene.py)으로 별도 렌더링, 여기서 삽입

    # ── scene 4: admin_view — 문의함 관리화면 목업 ──────────────────
    admin_total = durations["admin_view"]
    p = FRAME_DIR / "s4_admin.png"
    _demo_card(admin_mock, "카테고리 자동분류 → 관리화면에 정리", "여기까진 규칙 기반이에요").save(p)
    frames.append((p, admin_total))
    pitfalls_end_index = pitfalls_start_index  # Manim은 여기(관리화면 앞)에 삽입

    # ── scene 5: cta — 4단계 (함정 3개 일관되게 recap) ──────────────
    cta_total = durations["cta"]
    cta_states = [
        ("직접 만들어보세요", ""),
        ("직접 만들어보세요", "저장≠배포 · 봇응답=스킬데이터 · 서버주소 재확인"),
        ("직접 만들어보세요", "구축이 필요하면 채널 링크로 문의"),
        ("다음 편 — 진짜 AI 상담사로", "우리 회사 정보로 답하는 AI · 구독 부탁드립니다"),
    ]
    for i, (dur, (line, sub)) in enumerate(zip(_spread(cta_total, [0.8, 1, 1, 1.3]), cta_states)):
        p = FRAME_DIR / f"s5_cta_{i}.png"
        _cta_card([line], sub, bg_photo=real_shot).save(p)
        frames.append((p, dur))

    return frames, pitfalls_start_index, pitfalls_end_index


MELT_EXE = Path.home() / "AppData" / "Local" / "Programs" / "Shotcut" / "melt.exe"
MELT_PROFILE = "atsc_1080p_30"
_MELT_CACHE_DIR = FRAME_DIR / "_melt_cache"
_MELT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _melt_kenburns_render(path: Path, duration: float, zoom_in: bool, k: float = 0.12) -> Path:
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
    pitfalls_start: int,
    pitfalls_end: int,
    manim_path: Path,
    out_path: Path,
    fade: float = 0.4,
) -> Path:
    """pre(정지카드) → pitfalls(Manim) → post(정지카드) 순으로 이어붙인다."""
    pre_frames = frames[:pitfalls_start]
    post_frames = frames[pitfalls_end:]

    def _card_paths(sub_frames: list[tuple[Path, float]], start_idx: int) -> list[tuple[Path, float]]:
        out = []
        for i, (p, d) in enumerate(sub_frames):
            mp4 = _melt_kenburns_render(p, d + fade, (start_idx + i) % 2 == 0)
            out.append((mp4, d + fade))
        return out

    clip_list = _card_paths(pre_frames, 0)
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
    clip_list += _card_paths(post_frames, len(pre_frames) + 1)

    n = len(clip_list)
    inputs: list[str] = []
    for p, _ in clip_list:
        inputs += ["-i", str(p)]

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
    total = sum(visible) + fade

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
    names = [
        "scene_00_cold_open.mp3",
        "scene_01_hook.mp3",
        "scene_02_solution_overview.mp3",
        "scene_03_pitfalls.mp3",
        "scene_04_admin_view.mp3",
        "scene_05_cta.mp3",
    ]
    list_file = OUT_DIR / "narration_concat.txt"
    list_file.write_text("\n".join(f"file '{(NARRATION_DIR / n).as_posix()}'" for n in names), encoding="utf-8")
    concat_raw = OUT_DIR / "narration_concat_raw.mp3"
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(concat_raw)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"나레이션 병합 실패: {proc.stderr[-2000:]}")

    # 음량 정규화 — v1 피드백: 통합음량 -19.7 LUFS로 조용함 → -16 LUFS, TP -1.5dB 목표.
    cmd2 = [
        "ffmpeg",
        "-y",
        "-i",
        str(concat_raw),
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar",
        "44100",
        str(out_path),
    ]
    proc2 = subprocess.run(cmd2, capture_output=True, text=True, encoding="utf-8")
    if proc2.returncode != 0:
        raise RuntimeError(f"음량 정규화 실패: {proc2.stderr[-2000:]}")
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


MANIM_MP4 = ROOT / "media" / "videos" / "manim_kakao_diagram_scene" / "1080p30" / "KakaoPitfallsScene.mp4"


def main() -> None:
    frames, pf_start, pf_end = render_frames()
    print(f"프레임 {len(frames)}개 생성 완료 (pitfalls 삽입 위치: {pf_start})")
    if not MANIM_MP4.exists():
        raise FileNotFoundError(f"Manim 함정 애니메이션이 없습니다: {MANIM_MP4}")

    silent = OUT_DIR / "silent.mp4"
    build_video(frames, pf_start, pf_end, MANIM_MP4, silent)
    print(f"무음 비디오 조립 완료: {silent}")

    narration = OUT_DIR / "narration_full.mp3"
    concat_narration(narration)
    print(f"나레이션 병합+음량정규화 완료: {narration}")

    final = OUT_DIR / "final.mp4"
    mux(silent, narration, final)
    print(f"최종 영상 완성: {final}")


if __name__ == "__main__":
    main()
