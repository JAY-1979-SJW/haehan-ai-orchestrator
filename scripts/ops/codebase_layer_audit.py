"""Classify repository files by architecture layer and audit drift.

Usage:
    python scripts/ops/codebase_layer_audit.py --once
    python scripts/ops/codebase_layer_audit.py --json
    python scripts/ops/codebase_layer_audit.py --watch --interval 2
"""
from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "data" / "codebase_layer_audit_latest.json"
DEFAULT_CONFIG = ROOT / "configs" / "codebase_layer_audit.json"
LAYER_DOC = ROOT / "docs" / "layer_classification.md"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "data",
    "logs",
    "runs",
    "storage",
    "tmp",
    "node_modules",
    ".next",
    ".claude",
}

ACTIVE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".sql",
    ".ps1",
    ".sh",
    ".yml",
    ".yaml",
    ".md",
}

IMPORT_SCAN_PREFIXES = {
    "scripts",
    "ai_orchestrator",
    "agent",
    "local_agent",
    "browser_api",
    "browser_worker",
    "services",
    "mcp_server",
    "adapters",
}

OPENAPI_APP_MODULES = (
    "browser_api.server",
    "browser_worker.app",
    "services.file_map_executor.app",
    "ai_orchestrator.server",
)

PYDANTIC_SCHEMA_MODULES = (
    "scripts.schemas",
    "browser_worker.schemas",
    "services.file_map_executor.schemas",
    "ai_orchestrator.browser_tool.schemas",
    "ai_orchestrator.browser_tool.unified_browser_task_schema",
    "ai_orchestrator.server.task_queue_schema",
    "ai_orchestrator.local_agent.action_schemas",
    "local_agent.browser_websocket_schema",
    "agent.models",
)

SITE_MODULES = {
    "eum",
    "gabia",
    "hiworks",
    "naver",
    "google",
    "g2b",
    "kakao",
    "smartstore",
}

SITE_STANDARD_FILES = {
    "__init__.py",
    "router.py",
    "schemas.py",
    "gates.py",
    "explorer.py",
    "workflows.py",
}


@dataclass(frozen=True)
class Layer:
    key: str
    name: str
    rule: str


@dataclass(frozen=True)
class ClassifiedFile:
    path: str
    layer: str
    reason: str
    size: int
    mtime: float


@dataclass(frozen=True)
class AuditIssue:
    severity: str
    code: str
    path: str
    message: str
    layer: str = ""


@dataclass(frozen=True)
class ConsistencyCheck:
    name: str
    ok: bool
    message: str


LAYERS = {
    "L0": Layer("L0", "Runtime/Data", "Generated state and runtime output."),
    "L1": Layer("L1", "Shared Contracts", "Schemas, DTOs, models, redaction helpers."),
    "L2": Layer("L2", "Policy/Gate/Security", "Risk gates, policies, approvals, allowlists."),
    "L3": Layer("L3", "Connectors/Adapters", "External clients and low-level IO wrappers."),
    "L4": Layer("L4", "Browser/Automation Engine", "Generic browser/session/form automation."),
    "L5": Layer("L5", "Site Modules", "Site-specific routers, selectors, capabilities."),
    "L6": Layer("L6", "Business Workflows", "Company workflow orchestration and queues."),
    "L7": Layer("L7", "Persistence/Audit", "DB, audit, operation logs, migrations."),
    "L8": Layer("L8", "Server API", "FastAPI/Flask routers and server task APIs."),
    "L9": Layer("L9", "Admin UI", "Frontend/admin/desktop UI."),
    "L10": Layer("L10", "Local PC App Automation", "Excel/HWP/CAD/inventory/file-map automation."),
    "L11": Layer("L11", "Tests/Fixtures", "Tests and fixtures."),
    "L12": Layer("L12", "Docs/Reports/Archive", "Documentation, reports, archive."),
    "UNKNOWN": Layer("UNKNOWN", "Unknown", "Not matched by current layer rules."),
}


def relpath(path: Path, root: Path = ROOT) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def is_excluded(path: Path, root: Path = ROOT) -> bool:
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return True
    return any(part in EXCLUDED_DIRS for part in parts)


def iter_files(root: Path = ROOT) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".mypy_cache")]
        if is_excluded(current_path, root):
            continue
        for file_name in files:
            path = current_path / file_name
            if path.suffix.lower() not in ACTIVE_EXTENSIONS:
                continue
            yield path


