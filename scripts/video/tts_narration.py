"""홍보 영상 나레이션 TTS 생성 — Microsoft Edge TTS (ko-KR-InJoonNeural).

실행:
  python scripts/video/tts_narration.py           # 전체 생성
  python scripts/video/tts_narration.py --scene 0 # 특정 장면만
  python scripts/video/tts_narration.py --list    # 장면 목록 출력

출력: data/video/narration/scene_XX_*.mp3
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ai_orchestrator.core.config import get_local_data_dir  # noqa: E402


def _output_dir():
    return get_local_data_dir() / "video" / "narration"


VOICE = "ko-KR-InJoonNeural"

# ──────────────────────────────────────────────
# 나레이션 대본 (6개 장면)
# ──────────────────────────────────────────────
SCENES: list[dict] = [
    {
        "id": 0,
        "name": "intro",
        "title": "인트로 — 해한 AI 오케스트레이터 소개",
        "text": """
반복되는 업무, 이제 AI가 대신합니다.

해한 AI 오케스트레이터는 스마트스토어 주문 관리부터
건설 현장 단말기 모니터링, 네이버 카페·블로그 콘텐츠 수집,
정부 지원사업 탐색까지—

사람이 하던 모든 반복 작업을 자동으로 처리합니다.

지금부터 네 가지 핵심 기능을 소개합니다.
        """.strip(),
    },
    {
        "id": 1,
        "name": "smartstore",
        "title": "기능 1 — 스마트스토어 자동화",
        "text": """
첫 번째, 스마트스토어 자동화입니다.

매일 수십 건의 주문을 일일이 확인하고 처리하던 시간,
이제 AI가 대신합니다.

주문 목록 조회, 발주 현황 분석, 재고 알림까지
네이버 스마트스토어 관리 화면을 AI가 직접 탐색하며
실시간으로 데이터를 수집하고 보고합니다.

담당자는 AI가 정리한 요약 리포트만 확인하면 됩니다.
        """.strip(),
    },
    {
        "id": 2,
        "name": "eum",
        "title": "기능 2 — EUM 단말기 모니터링",
        "text": """
두 번째, 건설근로자공제회 EUM 단말기 모니터링입니다.

전국 22개 건설 현장에 설치된 임대 단말기,
통신 단절이나 미사용 현장을 매주 자동으로 점검합니다.

수동으로 사이트에 접속해 확인하던 작업을
AI가 자동으로 수행하고, 이상 징후 발생 시
즉시 담당자에게 알림을 전송합니다.

단말기 관리 업무의 90%가 자동화됩니다.
        """.strip(),
    },
    {
        "id": 3,
        "name": "naver_collection",
        "title": "기능 3 — 네이버 카페·블로그 수집",
        "text": """
세 번째, 네이버 카페와 블로그 콘텐츠 자동 수집입니다.

경쟁사 동향, 시장 트렌드, 고객 반응—
원하는 키워드로 네이버 전체를 자동으로 모니터링합니다.

수집된 게시물은 AI가 자동 분류하고
엑셀 리포트로 정리해 제공합니다.

마케팅 인사이트를 얻기 위한 수작업 조사,
이제 AI에게 맡기세요.
        """.strip(),
    },
    {
        "id": 4,
        "name": "grant_radar",
        "title": "기능 4 — 정부 지원사업 레이더",
        "text": """
네 번째, 정부 지원사업 레이더입니다.

중소기업을 위한 정부 지원사업은 수백 가지지만,
놓치기 쉽습니다.

AI가 매일 정부24, 중소벤처기업부,
각 지자체 공고를 자동으로 스캔하고
우리 기업에 맞는 지원사업만 필터링해 알려드립니다.

놓쳤던 기회, 이제 AI가 찾아드립니다.
        """.strip(),
    },
    {
        "id": 5,
        "name": "outro",
        "title": "아웃트로 — 도입 안내",
        "text": """
해한 AI 오케스트레이터,

스마트스토어 자동화, 현장 단말기 모니터링,
시장 조사 수집, 지원사업 탐색까지—

귀사의 반복 업무를 AI가 대신합니다.

도입 문의는 해한 주식회사로 연락 주세요.
감사합니다.
        """.strip(),
    },
]


async def generate_scene(scene: dict) -> Path:
    import edge_tts  # type: ignore[import-not-found]  # 선택적 의존성(docs_registry.toml 등록)

    output_dir = _output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"scene_{scene['id']:02d}_{scene['name']}.mp3"

    communicate = edge_tts.Communicate(text=scene["text"], voice=VOICE, rate="-5%")
    await communicate.save(str(out))
    size = out.stat().st_size
    print(f"  ✓ scene_{scene['id']:02d} {scene['name']:20s} → {out.name}  ({size // 1024}KB)")
    return out


async def main(scene_ids: list[int] | None = None) -> None:
    targets = [s for s in SCENES if scene_ids is None or s["id"] in scene_ids]
    print(f"[TTS] voice={VOICE}, 생성 장면={len(targets)}개\n")
    for s in targets:
        await generate_scene(s)
    print(f"\n[TTS] 완료 → {_output_dir()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", type=int, nargs="+", help="생성할 장면 ID (기본: 전체)")
    parser.add_argument("--list", action="store_true", help="장면 목록 출력")
    args = parser.parse_args()

    if args.list:
        for s in SCENES:
            print(f"  [{s['id']}] {s['name']:20s} — {s['title']}")
        sys.exit(0)

    asyncio.run(main(args.scene))
