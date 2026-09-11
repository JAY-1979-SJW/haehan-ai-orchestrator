"""RAG 검색 — 새 제목/주제와 가장 비슷한 "잘된 영상" 사례를 자동으로 찾아온다.

사용:
    from scripts.content_rag.query import search
    hits = search("인스타 DM 자동화 소개 영상 제목 후보", top_k=5)
    for h in hits:
        print(h["views"], h["title"])
"""

from __future__ import annotations

from typing import Any

from scripts.content_rag.store import _EMB_NPY, _get_model, load_records


def search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    import numpy as np

    records = load_records()
    if not records or not _EMB_NPY.exists():
        return []
    embeddings = np.load(_EMB_NPY)
    if len(embeddings) != len(records):
        from scripts.content_rag.store import rebuild_index

        rebuild_index()
        embeddings = np.load(_EMB_NPY)

    model = _get_model()
    q_vec = model.encode([query], normalize_embeddings=True)[0]
    scores = embeddings @ q_vec  # 코사인 유사도(정규화됐으므로 내적으로 충분)

    ranked = sorted(zip(scores, records), key=lambda x: x[0], reverse=True)
    out = []
    for score, rec in ranked[:top_k]:
        out.append({**rec, "similarity": round(float(score), 3)})
    return out