def classify_path(path: str) -> tuple[str, str]:
    p = path.replace("\\", "/")
    name = Path(p).name
    suffix = Path(p).suffix.lower()
    parts = p.split("/")

    if name in {".gitignore", ".gitattributes", ".dockerignore"}:
        return "L1", "repository configuration or policy"
    if p.startswith(("docs/", "scripts/archive/")) or name.startswith(("BOOTSTRAP", "HANDOVER")):
        return "L12", "documentation/report/archive path"
    if "/" not in p and suffix == ".py":
        if name.startswith("test_"):
            return "L11", "root-level legacy test"
        if name in {"security_utils.py"}:
            return "L1", "root shared security helper"
        if name in {"logging_utils.py"}:
            return "L7", "root shared logging facade"
        if name.startswith(("debug_", "check_", "close_")) or name in {"list_tabs.py", "eum_docs.py"}:
            return "L12", "root one-off utility or probe pending archive"
        return "L4", "root generic automation script"
    if parts[0] in {"tests"} or "/tests/" in p or "/__tests__/" in p:
        return "L11", "test path"
    if p.startswith("agent/tests/") or p.startswith("ai_orchestrator/tests/") or p.startswith("mcp_server/tests/"):
        return "L11", "test path"
    if p.startswith(("admin-web/", "ui/", "desktop/")):
        return "L9", "admin or desktop UI path"
    if p.startswith(("migrations/",)) or "audit" in name or "cdp_db" in name or "op_log" in name:
        return "L7", "persistence or audit path"
    if p.startswith(("browser_api/", "ai_orchestrator/server/")):
        return "L8", "server API path"
    if p.startswith("ai_orchestrator/") and ("router" in name or name in {"app.py"}):
        return "L8", "platform API router/app"
    if p.startswith(("agent/excel/", "agent/hancom/", "agent/local_inventory/", "agent/local_software_manager/", "local_agent/cad/")):
        return "L10", "local PC app automation path"
    if p.startswith(("agent/connectors/", "ai_orchestrator/connectors/", "browser_worker/", "mcp_server/", "adapters/")):
        return "L3", "connector/adapter path"
    if p.startswith(("scripts/explorer/", "scripts/form/")) or name.startswith(("cdp_", "navigator", "popup_", "page_")):
        return "L4", "generic browser automation path"
    if p.startswith("ai_orchestrator/local_agent/browser/") or p.startswith("local_agent/browser_"):
        return "L4", "local browser automation path"
    if p.startswith("scripts/"):
        if len(parts) > 1 and parts[1] in SITE_MODULES:
            if name in {"sales_mail.py", "workspace.py", "workflows.py", "mail_batch.py"}:
                return "L6", "site business workflow"
            return "L5", "site module"
        if name in {"schemas.py", "security.py"}:
            return "L1", "shared contract/security helper"
        if name in {"gate.py"} or "policy" in name:
            return "L2", "gate or policy"
        if name in {"web_connector.py", "credentials.py", "config.py", "logger.py"}:
            return "L3", "shared connector/config"
        if p.startswith("scripts/ops/"):
            return "L7", "ops/audit tooling"
        return "L4", "generic script automation"
    if p.startswith("ai_orchestrator/"):
        if any(token in name for token in ("schema", "model")):
            return "L1", "platform contract/model"
        if any(token in name for token in ("policy", "gate", "approval", "auth")):
            return "L2", "platform policy/security"
        if any(token in name for token in ("connector", "client")):
            return "L3", "platform connector/client"
        return "L8", "platform application code"
    if p.startswith(("agent/", "local_agent/")):
        if any(token in name for token in ("policy", "approval")):
            return "L2", "agent policy"
        return "L10", "agent/local automation"
    if p.startswith("services/"):
        return "L8", "standalone service path"
    if suffix in {".md"}:
        return "L12", "markdown documentation"
    if suffix in {".yml", ".yaml", ".json", ".sql"}:
        return "L1", "configuration or structured contract"
    return "UNKNOWN", "no matching layer rule"


def classify_files(root: Path = ROOT) -> list[ClassifiedFile]:
    rows: list[ClassifiedFile] = []
    for path in sorted(iter_files(root), key=lambda p: relpath(p, root)):
        stat = path.stat()
        layer, reason = classify_path(relpath(path, root))
        rows.append(
            ClassifiedFile(
                path=relpath(path, root),
                layer=layer,
                reason=reason,
                size=stat.st_size,
                mtime=stat.st_mtime,
            )
        )
    return rows


