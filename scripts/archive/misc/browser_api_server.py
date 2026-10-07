"""브라우저 자동화 API 서버 — 포트 8100

실행:
  python scripts/archive/misc/browser_api_server.py
  uvicorn scripts.archive.misc.browser_api_server:app --host 0.0.0.0 --port 8100 --reload

API 문서:
  http://localhost:8100/docs
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from scripts.archive.misc.browser_api_router import router

app = FastAPI(
    title="Browser Automation API",
    description="네이버 / 구글 / 카카오 브라우저 자동화 API",
    version="1.0.0",
)

app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("scripts.archive.misc.browser_api_server:app", host="0.0.0.0", port=8100, reload=True)
