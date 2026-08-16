"""20편 배치 — AI 비중 60%+, A4 3장 분량(약 3500자+), 표+그래프 포함 본문 생성."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
POSTS_PATH = ROOT / "data" / "marketing" / "ep_batch_posts.json"
CHART_DIR = ROOT / "data" / "blog_uploads"
CHART_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

DISCLAIMER = (
    "\n\n※ 이 글은 건설공무 실무 커뮤니티에서 실제로 반복되는 질문을 바탕으로 정리했습니다. "
    "세부 기준·수치는 발주기관·공고 시기·현장 조건에 따라 달라질 수 있고, 그래프의 소요시간은 "
    "실무 사례를 참고한 예시 비교이지 공식 통계가 아닙니다. 실제 적용 전에는 반드시 관련 부서·관할 기관 확인을 거치시기 바랍니다."
)
CTA = "\n\n더 많은 AI 업무자동화 사례는 홈페이지(haehan-ai.kr)와 유튜브 채널(@해한ai)에서 확인하실 수 있습니다."


def make_chart(idx: int, topic_short: str) -> str:
    """'AI 활용 전/후 소요시간' 예시 막대그래프 생성 → 파일명 반환."""
    fig, ax = plt.subplots(figsize=(6, 3.6), dpi=150)
    stages = ["자료\n찾기", "항목\n대조", "1차\n정리", "최종\n확인"]
    before = [25, 20, 30, 15]
    after = [6, 5, 8, 15]
    x = range(len(stages))
    width = 0.35
    ax.bar([i - width / 2 for i in x], before, width, label="AI 활용 전(예시)", color="#9aa5b1")
    ax.bar([i + width / 2 for i in x], after, width, label="AI 활용 후(예시)", color="#2f6fed")
    ax.set_xticks(list(x))
    ax.set_xticklabels(stages)
    ax.set_ylabel("소요시간(분, 예시)")
    ax.set_title(f"{topic_short} 업무 단계별 소요시간 비교(예시)", fontsize=11)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fname = f"chart_{idx:02d}.png"
    fig.savefig(CHART_DIR / fname)
    plt.close(fig)
    return fname


def build_body(item: dict, idx: int) -> tuple[str, str]:
    title = item["title"]
    topic_short = item.get("short") or title.split(",")[0]

    parts = []
    parts.append(item["hook"])
    parts.append("")
    parts.append(
        "건설공무 실무자 커뮤니티에서 이 주제는 매번 비슷한 질문과 답변이 반복됩니다. "
        "오늘은 이 질문을 실무 기준으로 한 번 정리하고, 같은 판단을 AI로 어떻게 더 빠르고 "
        "일관되게 확인할 수 있는지까지 함께 다뤄보겠습니다. 사람이 서류를 뒤져가며 확인하던 "
        "작업을, AI가 1차로 찾고 정리한 뒤 사람이 최종 확인하는 구조로 바꾸면 같은 시간에 "
        "훨씬 많은 현장을 처리할 수 있습니다."
    )
    parts.append("")
    parts.append("■ 실무자들이 자주 하는 질문")
    parts.append("")
    parts.append(f'"{item["q"]}"')
    parts.append("")
    parts.append("■ 기본 실무 정리")
    parts.append("")
    parts.append(item["a"])
    parts.append(
        "\n실무에서는 이 판단을 문서 하나만 보고 끝내지 않고, 관련 고시·공고문·계약 특수조건을 "
        "함께 대조하는 경우가 많습니다. 특히 여러 현장을 동시에 관리하는 담당자라면 현장마다 "
        "적용 시점과 기준 문서가 달라서, 매번 처음부터 다시 확인하는 데 시간이 많이 듭니다. "
        "이 반복 확인 작업이야말로 AI가 가장 잘 도와줄 수 있는 영역입니다."
    )
    parts.append("")
    parts.append("■ AI 활용 전 / 후 — 무엇이 달라지는가")
    parts.append("")
    parts.append("[표] AI 활용 전후 비교")
    parts.append("--------------------------------------------------")
    parts.append("구분        | AI 활용 전          | AI 활용 후")
    parts.append("--------------------------------------------------")
    parts.append("자료 확인   | 문서를 처음부터 직독 | 관련 조항만 1차로 찾아 요약")
    parts.append("근거 대조   | 여러 문서 수기 대조  | 문서 간 차이점을 표로 정리")
    parts.append("현장 반복   | 현장마다 작업 반복   | 같은 프롬프트를 현장별 재사용")
    parts.append("최종 판단   | 사람이 전 과정 판단  | 사람은 결과 최종 확인만 수행")
    parts.append("--------------------------------------------------")
    parts.append("")
    parts.append(
        "표에서 보듯, AI가 대체하는 부분은 '찾고 정리하는' 반복 작업이고, '맞는지 최종 판단하는' "
        "부분은 여전히 사람의 몫입니다. 이 역할 분담이 명확해야 실수 없이 시간을 아낄 수 있습니다."
    )
    parts.append("")
    parts.append("■ AI로 확인하는 방법 — 실제 사용 프롬프트")
    parts.append("")
    parts.append("1단계: 자료 찾기")
    parts.append("")
    parts.append(item["prompt"])
    parts.append("")
    parts.append("2단계: 결과 검증 (1단계 답변에 이어서 입력)")
    parts.append("")
    parts.append(
        "위 결과에서 근거로 제시한 조항을 원문 그대로 다시 인용해서 보여줘. "
        "원문에 없는 내용이 섞여 있으면 그 부분을 명확히 표시해줘. "
        "확신이 없는 항목은 '확인 필요'로 남기고 추정하지 마."
    )
    parts.append("")
    parts.append(
        "1단계에서 AI가 관련 조항을 찾아 정리하면, 2단계에서는 그 근거를 원문 그대로 다시 "
        "인용시켜서 AI가 만들어낸 내용은 아닌지 교차 검증합니다. 이 두 단계를 거치면 AI 특유의 "
        "그럴듯한 오답(할루시네이션) 위험을 크게 줄일 수 있습니다."
    )
    parts.append("")
    parts.append("■ 업무 단계별 소요시간 비교(예시)")
    parts.append("")
    parts.append("[[CHART]]")
    parts.append("")
    parts.append(
        "위 그래프는 자료 찾기 → 항목 대조 → 1차 정리 → 최종 확인 네 단계 중, AI가 앞의 세 "
        "단계를 보조했을 때의 예시 비교입니다. 마지막 '최종 확인' 단계는 AI를 쓰든 안 쓰든 "
        "사람이 반드시 직접 해야 하는 부분이라 시간이 줄지 않습니다. 즉 AI는 확인 작업 자체를 "
        "없애주는 게 아니라, 확인하기 전 준비 과정을 줄여주는 도구라는 점이 핵심입니다."
    )
    parts.append("")
    parts.append("■ 실무 적용 팁")
    parts.append("")
    parts.append(
        "1. 문서를 통째로 AI에 넣을 때는 원문 페이지 수·조항 번호가 잘리지 않았는지 먼저 확인하세요.\n"
        "2. 같은 질문이라도 현장 조건(공사 종류, 규모, 계약 형태)을 프롬프트에 구체적으로 넣을수록 답변 정확도가 올라갑니다.\n"
        "3. AI 답변은 '초안'으로만 쓰고, 실제 서류 제출 전에는 반드시 사람이 원문과 다시 대조하세요.\n"
        "4. 반복되는 현장이라면 프롬프트를 템플릿으로 저장해두고 현장 정보만 바꿔서 재사용하면 효율이 더 올라갑니다."
    )
    parts.append("")
    parts.append("■ 실무자들이 자주 틀리는 포인트")
    parts.append("")
    parts.append(
        "이 주제로 상담을 받다 보면 반복적으로 나오는 착각이 몇 가지 있습니다. 첫째, "
        "'예전에 이렇게 처리했으니 이번에도 같은 방식이 맞겠지'라고 넘겨짚는 경우입니다. "
        "고시·공고문 기준은 시점에 따라 계속 바뀌기 때문에, 과거 사례를 그대로 재사용하면 "
        "오히려 최신 기준을 놓치는 원인이 됩니다. 둘째, 한 문서만 보고 판단을 끝내는 경우입니다. "
        "실제로는 계약 특수조건, 공고문, 관련 고시가 서로 다른 위치에서 조건을 정하고 있어서 "
        "한 문서만 확인하면 놓치는 조항이 생깁니다. 셋째, 담당자 개인의 기억에 의존해 처리하는 "
        "경우입니다. 사람이 여러 현장을 동시에 맡다 보면 세부 조건이 헷갈리기 쉬운데, 이 부분을 "
        "AI에게 '문서 원문 기준으로만 답하라'고 명시해서 위임하면 기억에 의존한 실수를 줄일 수 "
        "있습니다."
    )
    parts.append("")
    parts.append("■ AI 도입 시 놓치기 쉬운 주의사항")
    parts.append("")
    parts.append(
        "AI를 업무에 붙일 때 가장 많이 하는 실수는 'AI가 알아서 다 해줄 것'이라는 기대입니다. "
        "실제로는 AI가 원문에 없는 내용을 그럴듯하게 만들어내는 경우(할루시네이션)가 분명히 "
        "존재하기 때문에, 앞서 소개한 것처럼 1단계 조사 → 2단계 원문 재인용 검증의 두 단계 "
        "구조로 쓰는 것이 안전합니다. 또한 사내 규정상 외부 서비스에 올리면 안 되는 문서(개인정보, "
        "입찰 관련 민감정보 등)가 섞여 있지는 않은지 먼저 확인한 뒤 AI에 입력해야 합니다. 이런 "
        "기본 원칙만 지키면, AI는 반복적인 서류 확인 업무의 속도를 확실히 끌어올려주는 도구가 "
        "됩니다."
    )
    parts.append("")
    parts.append(
        "이런 식으로 건설공무 실무에서 반복되는 판단 포인트들을 AI로 정리하는 작업을 계속 "
        "테스트하고 있습니다. 비슷한 고민이 있는 항목이 있으시면 댓글로 남겨주세요."
    )

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
    out_path = ROOT / "data" / "marketing" / "ep_batch_full.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out_path}")


if __name__ == "__main__":
    main()
