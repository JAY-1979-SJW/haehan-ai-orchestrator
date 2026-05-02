"""설치된 프로그램 메타데이터 정규화.

Registry와 파일시스템 정보를 통합하여
프로그램의 설치 상태, 버전, 경로를 추출.

read-only 메타데이터만 사용.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class SoftwareInfo:
    """설치된 프로그램 정보."""
    name: str
    category: str  # hancom, excel, cad, pdf, design, archive, etc.
    installed: bool
    version: Optional[str] = None
    install_paths: list[str] = None
    publisher: Optional[str] = None
    detection_method: Optional[str] = None  # registry, filesystem, both

    def __post_init__(self) -> None:
        if self.install_paths is None:
            object.__setattr__(self, "install_paths", [])


class SoftwareCatalog:
    """프로그램 정보를 정규화하고 저장."""

    def __init__(self) -> None:
        self.programs: dict[str, SoftwareInfo] = {}
        self.detection_log: list[dict[str, Any]] = []

    def add_program(
        self,
        name: str,
        category: str,
        installed: bool = True,
        version: Optional[str] = None,
        install_paths: Optional[list[str]] = None,
        publisher: Optional[str] = None,
        detection_method: Optional[str] = None,
    ) -> None:
        """프로그램 정보 추가."""
        if not name or not category:
            return

        paths = install_paths or []
        # 민감한 경로 제외 (검증)
        paths = [p for p in paths if not self._is_sensitive_path(p)]

        info = SoftwareInfo(
            name=name,
            category=category,
            installed=installed,
            version=version,
            install_paths=paths,
            publisher=publisher,
            detection_method=detection_method,
        )
        self.programs[name] = info
        self.detection_log.append({
            "name": name,
            "method": detection_method or "unknown",
            "installed": installed,
        })

    @staticmethod
    def _is_sensitive_path(path: str) -> bool:
        """민감한 경로 필터링."""
        sensitive_patterns = [
            "password", "credential", "secret", "token", "api_key",
            ".ssh", ".aws", ".kube", ".git", "ssh_key",
        ]
        path_lower = path.lower()
        return any(p in path_lower for p in sensitive_patterns)

    def get_program(self, name: str) -> Optional[SoftwareInfo]:
        """프로그램 정보 조회."""
        return self.programs.get(name)

    def list_by_category(self, category: str) -> list[SoftwareInfo]:
        """카테고리별 프로그램 조회."""
        return [
            info for info in self.programs.values()
            if info.category == category and info.installed
        ]

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화."""
        return {
            "total": len(self.programs),
            "installed": sum(1 for p in self.programs.values() if p.installed),
            "programs": {
                name: {
                    "name": info.name,
                    "category": info.category,
                    "installed": info.installed,
                    "version": info.version,
                    "install_paths": info.install_paths,
                    "publisher": info.publisher,
                    "detection_method": info.detection_method,
                }
                for name, info in self.programs.items()
            },
            "detection_log": self.detection_log,
        }
