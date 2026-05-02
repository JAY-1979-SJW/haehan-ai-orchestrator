"""프로그램의 AI 제어 가능성 판단.

프로그램 설치, COM 등록, 버전 정보를 기반으로
AI 자동화 가능 기능을 매핑.

read-only: 기존 inventory 데이터만 사용.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class CapabilityInfo:
    """프로그램 AI 제어 가능성."""
    name: str
    category: str
    is_installed: bool
    com_available: bool = False
    capabilities: list[str] = field(default_factory=list)
    setup_required: bool = False
    setup_reason: Optional[str] = None
    automation_ready: bool = False
    notes: Optional[str] = None


class CapabilityMapper:
    """프로그램별 AI 제어 능력 평가."""

    def __init__(self, inventory: Optional[dict[str, Any]] = None) -> None:
        self.inventory = inventory or {}
        self.capabilities: dict[str, CapabilityInfo] = {}

    def analyze(self) -> dict[str, CapabilityInfo]:
        """inventory를 기반으로 capabilities 분석."""
        programs = self.inventory.get("programs", {})

        for key, prog in programs.items():
            try:
                cap = self._analyze_program(key, prog)
                if cap:
                    self.capabilities[key] = cap
            except Exception:
                pass

        return self.capabilities

    def _analyze_program(
        self,
        key: str,
        prog: dict[str, Any],
    ) -> Optional[CapabilityInfo]:
        """단일 프로그램 분석."""
        name = prog.get("name", key)
        category = prog.get("category", "unknown")
        installed = prog.get("installed", False)

        if not installed:
            return CapabilityInfo(
                name=name,
                category=category,
                is_installed=False,
            )

        # 카테고리별 분석
        if category == "hancom":
            return self._analyze_hancom(name, prog)
        elif category == "office_excel":
            return self._analyze_excel(name, prog)
        elif category == "cad":
            return self._analyze_cad(name, prog)
        elif category == "pdf":
            return self._analyze_pdf(name, prog)
        elif category in ["lighting", "design"]:
            return self._analyze_specialized(name, category, prog)

        return CapabilityInfo(
            name=name,
            category=category,
            is_installed=True,
            automation_ready=False,
        )

    def _analyze_hancom(
        self,
        name: str,
        prog: dict[str, Any],
    ) -> CapabilityInfo:
        """한컴 분석."""
        com_classes = prog.get("com_classes", {})
        has_com = any(com_classes.values()) if com_classes else False

        # 보안모듈 확인
        security_module_ok = prog.get("security_module_registered", False)

        setup_required = False
        setup_reason = None

        if not security_module_ok:
            setup_required = True
            setup_reason = "security_module_not_registered"

        capabilities = []
        if has_com:
            capabilities.extend([
                "hwp_read",
                "hwp_to_hwpx_convert",
                "hwpx_analysis",
                "pdf_export",
            ])

        automation_ready = has_com and not setup_required

        return CapabilityInfo(
            name=name,
            category="hancom",
            is_installed=True,
            com_available=has_com,
            capabilities=capabilities,
            setup_required=setup_required,
            setup_reason=setup_reason,
            automation_ready=automation_ready,
            notes="보안모듈 등록이 필요합니다" if setup_required else None,
        )

    def _analyze_excel(
        self,
        name: str,
        prog: dict[str, Any],
    ) -> CapabilityInfo:
        """Excel 분석."""
        com_classes = prog.get("com_classes", {})
        has_com = any(com_classes.values()) if com_classes else False

        capabilities = []
        if has_com:
            capabilities.extend([
                "read_cell",
                "write_cell",
                "read_sheet",
                "write_formula",
                "save_as",
            ])

        return CapabilityInfo(
            name=name,
            category="office_excel",
            is_installed=True,
            com_available=has_com,
            capabilities=capabilities,
            automation_ready=has_com,
        )

    def _analyze_cad(
        self,
        name: str,
        prog: dict[str, Any],
    ) -> CapabilityInfo:
        """AutoCAD 분석."""
        com_classes = prog.get("com_classes", {})
        has_com = any(com_classes.values()) if com_classes else False

        capabilities = []
        if has_com:
            capabilities.extend([
                "open_drawing",
                "add_text",
                "save_drawing",
            ])

        return CapabilityInfo(
            name=name,
            category="cad",
            is_installed=True,
            com_available=has_com,
            capabilities=capabilities,
            automation_ready=has_com,
            notes="COM 확인이 필요합니다" if not has_com else None,
        )

    def _analyze_pdf(
        self,
        name: str,
        prog: dict[str, Any],
    ) -> CapabilityInfo:
        """PDF 분석."""
        return CapabilityInfo(
            name=name,
            category="pdf",
            is_installed=True,
            capabilities=["pdf_read", "pdf_export"],
            automation_ready=True,
        )

    def _analyze_specialized(
        self,
        name: str,
        category: str,
        prog: dict[str, Any],
    ) -> CapabilityInfo:
        """전문 프로그램 분석 (조명계산, 디자인 등)."""
        return CapabilityInfo(
            name=name,
            category=category,
            is_installed=True,
            automation_ready=False,
            notes="전문가 검토 필요",
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화."""
        return {
            "total": len(self.capabilities),
            "capabilities": {
                key: {
                    "name": cap.name,
                    "category": cap.category,
                    "is_installed": cap.is_installed,
                    "com_available": cap.com_available,
                    "capabilities": cap.capabilities,
                    "setup_required": cap.setup_required,
                    "setup_reason": cap.setup_reason,
                    "automation_ready": cap.automation_ready,
                    "notes": cap.notes,
                }
                for key, cap in self.capabilities.items()
            },
        }
