"""승인형 실행 게이트 (B안 4단계).

``local_agent`` 가 fetch 이후 ``execute_task`` 전에 task 를 통과시킬지
판단한다. 검사 항목:

1. action 이 ``action_registry`` + ``policy.ALLOWED_ACTIONS`` 에 등록되어
   있는가.
2. 입력 파일(``file_path``) 이 허용 경로(``AGENT_WORK_DIR``) 안에 존재하는가.
3. 쓰기 작업이면 ``save_as`` 가 필수이며 허용 출력 경로
   (``AGENT_OUTPUT_DIR``) 안이고 원본 파일을 overwrite 하지 않아야 한다.
4. risk_level 이 ``medium`` 이상이면 ``approval_token`` 이 제공되어야
   한다 (본 단계 mock 서버 기준 — 값이 존재하면 승인으로 간주).
5. risk_level 이 ``high`` / ``critical`` 이면 이번 단계에서는 전부 차단.

모든 거부는 표준 err_code 문자열로 환원되어 ``local_agent`` 가 그대로
``report_result`` 로 전송한다. 이 모듈은 ``agent.errors`` /
``agent.file_policy`` 를 재사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import action_registry, errors as _err, file_policy, policy as _policy

APPROVAL_REQUIRED = "approval_required"
SAVE_AS_REQUIRED = "save_as_required"


@dataclass(frozen=True)
class Decision:
    allowed: bool
    error: Optional[str]
    category: str
    risk_level: str
    approved: bool
    approved_by: Optional[str]


def _meta_for(action: Optional[str]):
    if not isinstance(action, str) or not action:
        return None
    return action_registry.get_meta(action)


def _deny(
    err: str, *, category: str = "unknown", risk_level: str = "unknown",
) -> Decision:
    return Decision(
        allowed=False, error=err,
        category=category, risk_level=risk_level,
        approved=False, approved_by=None,
    )


def evaluate(task) -> Decision:
    """task dict 를 검사해 Decision 반환. crash 하지 않는다."""
    if not isinstance(task, dict):
        return _deny(_err.ACTION_NOT_ALLOWED)

    action = task.get("action")
    meta = _meta_for(action)
    if meta is None:
        return _deny(_err.ACTION_NOT_ALLOWED)
    if not _policy.is_allowed_action(action):
        return _deny(
            _err.ACTION_NOT_ALLOWED,
            category=meta.category, risk_level=meta.risk_level,
        )

    cat = meta.category
    risk = meta.risk_level

    # 입력 경로: 파일 기반 action 은 file_path 가 AGENT_WORK_DIR 하위여야 한다.
    # meta.requires_file_path=False 인 헬스체크류 액션(cad.health 등)은 건너뛴다.
    file_path_raw = task.get("file_path")
    src_resolved: Optional[Path] = None
    if getattr(meta, "requires_file_path", True):
        if isinstance(file_path_raw, str) and file_path_raw:
            src_resolved, path_err = file_policy.resolve_input_path(file_path_raw)
            if path_err:
                return _deny(path_err, category=cat, risk_level=risk)
        else:
            return _deny(_err.FILE_PATH_REQUIRED, category=cat, risk_level=risk)

    # 출력 경로: 쓰기 작업은 save_as 필수. 읽기 작업에 save_as 가 들어오면 검증만.
    # meta.requires_save_as=False 인 CAD API write 등 "서버 리소스 조작" 액션은
    # 로컬 출력이 없으므로 save_as 강제 검사 및 출력 경로 검증을 모두 건너뛴다.
    save_as_raw = task.get("save_as")
    needs_save_as = (
        meta.read_only is False
        and getattr(meta, "requires_save_as", True)
    )
    if needs_save_as:
        if not isinstance(save_as_raw, str) or not save_as_raw:
            return _deny(SAVE_AS_REQUIRED, category=cat, risk_level=risk)
    if (
        getattr(meta, "requires_save_as", True)
        and isinstance(save_as_raw, str) and save_as_raw
    ):
        _, out_err = file_policy.resolve_output_path(
            save_as_raw, source_path=src_resolved,
        )
        if out_err:
            return _deny(out_err, category=cat, risk_level=risk)

    # 승인 게이트
    approval_token = task.get("approval_token")
    approved_by = task.get("approved_by")
    has_token = bool(
        isinstance(approval_token, str) and approval_token.strip()
    )
    approved_by_clean = (
        approved_by.strip() if isinstance(approved_by, str) and approved_by.strip()
        else None
    )

    if risk == action_registry.RISK_LOW:
        approved = True
    elif risk == action_registry.RISK_MEDIUM:
        if not has_token:
            return _deny(APPROVAL_REQUIRED, category=cat, risk_level=risk)
        approved = True
    else:
        # HIGH / CRITICAL — 이번 단계에서는 전부 차단.
        return _deny(APPROVAL_REQUIRED, category=cat, risk_level=risk)

    return Decision(
        allowed=True, error=None,
        category=cat, risk_level=risk,
        approved=approved, approved_by=approved_by_clean,
    )


__all__ = [
    "Decision",
    "evaluate",
    "APPROVAL_REQUIRED",
    "SAVE_AS_REQUIRED",
]