def audit(rows: list[ClassifiedFile], root: Path = ROOT) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    by_path = {row.path: row for row in rows}

    for row in rows:
        parts = row.path.split("/")
        name = Path(row.path).name
        if row.layer == "UNKNOWN":
            issues.append(AuditIssue("warn", "UNKNOWN_LAYER", row.path, "File does not match any layer rule."))
        if len(parts) == 1 and Path(row.path).suffix == ".py":
            issues.append(
                AuditIssue(
                    "warn",
                    "ROOT_PY_SCRIPT",
                    row.path,
                    "Root-level Python script should be moved into a module or archive if active.",
                    row.layer,
                )
            )
        if row.path.startswith("scripts/hiworks/") and name == "router.py" and row.size > 12000:
            issues.append(
                AuditIssue(
                    "warn",
                    "FAT_SITE_ROUTER",
                    row.path,
                    "Hiworks router contains too much logic; split into schemas/gates/explorer/mail/workflows.",
                    row.layer,
                )
            )
        if row.path.startswith("scripts/") and "/archive/" not in row.path and name.startswith(("debug_", "test_")):
            issues.append(
                AuditIssue(
                    "info",
                    "ACTIVE_DEBUG_SCRIPT",
                    row.path,
                    "Debug/test script is in an active scripts path.",
                    row.layer,
                )
            )

    for site in sorted(SITE_MODULES):
        site_dir = root / "scripts" / site
        if not site_dir.exists():
            continue
        existing = {Path(path).name for path in by_path if path.startswith(f"scripts/{site}/")}
        missing = sorted(SITE_STANDARD_FILES - existing)
        if missing:
            severity = "warn" if site == "hiworks" else "info"
            issues.append(
                AuditIssue(
                    severity,
                    "SITE_STANDARD_FILES_MISSING",
                    f"scripts/{site}/",
                    "Missing standard site module files: " + ", ".join(missing),
                    "L5",
                )
            )

    return sorted(issues, key=lambda x: ({"warn": 0, "info": 1}.get(x.severity, 2), x.code, x.path))


# ── 역방향 import 게이트 ────────────────────────────────────────────────────────

# 레이어 번호 낮을수록 하위. 상위→하위만 허용.
_LAYER_ORDER = {
    "L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5,
    "L6": 6, "L7": 7, "L8": 8, "L9": 9, "L10": 10,
    "L11": 11, "L12": 12, "UNKNOWN": 99,
}

# 절대 금지 import 패턴: (소스 모듈 prefix, 금지 import prefix, 이유)
_FORBIDDEN_IMPORT_PAIRS: list[tuple[str, str, str]] = [
    # core/domain은 API, UI, DB, 외부 호출 import 금지
    ("scripts.site_engine", "fastapi", "core must not import fastapi"),
    ("scripts.site_engine", "ai_orchestrator.server", "core must not import server layer"),
    ("scripts.site_engine", "scripts.cdp_", "core must not import browser adapters"),
    # site router는 DB 직접 접근 금지
    ("scripts.hiworks.router", "scripts.db", "site router must not access DB directly"),
    ("scripts.youtube.router", "scripts.db", "site router must not access DB directly"),
    ("scripts.naver.router", "scripts.db", "site router must not access DB directly"),
    ("scripts.g2b.router", "scripts.db", "site router must not access DB directly"),
    # site router는 DB 직접 접근 금지
    ("scripts.google.router", "scripts.db", "site router must not access DB directly"),
    # 서로 다른 업무 도메인 간 직접 import
    ("scripts.hiworks", "scripts.eum", "cross-domain import: hiworks must not import eum"),
    ("scripts.hiworks", "scripts.youtube", "cross-domain import: hiworks must not import youtube"),
    ("scripts.hiworks", "scripts.google", "cross-domain import: hiworks must not import google"),
    ("scripts.eum", "scripts.hiworks", "cross-domain import: eum must not import hiworks"),
    ("scripts.eum", "scripts.google", "cross-domain import: eum must not import google"),
    ("scripts.youtube", "scripts.hiworks", "cross-domain import: youtube must not import hiworks"),
    ("scripts.youtube", "scripts.google", "cross-domain import: youtube must not import google"),
    ("scripts.g2b", "scripts.hiworks", "cross-domain import: g2b must not import hiworks"),
    ("scripts.g2b", "scripts.google", "cross-domain import: g2b must not import google"),
    ("scripts.google", "scripts.hiworks", "cross-domain import: google must not import hiworks"),
    ("scripts.google", "scripts.eum", "cross-domain import: google must not import eum"),
    ("scripts.google", "scripts.youtube", "cross-domain import: google must not import youtube domain"),
    ("scripts.google", "scripts.g2b", "cross-domain import: google must not import g2b"),
    # gabia cross-domain import 금지
    ("scripts.gabia.router", "scripts.db", "site router must not access DB directly"),
    ("scripts.gabia", "scripts.hiworks", "cross-domain import: gabia must not import hiworks"),
    ("scripts.gabia", "scripts.eum", "cross-domain import: gabia must not import eum"),
    ("scripts.gabia", "scripts.youtube", "cross-domain import: gabia must not import youtube"),
    ("scripts.gabia", "scripts.g2b", "cross-domain import: gabia must not import g2b"),
    ("scripts.gabia", "scripts.google", "cross-domain import: gabia must not import google"),
    ("scripts.hiworks", "scripts.gabia", "cross-domain import: hiworks must not import gabia"),
    ("scripts.eum", "scripts.gabia", "cross-domain import: eum must not import gabia"),
    ("scripts.youtube", "scripts.gabia", "cross-domain import: youtube must not import gabia"),
    ("scripts.g2b", "scripts.gabia", "cross-domain import: g2b must not import gabia"),
    ("scripts.google", "scripts.gabia", "cross-domain import: google must not import gabia"),
]

