"""잘되는 유튜브 영상(제목/썸네일/패턴) RAG 저장소 — 로컬 임베딩, API 비용 없음.

2026-09-12: "썸네일 잘되는 거 분석해서 저장하고 RAG" 요청으로 신설.
sentence-transformers(로컬 다국어 모델)로 임베딩 — OpenAI 임베딩 API 안 씀
(오늘 세션 결정: 유료 API 전면 중단, 로컬/구독 웹만 사용).

저장 형식: data/content_rag/videos.jsonl(원본 레코드) +
           data/content_rag/embeddings.npy(임베딩 행렬, 같은 순서)

사용:
    from scripts.content_rag.store import add_video, rebuild_index
    add_video(title="...", channel="...", views=1234567, category="...",
              pattern_notes="...", thumbnail_path="...")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
_DIR = ROOT / "data" / "content_rag"
_JSONL = _DIR / "videos.jsonl"
_EMB_NPY = _DIR / "embeddings.npy"

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def _embed_text(record: dict) -> str:
    """검색에 쓸 텍스트 — 제목+카테고리+패턴노트를 합친다."""
    parts = [record.get("title", ""), record.get("category", ""), record.get("pattern_notes", "")]
    return " | ".join(p for p in parts if p)


def load_records() -> list[dict[str, Any]]:
    if not _JSONL.exists():
        return []
    return [json.loads(line) for line in _JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]


def add_video(
    *,
    title: str,
    channel: str = "",
    views: int = 0,
    category: str = "",
    pattern_notes: str = "",
    thumbnail_path: str = "",
    url: str = "",
) -> None:
    """영상 1건을 저장소에 추가(중복 제목은 갱신). 임베딩은 add 시점에 바로 계산."""
    _DIR.mkdir(parents=True, exist_ok=True)
    records = load_records()
    records = [r for r in records if r.get("title") != title]  # 같은 제목 갱신
    records.append(
        {
            "title": title,
            "channel": channel,
            "views": views,
            "category": category,
            "pattern_notes": pattern_notes,
            "thumbnail_path": thumbnail_path,
            "url": url,
        }
    )
    _JSONL.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
    rebuild_index()


def rebuild_index() -> None:
    """전체 레코드를 다시 임베딩해서 embeddings.npy 갱신."""
    import numpy as np

    records = load_records()
    if not records:
        return
    model = _get_model()
    texts = [_embed_text(r) for r in records]
    embeddings = model.encode(texts, normalize_embeddings=True)
    np.save(_EMB_NPY, embeddings)


def import_from_json(path: str, *, category: str = "") -> int:
    """기존 조사 결과(JSON 배열, {title,channel,views,...} 형태)를 일괄 저장.

    path는 반드시 이 프로젝트 저장소(ROOT) 내부 파일이어야 한다(경로 이탈 방지).
    """
    resolved = Path(path).resolve()
    if ROOT not in resolved.parents and resolved != ROOT:
        raise ValueError(f"허용되지 않은 경로입니다(프로젝트 외부): {resolved}")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    data = json.loads(resolved.read_text(encoding="utf-8"))
    records = load_records()
    existing_titles = {r["title"] for r in records}
    added = 0
    for item in data:
        title = item.get("title", "").strip()
        if not title or title in existing_titles:
            continue
        records.append(
            {
                "title": title,
                "channel": item.get("channel", ""),
                "views": item.get("views", 0),
                "category": category,
                "pattern_notes": "",
                "thumbnail_path": "",
                "url": item.get("url", ""),
            }
        )
        existing_titles.add(title)
        added += 1
    _DIR.mkdir(parents=True, exist_ok=True)
    _JSONL.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
    rebuild_index()
    return added
