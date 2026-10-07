"""인스타 DM 봇 소개 영상 1편 — 나레이션 TTS 생성 + 길이 검증.

기획: [[channel-youtube-worklog]] 메모리 참조 (2026-09-11 확정).
제목: "인스타 댓글 하나로 DM 자동발송, AI 에이전트로 직접 만들었습니다 (툴 없이)"
목표 길이: 4~5분. 코드/레포 비공개 — 아키텍처 개념만 설명.

실행:
  python scripts/archive/one_off/ig_dm_bot_ep01.py           # 전체 생성 + 길이 검증
  python scripts/archive/one_off/ig_dm_bot_ep01.py --scene 0 # 특정 장면만
  python scripts/archive/one_off/ig_dm_bot_ep01.py --list    # 장면 목록 출력

출력: data/video/ig_dm_bot_ep01/narration/scene_XX_*.mp3
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ai_orchestrator.core.config import get_local_data_dir  # noqa: E402

VOICE = "ko-KR-InJoonNeural"
TTS_RATE = "+15%"


def _output_dir() -> Path:
    d = get_local_data_dir() / "video" / "ig_dm_bot_ep01" / "narration"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ──────────────────────────────────────────────
# 나레이션 대본 (4장면 — 문제제기/아키텍처/데모/CTA)
# ──────────────────────────────────────────────
SCENES: list[dict] = [
    {
        "id": 4,
        "name": "teaser",
        "title": "장면 0 — 콜드오픈 데모 (목표 0:12, 맨 앞 배치)",
        "text": """
이 게시물에, 가격이 궁금하다는 댓글을 달아보겠습니다.

몇 초 지나지 않아, 다이렉트 메시지함에 자동으로 답장이 도착합니다.

저는 지금, 아무것도 하지 않았습니다.

이걸, AI 에이전트로 직접 만들었습니다.
        """.strip(),
    },
    {
        "id": 0,
        "name": "hook",
        "title": "장면 1 — 문제제기 (목표 0:30)",
        "text": """
인스타그램에서, 팔로우도 자동으로 하고 DM도 마음대로 보낼 수 있을까요?

결론부터 말씀드리면, 안 됩니다.

인스타그램 공식 API에는 팔로우 기능 자체가 없습니다.
다른 사람 게시물에 댓글을 달거나, 좋아요를 누르는 것도 불가능합니다.
시중에 나와 있는 자동화 툴들도 결국 이 벽 안에서만 동작합니다.

하지만 한 가지, 확실히 되는 게 있습니다.

내 게시물에 누군가 댓글을 달면, 그 사람에게 DM을 자동으로 보내는 것.
이건 공식적으로 지원됩니다.

오늘은 이 기능을, 툴 없이 직접 만든 과정을 보여드리겠습니다.
        """.strip(),
    },
    {
        "id": 1,
        "name": "architecture",
        "title": "장면 2 — 핵심 아키텍처 (목표 2:30~3:00)",
        "text": """
전체 구조는 네 단계입니다.

첫 번째, 웹훅입니다.
누군가 내 게시물에 댓글을 달면, 메타 서버가 그 사실을
우리 서버로 실시간으로 알려줍니다.
사람이 계속 화면을 지켜보고 있을 필요가 없습니다.
댓글이 달리는 순간, 서버가 자동으로 이벤트를 전달받습니다.

두 번째, 댓글 감지입니다.
들어온 댓글 중에서, 우리가 반응할 키워드가 있는지 확인합니다.
예를 들어 가격, 문의, 구매, 이런 단어가 포함되어 있으면
그 댓글을 처리 대상으로 분류합니다.
반대로 아무 의미 없는 댓글, 예를 들어 이모티콘만 있는 댓글은
그냥 지나칩니다.

세 번째, 규칙 매칭입니다.
어떤 키워드에는 어떤 답변을 보낼지, 미리 정해둔 규칙과 대조합니다.
계정마다, 게시물마다 서로 다른 규칙을 걸 수 있습니다.
예를 들어 가격을 물어보면 가격표를, 설치 문의면 설치 안내를
자동으로 골라서 보내는 식입니다.
규칙은 데이터베이스에 저장해두고, 필요할 때마다 추가하거나
수정할 수 있게 만들었습니다.

네 번째, 프라이빗 리플라이입니다.
매칭된 규칙에 맞는 메시지를, 댓글 작성자에게
다이렉트 메시지로 보냅니다.
공개 댓글이 아니라 개인 메시지함으로 들어가기 때문에,
가격이나 연락처 같은 정보도 부담 없이 전달할 수 있습니다.

