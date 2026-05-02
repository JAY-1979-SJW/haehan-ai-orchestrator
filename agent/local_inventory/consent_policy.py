"""로컬 인벤토리 스캔 동의 정책.

- 사용자 동의 상태 관리
- scope별 동의 추적
- 레벨별 동의 추적
- 동의 없으면 스캔 차단
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .scan_scope import ScanScope, ALL_SCOPES
from .scan_level import ScanLevel

logger = logging.getLogger(__name__)

DEFAULT_CONSENT_PATH = Path.home() / "AppData" / "Local" / "HaehanAI" / "inventory" / "consent.json"
CONSENT_POLICY_VERSION = "1.1"


class ConsentPolicy:
    """사용자 동의 상태 관리."""

    def __init__(self, state_path: Optional[Path] = None):
        """초기화.

        Args:
            state_path: 동의 상태 저장 경로 (기본값: DEFAULT_CONSENT_PATH)
        """
        self.state_path = state_path or DEFAULT_CONSENT_PATH
        self._scopes: set[ScanScope] = set()
        self._level: Optional[ScanLevel] = None
        self._granted_at: Optional[str] = None
        self._load()

    def has_consent(self, scope: ScanScope) -> bool:
        """특정 scope에 대한 동의 여부.

        Args:
            scope: 확인할 scope

        Returns:
            동의 여부
        """
        return scope in self._scopes

    def has_all_consent(self, scopes: list[ScanScope]) -> bool:
        """모든 scope에 대한 동의 여부."""
        return all(scope in self._scopes for scope in scopes)

    def granted_scopes(self) -> list[ScanScope]:
        """동의된 scope 목록."""
        return sorted(list(self._scopes), key=lambda s: s.value)

    def grant(self, scopes: list[ScanScope]) -> None:
        """scope에 동의.

        Args:
            scopes: 동의할 scope 목록
        """
        self._scopes.update(scopes)
        self._granted_at = datetime.utcnow().isoformat() + "Z"

    def revoke(self, scope: ScanScope) -> None:
        """scope 동의 철회."""
        self._scopes.discard(scope)

    def has_level_consent(self, level: ScanLevel) -> bool:
        """특정 레벨에 대한 동의 여부.

        Args:
            level: 확인할 레벨

        Returns:
            동의 여부 (None이면 False)
        """
        if self._level is None:
            return False
        return self._level >= level

    def grant_level(self, level: ScanLevel) -> None:
        """레벨에 동의.

        Args:
            level: 동의할 레벨
        """
        self._level = level
        self._granted_at = datetime.utcnow().isoformat() + "Z"

    def granted_level(self) -> Optional[ScanLevel]:
        """동의된 레벨."""
        return self._level

    def save(self) -> bool:
        """동의 상태를 파일에 저장.

        Returns:
            성공 여부
        """
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "version": CONSENT_POLICY_VERSION,
                "scopes": [s.value for s in self.granted_scopes()],
                "level": self._level.value if self._level else None,
                "granted_at": self._granted_at,
                "saved_at": datetime.utcnow().isoformat() + "Z",
            }

            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved consent state to {self.state_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save consent state: {e}")
            return False

    def _load(self) -> None:
        """파일에서 동의 상태 로드."""
        try:
            if not self.state_path.exists():
                logger.info(f"Consent state file not found: {self.state_path}")
                return

            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            scopes = data.get("scopes", [])
            self._scopes = {
                ScanScope(s) for s in scopes
                if s in {scope.value for scope in ALL_SCOPES}
            }

            # 레벨 로드 (하위 호환성: level 필드 없으면 None)
            level_val = data.get("level")
            if level_val is not None:
                try:
                    self._level = ScanLevel(level_val)
                except (ValueError, KeyError):
                    logger.warning(f"Invalid level in consent: {level_val}")
                    self._level = None

            self._granted_at = data.get("granted_at")

            logger.info(f"Loaded consent state: {len(self._scopes)} scope(s), level={self._level}")

        except Exception as e:
            logger.warning(f"Failed to load consent state: {e}")
            self._scopes = set()
            self._level = None


def inventory_scan_consent(
    scopes: list[ScanScope],
    force_dialog: bool = False,
    state_path: Optional[Path] = None,
    level: Optional[ScanLevel] = None,
) -> bool:
    """사용자 동의 획득 및 확인.

    Args:
        scopes: 요청할 scope 목록
        force_dialog: True면 저장된 동의 무시하고 재확인
        state_path: 동의 상태 파일 경로
        level: 요청할 스캔 레벨

    Returns:
        모든 scope 및 레벨에 대한 동의 여부
    """
    policy = ConsentPolicy(state_path)

    # 레벨 동의 검증 (requires_explicit_consent=True면 force_dialog 강제)
    if level:
        from .scan_level import get_level_config

        level_config = get_level_config(level)
        if level_config.requires_explicit_consent:
            force_dialog = True

        # 이미 더 높은 레벨로 동의했으면 패스
        if not force_dialog and policy.has_level_consent(level):
            logger.info(f"Using existing level consent: {level.name}")
            return True
    else:
        # 모든 scope에 동의 있으면 패스
        if not force_dialog and policy.has_all_consent(scopes):
            logger.info("Using existing consent")
            return True

    # 동의 대화
    print()
    print("=" * 70)
    print("📋 로컬 자산 인벤토리 스캔")
    if level:
        from .scan_level import get_level_config
        level_config = get_level_config(level)
        print(f"   [레벨 {level.value}: {level_config.description}]")
    print("=" * 70)
    print()

    if level:
        from .scan_level import get_level_config
        level_config = get_level_config(level)
        print(f"스캔 레벨: {level.name}")
        print(f"설명: {level_config.description}")
        print(f"파일 개수 제한: {level_config.max_files}")
        print(f"폴더 깊이 제한: {level_config.max_depth}")
        print()

    print("다음 정보를 수집합니다 (로컬만 저장, 서버 전송 없음):")
    for scope in scopes:
        if scope == ScanScope.PROGRAMS:
            print("  ✓ 설치된 프로그램 목록")
        elif scope == ScanScope.COM_REGISTRY:
            print("  ✓ COM 클래스 등록 상태")
        elif scope == ScanScope.HANCOM:
            print("  ✓ 한컴 설치 상태 및 버전")
        elif scope == ScanScope.OFFICE:
            print("  ✓ Office 설치 상태 및 버전")
        elif scope == ScanScope.CAD:
            print("  ✓ AutoCAD 설치 상태")
        elif scope == ScanScope.USER_SELECTED_FOLDERS:
            print("  ✓ 사용자 선택 폴더 메타데이터 (문서 내용 미조회)")
    print()

    print("수집되지 않는 정보:")
    print("  ✗ 파일 내용")
    print("  ✗ 비밀번호, 인증서, 쿠키")
    print("  ✗ 브라우저 히스토리")
    print("  ✗ 개인 정보")
    print()

    print("저장 위치: 로컬 PC (%LOCALAPPDATA%\\HaehanAI\\inventory)")
    print("전송: 없음 (오프라인 사용)")
    print("삭제: 사용자가 언제든 삭제 가능")
    print()

    response = input("계속 진행하시겠습니까? (y/n): ").strip().lower()
    if response != "y":
        logger.info("User declined consent")
        return False

    policy.grant(scopes)
    if level:
        policy.grant_level(level)
        logger.info(f"User granted level consent: {level.name}")
    policy.save()
    logger.info(f"User granted consent for {len(scopes)} scope(s)")
    return True
