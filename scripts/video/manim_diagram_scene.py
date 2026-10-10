"""인스타 DM 봇 1편 — 아키텍처 장면을 실제 애니메이션으로 렌더링 (Manim).

정지 카드 스왑 대신, 박스가 순서대로 강조되고 화살표가 그려지는 진짜 애니메이션.
① 전체 흐름 개요(사용자→서버→DM) → ② 4단계 상세(단계별 불릿+실캡처 인서트) 순으로
강의처럼 구성한다. 나레이션(scene_01_architecture.mp3, 137.664초)과 길이를 맞춘다.

렌더링(Windows, VS Build Tools 설치 후 PowerShell 개발자 셸에서):
  python -m manim -qh --fps 30 -r 1920,1080 scripts/video/manim_diagram_scene.py DiagramScene

출력: media/videos/manim_diagram_scene/1080p30/DiagramScene.mp4
"""

from __future__ import annotations

from pathlib import Path

from manim import (  # type: ignore[import-not-found]  # 선택적 무거운 의존성(docs_registry.toml 등록), 필요시에만 설치
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
from ai_orchestrator.core.config import get_local_data_dir  # noqa: E402

DEMO_DIR = get_local_data_dir() / "video" / "ig_dm_bot_ep01" / "demo_frames"

INK = "#181614"
CREAM = "#F7F3EC"
GOLD = "#C4A46C"
WHITE = "#FFFFFF"
DONE = "#3C3832"

# (번호, 라벨, 설명 1줄, 불릿 3개, 실캡처 경로)
STEPS = [
    (
        1,
        "웹훅",
        "댓글이 달리면 메타 서버가 우리 서버로 실시간 전달합니다.",
        ["댓글이 달리는 즉시 이벤트 발생", "메타가 우리 서버 주소로 알림 전송", "사람이 화면을 지켜볼 필요 없음"],
        None,
    ),
    (
        2,
        "댓글 감지",
        "가격, 문의 같은 반응 키워드가 있는지 확인합니다.",
        ["가격·문의·구매 등 키워드 매칭", "이모티콘만 있는 댓글은 무시", "실제 화면 →"],
        DEMO_DIR / "01_comment_posted.png",
    ),
    (
        3,
        "규칙 매칭",
        "계정·게시물별로 정해둔 규칙과 대조합니다.",
        ["키워드별 답변을 미리 등록", "계정·게시물마다 다른 규칙 적용", "DB에 저장해 언제든 수정 가능"],
        None,
    ),
    (
        4,
        "프라이빗 리플라이",
        "매칭된 메시지를 DM으로 자동 발송합니다.",
        ["매칭된 메시지를 DM으로 발송", "개인 메시지라 가격·연락처도 OK", "실제 화면 →"],
        DEMO_DIR / "02_dm_received.png",
    ),
]

TOTAL = 145.848
OVERVIEW_DUR = 16.0
WEIGHTS = [0.9, 1.2, 0.9, 1.2]
_w_sum = sum(WEIGHTS)
STEP_DURATIONS = [(TOTAL - OVERVIEW_DUR) * w / _w_sum for w in WEIGHTS]

config.background_color = CREAM


def _build_step_boxes():
    title = Text("핵심 구조 — 댓글이 DM이 되기까지", font="Malgun Gothic", font_size=32, color=INK)
    title.to_edge(UP, buff=0.5)

    boxes = VGroup()
    for no, label, _, _, _ in STEPS:
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
    return title, boxes, arrows


class DiagramScene(Scene):
    def construct(self):
        self.camera.background_color = CREAM
        self._overview()
        self._steps()

    # ── ① 전체 흐름 개요 ────────────────────────────────────────────────
    def _overview(self):
        title = Text("전체 흐름 — 누가, 무엇을 주고받나", font="Malgun Gothic", font_size=36, color=INK)
        title.to_edge(UP, buff=0.7)

        def actor(label: str) -> VGroup:
            box = RoundedRectangle(corner_radius=0.18, width=3.6, height=1.5, color=INK, stroke_width=3)
            box.set_fill(CREAM, opacity=1)
            txt = Text(label, font="Malgun Gothic", font_size=26, color=INK, line_spacing=1.2)
            txt.move_to(box)
            return VGroup(box, txt)

        user = actor("인스타그램\n사용자")
        server = actor("우리 서버\n(AI 에이전트)")
        dm = actor("인스타그램\nDM")
        row = VGroup(user, server, dm).arrange(RIGHT, buff=2.3)
        row.scale_to_fit_width(11.5).move_to([0, 0.3, 0])

        a1 = Arrow(user.get_right(), server.get_left(), buff=0.12, color=INK, stroke_width=4)
        a1_label = Text("① 댓글 게시", font="Malgun Gothic", font_size=20, color=GOLD).next_to(a1, UP, buff=0.2)
        a2 = Arrow(server.get_right(), dm.get_left(), buff=0.12, color=INK, stroke_width=4)
        a2_label = Text("② DM 자동발송", font="Malgun Gothic", font_size=20, color=GOLD).next_to(a2, UP, buff=0.2)

        self.play(FadeIn(title), run_time=0.6)
        self.play(FadeIn(user), FadeIn(server), FadeIn(dm), run_time=0.8)
        self.play(Create(a1), Write(a1_label), run_time=0.8)
        self.wait(0.4)
        self.play(Create(a2), Write(a2_label), run_time=0.8)

        note = Text(
            "메타 공식 API로 지원되는 유일한 자동 반응 — 팔로우·좋아요·댓글은 불가",
            font="Malgun Gothic",
            font_size=24,
            color=INK,
        )
        note.next_to(row, DOWN, buff=1.2)
        self.play(FadeIn(note), run_time=0.6)
        self.wait(max(0.3, OVERVIEW_DUR - 0.6 - 0.8 - 0.4 - 0.8 - 0.6))

        self.play(
            FadeOut(title),
            FadeOut(row),
            FadeOut(a1),
            FadeOut(a1_label),
            FadeOut(a2),
            FadeOut(a2_label),
            FadeOut(note),
            run_time=0.5,
        )

    # ── ② 4단계 상세 ────────────────────────────────────────────────────
    def _steps(self):
        title, boxes, arrows = _build_step_boxes()

        self.play(FadeIn(title), run_time=0.5)
        self.play(*[FadeIn(b) for b in boxes], run_time=0.7)
        self.play(*[Create(a) for a in arrows], run_time=0.5)
        self.wait(0.2)

        prev_group: VGroup | None = None
        prev_inset = None
        for (no, label, desc, bullets, inset_path), dur in zip(STEPS, STEP_DURATIONS):
            box_rect = boxes[no - 1][0]
            anims = [box_rect.animate.set_fill(GOLD, opacity=1).set_stroke(GOLD)]
            if prev_group is not None:
                anims.append(FadeOut(prev_group))
            if prev_inset is not None:
                anims.append(FadeOut(prev_inset))
            self.play(*anims, run_time=0.4)

            desc_text = Text(desc, font="Malgun Gothic", font_size=30, color=INK, line_spacing=1.3)
            bullet_lines = VGroup(
                *[Text(f"·  {b}", font="Malgun Gothic", font_size=24, color="#46423C") for b in bullets]
            ).arrange(DOWN, aligned_edge=LEFT, buff=0.22)

            has_inset = inset_path and Path(inset_path).exists()
            if has_inset:
                block = VGroup(desc_text, bullet_lines).arrange(DOWN, aligned_edge=LEFT, buff=0.35)
                block.next_to(boxes, DOWN, buff=0.9).to_edge(LEFT, buff=1.1)
                img = ImageMobject(str(inset_path))
                img.scale_to_fit_height(3.3)
                img.next_to(block, RIGHT, buff=0.9)
            else:
                block = VGroup(desc_text, bullet_lines).arrange(DOWN, aligned_edge=LEFT, buff=0.35)
                block.next_to(boxes, DOWN, buff=0.9)
                img = None

            self.play(Write(desc_text), run_time=0.7)
            self.play(FadeIn(bullet_lines), run_time=0.6)
            reveal = 0.4 + 0.7 + 0.6
            if img is not None:
                self.play(FadeIn(img), run_time=0.5)
                reveal += 0.5
                prev_inset = img
            else:
                prev_inset = None

            self.wait(max(0.3, dur - reveal))
            prev_group = block

            self.play(box_rect.animate.set_fill(DONE, opacity=1).set_stroke(DONE), run_time=0.01)
            boxes[no - 1][1].set_color(WHITE)

        if prev_group is not None:
            self.play(FadeOut(prev_group), run_time=0.3)
        if prev_inset is not None:
            self.play(FadeOut(prev_inset), run_time=0.3)
