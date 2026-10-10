"""YouTube 업로드 라우트 — 플랜 생성 → 사용자 승인 → 실행."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ai_orchestrator.paths.runtime import data_dir, storage_dir
from scripts.youtube import uploader as _uploader
from tools.gates.auth import require_role

from ._helpers import audit

router = APIRouter()

_TOKEN_NAME = "youtube_oauth_authorized_user.json"  # noqa: S105 - 파일 이름이지 비밀 값이 아니다


def _default_token_file() -> str:
    """OAuth 토큰 기본 위치 — 예전 기본값은 cwd 상대 문자열이라 데스크톱(포터블은 실행마다 TEMP 에 풀림)에서는 번들 안을 가리켰다.
    storage_dir()/secrets(서버 볼륨·데스크톱 userData/storage 와 같은 위치)를 기본으로 하되, scripts.youtube.oauth 가 쓰는
    data_dir()/secrets 에 이미 토큰이 있으면 그쪽을 쓴다. 예전 위치의 파일은 paths.migrate/legacy_import 가 새 위치로 복사한다."""
    primary = storage_dir() / "secrets" / _TOKEN_NAME
    if primary.exists():
        return str(primary)
    alt = data_dir() / "secrets" / _TOKEN_NAME
    return str(alt if alt.exists() else primary)


_TOKEN_FILE = os.getenv("YOUTUBE_OAUTH_TOKEN_FILE") or _default_token_file()


class ExecuteRequest(BaseModel):
    plan_path: str
    confirm: str  # 사용자가 직접 입력한 승인 문구(틀리면 403)
    # 기본은 dry_run — 실제 업로드는 호출자가 dry_run=false 를 명시해야 한다(승인 문구가 있어도 기본으로 업로드되지 않는다).
    dry_run: bool = True


@router.post("/prepare")
async def prepare_upload(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    file: UploadFile = File(...),
    title: str = Form(""),
    description: str = Form(""),
    privacy: str = Form("private"),
    tags: str = Form(""),
    category_id: str = Form("22"),
    publish_at: str = Form(""),  # ISO 8601 예: 2026-06-01T09:00:00+09:00 (예약 게시)
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """영상 파일을 받아 업로드 플랜을 생성합니다. 실제 업로드는 실행하지 않습니다."""
    if not file.filename:
        raise HTTPException(400, "파일이 없습니다.")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in _uploader.VIDEO_EXTENSIONS:
        raise HTTPException(400, f"지원하지 않는 파일 형식: {suffix}")

    # 서버 임시 파일로 저장
    tmp_dir = Path(tempfile.mkdtemp(prefix="yt_upload_"))
    tmp_path = tmp_dir / file.filename
    try:
        with tmp_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    finally:
        file.file.close()

    plan, plan_path = _uploader.prepare_upload_plan(
        tmp_path,
        {
            "title": title or tmp_path.stem,
            "description": description,
            "privacy": privacy,
            "tags": tags,
            "category_id": category_id,
            "publish_at": publish_at,
            "token_file": _TOKEN_FILE,
        },
    )

    # audit() 는 metadata= 가 아니라 note=(문자열) 를 받음(2026-09-29 defect_index #38 —
    # 이 kwarg 불일치 때문에 업로드 플랜 생성이 실제로 성공해도 이 감사로그 호출에서
    # TypeError 로 요청 전체가 500 으로 끝나던 실사용 버그).
    audit("YOUTUBE_UPLOAD_PLAN_CREATED", user, status="ok", note=f"plan_path={plan_path}")
    return {"ok": True, "plan": plan, "plan_path": str(plan_path)}


@router.post("/execute")
def execute_upload(
    body: ExecuteRequest,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """승인된 업로드 플랜을 실행합니다."""
    if body.confirm != _uploader.APPROVAL_PHRASE:
        raise HTTPException(403, "승인 문구가 올바르지 않습니다.")

    result, result_path = _uploader.execute_upload_plan(
        body.plan_path,
        approved=True,
        confirm=body.confirm,
        dry_run=body.dry_run,
    )

    # audit() 는 metadata= 가 아니라 note=(문자열) 를 받음(2026-09-29 defect_index #38,
    # 위 PLAN_CREATED 와 동일 원인 — 실제 업로드가 성공해도 감사로그에서 TypeError).
    audit(
        "YOUTUBE_UPLOAD_EXECUTED",
        user,
        status=result.get("status", "unknown"),
        note=f"video_id={result.get('video_id', '')} dry_run={body.dry_run} result_path={result_path}",
    )
    return {"ok": result.get("status") in ("ok", "dry_run_ok"), "result": result}
