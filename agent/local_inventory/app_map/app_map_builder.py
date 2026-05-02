"""비즈니스 앱 지도 구축 및 사용자 요약 생성.

local_inventory 스캔 결과를 기반으로
사용자용 업무 프로그램 지도 및 AI 자동화 권장사항을 생성.

read-only: 저장된 inventory 데이터만 사용.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .capability_mapper import CapabilityMapper, CapabilityInfo
from .software_catalog import SoftwareCatalog
from .file_association_scanner import FileAssociationScanner
from .portable_app_detector import PortableAppDetector
from .shortcut_scanner import ShortcutScanner


@dataclass
class AppMap:
    """비즈니스 앱 지도."""
    generated_at: str
    scan_source: str  # "inventory" or "fresh_scan"
    detected_apps: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


class AppMapBuilder:
    """앱 지도 빌더."""

    def __init__(self) -> None:
        self.catalog = SoftwareCatalog()
        self.capability_mapper: Optional[CapabilityMapper] = None
        self.file_assoc_scanner = FileAssociationScanner()
        self.portable_detector = PortableAppDetector()
        self.shortcut_scanner = ShortcutScanner()
        self.app_map: Optional[AppMap] = None

    def build_from_inventory(self, inventory: dict[str, Any]) -> AppMap:
        """저장된 inventory 데이터로부터 app_map 빌드."""
        self.capability_mapper = CapabilityMapper(inventory)
        capabilities = self.capability_mapper.analyze()

        detected_apps = {}
        for key, prog in inventory.get("programs", {}).items():
            if prog.get("installed"):
                detected_apps[key] = {
                    "name": prog.get("name"),
                    "category": prog.get("category"),
                    "version": prog.get("version"),
                }

        self.app_map = AppMap(
            generated_at=datetime.now().isoformat(),
            scan_source="inventory",
            detected_apps=detected_apps,
            capabilities={
                k: asdict(v) for k, v in capabilities.items()
            },
        )

        self._generate_summary()
        self._generate_recommendations()

        return self.app_map

    def _generate_summary(self) -> None:
        """사용자용 요약 생성."""
        if not self.app_map:
            return

        capabilities = self.app_map.capabilities
        total_apps = len(self.app_map.detected_apps)
        automation_ready = sum(
            1 for c in capabilities.values()
            if c.get("automation_ready")
        )
        setup_required = sum(
            1 for c in capabilities.values()
            if c.get("setup_required")
        )

        self.app_map.summary = {
            "total_apps": total_apps,
            "automation_ready": automation_ready,
            "setup_required": setup_required,
            "not_detected": 0,
            "categories": self._count_by_category(),
        }

    def _count_by_category(self) -> dict[str, int]:
        """카테고리별 프로그램 수."""
        counts: dict[str, int] = {}
        for app in self.app_map.detected_apps.values():
            cat = app.get("category", "unknown")
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def _generate_recommendations(self) -> None:
        """AI 자동화 권장사항 생성."""
        if not self.app_map:
            return

        recommendations = []
        capabilities = self.app_map.capabilities

        for key, cap in capabilities.items():
            if cap.get("setup_required"):
                reason = cap.get("setup_reason", "unknown")
                if reason == "security_module_not_registered":
                    recommendations.append(
                        f"한컴: 보안모듈 등록이 필요합니다 (자동화 활성화를 위해)"
                    )
                elif reason:
                    recommendations.append(
                        f"{cap.get('name')}: {reason}"
                    )

            if cap.get("category") == "cad" and not cap.get("automation_ready"):
                if cap.get("is_installed"):
                    recommendations.append(
                        "AutoCAD: COM 확인이 필요합니다"
                    )

        if not any(c.get("automation_ready") for c in capabilities.values()):
            recommendations.append(
                "자동화 가능 프로그램이 없습니다. 설정을 확인하세요."
            )

        self.app_map.recommendations = recommendations

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화."""
        if not self.app_map:
            return {}

        return {
            "generated_at": self.app_map.generated_at,
            "scan_source": self.app_map.scan_source,
            "summary": self.app_map.summary,
            "detected_apps": self.app_map.detected_apps,
            "capabilities": self.app_map.capabilities,
            "recommendations": self.app_map.recommendations,
        }


def build_app_map(inventory: dict[str, Any]) -> dict[str, Any]:
    """inventory로부터 app_map 빌드."""
    builder = AppMapBuilder()
    app_map = builder.build_from_inventory(inventory)
    return builder.to_dict()


def get_app_map_status(app_map_path: Optional[str] = None) -> dict[str, Any]:
    """저장된 app_map 상태 조회."""
    if not app_map_path:
        from pathlib import Path
        app_map_path = str(
            Path.home()
            / "AppData"
            / "Local"
            / "HaehanAI"
            / "inventory"
            / "local_app_map.json"
        )

    try:
        p = Path(app_map_path)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "ok": True,
                "app_map": data,
            }
    except Exception:
        pass

    return {
        "ok": False,
        "app_map": None,
        "error": "app_map_not_found",
    }
