"""로컬 PC 탐색 결과를 FastAPI로 제공 (포트 8402, 로컬 전용).

엔드포인트:
  GET /inventory          — 전체 수집 (캐시 60초)
  GET /inventory/system   — 시스템 정보
  GET /inventory/apps     — 설치된 프로그램
  GET /inventory/processes— 실행 중인 프로세스
  GET /inventory/ports    — 열린 포트
  GET /inventory/services — Windows 서비스
  GET /inventory/startup  — 시작프로그램
  POST /inventory/refresh — 캐시 강제 갱신

실행:
  python tools/pc_inventory_server.py

보안: 127.0.0.1 바인딩 (로컬 전용), 외부 노출 없음.
"""

from __future__ import annotations

import time
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pc_inventory import (  # type: ignore[import-not-found]  # 직접실행 시 스크립트 자기 폴더가 sys.path[0] — 정적 분석 범위 밖
    SECTIONS,
    collect_all,
    save,
)

app = FastAPI(title="PC Inventory", version="1.0.0")

_cache: dict[str, Any] = {}
_cache_ts: float = 0.0
CACHE_TTL = 60  # 초


def _get_cache() -> dict[str, Any]:
    global _cache, _cache_ts
    if time.time() - _cache_ts > CACHE_TTL:
        _cache = collect_all()
        _cache_ts = time.time()
        save(_cache)
    return _cache


@app.get("/inventory")
def get_inventory() -> JSONResponse:
    return JSONResponse(_get_cache())


@app.get("/inventory/{section}")
def get_section(section: str) -> JSONResponse:
    if section not in SECTIONS:
        raise HTTPException(status_code=404, detail=f"unknown section: {section}")
    data = _get_cache()
    return JSONResponse(
        {
            "section": section,
            "collected_at": data.get("collected_at"),
            "data": data.get(section),
            "secret_values_output": False,
        }
    )


@app.post("/inventory/refresh")
def refresh() -> dict[str, Any]:
    global _cache_ts
    _cache_ts = 0.0
    data = _get_cache()
    return {"refreshed": True, "collected_at": data.get("collected_at")}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "pc-inventory"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8402, log_level="info")
