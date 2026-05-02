"""로컬 앱 지도 (app_map) 테스트.

- software_catalog 정규화
- capability_mapper 분석
- app_map_builder 통합
- action 등록 검증
- task_executor handler 검증
- 안전성 검증 (파일 read 없음, registry write 없음, 프로그램 실행 없음)
"""
import pytest
from pathlib import Path
from datetime import datetime

# ── SoftwareCatalog 테스트 ──────────────────────────────────────────────


def test_software_catalog_add_program() -> None:
    """프로그램 추가."""
    from agent.local_inventory.app_map.software_catalog import SoftwareCatalog

    catalog = SoftwareCatalog()
    catalog.add_program(
        name="Hancom Office",
        category="hancom",
        installed=True,
        version="14.0.2000",
        install_paths=["C:\\Program Files\\HNC\\HOffice"],
        publisher="Hansol Corp",
        detection_method="registry",
    )

    prog = catalog.get_program("Hancom Office")
    assert prog is not None
    assert prog.name == "Hancom Office"
    assert prog.category == "hancom"
    assert prog.installed is True
    assert prog.version == "14.0.2000"


def test_software_catalog_filters_sensitive_paths() -> None:
    """민감한 경로 필터링."""
    from agent.local_inventory.app_map.software_catalog import SoftwareCatalog

    catalog = SoftwareCatalog()
    catalog.add_program(
        name="Test",
        category="test",
        installed=True,
        install_paths=[
            "C:\\Program Files\\Test",
            "C:\\Users\\test\\.ssh\\key",
            "C:\\secret\\password",
        ],
    )

    prog = catalog.get_program("Test")
    assert prog is not None
    # 민감한 경로는 제외되어야 함
    assert len(prog.install_paths) < 3


def test_software_catalog_list_by_category() -> None:
    """카테고리별 조회."""
    from agent.local_inventory.app_map.software_catalog import SoftwareCatalog

    catalog = SoftwareCatalog()
    catalog.add_program("Hancom", "hancom", True)
    catalog.add_program("Excel", "office_excel", True)
    catalog.add_program("CAD", "cad", False)

    hancom_list = catalog.list_by_category("hancom")
    assert len(hancom_list) == 1
    assert hancom_list[0].name == "Hancom"

    # 미설치 프로그램은 제외
    cad_list = catalog.list_by_category("cad")
    assert len(cad_list) == 0


def test_software_catalog_to_dict() -> None:
    """JSON 직렬화."""
    from agent.local_inventory.app_map.software_catalog import SoftwareCatalog

    catalog = SoftwareCatalog()
    catalog.add_program("Test1", "test", True)
    catalog.add_program("Test2", "test", True)

    result = catalog.to_dict()
    assert result["total"] == 2
    assert result["installed"] == 2
    assert "programs" in result
    assert "detection_log" in result


# ── CapabilityMapper 테스트 ────────────────────────────────────────────


def test_capability_mapper_analyzes_hancom() -> None:
    """한컴 분석."""
    from agent.local_inventory.app_map.capability_mapper import CapabilityMapper

    inventory = {
        "programs": {
            "hancom": {
                "name": "Hancom Office",
                "category": "hancom",
                "installed": True,
                "version": "14.0.2000",
                "com_classes": {
                    "HWPFrame.HwpObject": True,
                    "HWPFrame.HwpObjForm": True,
                },
                "security_module_registered": False,
            }
        }
    }

    mapper = CapabilityMapper(inventory)
    caps = mapper.analyze()

    assert "hancom" in caps
    hancom = caps["hancom"]
    assert hancom.is_installed is True
    assert hancom.com_available is True
    assert hancom.setup_required is True  # 보안모듈 미등록
    assert hancom.setup_reason == "security_module_not_registered"
    assert hancom.automation_ready is False


