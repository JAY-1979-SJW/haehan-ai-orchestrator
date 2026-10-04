"""정부점검 대비 AI 자체점검 20편 — build_ep_batch_content.py와 동일 구조,
'상시 AI 반영' 주제로 입력/출력 경로만 분리."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
POSTS_PATH = ROOT / "data" / "marketing" / "ep_batch_posts_gov2.json"
CHART_DIR = ROOT / "data" / "blog_uploads"
CHART_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

DISCLAIMER = (
    "\n\n※ 이 글은 일반적인 건설현장 노무·안전·공무 실무에서 반복되는 확인 포인트를 정리한 것입니다. "
    "세부 기준·수치는 발주기관·공고 시기·현장 조건에 따라 달라질 수 있고, 그래프의 소요시간은 "
    "예시 비교이지 공식 통계가 아닙니다. 특정 행위의 적법·위법 여부에 대한 법률·노무·세무 전문판단을 "
    "대신하지 않으며, 실제 적용 전에는 반드시 관련 부서·관할 기관·전문가 확인을 거치시기 바랍니다."
)
CTA = "\n\n정부점검 대비 AI 자체점검 1시간 무상 방문교육 문의: 실무형 AI 교육 010-7387-6635 | haehan-ai.kr"


def make_chart(idx: int, topic_short: str) -> str:
    fig, ax = plt.subplots(figsize=(6, 3.6), dpi=150)
    stages = ["자료\n찾기", "항목\n대조", "1차\n정리", "최종\n확인"]
    before = [25, 20, 30, 15]
    after = [6, 5, 8, 15]
    x = range(len(stages))
    width = 0.35
    ax.bar([i - width / 2 for i in x], before, width, label="AI 활용 전(예시)", color="#9aa5b1")
    ax.bar([i + width / 2 for i in x], after, width, label="AI 활용 후(예시)", color="#16324f")
    ax.set_xticks(list(x))
    ax.set_xticklabels(stages)
    ax.set_ylabel("소요시간(분, 예시)")
    ax.set_title(f"{topic_short} 단계별 소요시간 비교(예시)", fontsize=11)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fname = f"chart_gov2_{idx:02d}.png"
    fig.savefig(CHART_DIR / fname)
    plt.close(fig)
    return fname


def _body_part_intro(parts, item):
    parts.append(item["hook"])
    parts.append("")
    parts.append(
        "2026년 정부의 현장 점검·감독 역량은 실제로 확대되고 있습니다. 문제는 점검을 받고 나서 "
        "준비하면 이미 늦다는 것입니다. 오늘은 이 주제를 실무 기준으로 정리하고, 같은 확인을 "
        "AI로 상시(주기적으로 반복해서) 어떻게 더 빠르고 일관되게 할 수 있는지까지 함께 다뤄보겠습니다. "
        "핵심은 '한 번 점검하고 끝'이 아니라, 사람이 매번 서류를 뒤지는 대신 AI가 1차로 찾고 정리한 뒤 "
        "사람이 최종 확인하는 구조를 상시 루틴으로 만드는 것입니다."
    )
    parts.append("")
    parts.append("■ 실무자들이 자주 하는 질문")
    parts.append("")
    parts.append(f'"{item["q"]}"')
    parts.append("")
    parts.append("■ 기본 실무 정리")
    parts.append("")


def _body_part_compare(parts, item):
    parts.append(item["a"])
    parts.append(
        "\n이 확인을 한 번만 하고 끝내면 다음 달, 다음 현장에서 같은 문제가 반복됩니다. "
        "여러 현장을 동시에 관리하는 담당자라면 이 반복 확인이 가장 시간을 많이 잡아먹는 "
        "업무이기도 합니다. 이 반복 확인 작업이야말로 AI를 상시로 붙였을 때 가장 효과가 큰 영역입니다."
    )
    parts.append("")
    parts.append("■ AI 활용 전 / 후 — 무엇이 달라지는가")
    parts.append("")
    parts.append("[표] AI 활용 전후 비교")
    parts.append("--------------------------------------------------")
    parts.append("구분        | AI 활용 전          | AI 활용 후")
    parts.append("--------------------------------------------------")
    parts.append("자료 확인   | 서류를 처음부터 직독 | 관련 항목만 1차로 찾아 요약")
    parts.append("자료 대조   | 여러 자료 수기 대조  | 자료 간 불일치를 표로 정리")
    parts.append("점검 주기   | 생각날 때 한 번 점검 | 매주/매달 같은 프롬프트로 상시 재점검")
    parts.append("최종 판단   | 사람이 전 과정 판단  | 사람은 결과 최종 확인만 수행")
    parts.append("--------------------------------------------------")
    parts.append("")
    parts.append(
        "표에서 보듯, AI가 대체하는 부분은 '찾고 대조하는' 반복 작업이고, '맞는지 최종 판단하는' "
        "부분과 '위법 여부를 결론 내리는' 부분은 여전히 사람과 전문가의 몫입니다. AI는 법적 결론을 "
        "내리지 않고, 확인이 필요한 항목을 찾아 정리해주는 역할까지만 합니다."
    )


def _body_part_prompt(parts, item):
    parts.append("")
    parts.append("■ AI로 확인하는 방법 — 실제 사용 프롬프트")
    parts.append("")
    parts.append("1단계: 자료 찾기·대조")
    parts.append("")
    parts.append(item["prompt"])
    parts.append("")
    parts.append("2단계: 결과 검증 (1단계 답변에 이어서 입력)")
    parts.append("")
    parts.append(
        "위 결과에서 근거로 제시한 내용을 원문 자료 그대로 다시 인용해서 보여줘. "
        "원문에 없는 내용이 섞여 있으면 그 부분을 명확히 표시해줘. "
        "확신이 없는 항목은 '확인 필요'로 남기고 추정하지 마."
    )
    parts.append("")
    parts.append(
        "1단계에서 AI가 자료를 찾아 정리하면, 2단계에서는 그 근거를 원문 그대로 다시 인용시켜서 "
        "AI가 만들어낸 내용은 아닌지 교차 검증합니다. 이 두 단계를 매주·매달 반복하는 것이 "
        "'상시 AI 자체점검'의 기본 구조입니다."
    )


def _body_part_chart_tips(parts):
    parts.append("")
    parts.append("■ 확인 단계별 소요시간 비교(예시)")
    parts.append("")
    parts.append("[[CHART]]")
    parts.append("")
    parts.append(
        "위 그래프는 자료 찾기 → 항목 대조 → 1차 정리 → 최종 확인 네 단계 중, AI가 앞의 세 단계를 "
        "보조했을 때의 예시 비교입니다. 마지막 '최종 확인' 단계는 AI를 쓰든 안 쓰든 사람이 반드시 "
        "직접 해야 하는 부분이라 시간이 줄지 않습니다. AI는 확인 작업 자체를 없애주는 게 아니라, "
        "확인하기 전 준비 과정을 줄여서 '상시로' 반복할 수 있게 해주는 도구입니다."
    )
    parts.append("")
    parts.append("■ 상시 점검으로 만드는 실무 팁")
    parts.append("")
    parts.append(
        "1. 이번 프롬프트를 템플릿으로 저장해두고, 매주/매달 같은 시점에 자료만 갈아끼워 재사용하세요.\n"
        "2. 원문 자료를 AI에 넣을 때는 최신 자료인지(작성일·발급일) 먼저 확인하세요.\n"
        "3. AI 답변은 '1차 확인용 초안'으로만 쓰고, 실제 조치 전에는 반드시 사람이 원문과 다시 대조하세요.\n"
        "4. 여러 현장을 관리한다면 현장별로 같은 프롬프트를 재사용해 점검 주기를 통일하세요."
    )


def _body_part_pitfalls(parts):
    parts.append("")
    parts.append("■ AI 자체점검 도입 시 놓치기 쉬운 주의사항")
    parts.append("")
    parts.append(
        "AI를 이런 확인 업무에 붙일 때 가장 많이 하는 실수는 'AI가 알아서 위법 여부까지 판단해 줄 "
        "것'이라는 기대입니다. 이 글에서 소개하는 방식은 AI가 자료를 찾고 대조해서 확인이 필요한 "
        "항목을 정리하는 것까지이고, 최종적으로 위법 여부를 판단하는 것은 노무사·변호사·세무사 등 "
        "전문가의 영역입니다. 또한 개인정보나 민감한 계약정보가 포함된 자료를 AI에 올릴 때는 사내 "
        "규정과 정보보호 원칙을 먼저 확인해야 합니다. 이 원칙만 지키면, AI는 반복적인 확인 업무를 "
        "상시로 돌릴 수 있게 해주는 도구가 됩니다."
    )
    parts.append("")
    parts.append(
        "이런 식으로 정부점검에 대비한 자체점검 포인트들을 AI로 상시 정리하는 방법을 계속 소개하고 "
        "있습니다. 비슷한 고민이 있는 항목이 있으시면 댓글로 남겨주세요."
    )


def build_body(item: dict, idx: int) -> tuple[str, str]:
    title = item["title"]
    topic_short = item.get("short") or title.split(",")[0]

    parts: list[Any] = []
    _body_part_intro(parts, item)
    _body_part_compare(parts, item)
    _body_part_prompt(parts, item)
    _body_part_chart_tips(parts)
    _body_part_pitfalls(parts)

    body = "\n".join(parts) + DISCLAIMER + CTA
    return body, topic_short


def main():
    items = json.loads(POSTS_PATH.read_text(encoding="utf-8"))
    out = []
    for i, item in enumerate(items, 1):
        body, topic_short = build_body(item, i)
        chart_file = make_chart(i, topic_short)
        out.append({"index": i, "title": item["title"], "body": body, "chart": chart_file})
        print(f"[{i}] {len(body)}자 본문 + {chart_file}")
    out_path = ROOT / "data" / "marketing" / "ep_batch_full_gov2.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out_path}")


if __name__ == "__main__":
    main()
