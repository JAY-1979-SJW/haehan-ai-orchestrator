"""스마트스토어 이미지 업로드 — GPT 채팅 루프(/chat)는 삭제됨.

AI(자연어 명령→도구 호출)는 이제 Claude Code 가 MCP(`ai_orchestrator/server/mcp_server.py`,
`list_api_endpoints`/`call_api`)로 앱 API를 직접 호출해 수행한다.
이 파일은 채팅과 무관한 이미지 업로드 엔드포인트만 유지한다(상세설명 생성 등에서 사용).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from tools.gates.auth import require_role

from ...audit.audit_logger import log_event
from ._helpers import ROOT

_TEMP_IMAGE_DIR = ROOT / "data" / "temp_images"

router = APIRouter()


@router.post("/images/upload")
async def api_upload_images(
    files: list[UploadFile] = File(...),
    user: dict = Depends(require_role("admin", "owner")),
) -> dict:
    """웹 브라우저에서 첨부한 이미지를 서버 임시 디렉터리에 저장 후 경로 반환.

    반환된 경로는 상품 등록·상세설명 생성 등 다른 앱 기능(또는 Claude Code의 MCP 호출)에
    그대로 전달할 수 있다.
    """
    _TEMP_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for f in files:
        ext = Path(f.filename or "img").suffix or ".jpg"
        dest = _TEMP_IMAGE_DIR / f"{uuid.uuid4().hex}{ext}"
        dest.write_bytes(await f.read())
        saved.append(str(dest))
    log_event(
        "SMARTSTORE_IMAGE_UPLOAD",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"count={len(saved)}",
    )
    return {"ok": True, "paths": saved}
