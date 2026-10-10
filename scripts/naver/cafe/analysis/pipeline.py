"""카페 게시글 분류·가공 파이프라인 (API 호출 없음).

Stage 1: 키워드 규칙 분류
Stage 2: KoNLPy 형태소 분석
Stage 3: TF-IDF 유사도 군집화 (미분류 보완)
출력: data/cafe/classified_*.json, data/cafe/knowledge_base_*.json

사용:
    python -m scripts.naver.cafe.pipeline --input data/cafe/raw_articles_*.json
    python -m scripts.naver.cafe.pipeline  # data/cafe/ 최신 파일 자동 선택
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from scripts.common.app_paths import repo_root

ROOT = repo_root()


def _cafe_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("cafe")


_DATA_DIR = _cafe_dir()


def _load_raw(input_path: str | None = None) -> list[dict]:
    if input_path:
        return json.loads(Path(input_path).read_text(encoding="utf-8"))
    files = sorted(_DATA_DIR.glob("raw_articles_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"수집 파일 없음: {_DATA_DIR}")
    print(f"[pipeline] 입력 파일: {files[0].name}")
    return json.loads(files[0].read_text(encoding="utf-8"))


def _stage3_tfidf(articles: list[dict], classified: list[dict]) -> list[dict]:
    """Stage 3: TF-IDF 코사인 유사도로 미분류 보완."""
    try:
        import numpy as np
        from sklearn.feature_extraction.text import (  # type: ignore[import-not-found]  # 선택적 무거운 의존성(docs_registry.toml 등록)
            TfidfVectorizer,
        )
        from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - sklearn 미설치/로드 실패시 TF-IDF 보완단계만 생략하고 이미 분류된 결과를 그대로 반환 — 읽기전용 분석
        # sklearn 미설치/번들 누락(frozen exe의 OSError 포함) → TF-IDF 보완 생략
        return classified

    needs_review_idx = [i for i, c in enumerate(classified) if c.get("needs_review")]
    if not needs_review_idx:
        return classified

    high_conf = [
        (i, c) for i, c in enumerate(classified) if c["confidence"] in ("high", "medium") and not c.get("needs_review")
    ]
    if not high_conf:
        return classified

    # 텍스트 준비
    all_texts = [(articles[i].get("title", "") + " " + articles[i].get("body", ""))[:500] for i in range(len(articles))]
    try:
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), max_features=3000)
        tfidf = vec.fit_transform(all_texts)

        ref_indices = [i for i, _ in high_conf]
        ref_mat = tfidf[ref_indices]
        review_mat = tfidf[needs_review_idx]

        sims = cosine_similarity(review_mat, ref_mat)

        for j, review_i in enumerate(needs_review_idx):
            best_ref_j = int(np.argmax(sims[j]))
            best_score = float(sims[j][best_ref_j])
            if best_score >= 0.25:
                ref_cls = classified[ref_indices[best_ref_j]]
                classified[review_i].update(
                    {
                        "type": ref_cls["type"],
                        "category": ref_cls["category"],
                        "confidence": "medium",
                        "stage": 3,
                        "needs_review": False,
                        "tfidf_similarity": round(best_score, 3),
                    }
                )
    except Exception as e:  # noqa: BLE001 - sklearn 미설치/로드 실패시 TF-IDF 보완단계만 생략하고 이미 분류된 결과를 그대로 반환 — 읽기전용 분석
        print(f"[pipeline] Stage3 TF-IDF 실패 (무시): {e}")

    return classified


def build_knowledge_base(classified: list[dict]) -> dict:
    """분류 결과 → 지식베이스 구조체 생성."""
    faq: list[dict] = []
    info_pool: list[dict] = []
    notices: list[dict] = []
    resources: list[dict] = []

    for c in classified:
        base = {
            "article_id": c["article_id"],
            "title": c["title"],
            "author": c["author"],
            "date": c["date"],
            "category": c["category"],
            "href": c["href"],
            "view_count": c.get("view_count", "0"),
            "summary": c.get("summary", ""),
            "entities": c.get("entities", {}),
            "tags": c.get("tags", []),
            "top_nouns": c.get("top_nouns", []),
        }
        t = c.get("type", "기타")
        if t == "질문":
            faq.append({**base, "question": c["title"]})
        elif t == "정보공유":
            info_pool.append(base)
        elif t == "공지":
            notices.append(base)
        elif t == "자료공유":
            resources.append(base)

    # 카테고리별 인덱스
    cat_index: dict[str, list[str]] = defaultdict(list)
    for c in classified:
        cat_index[c.get("category", "기타")].append(c["article_id"])

    return {
        "generated_at": datetime.now().isoformat(),
        "total": len(classified),
        "faq": faq,
        "info_pool": info_pool,
        "notices": notices,
        "resources": resources,
        "category_index": dict(cat_index),
    }


def run_pipeline(input_path: str | None = None) -> dict:
    """전체 파이프라인 실행. 결과 dict 반환."""
    from .classifier import classify_all

    articles = _load_raw(input_path)
    print(f"[pipeline] 총 {len(articles)}건 분류 시작")

    # Stage 1 + 2
    classified = classify_all(articles)

    # 통계
    low_count = sum(1 for c in classified if c.get("needs_review"))
    print(f"[pipeline] Stage 1+2 완료 — 저신뢰: {low_count}건")

    # Stage 3
    classified = _stage3_tfidf(articles, classified)
    remaining_low = sum(1 for c in classified if c.get("needs_review"))
    print(f"[pipeline] Stage 3 완료 — 잔여 저신뢰: {remaining_low}건")

    # 저장
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    cls_path = _DATA_DIR / f"classified_{ts}.json"
    cls_path.write_text(json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[pipeline] 분류 저장: {cls_path.name}")

    kb = build_knowledge_base(classified)
    kb_path = _DATA_DIR / f"knowledge_base_{ts}.json"
    kb_path.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[pipeline] 지식베이스 저장: {kb_path.name}")

    return {
        "classified": classified,
        "knowledge_base": kb,
        "classified_path": str(cls_path),
        "kb_path": str(kb_path),
        "stats": {
            "total": len(classified),
            "low_confidence": remaining_low,
            "faq_count": len(kb["faq"]),
            "info_count": len(kb["info_pool"]),
            "notice_count": len(kb["notices"]),
            "resource_count": len(kb["resources"]),
        },
    }


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(ROOT))
    p = argparse.ArgumentParser()
    p.add_argument("--input", default=None)
    args = p.parse_args()
    result = run_pipeline(args.input)
    print(json.dumps(result["stats"], ensure_ascii=False, indent=2))