def test_capability_mapper_analyzes_excel() -> None:
    """Excel 분석."""
    from agent.local_inventory.app_map.capability_mapper import CapabilityMapper

    inventory = {
        "programs": {
            "excel": {
                "name": "Microsoft Excel",
                "category": "office_excel",
                "installed": True,
                "version": "16.0",
                "com_classes": {
                    "Excel.Application": True,
                },
            }
        }
    }

    mapper = CapabilityMapper(inventory)
    caps = mapper.analyze()

    assert "excel" in caps
    excel = caps["excel"]
    assert excel.is_installed is True
    assert excel.com_available is True
    assert excel.automation_ready is True
    assert "read_cell" in excel.capabilities


def test_capability_mapper_analyzes_uninstalled() -> None:
    """미설치 프로그램 분석."""
    from agent.local_inventory.app_map.capability_mapper import CapabilityMapper

    inventory = {
        "programs": {
            "cad": {
                "name": "AutoCAD",
                "category": "cad",
                "installed": False,
            }
        }
    }

    mapper = CapabilityMapper(inventory)
    caps = mapper.analyze()

    assert "cad" in caps
    cad = caps["cad"]
    assert cad.is_installed is False


# ── AppMapBuilder 테스트 ───────────────────────────────────────────────


def test_app_map_builder_builds_from_inventory() -> None:
    """inventory로부터 app_map 빌드."""
    from agent.local_inventory.app_map.app_map_builder import AppMapBuilder

    inventory = {
        "programs": {
            "hancom": {
                "name": "Hancom Office",
                "category": "hancom",
                "installed": True,
                "version": "14.0.2000",
                "com_classes": {"HWPFrame.HwpObject": True},
                "security_module_registered": True,
            },
            "excel": {
                "name": "Microsoft Excel",
                "category": "office_excel",
                "installed": True,
                "version": "16.0",
                "com_classes": {"Excel.Application": True},
            },
        }
    }

    builder = AppMapBuilder()
    app_map = builder.build_from_inventory(inventory)

    assert app_map.generated_at is not None
    assert app_map.scan_source == "inventory"
    assert len(app_map.detected_apps) == 2
    assert "summary" in app_map.__dict__
    assert "recommendations" in app_map.__dict__


def test_app_map_builder_generates_summary() -> None:
    """요약 생성."""
    from agent.local_inventory.app_map.app_map_builder import AppMapBuilder

    inventory = {
        "programs": {
            "hancom": {
                "name": "Hancom",
                "category": "hancom",
                "installed": True,
                "com_classes": {"HWPFrame.HwpObject": True},
                "security_module_registered": True,
            },
            "excel": {
                "name": "Excel",
                "category": "office_excel",
                "installed": True,
                "com_classes": {"Excel.Application": True},
            },
            "cad": {
                "name": "AutoCAD",
                "category": "cad",
                "installed": False,
            },
        }
    }

    builder = AppMapBuilder()
    app_map = builder.build_from_inventory(inventory)

    summary = app_map.summary
    assert summary["total_apps"] == 2  # installed인 것만
    assert summary["automation_ready"] > 0


def test_app_map_builder_generates_recommendations() -> None:
    """권장사항 생성."""
    from agent.local_inventory.app_map.app_map_builder import AppMapBuilder

    inventory = {
        "programs": {
            "hancom": {
                "name": "Hancom",
                "category": "hancom",
                "installed": True,
                "com_classes": {"HWPFrame.HwpObject": True},
                "security_module_registered": False,  # 보안모듈 미등록
            },
        }
    }

    builder = AppMapBuilder()
    app_map = builder.build_from_inventory(inventory)

    assert len(app_map.recommendations) > 0
    assert any("보안모듈" in rec for rec in app_map.recommendations)


def test_app_map_builder_to_dict() -> None:
    """JSON 직렬화."""
    from agent.local_inventory.app_map.app_map_builder import AppMapBuilder

    inventory = {
        "programs": {
            "test": {
                "name": "Test",
                "category": "test",
                "installed": True,
                "com_classes": {},
            }
        }
    }

    builder = AppMapBuilder()
    app_map = builder.build_from_inventory(inventory)
    result = builder.to_dict()

    assert "generated_at" in result
    assert "summary" in result
    assert "detected_apps" in result
    assert "capabilities" in result
    assert "recommendations" in result


