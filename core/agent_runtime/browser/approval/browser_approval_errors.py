"""브라우저 승인 저장소·검증기가 함께 쓰는 예외(L1 공용 계약).

저장소(L7)가 검증기(L2)를 가져오지 않고도 같은 예외를 쓰도록 분리했다.
`browser_approval_verifier` 가 같은 이름으로 다시 내보내므로(재노출) 기존 `from .browser_approval_verifier import DuplicateApprovalError`
와 `except DuplicateApprovalError` 는 그대로 동작한다. (결함: 층간 위반 L7→L2 정리, 2026-10-01)
"""

from __future__ import annotations


class DuplicateApprovalError(ValueError):
    """Raised when create_approval() is called with an existing approval_id.

    Prevents silent overwrite of token_hash, status, or any record fields.
    Applies uniformly across in-memory, JSONL, and DB stores.
    """
