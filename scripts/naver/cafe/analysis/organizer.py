"""카페 게시글 자체 정리 — 군집화·중복제거·지식베이스 구조화.

API 호출 없음. TF-IDF + 코사인 유사도로 유사 질문 군집화.

사용:
    python -m scripts.naver.cafe.organizer
    python -m scripts.naver.cafe.organizer --input data/cafe/classified_*.json
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.app_paths import repo_root

ROOT = repo_root()
_DATA_DIR = data_dir() / "cafe"

# ── 카테고리 순서 (보고서용) ──────────────────────────────────────────
CAT_ORDER = [
    "노무",
    "계약·하도급",
    "공사관리",
    "세무·회계",
    "법규·인허가",
    "안전",
    "행정·서류",
    "장비·자재",
    "커뮤니티",
    "기타",
]


def _load_classified(input_path: str | None = None) -> list[dict]:
    if input_path:
        return json.loads(Path(input_path).read_text(encoding="utf-8"))
    files = sorted(_DATA_DIR.glob("classified_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"분류 파일 없음: {_DATA_DIR}")
    print(f"[organizer] 입력: {files[0].name}")
    return json.loads(files[0].read_text(encoding="utf-8"))


def _cluster_questions(questions: list[dict], sim_threshold: float = 0.35) -> list[dict]:
    """TF-IDF 코사인 유사도로 유사 질문 군집화.

    반환: 군집 list, 각 군집 = {
        representative: 가장 조회수 높은 대표 질문,
        members: 유사 질문 목록,
        size: 군집 크기,
        avg_views: 평균 조회수,
        total_views: 총 조회수,
    }
    """
    if not questions:
        return []

    try:
        from sklearn.feature_extraction.text import (  # type: ignore[import-not-found]  # 선택적 무거운 의존성(docs_registry.toml 등록)
            TfidfVectorizer,
        )
        from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - sklearn 미설치/로드 실패시 군집화 없이 원본 질의를 개별 항목으로 반환 — 읽기전용 텍스트 분석의 안전한 폴백
        # sklearn 미설치/번들 누락(frozen exe의 OSError 포함) → 군집화 없이 개별 반환
        return [
            {
                "representative": q,
                "members": [],
                "size": 1,
                "avg_views": int(q.get("view_count", 0) or 0),
                "total_views": int(q.get("view_count", 0) or 0),
            }
            for q in questions
        ]

    texts = [q.get("title", "") for q in questions]
    try:
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), max_features=5000)
        tfidf = vec.fit_transform(texts)
    except Exception:  # noqa: BLE001 - sklearn 미설치/로드 실패시 군집화 없이 원본 질의를 개별 항목으로 반환 — 읽기전용 텍스트 분석의 안전한 폴백
        return [
            {
                "representative": q,
                "members": [],
                "size": 1,
                "avg_views": int(q.get("view_count", 0) or 0),
                "total_views": int(q.get("view_count", 0) or 0),
            }
            for q in questions
        ]

    n = len(questions)
    assigned = [-1] * n
    cluster_id = 0

    # 조회수 내림차순으로 대표 선정
    order = sorted(range(n), key=lambda i: int(questions[i].get("view_count", 0) or 0), reverse=True)

    for i in order:
        if assigned[i] != -1:
            continue
        assigned[i] = cluster_id
        # i번과 유사한 미할당 문서 찾기
        sims = cosine_similarity(tfidf[i], tfidf).flatten()
        for j in range(n):
            if assigned[j] == -1 and sims[j] >= sim_threshold:
                assigned[j] = cluster_id
        cluster_id += 1

    # 군집별 집계
    clusters: dict[int, list[int]] = defaultdict(list)
    for idx, cid in enumerate(assigned):
        clusters[cid].append(idx)

    result = []
    for cid, indices in sorted(clusters.items()):
        members = [questions[i] for i in indices]
        # 대표 = 조회수 최고
        rep = max(members, key=lambda q: int(q.get("view_count", 0) or 0))
        non_rep = [m for m in members if m["article_id"] != rep["article_id"]]
        views = [int(m.get("view_count", 0) or 0) for m in members]
        result.append(
            {
                "representative": rep,
                "members": non_rep,
                "size": len(members),
                "avg_views": round(sum(views) / len(views), 1) if views else 0,
                "total_views": sum(views),
            }
        )

    # 총 조회수 내림차순 정렬
    result.sort(key=lambda c: c["total_views"], reverse=True)
    return result


def _extract_recurring_keywords(articles: list[dict], top_n: int = 30) -> list[dict]:
    """제목 한글 명사 2글자 이상 빈도 추출."""
    STOP = {
        "것",
        "수",
        "때",
        "곳",
        "중",
        "후",
        "전",
        "분",
        "점",
        "등",
        "및",
        "관련",
        "해당",
        "경우",
        "내용",
        "부분",
        "현재",
        "상태",
        "사항",
        "방법",
        "문제",
        "작업",
        "진행",
        "확인",
        "처리",
        "요청",
        "질문",
        "답변",
        "건설",
        "공무",
        "카페",
        "회원",
        "게시",
        "문의",
        "부탁",
        "안녕",
        "감사",
        "합니다",
        "드립니다",
        "입니다",
        "있나요",
        "인가요",
        "될까요",
        "할까요",
        "어떻게",
        "어디서",
    }
    cnt: Counter = Counter()
    for a in articles:
        words = re.findall(r"[가-힣]{2,}", a.get("title", ""))
        for w in words:
            if w not in STOP:
                cnt[w] += 1
    return [{"word": k, "count": v} for k, v in cnt.most_common(top_n)]


def _build_category_summary(cat: str, articles: list[dict]) -> dict:
    """카테고리 단위 요약 구조체."""
    questions = [a for a in articles if a.get("type") == "질문"]
    infos = [a for a in articles if a.get("type") == "정보공유"]
    notices = [a for a in articles if a.get("type") == "공지"]
    resources = [a for a in articles if a.get("type") == "자료공유"]

    all_views = [int(a.get("view_count", 0) or 0) for a in articles]
    q_views = [int(a.get("view_count", 0) or 0) for a in questions]

    top_questions = sorted(questions, key=lambda a: int(a.get("view_count", 0) or 0), reverse=True)[:10]
    top_infos = sorted(infos, key=lambda a: int(a.get("view_count", 0) or 0), reverse=True)[:5]

    keywords = _extract_recurring_keywords(articles, top_n=15)

    # 유사 질문 군집화
    clusters = _cluster_questions(questions[:500], sim_threshold=0.35)  # 최대 500건

    return {
        "category": cat,
        "total": len(articles),
        "question_count": len(questions),
        "info_count": len(infos),
        "notice_count": len(notices),
        "resource_count": len(resources),
        "total_views": sum(all_views),
        "avg_question_views": round(sum(q_views) / len(q_views), 1) if q_views else 0,
        "top_questions": [
            {
                "title": a["title"][:60],
                "views": a.get("view_count", "0"),
                "date": a.get("date", ""),
                "href": a.get("href", ""),
            }
            for a in top_questions
        ],
        "top_infos": [
            {"title": a["title"][:60], "views": a.get("view_count", "0"), "date": a.get("date", "")} for a in top_infos
        ],
        "keywords": keywords,
        "question_clusters": [
            {
                "topic": c["representative"]["title"][:50],
                "size": c["size"],
                "total_views": c["total_views"],
                "avg_views": c["avg_views"],
                "rep_href": c["representative"].get("href", ""),
                "similar": [m["title"][:45] for m in c["members"][:5]],
            }
            for c in clusters[:20]
        ],
    }


def _generate_text_report(summaries: list[dict], total: int) -> str:
    """전체 텍스트 보고서 생성."""
    sep = "=" * 65
    lines = [
        sep,
        "  건설공무 카페 — 회원 관심사·니즈 자체 정리 보고서",
        f"  분석 일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  총 게시글: {total:,}건",
        sep,
    ]

    for s in summaries:
        cat = s["category"]
        lines.append(f"\n{'─' * 65}")
        lines.append(
            f"▶ [{cat}]  총 {s['total']:,}건  |  질문 {s['question_count']:,}건  |  "
            f"총조회 {s['total_views']:,}  |  질문평균조회 {s['avg_question_views']}회"
        )
        lines.append(f"{'─' * 65}")

        if s["keywords"]:
            kw = "  ".join(f"{k['word']}({k['count']})" for k in s["keywords"][:12])
            lines.append(f"  🔑 핵심 키워드: {kw}")

        if s["top_questions"]:
            lines.append("\n  📌 조회수 상위 질문")
            for i, q in enumerate(s["top_questions"][:7], 1):
                lines.append(f"     {i}. [{q['views']:>5}회] {q['title']}")

        if s["top_infos"]:
            lines.append("\n  📖 정보공유 상위")
            for inf in s["top_infos"][:3]:
                lines.append(f"     · [{inf['views']:>5}회] {inf['title']}")

        if s["question_clusters"]:
            lines.append("\n  🔗 반복 질문 군집 (유사 질문 묶음)")
            for c in s["question_clusters"][:8]:
                lines.append(f"     [{c['size']}건 / 총{c['total_views']}조회] {c['topic']}")
                for sim in c["similar"][:3]:
                    lines.append(f"          └ {sim}")

    lines.append(f"\n{sep}")
    return "\n".join(lines)


def organize(input_path: str | None = None) -> dict:
    """전체 정리 실행. 카테고리별 지식베이스 + 텍스트 보고서 반환."""
    articles = _load_classified(input_path)
    print(f"[organizer] 총 {len(articles):,}건 정리 시작")

    # 카테고리별 분리
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        by_cat[a.get("category", "기타")].append(a)

    summaries = []
    for cat in CAT_ORDER:
        cat_articles = by_cat.get(cat, [])
        if not cat_articles:
            continue
        print(f"  [{cat}] {len(cat_articles):,}건 군집화 중...", end=" ", flush=True)
        s = _build_category_summary(cat, cat_articles)
        summaries.append(s)
        print(f"군집 {len(s['question_clusters'])}개 완료")

    report_text = _generate_text_report(summaries, len(articles))

    # 저장
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    kb_path = _DATA_DIR / f"organized_kb_{ts}.json"
    txt_path = _DATA_DIR / f"organized_report_{ts}.txt"

    kb_data = {"generated_at": datetime.now().isoformat(), "total": len(articles), "categories": summaries}
    kb_path.write_text(json.dumps(kb_data, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(report_text, encoding="utf-8")

    print("\n[organizer] 저장 완료:")
    print(f"  JSON: {kb_path.name}")
    print(f"  TXT : {txt_path.name}")
    return {"kb_path": str(kb_path), "txt_path": str(txt_path), "report_text": report_text, "summaries": summaries}


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(ROOT))
    p = argparse.ArgumentParser()
    p.add_argument("--input", default=None)
    args = p.parse_args()
    result = organize(args.input)
    print(result["report_text"])
