"""로컬 소프트웨어 관리자 데이터 모델.

프로그램 설치 상태 진단 결과를 담는 데이터 클래스.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, List


@dataclass(frozen=True)
class SoftwareProgram:
    """프로그램 정보."""
    id: str
    name: str
    installed: bool
    version: Optional[str] = None
    path: Optional[str] = None
    install_required: bool = False
    admin_required_for_install: bool = False
    reboot_may_be_required: bool = False
    notes: List[str] = None

    def __post_init__(self):
        if self.notes is None:
            object.__setattr__(self, 'notes', [])


@dataclass(frozen=True)
class SoftwareSummary:
    """소프트웨어 요약."""
    total: int
    installed: int
    missing: int
    needs_setup: int


@dataclass(frozen=True)
class SoftwareReport:
    """소프트웨어 진단 리포트."""
    ok: bool
    summary: SoftwareSummary
    programs: List[SoftwareProgram]
    recommendations: List[str]

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            'ok': self.ok,
            'summary': asdict(self.summary),
            'programs': [asdict(p) for p in self.programs],
            'recommendations': self.recommendations,
        }
