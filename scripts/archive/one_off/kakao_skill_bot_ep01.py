"""카카오톡 챗봇 자동상담 소개 영상 1편 — 나레이션 TTS 생성 + 길이 검증.

기획: [[video-production-pipeline-standard]] 표준 적용, [[kakao-channel-consultation-setup]] 참조.
제목: "카톡 문의, 퇴근하면 놓치고 계신가요? AI가 대신 상담합니다"
목표 길이: 4~5분. 통증포인트(놓치는 문의) → 해결책(자동상담) → 실제 함정/해결 → 실증 데모 → CTA.

실행:
  python scripts/archive/one_off/kakao_skill_bot_ep01.py           # 전체 생성 + 길이 검증
  python scripts/archive/one_off/kakao_skill_bot_ep01.py --scene 0 # 특정 장면만
  python scripts/archive/one_off/kakao_skill_bot_ep01.py --list    # 장면 목록 출력

출력: data/video/kakao_skill_bot_ep01/narration/scene_XX_*.mp3
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
    d = get_local_data_dir() / "video" / "kakao_skill_bot_ep01" / "narration"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ──────────────────────────────────────────────
# 나레이션 대본 v2 (6장면 — 콜드오픈 데모/통증포인트/개요/함정/관리화면/CTA)
# v1 피드백 반영(2026-09-11): 데모를 맨 앞으로, "0원" 표현 정확화, 함정 개수 일관성,
# 문장 사이 쉼표 위주로 재작성해 무음 구간 축소.
# ──────────────────────────────────────────────
SCENES: list[dict] = [
    {
        "id": 0,
        "name": "cold_open",
        "title": "장면 1 — 콜드오픈 데모 (목표 0:15)",
        "text": """
지금 실제로 카카오톡으로 문의를 하나 보내보겠습니다.
몇 초 지나지 않아 자동으로 답변이 도착하고, 동시에 사장님 텔레그램에도 알림이 도착합니다.
사람은 아무것도 하지 않았습니다. 이걸 AI를 이용해서 직접 만들었습니다.
        """.strip(),
    },
    {
        "id": 1,
        "name": "hook",
        "title": "장면 2 — 통증포인트 (목표 0:25)",
        "text": """
왜 이걸 만들었는지부터 말씀드릴게요.
사장님, 퇴근하고 나서 카톡으로 온 문의, 다음 날 아침에나 확인하신 적 있으세요? 고객은 그 사이에 이미 다른 곳에 연락했을 수도 있습니다.
상담 직원을 따로 두자니 비용이 부담되고, 카톡에 개인 번호를 그대로 적어두자니 그것도 꺼려지죠. 저도 똑같은 고민을 했습니다.
        """.strip(),
    },
    {
        "id": 2,
        "name": "solution_overview",
        "title": "장면 3 — 구조 개요 (목표 0:30)",
        "text": """
전체 구조는 이렇습니다. 카카오톡 채널의 오픈빌더라는 챗봇 도구에, 스킬이라는 걸 하나 연결합니다. 고객이 메시지를 보내면 카카오 서버가 우리 서버로 그 내용을 전달하고, 우리 서버는 문의 내용을 분류한 다음 답변을 다시 카카오로 돌려보냅니다.
카카오톡 채널 챗봇 자체는 무료입니다. 여기에 저는 기존에 쓰던 서버를 그대로 활용해서, 추가 인공지능 API 비용 없이 만들었습니다. 서버비까지 0원이라는 뜻은 아니고, 새로 드는 유료 인공지능 비용이 0원이라는 뜻입니다.
        """.strip(),
    },
    {
        "id": 3,
        "name": "pitfalls",
        "title": "장면 4 — 실전 함정 3가지 (목표 1:50~2:10)",
        "text": """
간단해 보이지만, 실제로 붙여보니 아무도 알려주지 않는 함정이 세 곳 있었습니다.
첫 번째, 저장과 배포는 다릅니다. 오픈빌더에서 블록을 고치고 저장 버튼을 눌러도, 그건 초안을 저장한 것일 뿐입니다. 실제 운영 중인 봇에 반영하려면, 배포라는 별도 버튼을 또 눌러야 합니다. 이걸 몰라서, 분명히 고쳤는데 왜 안 되지 하고 한참 헤맸습니다.
두 번째, 폴백 블록의 봇 응답 설정입니다. 스킬을 연결했다고 끝이 아닙니다. 봇 응답이라는 별도 항목이 기본값인 텍스트형으로 남아있으면, 우리 서버 응답은 무시되고 카카오의 기본 안내 문구, 그러니까 무엇을 원하는지 모르겠다는 문구가 계속 나갑니다. 이걸 스킬데이터라는 타입으로 바꿔줘야, 진짜 우리 답변이 고객에게 갑니다.
세 번째, 서버 주소 캐싱 문제입니다. 저희는 서버를 새로 배포할 때마다 내부 주소가 바뀌는데, 프록시 서버가 예전 주소를 그대로 캐싱하고 있어서 고객이 보낸 메시지가 아예 서버에 도착조차 못 하는 경우가 있었습니다. 이건 프록시 설정에서 주소를 매번 다시 확인하도록 고쳐서 해결했습니다.
그리고 하나 더, 챗봇이 자동으로 답장을 하면 정작 사장님 폰에는 새 문의가 왔다는 알림이 오지 않는다는 것도 알게 됐습니다. 챗봇이 이미 처리했다고 판단하기 때문인데요, 그래서 별도로 텔레그램 알림을 추가로 붙여서 문의가 올 때마다 사장님이 놓치지 않도록 만들었습니다.
        """.strip(),
    },
    {
        "id": 4,
        "name": "admin_view",
        "title": "장면 5 — 관리화면 (목표 0:20)",
        "text": """
문의가 들어오면 카테고리별로 자동 분류되어서 저희 관리 화면에 정리되어 쌓입니다. 여기까지는 정해진 규칙대로 답하는, 규칙 기반 자동상담입니다.
        """.strip(),
    },
    {
        "id": 5,
        "name": "cta",
        "title": "장면 6 — 마무리 CTA (목표 0:30)",
        "text": """
오늘은 카카오톡 채널에 24시간 자동상담을 붙이는 과정을, 실제로 겪었던 함정까지 그대로 보여드렸습니다.
저장과 배포는 다르다는 것, 봇 응답을 스킬데이터로 바꿔야 한다는 것, 서버 주소는 매번 재확인해야 한다는 것, 이 세 가지만 기억하셔도 시행착오를 크게 줄이실 수 있습니다.
직접 만들기 어렵고 구축이 필요하시다면, 채널 링크로 문의 주세요.
다음 편에서는 한 단계 더 갑니다. 정해진 답변이 아니라 고객 질문을 AI가 이해하고, 우리 회사 정보를 찾아 답하는 회사 전용 AI 상담사로 만들어보겠습니다. 놓치지 않으시려면 구독 부탁드립니다.
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