이 네 단계를 자동으로 처리하는 프로그램을 만들면,
댓글이 달릴 때마다 사람이 직접 답장하지 않아도 됩니다.
새벽에 댓글이 달려도, 자고 있는 동안에도 자동으로 응답이 나갑니다.

물론 쉽지만은 않았습니다.
메타 앱을 만들 때 헷갈리는 설정이 많았고,
앱 시크릿이라는 값도 화면에 표시되는 위치에 따라
전혀 다른 값이라 시행착오를 여러 번 겪었습니다.
그리고 댓글에 대한 첫 자동 답장은, 댓글이 달린 지 칠 일 안에
한 번만 보낼 수 있고, 상대방이 그 메시지에 답장을 하면
그 이후부터는 스물네 시간 안에만 추가 메시지를 보낼 수 있다는
제약도 있습니다.
이런 함정들은 다음 영상에서 하나씩 자세히 다뤄보겠습니다.
        """.strip(),
    },
    {
        "id": 2,
        "name": "demo",
        "title": "장면 3 — 실동작 데모 (목표 1:00)",
        "text": """
실제로 어떻게 동작하는지 보여드리겠습니다.

이 게시물에, 가격이 궁금하다는 댓글을 달아보겠습니다.

댓글을 달고 몇 초 지나지 않아,
다이렉트 메시지함에 자동으로 답장이 도착합니다.

사람이 개입하지 않았습니다.
댓글이 달린 순간부터, 답장이 도착하기까지 전부 자동입니다.
        """.strip(),
    },
    {
        "id": 3,
        "name": "cta",
        "title": "장면 4 — 마무리 CTA (목표 0:30)",
        "text": """
오늘은 인스타그램 댓글 하나로 DM을 자동으로 보내는 프로그램을
직접 만든 원리를 보여드렸습니다.

코드를 그대로 드리지는 않지만, 오늘 보여드린 네 단계 구조대로 만들면
여러분도 직접 구현하실 수 있습니다.
웹훅으로 받고, 키워드로 감지하고, 규칙으로 매칭하고,
개인 메시지로 보낸다. 이 순서만 기억하시면 됩니다.

혹시 직접 만들기 어렵고 구축이 필요하시다면,
채널 링크로 문의 주세요.

세부 구현 과정은 다음 영상에서 다룰 예정이니,
놓치지 않으시려면 구독 부탁드립니다.
        """.strip(),
    },
]


def list_scenes() -> None:
    total_chars = 0
    for s in SCENES:
        n = len(s["text"].replace("\n", "").replace(" ", ""))
        total_chars += n
        print(f"[{s['id']}] {s['title']} — {n}자")
    print(f"총 글자수: {total_chars}자")


async def _gen_one(scene: dict) -> Path:
    import edge_tts  # type: ignore[import-not-found]  # 선택적 의존성(docs_registry.toml 등록)

    out = _output_dir() / f"scene_{scene['id']:02d}_{scene['name']}.mp3"
    communicate = edge_tts.Communicate(scene["text"], VOICE, rate=TTS_RATE)
    await communicate.save(str(out))
    return out


def _mp3_duration_sec(path: Path) -> float:
    import subprocess

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    return float(out.stdout.strip())


async def generate_all(only_scene: int | None = None) -> None:
    targets = [s for s in SCENES if only_scene is None or s["id"] == only_scene]
    total = 0.0
    durations: dict[str, float] = {}
    for s in targets:
        path = await _gen_one(s)
        dur = _mp3_duration_sec(path)
        durations[s["name"]] = dur
        total += dur
        print(f"[{s['id']}] {s['name']}: {dur:.1f}초 → {path}")
    if only_scene is None:
        import json

        (_output_dir().parent / "scene_durations.json").write_text(
            json.dumps(durations, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n총 나레이션 길이: {total:.1f}초 ({total / 60:.1f}분)")
        print("목표: 4~5분 (240~300초)")
        if total < 200:
            print("⚠ 목표보다 짧음 — 장면별 설명 보강 고려")
        elif total > 330:
            print("⚠ 목표보다 김 — 장면별 문장 축약 고려")
        else:
            print("✅ 목표 범위 내")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", type=int, default=None)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        list_scenes()
        return

    asyncio.run(generate_all(args.scene))


if __name__ == "__main__":
    main()