# 보안 금지 패턴: (정규식 패턴, 이유)
# 주의: 오탐 최소화를 위해 변수명을 엄격히 한정 (token_id, token_status 등은 제외)
_SECURITY_FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    # print(password) / print(passwd) / print(secret) 등 — 단독 변수명만
    (r"print\s*\(\s*(password|passwd|pw_\w*|secret\b|api_key\b|apikey\b)\s*\)",
     "Secret variable printed directly"),
    # os.environ["PASSWORD"] 등 — 대문자 환경변수 직접 출력
    (r"print\s*\(\s*os\.environ\s*[\[.]\s*['\"](?:PASSWORD|PASSWD|SECRET|API_KEY|APIKEY)['\"]",
     "Env secret printed directly"),
    # f"{password}" / f"{secret}" — 단독 변수명 보간 (token_id, token_status 등 제외)
    (r"\{(password|passwd|secret\b|api_key\b|apikey\b)\}",
     "Plain secret variable in f-string or format"),
]


def check_forbidden_imports(rows: list[ClassifiedFile], root: Path = ROOT) -> list[AuditIssue]:
    """금지 import 방향 검사."""
    import re
    issues: list[AuditIssue] = []
    for row in rows:
        if not row.path.endswith(".py"):
            continue
        path = root / row.path
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for src_prefix, forbidden_prefix, reason in _FORBIDDEN_IMPORT_PAIRS:
            src_mod = row.path.replace("/", ".").removesuffix(".py")
            if not src_mod.startswith(src_prefix.replace("/", ".")):
                continue
            # import 문에서 금지 모듈 사용 여부 검사
            pattern = re.compile(
                r"^\s*(?:import|from)\s+(" + re.escape(forbidden_prefix) + r"[\w.]*)",
                re.MULTILINE,
            )
            matches = pattern.findall(source)
            for match in matches:
                issues.append(
                    AuditIssue(
                        "warn",
                        "FORBIDDEN_IMPORT",
                        row.path,
                        f"{reason}: found 'import {match}'",
                        row.layer,
                    )
                )
    return issues


def check_security_patterns(rows: list[ClassifiedFile], root: Path = ROOT) -> list[AuditIssue]:
    """보안 금지 패턴 스캔 (secret/token 출력, env 직접 노출 등)."""
    import re
    issues: list[AuditIssue] = []
    compiled = [(re.compile(pat, re.IGNORECASE | re.MULTILINE), msg)
                for pat, msg in _SECURITY_FORBIDDEN_PATTERNS]
    skip_prefixes = ("tests/", "docs/", "scripts/archive/", "data/")
    skip_exact = {"scripts/ops/codebase_layer_audit.py"}  # 패턴 정의 자체를 스캔 제외
    for row in rows:
        if not row.path.endswith(".py"):
            continue
        if any(row.path.startswith(p) for p in skip_prefixes):
            continue
        if row.path in skip_exact:
            continue
        path = root / row.path
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for pattern, msg in compiled:
            for m in pattern.finditer(source):
                lineno = source[: m.start()].count("\n") + 1
                issues.append(
                    AuditIssue(
                        "warn",
                        "SECURITY_PATTERN",
                        f"{row.path}:{lineno}",
                        msg,
                        row.layer,
                    )
                )
    return issues


