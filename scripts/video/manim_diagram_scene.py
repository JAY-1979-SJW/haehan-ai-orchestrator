"""인스타 DM 봇 1편 — 아키텍처 장면을 실제 애니메이션으로 렌더링 (Manim).

정지 카드 스왑 대신, 박스가 순서대로 강조되고 화살표가 그려지는 진짜 애니메이션.
2·4단계에는 실제 데모 캡처를 인서트한다. 나레이션(scene_01_architecture.mp3,
137.664초)과 길이를 맞춰 self.wait()로 타이밍을 맞춘다.

렌더링(Windows, VS Build Tools 설치 후 PowerShell 개발자 셸에서):
  python -m manim -qh --fps 30 -r 1920,1080 scripts/video/manim_diagram_scene.py DiagramScene

출력: media/videos/manim_diagram_scene/1080p30/DiagramScene.mp4
"""

from __future__ import annotations

from pathlib import Path

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Arrow,
    Create,
    FadeIn,
    FadeOut,
    ImageMobject,
    RoundedRectangle,
    Scene,
    Text,
    VGroup,
    Write,
    config,
)

ROOT = Path(__file__).resolve().parents[2]
from ai_orchestrator.config import get_local_data_dir  # noqa: E402

DEMO_DIR = get_local_data_dir() / "video" / "ig_dm_bot_ep01" / "demo_frames"

INK = "#181614"
CREAM = "#F7F3EC"
GOLD = "#C4A46C"
WHITE = "#FFFFFF"
DONE = "#3C3832"

STEPS = [
    (1, "웹훅", "댓글이 달리면 메타 서버가 우리 서버로\n실시간 전달합니다.", None),
    (2, "댓글 감지", "가격, 문의 같은 반응 키워드가\n있는지 확인합니다.", DEMO_DIR / "01_comment_posted.png"),
    (3, "규칙 매칭", "계정·게시물별로 정해둔\n규칙과 대조합니다.", None),
    (4, "프라이빗 리플라이", "매칭된 메시지를 DM으로\n자동 발송합니다.", DEMO_DIR / "02_dm_received.png"),
]

# 나레이션(scene_01_architecture.mp3) 길이에 맞춘 단계별 배분(초). 텍스트 길이 비례.
TOTAL = 137.664
WEIGHTS = [0.8, 1.25, 0.8, 1.25]
_w_sum = sum(WEIGHTS)
STEP_DURATIONS = [TOTAL * w / _w_sum for w in WEIGHTS]

config.background_color = CREAM


class DiagramScene(Scene):
    def construct(self):
        self.camera.background_color = CREAM

        title = Text("핵심 구조 — 댓글이 DM이 되기까지", font="Malgun Gothic", font_size=32, color=INK)
        title.to_edge(UP, buff=0.5)

        boxes = VGroup()
        for no, label, _, _ in STEPS:
            box = RoundedRectangle(corner_radius=0.15, width=2.9, height=1.4, color=INK, stroke_width=3)
            box.set_fill(CREAM, opacity=1)
            txt = Text(f"{no}\n{label}", font="Malgun Gothic", font_size=22, color=INK, line_spacing=1.2)
            txt.move_to(box)
            boxes.add(VGroup(box, txt))
        boxes.arrange(RIGHT, buff=0.55)
        boxes.move_to(UP * 2.3)

        arrows = VGroup()
        for i in range(len(STEPS) - 1):
            a = Arrow(boxes[i].get_right(), boxes[i + 1].get_left(), buff=0.08, color=INK, stroke_width=4)
            arrows.add(a)

        self.play(FadeIn(title), run_time=0.6)
        self.play(*[FadeIn(b) for b in boxes], run_time=0.8)
        self.play(*[Create(a) for a in arrows], run_time=0.6)
        self.wait(0.3)

        prev_desc = None
        prev_inset = None
        for (no, label, desc, inset_path), dur in zip(STEPS, STEP_DURATIONS):
            box_rect = boxes[no - 1][0]
            anims = [box_rect.animate.set_fill(GOLD, opacity=1).set_stroke(GOLD)]
            if prev_desc is not None:
                anims.append(FadeOut(prev_desc))
            if prev_inset is not None:
                anims.append(FadeOut(prev_inset))
            self.play(*anims, run_time=0.5)

            desc_text = Text(desc, font="Malgun Gothic", font_size=28, color=INK, line_spacing=1.3)
            desc_text.next_to(boxes, DOWN, buff=1.0)
            if inset_path and Path(inset_path).exists():
                desc_text.to_edge(LEFT, buff=1.2)
                img = ImageMobject(str(inset_path))
                img.scale_to_fit_height(3.2)
                img.next_to(desc_text, RIGHT, buff=0.8)
                img.shift(DOWN * 0.1)
                self.play(Write(desc_text), run_time=1.0)
                self.play(FadeIn(img), run_time=0.6)
                held = dur - 0.5 - 1.0 - 0.6
                self.wait(max(0.2, held))
                prev_inset = img
            else:
                self.play(Write(desc_text), run_time=1.0)
                held = dur - 0.5 - 1.0
                self.wait(max(0.2, held))
                prev_inset = None
            prev_desc = desc_text

            self.play(box_rect.animate.set_fill(DONE, opacity=1).set_stroke(DONE), run_time=0.01)
            boxes[no - 1][1].set_color(WHITE)

        if prev_desc is not None:
            self.play(FadeOut(prev_desc), run_time=0.3)
        if prev_inset is not None:
            self.play(FadeOut(prev_inset), run_time=0.3)
