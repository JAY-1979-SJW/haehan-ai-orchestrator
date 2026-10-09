"""외부 플랫폼(Instagram Graph API 등)이 인증 없이 직접 다운로드해야 하는
미디어를 위한 공개 서빙 엔드포인트.

Instagram Graph API의 `/{ig-user-id}/media`(video_url/image_url)는 Meta 서버가
그 URL을 직접 GET으로 가져간다 — 우리 관리자 인증 쿠키/토큰을 가질 수 없으므로
`naver_blog_router.get_media()`(admin 인증 필수)는 쓸 수 없다.

보안 설계:
  - 업로드(POST)는 admin/owner 인증 필수 — 아무나 파일을 올릴 수 없다.
  - 파일명은 추측 불가능한 32자 hex 토큰(업로드 시 서버가 생성) — 사용자가
    지정한 원본 파일명을 그대로 쓰지 않는다.
  - 서빙(GET)은 인증 없음(의도적) — 토큰을 아는 사람만 접근 가능한 "unlisted"
    방식. 디렉터리 리스팅 없음, 토큰 패턴 미일치 시 404.
  - 운영 DB/개인정보와 무관한 홍보용 이미지·영상만 취급 — 민감정보 업로드 금지.
  - 임시 호스팅 용도다. 오래된 파일은 사람이 주기적으로 정리한다(자동 삭제
    없음 — 필요시 추가).
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ai_orchestrator.audit.audit_logger import log_event
from ai_orchestrator.paths.runtime import data_dir
from tools.gates.auth import require_role

public_media_router = APIRouter(prefix="/public-media", tags=["public-media"])

MEDIA_DIR = data_dir() / "public_media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

_ALLOWED_EXT = {".mp4", ".mov", ".jpg", ".jpeg", ".png"}
_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}(\.[a-z0-9]{2,4})$")


@public_media_router.post("/upload")
async def upload_public_media(
    file: UploadFile = File(...),
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """홍보용 이미지/영상을 업로드하고, 외부 플랫폼이 인증 없이 가져갈 수 있는
    공개 URL을 발급한다. 파일명은 서버가 생성한 추측 불가 토큰으로 대체한다.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 형식입니다: {ext or '(없음)'}")

    token_name = f"{secrets.token_hex(16)}{ext}"
    dest = MEDIA_DIR / token_name
    size = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_UPLOAD_BYTES:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="파일이 너무 큽니다 (최대 200MB)")
                out.write(chunk)
    finally:
        await file.close()

    log_event(
        event_type="PUBLIC_MEDIA_UPLOAD",
        task_id=token_name,
        actor=user.get("username", "unknown"),
        target=token_name,
        note=f"size={size} original={file.filename}",
    )

    return {
        "ok": True,
        "token": token_name,
        "size": size,
        "path": f"/api/v1/public-media/{token_name}",
        "public_url": f"https://haehan-ai.kr/orchestrator/api/v1/public-media/{token_name}",
    }


@public_media_router.api_route("/{token}", methods=["GET", "HEAD"])
def get_public_media(token: str) -> FileResponse:
    """인증 없이 서빙 — 외부 플랫폼(Meta 등)의 다운로드 요청용. 토큰 패턴이
    맞지 않거나 파일이 없으면 404 (경로주입·리스팅 차단).

    HEAD도 명시적으로 받는다 — Instagram Graph API의 비디오 수집기가 GET 전에
    HEAD로 존재/Content-Length를 먼저 확인하는데, HEAD가 405면 컨테이너
    처리 자체가 ERROR로 실패한다(2026-08-25 실측)."""
    if not _TOKEN_RE.match(token):
        raise HTTPException(status_code=404, detail="not found")
    path = MEDIA_DIR / token
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(path))