def module_name_from_path(path: str) -> str | None:
    if not path.endswith(".py"):
        return None
    if path.startswith(("tests/", "scripts/archive/")) or "/tests/" in path:
        return None
    parts = path[:-3].split("/")
    if not parts or parts[0] not in IMPORT_SCAN_PREFIXES:
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def resolve_import_name(current_module: str, module: str | None, level: int) -> str | None:
    if level <= 0:
        return module
    package = current_module.split(".")[:-1]
    if level > len(package) + 1:
        return None
    base = package[: len(package) - level + 1]
    if module:
        base.extend(module.split("."))
    return ".".join(base) if base else None


def import_owner(module: str, known_modules: set[str]) -> str | None:
    parts = module.split(".")
    for idx in range(len(parts), 0, -1):
        candidate = ".".join(parts[:idx])
        if candidate in known_modules:
            return candidate
    return None


def parse_import_edges(rows: list[ClassifiedFile], root: Path = ROOT) -> dict[str, set[str]]:
    known = {
        module
        for row in rows
        if (module := module_name_from_path(row.path))
    }
    graph: dict[str, set[str]] = {module: set() for module in known}
    for row in rows:
        current = module_name_from_path(row.path)
        if not current:
            continue
        path = root / Path(row.path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                resolved = resolve_import_name(current, node.module, node.level)
                if resolved:
                    imported = [resolved]
            for name in imported:
                owner = import_owner(name, known)
                if owner and owner != current:
                    graph[current].add(owner)
    return graph


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        indexes[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for target in graph.get(node, set()):
            if target not in indexes:
                strongconnect(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[target])

        if lowlinks[node] == indexes[node]:
            component = []
            while True:
                item = stack.pop()
                on_stack.remove(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1:
                components.append(sorted(component))

    for node in sorted(graph):
        if node not in indexes:
            strongconnect(node)
    return sorted(components, key=lambda c: (len(c), c))


def check_circular_imports(rows: list[ClassifiedFile], root: Path = ROOT) -> dict:
    graph = parse_import_edges(rows, root)
    cycles = find_cycles(graph)
    return {
        "module_count": len(graph),
        "edge_count": sum(len(v) for v in graph.values()),
        "cycle_count": len(cycles),
        "cycles": cycles,
    }


def validate_openapi_apps() -> list[dict]:
    results = []
    for module_name in OPENAPI_APP_MODULES:
        result = {"module": module_name, "ok": False, "title": "", "path_count": 0, "error": ""}
        try:
            module = importlib.import_module(module_name)
            app = getattr(module, "app")
            schema = app.openapi()
            result.update(
                {
                    "ok": bool(schema.get("openapi") and schema.get("paths") is not None),
                    "title": str((schema.get("info") or {}).get("title", "")),
                    "path_count": len(schema.get("paths") or {}),
                }
            )
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        results.append(result)
    return results


def validate_pydantic_schema_modules() -> list[dict]:
    results = []
    for module_name in PYDANTIC_SCHEMA_MODULES:
        result = {"module": module_name, "ok": False, "model_count": 0, "error": ""}
        try:
            module = importlib.import_module(module_name)
            try:
                from pydantic import BaseModel
            except Exception as exc:
                raise RuntimeError(f"pydantic import failed: {exc}") from exc
            model_count = 0
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if obj is BaseModel or not issubclass(obj, BaseModel):
                    continue
                if obj.__module__ != module.__name__:
                    continue
                model_count += 1
                if hasattr(obj, "model_json_schema"):
                    obj.model_json_schema()
                elif hasattr(obj, "schema"):
                    obj.schema()
            result.update({"ok": True, "model_count": model_count})
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        results.append(result)
    return results


def validate_json_yaml_files(root: Path = ROOT) -> list[dict]:
    candidates = []
    for path in iter_files(root):
        rel = relpath(path, root)
        if rel.startswith(("docs/reports/", "docs/design/", "tests/fixtures/")):
            continue
        if path.suffix.lower() in {".json", ".yml", ".yaml"}:
            candidates.append(path)
    results = []
    for path in sorted(candidates, key=lambda p: relpath(p, root)):
        item = {"path": relpath(path, root), "ok": False, "error": ""}
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix.lower() == ".json":
                json.loads(text)
            else:
                import yaml

                yaml.safe_load(text)
            item["ok"] = True
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        results.append(item)
    return results


def validate_schemas(root: Path = ROOT) -> dict:
    openapi = validate_openapi_apps()
    pydantic = validate_pydantic_schema_modules()
    documents = validate_json_yaml_files(root)
    return {
        "openapi": openapi,
        "pydantic": pydantic,
        "documents": documents,
        "summary": {
            "openapi_failed": sum(1 for item in openapi if not item["ok"]),
            "pydantic_failed": sum(1 for item in pydantic if not item["ok"]),
            "document_failed": sum(1 for item in documents if not item["ok"]),
            "document_count": len(documents),
        },
    }


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    if not path.exists():
        return {
            "schema_version": 1,
            "thresholds": {},
            "tracked_residuals": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: dict) -> list[ConsistencyCheck]:
    checks: list[ConsistencyCheck] = []
    checks.append(
        ConsistencyCheck(
            "config.schema_version",
            config.get("schema_version") == 1,
            "schema_version must be 1",
        )
    )
    thresholds = config.get("thresholds")
    checks.append(
        ConsistencyCheck(
            "config.thresholds",
            isinstance(thresholds, dict),
            "thresholds must be an object",
        )
    )
    residuals = config.get("tracked_residuals")
    checks.append(
        ConsistencyCheck(
            "config.tracked_residuals",
            isinstance(residuals, list),
            "tracked_residuals must be a list",
        )
    )
    for idx, item in enumerate(residuals or []):
        ok = (
            isinstance(item, dict)
            and bool(item.get("code"))
            and bool(item.get("path"))
            and item.get("status") in {"open", "accepted", "planned"}
        )
        checks.append(
            ConsistencyCheck(
                f"config.tracked_residuals[{idx}]",
                ok,
                "residual must include code, path, and status=open|accepted|planned",
            )
        )
    return checks


def issue_key(issue: dict | AuditIssue) -> tuple[str, str]:
    if isinstance(issue, AuditIssue):
        return issue.code, issue.path
    return str(issue.get("code", "")), str(issue.get("path", ""))


def build_residual_audit(issues: list[AuditIssue], config: dict) -> dict:
    tracked = config.get("tracked_residuals") or []
    tracked_keys = {(str(item.get("code")), str(item.get("path"))) for item in tracked}
    issue_keys = {issue_key(issue) for issue in issues}
    tracked_open = []
    resolved = []
    for item in tracked:
        key = (str(item.get("code")), str(item.get("path")))
        row = dict(item)
        row["present"] = key in issue_keys
        if row["present"]:
            tracked_open.append(row)
        else:
            resolved.append(row)

    untracked_warnings = [
        asdict(issue)
        for issue in issues
        if issue.severity == "warn" and issue_key(issue) not in tracked_keys
    ]
    return {
        "tracked_open": tracked_open,
        "resolved_tracked": resolved,
        "untracked_warning_count": len(untracked_warnings),
        "untracked_warnings": untracked_warnings[:100],
        "summary": {
            "tracked_open_count": len(tracked_open),
            "resolved_tracked_count": len(resolved),
            "tracked_config_count": len(tracked),
            "untracked_warning_count": len(untracked_warnings),
        },
    }


def check_consistency(report: dict, config: dict, root: Path = ROOT) -> dict:
    checks: list[ConsistencyCheck] = []
    checks.extend(validate_config(config))

    files = report.get("files") or []
    issues = report.get("issues") or []
    counts = report.get("counts") or {}
    summary = report.get("summary") or {}
    schema_summary = (report.get("schema_validation") or {}).get("summary") or {}
    circular = report.get("circular_imports") or {}
    thresholds = config.get("thresholds") or {}

    checks.append(
        ConsistencyCheck(
            "summary.file_count",
            summary.get("file_count") == len(files),
            "summary.file_count must equal files length",
        )
    )
    checks.append(
        ConsistencyCheck(
            "summary.issue_count",
            summary.get("issue_count") == len(issues),
            "summary.issue_count must equal issues length",
        )
    )
    checks.append(
        ConsistencyCheck(
            "summary.warn_count",
            summary.get("warn_count") == sum(1 for item in issues if item.get("severity") == "warn"),
            "summary.warn_count must equal warning issue count",
        )
    )
    checks.append(
        ConsistencyCheck(
            "counts.total",
            sum(int(v) for v in counts.values()) == len(files),
            "layer counts must sum to files length",
        )
    )
    unknown_layers = sorted({item.get("layer") for item in files if item.get("layer") not in LAYERS})
    checks.append(
        ConsistencyCheck(
            "layers.known",
            not unknown_layers,
            "all file layer keys must exist in LAYERS",
        )
    )
    doc_text = LAYER_DOC.read_text(encoding="utf-8") if LAYER_DOC.exists() else ""
    missing_doc_layers = [key for key in LAYERS if key != "UNKNOWN" and key not in doc_text]
    checks.append(
        ConsistencyCheck(
            "docs.layer_classification",
            not missing_doc_layers,
            "docs/layer_classification.md must mention every layer key",
        )
    )
    checks.append(
        ConsistencyCheck(
            "threshold.openapi_failed",
            schema_summary.get("openapi_failed", 0) <= thresholds.get("max_openapi_failed", 0),
            "OpenAPI failures must stay within threshold",
        )
    )
    checks.append(
        ConsistencyCheck(
            "threshold.pydantic_failed",
            schema_summary.get("pydantic_failed", 0) <= thresholds.get("max_pydantic_failed", 0),
            "Pydantic schema failures must stay within threshold",
        )
    )
    checks.append(
        ConsistencyCheck(
            "threshold.document_failed",
            schema_summary.get("document_failed", 0) <= thresholds.get("max_document_failed", 0),
            "JSON/YAML document failures must stay within threshold",
        )
    )
    checks.append(
        ConsistencyCheck(
            "threshold.circular_imports",
            circular.get("cycle_count", 0) <= thresholds.get("max_circular_imports", 0),
            "Circular imports must stay within threshold",
        )
    )
    checks.append(
        ConsistencyCheck(
            "threshold.unknown_layers",
            counts.get("UNKNOWN", 0) <= thresholds.get("max_unknown_layer_files", 0),
            "Unknown layer file count must stay within threshold",
        )
    )

    return {
        "ok": all(check.ok for check in checks),
        "checks": [asdict(check) for check in checks],
        "failed": [asdict(check) for check in checks if not check.ok],
    }


def build_report(root: Path = ROOT, config: dict | None = None) -> dict:
    config = config if config is not None else load_config()
    rows = classify_files(root)
    issues = audit(rows, root)
    circular_imports = check_circular_imports(rows, root)
    schema_validation = validate_schemas(root)
    forbidden_import_issues = check_forbidden_imports(rows, root)
    security_pattern_issues = check_security_patterns(rows, root)
    issues.extend(forbidden_import_issues)
    issues.extend(security_pattern_issues)
    for cycle in circular_imports["cycles"]:
        issues.append(
            AuditIssue(
                "warn",
                "CIRCULAR_IMPORT",
                cycle[0],
                "Circular import component: " + " -> ".join(cycle),
                "L4",
            )
        )
    for item in schema_validation["openapi"]:
        if not item["ok"]:
            issues.append(
                AuditIssue("warn", "OPENAPI_SCHEMA_FAILED", item["module"], item["error"], "L8")
            )
    for item in schema_validation["pydantic"]:
        if not item["ok"]:
            issues.append(
                AuditIssue("warn", "PYDANTIC_SCHEMA_FAILED", item["module"], item["error"], "L1")
            )
    for item in schema_validation["documents"]:
        if not item["ok"]:
            issues.append(
                AuditIssue("warn", "DOCUMENT_SCHEMA_FAILED", item["path"], item["error"], "L1")
            )
    issues = sorted(issues, key=lambda x: ({"warn": 0, "info": 1}.get(x.severity, 2), x.code, x.path))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.layer] = counts.get(row.layer, 0) + 1
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "layers": {key: asdict(layer) for key, layer in LAYERS.items()},
        "counts": dict(sorted(counts.items())),
        "files": [asdict(row) for row in rows],
        "issues": [asdict(issue) for issue in issues],
        "circular_imports": circular_imports,
        "schema_validation": schema_validation,
        "gate_results": {
            "forbidden_imports": len(forbidden_import_issues),
            "security_patterns": len(security_pattern_issues),
        },
        "summary": {
            "file_count": len(rows),
            "issue_count": len(issues),
            "warn_count": sum(1 for issue in issues if issue.severity == "warn"),
            "info_count": sum(1 for issue in issues if issue.severity == "info"),
        },
    }
    report["residual_audit"] = build_residual_audit(issues, config)
    report["consistency"] = check_consistency(report, config, root)
    return report


def save_report(report: dict, output: Path = DEFAULT_OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def print_report(report: dict, *, max_issues: int = 25) -> None:
    summary = report["summary"]
    circular = report.get("circular_imports") or {}
    schema = (report.get("schema_validation") or {}).get("summary") or {}
    residual = (report.get("residual_audit") or {}).get("summary") or {}
    consistency = report.get("consistency") or {}
    print("=" * 72)
    print("Codebase layer audit")
    print("=" * 72)
    print(f"files: {summary['file_count']}  issues: {summary['issue_count']}  warnings: {summary['warn_count']}")
    print(
        "imports: "
        f"modules={circular.get('module_count', 0)} "
        f"edges={circular.get('edge_count', 0)} "
        f"cycles={circular.get('cycle_count', 0)}"
    )
    print(
        "schemas: "
        f"openapi_failed={schema.get('openapi_failed', 0)} "
        f"pydantic_failed={schema.get('pydantic_failed', 0)} "
        f"document_failed={schema.get('document_failed', 0)}/"
        f"{schema.get('document_count', 0)}"
    )
    print(
        "residuals: "
        f"tracked_open={residual.get('tracked_open_count', 0)} "
        f"resolved={residual.get('resolved_tracked_count', 0)} "
        f"untracked_warnings={residual.get('untracked_warning_count', 0)}"
    )
    print(f"consistency: {'ok' if consistency.get('ok') else 'failed'}")
    for item in (consistency.get("failed") or [])[:10]:
        print(f"- CONSISTENCY {item['name']}: {item['message']}")
    print("layers:")
    for layer, count in report["counts"].items():
        name = report["layers"].get(layer, {}).get("name", "")
        print(f"- {layer:<7} {count:>4}  {name}")
    print("issues:")
    for issue in report["issues"][:max_issues]:
        print(f"- {issue['severity'].upper():<4} {issue['code']:<28} {issue['path']} :: {issue['message']}")
    if len(report["issues"]) > max_issues:
        print(f"... {len(report['issues']) - max_issues} more issues")


def snapshot(root: Path = ROOT) -> dict[str, tuple[float, int]]:
    return {row.path: (row.mtime, row.size) for row in classify_files(root)}


def diff_snapshot(prev: dict[str, tuple[float, int]], cur: dict[str, tuple[float, int]]) -> list[str]:
    changed = []
    for path in sorted(set(prev) | set(cur)):
        if path not in prev:
            changed.append(f"added:{path}")
        elif path not in cur:
            changed.append(f"deleted:{path}")
        elif prev[path] != cur[path]:
            changed.append(f"modified:{path}")
    return changed


def watch(root: Path, output: Path, interval: float, max_issues: int, config: dict) -> None:
    print(f"watching: {root}")
    previous = snapshot(root)
    report = build_report(root, config)
    save_report(report, output)
    print_report(report, max_issues=max_issues)
    print(f"saved: {output}")
    while True:
        time.sleep(interval)
        current = snapshot(root)
        changes = diff_snapshot(previous, current)
        if not changes:
            continue
        previous = current
        print("=" * 72)
        print(f"changes detected: {len(changes)}")
        for item in changes[:10]:
            print(f"- {item}")
        if len(changes) > 10:
            print(f"... {len(changes) - 10} more changes")
        report = build_report(root, config)
        save_report(report, output)
        print_report(report, max_issues=max_issues)
        print(f"saved: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify codebase files by layer and audit drift.")
    parser.add_argument("--root", default=str(ROOT), help="Repository root.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON report output path.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Residual audit config path.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report to stdout.")
    parser.add_argument("--watch", action="store_true", help="Continuously monitor files and rerun audit on changes.")
    parser.add_argument("--interval", type=float, default=2.0, help="Watch polling interval in seconds.")
    parser.add_argument("--max-issues", type=int, default=25, help="Maximum issues to print in text mode.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    config = load_config(Path(args.config).resolve())

    if args.watch:
        watch(root, output, args.interval, args.max_issues, config)
        return 0

    report = build_report(root, config)
    save_report(report, output)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report, max_issues=args.max_issues)
        print(f"saved: {output}")
    return 1 if report["summary"]["warn_count"] or not report["consistency"]["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