# ── 모듈 공개 API 테스트 ───────────────────────────────────────────────


def test_build_app_map_function() -> None:
    """build_app_map 함수."""
    from agent.local_inventory.app_map import build_app_map

    inventory = {
        "programs": {
            "excel": {
                "name": "Excel",
                "category": "office_excel",
                "installed": True,
                "com_classes": {"Excel.Application": True},
            }
        }
    }

    result = build_app_map(inventory)
    assert result is not None
    assert "summary" in result
    assert "detected_apps" in result


def test_get_app_map_status_not_found() -> None:
    """저장되지 않은 app_map 조회."""
    from agent.local_inventory.app_map import get_app_map_status

    result = get_app_map_status("/nonexistent/path/app_map.json")
    assert result["ok"] is False
    assert result["error"] == "app_map_not_found"


# ── Action Registry 테스트 ────────────────────────────────────────────


def test_action_registry_has_build_app_map() -> None:
    """build_app_map action 등록."""
    from agent.action_registry import get_meta, is_known_action

    assert is_known_action("local_inventory.build_app_map")
    meta = get_meta("local_inventory.build_app_map")
    assert meta is not None
    assert meta.action == "local_inventory.build_app_map"
    assert meta.category == "inventory"
    assert meta.risk_level == "medium"
    assert meta.read_only is True
    assert meta.requires_approval is True


def test_action_registry_has_app_map_status() -> None:
    """app_map_status action 등록."""
    from agent.action_registry import get_meta, is_known_action

    assert is_known_action("local_inventory.app_map_status")
    meta = get_meta("local_inventory.app_map_status")
    assert meta is not None
    assert meta.action == "local_inventory.app_map_status"
    assert meta.category == "inventory"
    assert meta.risk_level == "low"
    assert meta.read_only is True
    assert meta.requires_approval is False


# ── Task Executor 테스트 ───────────────────────────────────────────────


def test_task_executor_supports_build_app_map() -> None:
    """build_app_map action이 dispatch에 등록됨."""
    from agent.task_executor import supported_actions

    actions = supported_actions()
    assert "local_inventory.build_app_map" in actions


def test_task_executor_supports_app_map_status() -> None:
    """app_map_status action이 dispatch에 등록됨."""
    from agent.task_executor import supported_actions

    actions = supported_actions()
    assert "local_inventory.app_map_status" in actions


# ── 안전성 검증 테스트 ──────────────────────────────────────────────────


def test_no_file_content_reads_in_app_map() -> None:
    """파일 내용 read 호출 없음."""
    import inspect
    from agent.local_inventory.app_map import app_map_builder

    source = inspect.getsource(app_map_builder)
    # .read() / .open().read() 패턴 검사 (JSON 로드 제외)
    assert "read_text()" not in source
    assert "read_bytes()" not in source or "app_map" not in source


def test_no_registry_write_in_capability_mapper() -> None:
    """Capability mapper에서 registry write 없음."""
    import inspect
    from agent.local_inventory.app_map import capability_mapper

    source = inspect.getsource(capability_mapper)
    assert "SetValue" not in source
    assert "CreateKey" not in source
    assert "winreg.OpenKey(.*KEY_WRITE" not in source


def test_app_map_catalog_validates_paths() -> None:
    """경로 검증 (민감한 경로 제외)."""
    from agent.local_inventory.app_map.software_catalog import SoftwareCatalog

    catalog = SoftwareCatalog()

    # 민감한 경로는 자동 제외
    sensitive_paths = [
        "C:\\Users\\test\\.ssh\\key",
        "C:\\secret\\password",
        "C:\\token\\api_key",
    ]

    catalog.add_program(
        name="Test",
        category="test",
        install_paths=sensitive_paths + ["C:\\Program Files\\Test"],
    )

    prog = catalog.get_program("Test")
    assert prog is not None
    # 안전한 경로만 보존
    assert all("ssh" not in p.lower() for p in prog.install_paths)
    assert all("password" not in p.lower() for p in prog.install_paths)
    assert all("token" not in p.lower() for p in prog.install_paths)
