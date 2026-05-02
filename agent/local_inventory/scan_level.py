"""로컬 인벤토리 스캔 레벨 정의.

- Level 0: 스캔 안 함
- Level 1: 설치 프로그램/레지스트리 (기본값)
- Level 2: 사용자 선택 폴더
- Level 3: 깊이 있는 메타데이터 (명시 동의 필수, 기본값 비활성)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from agent.local_inventory.scan_scope import ScanScope


class ScanLevel(IntEnum):
    """스캔 레벨 정의."""
    NO_SCAN = 0
    SAFE_INVENTORY = 1
    USER_FOLDERS = 2
    DEEP_METADATA = 3


DEFAULT_SCAN_LEVEL = ScanLevel.SAFE_INVENTORY

# Level 별 허용 scope
LEVEL_SCOPES = {
    ScanLevel.NO_SCAN: frozenset(),
    ScanLevel.SAFE_INVENTORY: frozenset([
        ScanScope.PROGRAMS,
        ScanScope.COM_REGISTRY,
        ScanScope.HANCOM,
        ScanScope.OFFICE,
        ScanScope.CAD,
    ]),
    ScanLevel.USER_FOLDERS: frozenset([
        ScanScope.PROGRAMS,
        ScanScope.COM_REGISTRY,
        ScanScope.HANCOM,
        ScanScope.OFFICE,
        ScanScope.CAD,
        ScanScope.USER_SELECTED_FOLDERS,
    ]),
    ScanLevel.DEEP_METADATA: frozenset([
        ScanScope.PROGRAMS,
        ScanScope.COM_REGISTRY,
        ScanScope.HANCOM,
        ScanScope.OFFICE,
        ScanScope.CAD,
        ScanScope.USER_SELECTED_FOLDERS,
    ]),
}

# Level별 파일 시스템 제한
LEVEL_FILESYSTEM_CONFIG = {
    ScanLevel.NO_SCAN: {
        "max_depth": 0,
        "max_files": 0,
    },
    ScanLevel.SAFE_INVENTORY: {
        "max_depth": 2,
        "max_files": 1000,
    },
    ScanLevel.USER_FOLDERS: {
        "max_depth": 3,
        "max_files": 3000,
    },
    ScanLevel.DEEP_METADATA: {
        "max_depth": 5,
        "max_files": 10000,
    },
}


@dataclass(frozen=True)
class ScanLevelConfig:
    """스캔 레벨 설정."""
    level: ScanLevel
    allowed_scopes: frozenset[ScanScope]
    max_depth: int
    max_files: int
    requires_explicit_consent: bool  # True면 저장된 동의 무시하고 재확인 강제
    allows_user_folders: bool        # USER_SELECTED_FOLDERS 스캔 허용
    description: str


LEVEL_CONFIGS = {
    ScanLevel.NO_SCAN: ScanLevelConfig(
        level=ScanLevel.NO_SCAN,
        allowed_scopes=frozenset(),
        max_depth=0,
        max_files=0,
        requires_explicit_consent=False,
        allows_user_folders=False,
        description="스캔 안 함",
    ),
    ScanLevel.SAFE_INVENTORY: ScanLevelConfig(
        level=ScanLevel.SAFE_INVENTORY,
        allowed_scopes=LEVEL_SCOPES[ScanLevel.SAFE_INVENTORY],
        max_depth=2,
        max_files=1000,
        requires_explicit_consent=False,
        allows_user_folders=False,
        description="기본 인벤토리 (프로그램 설치/레지스트리/COM)",
    ),
    ScanLevel.USER_FOLDERS: ScanLevelConfig(
        level=ScanLevel.USER_FOLDERS,
        allowed_scopes=LEVEL_SCOPES[ScanLevel.USER_FOLDERS],
        max_depth=3,
        max_files=3000,
        requires_explicit_consent=True,
        allows_user_folders=True,
        description="사용자 선택 폴더 메타데이터 포함",
    ),
    ScanLevel.DEEP_METADATA: ScanLevelConfig(
        level=ScanLevel.DEEP_METADATA,
        allowed_scopes=LEVEL_SCOPES[ScanLevel.DEEP_METADATA],
        max_depth=5,
        max_files=10000,
        requires_explicit_consent=True,
        allows_user_folders=True,
        description="깊이 있는 메타데이터 스캔 (명시 동의 필수)",
    ),
}


def get_level_config(level: ScanLevel) -> ScanLevelConfig:
    """스캔 레벨 설정 조회.

    Args:
        level: 스캔 레벨

    Returns:
        해당 레벨의 설정
    """
    return LEVEL_CONFIGS.get(level, LEVEL_CONFIGS[DEFAULT_SCAN_LEVEL])


def get_allowed_scopes(level: ScanLevel) -> frozenset[ScanScope]:
    """스캔 레벨에서 허용되는 scope 목록.

    Args:
        level: 스캔 레벨

    Returns:
        허용되는 scope frozenset
    """
    return LEVEL_SCOPES.get(level, frozenset())


def validate_scan_level(
    level: ScanLevel,
    requested_scopes: list[ScanScope] = None,
) -> tuple[bool, str]:
    """스캔 레벨 검증.

    Args:
        level: 스캔 레벨
        requested_scopes: 요청한 scope 목록

    Returns:
        (유효성, 메시지)
    """
    if level == ScanLevel.NO_SCAN:
        return False, "no_scan"

    if not isinstance(level, ScanLevel):
        return False, "invalid_level"

    if requested_scopes:
        allowed = get_allowed_scopes(level)
        for scope in requested_scopes:
            if scope not in allowed:
                return False, f"scope_not_allowed_for_level: {scope.value}"

    return True, "ok"
