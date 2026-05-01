"""원본 저장 승인 정책."""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_change_hash(
    change_summary: dict,
) -> str:
    """변경 계획의 hash 생성 (일관성 검증용).

    Args:
        change_summary: {
            "total_changes": int,
            "cell_updates": int,
            "row_inserts": int,
            "column_inserts": int,
            "formula_writes": int,
        }

    Returns:
        변경 hash (SHA256 처음 16자)
    """
    try:
        content = str(sorted(change_summary.items()))
        hash_obj = hashlib.sha256(content.encode())
        return hash_obj.hexdigest()[:16]
    except Exception as e:  # noqa: BLE001
        logger.error("Hash generation failed: %s", type(e).__name__)
        return ""


def validate_approval_token(
    approval_token: str,
    expected_hash: Optional[str] = None,
    token_hash: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """승인 토큰 유효성 검증.

    Args:
        approval_token: 승인 토큰 (비어있지 않아야 함)
        expected_hash: 예상 변경 hash
        token_hash: 토큰에 포함된 hash (옵션)

    Returns:
        (유효 여부, 에러 메시지)
    """
    try:
        # 기본 검증: 토큰이 비어있지 않은지
        if not approval_token or not isinstance(approval_token, str):
            return False, "INVALID_APPROVAL_TOKEN"

        if not approval_token.strip():
            return False, "EMPTY_APPROVAL_TOKEN"

        # 선택 검증: hash 일치도 확인
        if expected_hash and token_hash:
            if expected_hash != token_hash:
                return False, "HASH_MISMATCH"

        return True, None
    except Exception as e:  # noqa: BLE001
        logger.error("Token validation failed: %s", type(e).__name__)
        return False, "TOKEN_VALIDATION_FAILED"


def check_document_protection(wb) -> tuple[bool, Optional[str]]:
    """문서 보호 상태 확인.

    Args:
        wb: Excel workbook object

    Returns:
        (보호되지 않음 여부, 에러 메시지)
        - (True, None): 보호되지 않음 - 저장 가능
        - (False, 에러 메시지): 보호됨 - 저장 불가
    """
    try:
        if wb is None:
            return False, "WORKBOOK_NOT_FOUND"

        # 보호된 문서 확인
        try:
            if wb.ProtectStructure:
                return False, "WORKBOOK_STRUCTURE_PROTECTED"
        except Exception:  # noqa: BLE001
            pass

        try:
            if wb.ProtectWindows:
                return False, "WORKBOOK_WINDOWS_PROTECTED"
        except Exception:  # noqa: BLE001
            pass

        # 읽기 전용 확인
        try:
            if wb.ReadOnly:
                return False, "WORKBOOK_READ_ONLY"
        except Exception:  # noqa: BLE001
            pass

        # 공유 문서 확인
        try:
            if hasattr(wb, "MultiUserEditing") and wb.MultiUserEditing:
                return False, "WORKBOOK_SHARED"
        except Exception:  # noqa: BLE001
            pass

        return True, None
    except Exception as e:  # noqa: BLE001
        logger.error("Protection check failed: %s", type(e).__name__)
        return False, "PROTECTION_CHECK_FAILED"


def check_save_readiness(
    wb,
    approval_token: str,
    change_hash: str,
    token_hash: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """원본 저장 준비 상태 종합 검증 (STOP 조건).

    Args:
        wb: Excel workbook object
        approval_token: 승인 토큰
        change_hash: 변경 hash
        token_hash: 토큰 hash (옵션)

    Returns:
        (저장 가능 여부, 에러 메시지)
    """
    try:
        # 승인 토큰 검증
        valid, error = validate_approval_token(approval_token, change_hash, token_hash)
        if not valid:
            return False, error

        # 문서 보호 검증
        valid, error = check_document_protection(wb)
        if not valid:
            return False, error

        return True, None
    except Exception as e:  # noqa: BLE001
        logger.error("Save readiness check failed: %s", type(e).__name__)
        return False, "SAVE_READINESS_CHECK_FAILED"


def describe_changes(change_summary: dict) -> list[str]:
    """변경 내역을 사용자 친화적으로 설명.

    Args:
        change_summary: 변경 계획 요약

    Returns:
        설명 텍스트 목록
    """
    try:
        descriptions = []

        cell_updates = change_summary.get("cell_updates", 0)
        row_inserts = change_summary.get("row_inserts", 0)
        column_inserts = change_summary.get("column_inserts", 0)
        formula_writes = change_summary.get("formula_writes", 0)

        if cell_updates > 0:
            descriptions.append(f"셀 수정: {cell_updates}개")
        if row_inserts > 0:
            descriptions.append(f"행 삽입: {row_inserts}개")
        if column_inserts > 0:
            descriptions.append(f"열 삽입: {column_inserts}개")
        if formula_writes > 0:
            descriptions.append(f"수식 입력: {formula_writes}개")

        total = change_summary.get("total_changes", 0)
        if total > 0:
            descriptions.append(f"(총 {total}개 변경)")

        return descriptions if descriptions else ["변경 없음"]
    except Exception as e:  # noqa: BLE001
        logger.error("Description generation failed: %s", type(e).__name__)
        return ["변경 내역 생성 실패"]
