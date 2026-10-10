"""Classify repository files by architecture layer and audit drift.

Usage:
    python tools/repo_gates/codebase_layer_audit.py --once
    python tools/repo_gates/codebase_layer_audit.py --json
    python tools/repo_gates/codebase_layer_audit.py --watch --interval 2
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import os
import re
import sys
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
DEFAULT_OUTPUT = ROOT / "data" / "codebase_layer_audit_latest.json"
DEFAULT_CONFIG = ROOT / "configs" / "codebase_layer_audit.json"
LAYER_DOC = ROOT / "docs" / "layer_classification.md"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.code_map.layer_rules import (  # noqa: E402,F401 — 규칙은 code_map/layer_rules.py 에 있고 여기서는 같은 이름으로 다시 내보낸다
    _FORBIDDEN_IMPORT_PAIRS,
    LAYER_OVERRIDES,
    SITE_MODULES,
    classify_path,
)

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
    # 빌드 아티팩트 — .gitignore와 동일 원칙, 소스 감사 제외
    "dist",
    "dist-installer",
    "dist-electron",
    "dist-electron-release",
    "dist-electron-setup",
    "build",
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
    "ai_orchestrator.connectors.instagram",
    "ai_orchestrator.browser_tool.worker",
    "services",
    "ai_orchestrator.connectors.g2b",
}

OPENAPI_APP_MODULES = (  # scripts.archive.misc.browser_api_server 는 2026-10-07 scripts/archive/misc 로 보관(실행 대상 아님) — 목록에서 뺌
    "ai_orchestrator.browser_tool.worker.app",
    "ai_orchestrator.asgi",
)

PYDANTIC_SCHEMA_MODULES = (
    "scripts.common.schemas",
    "ai_orchestrator.browser_tool.worker.schemas",
    "ai_orchestrator.browser_tool.schemas",
    "ai_orchestrator.browser_tool.unified_browser_task_schema",
    "ai_orchestrator.server.task_queue_schema",
    "ai_orchestrator.agent_hub.action_schemas",
    "core.agent_runtime.browser.bridge.browser_websocket_schema",
)  # scripts.archive.misc.agent_models 는 2026-10-07 scripts/archive/misc 로 보관(가져다 쓰는 곳 없음) — 목록에서 뺌


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


# 2026-09-29 STD-08(복잡도) 리팩터: classify_path() 하나(C901=35)에 있던 규칙을 "먼저 맞는
# 규칙이 이긴다"는 순서를 그대로 유지한 채 단계별 함수로 쪼갰다. 각 함수는 자기 담당 규칙이
# 안 맞으면 None 을 반환 — 원본의 순차 if/return 체인과 동일하게 동작한다(조건·순서·반환값
# 한 글자도 안 바꿈).


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
    "L1": 1,
    "L2": 2,
    "L3": 3,
    "L4": 4,
    "L5": 5,
    "L6": 6,
    "L7": 7,
    "L8": 8,
    "L9": 9,
    "L10": 10,
    "L11": 11,
    "L12": 12,
    "UNKNOWN": 99,
}


# 보안 금지 패턴: (정규식 패턴, 이유)
# 주의: 오탐 최소화를 위해 변수명을 엄격히 한정 (token_id, token_status 등은 제외)
_SECURITY_FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    # print(password) / print(passwd) / print(secret) 등 — 단독 변수명만
    (r"print\s*\(\s*(password|passwd|pw_\w*|secret\b|api_key\b|apikey\b)\s*\)", "Secret variable printed directly"),
    # os.environ["PASSWORD"] 등 — 대문자 환경변수 직접 출력
    (
        r"print\s*\(\s*os\.environ\s*[\[.]\s*['\"](?:PASSWORD|PASSWD|SECRET|API_KEY|APIKEY)['\"]",
        "Env secret printed directly",
    ),
    # f"{password}" / f"{secret}" — 단독 변수명 보간 (token_id, token_status 등 제외)
    (r"\{(password|passwd|secret\b|api_key\b|apikey\b)\}", "Plain secret variable in f-string or format"),
]


_SECURITY_FORBIDDEN_PATTERNS = [
    (
        r"\b(?:print|logger\.(?:debug|info|warning|error|critical)|logging\."
        r"(?:debug|info|warning|error|critical))\s*\([^)]*\b"
        r"(password|passwd|pw_\w*|secret\b|api_key\b|apikey\b)[^)]*\)",
        "Secret variable printed or logged directly",
    ),
    (
        r"\b(?:print|logger\.(?:debug|info|warning|error|critical)|logging\."
        r"(?:debug|info|warning|error|critical))\s*\([^)]*os\.environ\s*[\[.]"
        r"\s*['\"](?:PASSWORD|PASSWD|SECRET|API_KEY|APIKEY)['\"]",
        "Env secret printed or logged directly",
    ),
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
        except Exception:  # noqa: BLE001 - 레이어/순환참조/보안패턴 정적감사 스크립트 - 개별 파일 읽기 실패시 해당 파일만 continue 로 건너뛰고 감사 계속, 스키마/모델 검증 오류는 result.error 에 기록
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
    issues: list[AuditIssue] = []
    skip_prefixes = ("tests/", "docs/", "scripts/archive/", "data/")
    skip_exact = {"tools/repo_gates/codebase_layer_audit.py"}  # 패턴 정의 자체를 스캔 제외
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
        except Exception:  # noqa: BLE001 - 레이어/순환참조/보안패턴 정적감사 스크립트 - 개별 파일 읽기 실패시 해당 파일만 continue 로 건너뛰고 감사 계속, 스키마/모델 검증 오류는 result.error 에 기록
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_secret_output_call(node):
                continue
            if not any(_expr_exposes_secret(arg) for arg in [*node.args, *[kw.value for kw in node.keywords]]):
                continue
            issues.append(
                AuditIssue(
                    "warn",
                    "SECURITY_PATTERN",
                    f"{row.path}:{getattr(node, 'lineno', 1)}",
                    "Secret variable printed or logged directly",
                    row.layer,
                )
            )
    return issues


def _is_secret_output_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "print"
    if isinstance(func, ast.Attribute):
        if func.attr not in {"debug", "info", "warning", "error", "critical"}:
            return False
        return isinstance(func.value, ast.Name) and func.value.id in {"logger", "logging"}
    return False


def _expr_exposes_secret(node: ast.AST) -> bool:
    sensitive = {"password", "passwd", "pw", "secret", "api_key", "apikey", "token", "cookie"}
    if isinstance(node, ast.Name):
        name = node.id.lower()
        return name in sensitive and not name.endswith("_masked")
    if isinstance(node, ast.Subscript) and _expr_name(node.value) == "os.environ":
        key = _constant_string(node.slice)
        return bool(key and key.lower() in sensitive)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args:
            key = _constant_string(node.args[0])
            return bool(key and key.lower() in sensitive)
    if isinstance(node, ast.JoinedStr):
        has_sensitive_label = any(
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and any(word in value.value.lower() for word in sensitive)
            for value in node.values
        )
        return has_sensitive_label and any(
            isinstance(value, ast.FormattedValue) and _expr_exposes_secret(value.value) for value in node.values
        )
    return any(_expr_exposes_secret(child) for child in ast.iter_child_nodes(node))


def _expr_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _expr_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _constant_string(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


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


def _import_time_nodes(tree: ast.AST) -> list[ast.AST]:
    """모듈 import 시점에 '실제로 실행되는' import 노드만 수집한다.

    함수/메서드(FunctionDef/AsyncFunctionDef) 본문 안의 import 는 호출 시점에만
    실행되어 import-time 순환을 만들지 않는다(순환 회피용 표준 패턴). 이를 그래프
    엣지로 세면 false-positive CIRCULAR_IMPORT 가 발생하므로 제외한다.
    모듈/클래스 본문 및 모듈레벨 if·try·with 안의 import 는 import-time 이므로 포함.
    """
    nodes: list[ast.AST] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue  # 함수 본문(지연 import) → import-time 엣지 아님
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                nodes.append(child)
            walk(child)

    walk(tree)
    return nodes


def parse_import_edges(rows: list[ClassifiedFile], root: Path = ROOT) -> dict[str, set[str]]:
    known = {module for row in rows if (module := module_name_from_path(row.path))}
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
        for node in _import_time_nodes(tree):
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


def _pop_component(stack: list[str], on_stack: set[str], node: str, components: list[list[str]]) -> None:
    component = []
    while True:
        item = stack.pop()
        on_stack.remove(item)
        component.append(item)
        if item == node:
            break
    if len(component) > 1:
        components.append(sorted(component))


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
            _pop_component(stack, on_stack, node, components)

    for node in sorted(graph):
        if node not in indexes:
            strongconnect(node)
    return sorted(components, key=lambda c: (len(c), c))


# ── P1 Gate: Known Debt Allowlists (이전 코드 기존 위반, 신규 추가 금지) ──────

# ROUTER_THINNESS known debt — 거버넌스 도입 전 존재한 파일, 신규 추가 금지
_ROUTER_THINNESS_KNOWN_DEBT: set[str] = {
    "ai_orchestrator/browser_tool/router.py",
    "ai_orchestrator/routers/registry.py",
}

# STORAGE_BOUNDARY known debt — 거버넌스 도입 전 존재한 파일, 신규 추가 금지
# 2026-10-04: 허브 분리로 옮겨진 7개 파일의 경로를 갱신하고(같은 파일, 이미 허용된 부채), 이전에 목록에 없던 DB 직접 사용 6개를 추가 —
# 6개는 DB 모듈 자체이거나(instagram_dm_db·gonobi/db) 연결을 직접 여는 파일이라 L7 헬퍼로 옮기는 별도 리팩터링 대상.
_STORAGE_BOUNDARY_KNOWN_DEBT: set[str] = {
    "ai_orchestrator/connectors/instagram/instagram_dm_db.py",
    "scripts/naver/shopping/naver_search_db.py",
    "scripts/naver/shopping/naver_search_queries.py",
    "scripts/browser/agent/cdp_session_manager.py",
    "ai_orchestrator/auth/registration_code_store.py",
    "apps/ig-comment-dm-bot/core/processed_store.py",
    "core/agent_runtime/browser/approval/browser_approval_db_store.py",
    "scripts/browser/cdp/cdp_db.py",
    "scripts/common/youtube_search_cache.py",
    "scripts/common/critical_logger.py",
    "scripts/naver/automation/error_recovery.py",
    "scripts/naver/automation/scheduler.py",
    "scripts/naver/smartstore/automation/analytics_dashboard.py",
    "scripts/naver/smartstore/automation/competitor_analysis.py",
    "scripts/naver/blog/gonobi/db.py",
    "scripts/naver/blog/management/analytics.py",
    "scripts/naver/blog/management/schedule.py",
    "scripts/naver/shopping/analysis.py",
    "scripts/naver/shopping/crawl.py",
    "scripts/naver/smartstore/product/bulk.py",
    "scripts/common/op_log.py",
    "scripts/browser/navigator/popup_monitor.py",
}

# STORAGE_BOUNDARY test known debt (tests 폴더 내 sqlite3 사용)
_STORAGE_BOUNDARY_TEST_KNOWN_DEBT: set[str] = {
    "tests/naver_search/test_naver_search_db.py",
    "tests/naver_search/test_naver_search_incremental.py",
}


# ── P1 Gate: ROUTER_THINNESS ─────────────────────────────────────────────────

# router 파일에 있어서는 안 되는 패턴 (기존 known debt 제외, 신규 위반만 차단)
_ROUTER_FORBIDDEN_PATTERNS = [
    (r"\bexecute\s*\(", "router에 DB execute() 직접 호출 금지"),
    (r"\bcursor\s*\.", "router에 DB cursor 직접 사용 금지"),
    (r"\bpsycopg2\b", "router에 psycopg2 직접 import 금지"),
    (r"\bsqlite3\b", "router에 sqlite3 직접 import 금지"),
    (r"\bsqlalchemy\b", "router에 sqlalchemy 직접 import 금지"),
    (r"data/sessions/.*\.json", "router에 session 파일 경로 직접 참조 금지"),
    (r"open\s*\(\s*['\"]data/sessions", "router에 session 파일 open 금지"),
]

_ROUTER_FILE_PATTERNS = [
    "scripts/*/router.py",
    "ai_orchestrator/server/*.py",
    "ai_orchestrator.connectors.instagram/*.py",
]


# router 파일임을 판별하는 경로 패턴
def _is_router_file(path: str) -> bool:
    import fnmatch

    for pat in _ROUTER_FILE_PATTERNS:
        if fnmatch.fnmatch(path, pat):
            return True
    return path.endswith("/router.py") or path.endswith("_router.py") or ("/server/" in path and path.endswith(".py"))


def check_router_thinness(rows: list[ClassifiedFile], root: Path = ROOT) -> list[AuditIssue]:
    """ROUTER_THINNESS: router 파일에 DB 직접 접근·session 파일 접근 금지.

    known debt 파일은 INFO로 분류, 신규 위반만 WARN.
    """
    import re

    issues: list[AuditIssue] = []
    compiled = [(re.compile(pat, re.IGNORECASE | re.MULTILINE), msg) for pat, msg in _ROUTER_FORBIDDEN_PATTERNS]
    skip_prefixes = ("tests/", "docs/", "scripts/archive/", "scripts/ops/")
    for row in rows:
        if not row.path.endswith(".py"):
            continue
        if any(row.path.startswith(p) for p in skip_prefixes):
            continue
        if not _is_router_file(row.path):
            continue
        is_known_debt = row.path in _ROUTER_THINNESS_KNOWN_DEBT
        path = root / row.path
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 레이어/순환참조/보안패턴 정적감사 스크립트 - 개별 파일 읽기 실패시 해당 파일만 continue 로 건너뛰고 감사 계속, 스키마/모델 검증 오류는 result.error 에 기록
            continue
        for pattern, msg in compiled:
            for m in pattern.finditer(source):
                lineno = source[: m.start()].count("\n") + 1
                severity = "info" if is_known_debt else "warn"
                issues.append(
                    AuditIssue(
                        severity,
                        "ROUTER_THINNESS",
                        f"{row.path}:{lineno}",
                        f"{'[KNOWN_DEBT] ' if is_known_debt else ''}{msg}",
                        row.layer,
                    )
                )
    return issues


# ── P1 Gate: STORAGE_BOUNDARY ─────────────────────────────────────────────────

# session/cookie 파일 직접 접근 금지 패턴
_STORAGE_FORBIDDEN_PATTERNS = [
    (r"open\s*\(\s*['\"][^'\"]*data/sessions", "data/sessions 파일 직접 open 금지"),
    (r"json\.load\s*\([^)]*sessions", "sessions json.load 금지"),
    (r"read_text\s*\(\s*\)[^#]*sessions", "sessions read_text 금지"),
    (r"Path\s*\(['\"][^'\"]*data/sessions", "data/sessions Path 직접 참조 금지"),
]

# site module + router 에서 DB 직접 접근 금지
_DB_DIRECT_ACCESS_PATTERNS = [
    (r"import\s+psycopg2", "psycopg2 직접 import (storage 계층 외 금지)"),
    (r"import\s+sqlite3", "sqlite3 직접 import (storage 계층 외 금지)"),
    (r"from\s+sqlalchemy", "sqlalchemy 직접 import (storage 계층 외 금지)"),
]

# 이 경로들은 storage 계층이므로 DB 직접 접근 허용
_STORAGE_ALLOWED_PREFIXES = (
    "ai_orchestrator/storage/",
    "ai_orchestrator/persistence/",  # L7 Persistence 계층 자체 — DB 접근이 이 계층의 책임이다(2026-10-01)
    # 기능 폴더로 옮겨 온 저장소 파일 — 원래 persistence/ 에 있던 L7 저장소라 허용이었다(폴더 이동 F1·F9~F16 으로 접두사 밖이 됨). 폴더 전체가 아니라 파일 5개만 정확히 허용한다.
    "ai_orchestrator/agent_dispatch/agent_dispatch_store.py",
    "ai_orchestrator/auth/user_db.py",
    "ai_orchestrator/gongmu/gongmu_store.py",
    "ai_orchestrator/scheduler/scheduled_job_store.py",
    "ai_orchestrator/site_work/work_record_store.py",
    # 도구 폴더로 옮겨진 L7 저장소(F3·F4 묶음 이동 — 층은 registry 에서 그대로 L7 persistence, 위치만 도구 집 안)
    "ai_orchestrator/connectors/hanafax/authorization_store.py",
    "ai_orchestrator/connectors/naver_mail/bulk_store.py",
    "ai_orchestrator/connectors/naver_mail/draft_store.py",
    "scripts/common/sqlite_helpers.py",  # L7 persistence 공용 SQLite 헬퍼 — 흩어진 sqlite3 직접 사용(N6 중복 통합)을 이 한 파일로 모은 것이라 DB 직접 접근이 이 파일의 책임이다(registry 도 L7·persistence)
    "scripts/common/app_paths_migrate.py",  # 저장소 이전 도구 — sqlite 를 backup() 으로 복사하는 것이 본업(2026-10-01)
    "migrations/",
    "scripts/ops/",
    "tests/",
    "docs/",
    "scripts/archive/",
    "data/",
)

# session 접근 검사에서 제외할 경로 (constants 정의만 있는 파일)
_SESSION_SCAN_SKIP = {
    "tools/repo_gates/codebase_layer_audit.py",
    "scripts/gabia/domain_assist.py",  # _FORBIDDEN_SESSION_PATHS 상수 정의만
}


def _storage_boundary_skip(row: ClassifiedFile) -> bool:
    """check_storage_boundary 의 앞쪽 continue 조건들(2026-09-29 STD-08: C901=12>10 분리).

    tools/audits/ 는 2026-10-10 추가 — 감사 스크립트 자신이 탐지용 패턴 문자열로
    "import sqlite3" 같은 금지어를 리스트에 담고 있어(실제 import 아님, 텍스트 매칭용
    헬퍼), 단순 정규식 스캔이 이를 진짜 위반으로 오판했다(audit_standard_ui_package.py
    이동 후 신규 위반으로 잡힘 — PR165 verify FAIL). 감사/게이트 스크립트는 애초에
    L7 storage-boundary 규율 대상이 아니다(docs/·scripts/archive/ 와 같은 이유)."""
    if not row.path.endswith(".py"):
        return True
    if any(row.path.startswith(p) for p in ("docs/", "scripts/archive/", "tools/audits/")):
        return True
    return row.path in _SESSION_SCAN_SKIP


def _scan_session_patterns(
    row: ClassifiedFile, source: str, session_compiled: list, is_known_debt: bool, issues: list[AuditIssue]
) -> None:
    """session 파일 직접 접근 스캔(2026-09-29 STD-08 리팩터로 분리, 로직 동일)."""
    for pattern, msg in session_compiled:
        for m in pattern.finditer(source):
            lineno = source[: m.start()].count("\n") + 1
            severity = "info" if is_known_debt else "warn"
            issues.append(
                AuditIssue(
                    severity,
                    "STORAGE_BOUNDARY",
                    f"{row.path}:{lineno}",
                    f"{'[KNOWN_DEBT] ' if is_known_debt else ''}{msg}",
                    row.layer,
                )
            )


def _scan_db_patterns(
    row: ClassifiedFile,
    source: str,
    db_compiled: list,
    is_known_debt: bool,
    is_test: bool,
    issues: list[AuditIssue],
) -> None:
    """DB 직접 접근 스캔(2026-09-29 STD-08 리팩터로 분리, 로직 동일)."""
    for pattern, msg in db_compiled:
        for m in pattern.finditer(source):
            lineno = source[: m.start()].count("\n") + 1
            severity = "info" if (is_known_debt or is_test) else "warn"
            issues.append(
                AuditIssue(
                    severity,
                    "STORAGE_BOUNDARY",
                    f"{row.path}:{lineno}",
                    f"{'[KNOWN_DEBT] ' if (is_known_debt or is_test) else ''}{msg}",
                    row.layer,
                )
            )


def check_storage_boundary(rows: list[ClassifiedFile], root: Path = ROOT) -> list[AuditIssue]:
    """STORAGE_BOUNDARY: session 파일 직접 접근 및 비storage 계층의 DB 직접 접근 금지.

    known debt 파일은 INFO로 분류, 신규 위반만 WARN.
    """
    import re

    issues: list[AuditIssue] = []
    session_compiled = [
        (re.compile(pat, re.IGNORECASE | re.MULTILINE), msg) for pat, msg in _STORAGE_FORBIDDEN_PATTERNS
    ]
    db_compiled = [(re.compile(pat, re.IGNORECASE | re.MULTILINE), msg) for pat, msg in _DB_DIRECT_ACCESS_PATTERNS]
    all_known_debt = _STORAGE_BOUNDARY_KNOWN_DEBT | _STORAGE_BOUNDARY_TEST_KNOWN_DEBT
    for row in rows:
        if _storage_boundary_skip(row):
            continue
        # 테스트 파일은 세션 금지 패턴을 assert로 포함하므로 session 패턴 스캔 제외
        is_test_file = row.path.startswith("tests/") or "/tests/" in row.path
        is_known_debt = row.path in all_known_debt
        is_test = row.path.startswith("tests/") or "/tests/" in row.path
        path = root / row.path
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 레이어/순환참조/보안패턴 정적감사 스크립트 - 개별 파일 읽기 실패시 해당 파일만 continue 로 건너뛰고 감사 계속, 스키마/모델 검증 오류는 result.error 에 기록
            continue
        # session 파일 직접 접근 (테스트 파일 제외 — 테스트는 금지 검사 코드 포함 가능)
        if not is_test_file:
            _scan_session_patterns(row, source, session_compiled, is_known_debt, issues)
        # DB 직접 접근 (storage 계층 외, test 파일 별도 처리)
        if not any(row.path.startswith(p) for p in _STORAGE_ALLOWED_PREFIXES):
            _scan_db_patterns(row, source, db_compiled, is_known_debt, is_test, issues)
    return issues


# ── P1 Gate: HARDCODED_USER_PATH ─────────────────────────────────────────────

# 사용자 계정 이름이 들어간 절대경로(드라이브:\Users\<이름>\...)나 옛 작업 폴더(드라이브:\work)를 코드에 박으면
# 컴퓨터·계정이 바뀔 때 깨진다(결함 #17). 기존 16개 파일은 2026-10-01 에 모두 고쳐 목록을 비웠다 — 새로 생기면 경고.
_HARDCODED_USER_PATH_KNOWN_DEBT: set[str] = set()  # 2026-10-01 전부 해소 — 신규는 모두 경고

# 따옴표로 시작하는 문자열 안의 `드라이브:\Users\<실제 이름>` 또는 `드라이브:\work`. <user>·%USERNAME% 같은 자리표시자는 제외.
_HARDCODED_USER_PATH_RE = re.compile(
    r"""["'][A-Za-z]:[\\/]+(?:Users[\\/]+(?![<%])[^\\/"'<%]+|work)(?![A-Za-z0-9_])""",
    re.IGNORECASE,
)


def check_hardcoded_user_path(rows: list[ClassifiedFile], root: Path = ROOT) -> list[AuditIssue]:
    """HARDCODED_USER_PATH: 사용자 계정·옛 작업 폴더가 박힌 절대경로 리터럴.

    known debt 파일은 INFO로 분류, 신규 위반만 WARN. 테스트·archive·docs 는 제외.
    """
    issues: list[AuditIssue] = []
    for row in rows:
        path_str = row.path
        if (
            not path_str.endswith(".py")
            or path_str.startswith(("tests/", "docs/", "scripts/archive/"))
            or "/tests/" in path_str
        ):
            continue
        try:
            source = (root / path_str).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        severity = "info" if path_str in _HARDCODED_USER_PATH_KNOWN_DEBT else "warn"
        for lineno, line in enumerate(source.splitlines(), start=1):
            if line.lstrip().startswith("#") or not _HARDCODED_USER_PATH_RE.search(line):
                continue
            issues.append(
                AuditIssue(
                    severity,
                    "HARDCODED_USER_PATH",
                    f"{path_str}:{lineno}",
                    "사용자 계정/옛 작업 폴더가 박힌 절대경로 — 환경변수·scripts/common/data_paths·ai_orchestrator/config 경로 해석을 쓸 것",
                )
            )
    return issues


# ── P1 Gate: SERVER_BROWSER_GUARD ─────────────────────────────────────────────

# 서버 사이드에서 실행 금지 사이트 목록 (로그인/인증/결제/투찰 필요 사이트)
_SERVER_FORBIDDEN_SITES = [
    "gabia.com",
    "my.gabia.com",
    "accounts.gabia.com",
    "g2b.go.kr",
    "www.g2b.go.kr",
    "hiworks.co.kr",
    "hometax.go.kr",
    "unipass.customs.go.kr",
    "login.kakao.com",
    "accounts.kakao.com",
    "nid.naver.com",
    "accounts.google.com",
]

# 위 사이트를 URL로 직접 goto/navigate하는 패턴 (guard 없이)
_SERVER_BROWSER_FORBIDDEN_PATTERNS = [
    (r"goto\s*\(\s*['\"]https?://(?:my\.gabia\.com|accounts\.gabia\.com)", "Gabia 로그인 페이지 server-side goto 금지"),
    (r"goto\s*\(\s*['\"]https?://(?:www\.)?g2b\.go\.kr", "G2B server-side goto 금지"),
    (r"navigate\s*\(\s*['\"]https?://(?:my\.gabia\.com|g2b\.go\.kr)", "금지 사이트 server-side navigate 금지"),
    (r"playwright\s*\.\s*chromium.*launch.*gabia", "Gabia playwright 로그인 server-side 금지"),
    (
        r"cdp_client\.goto\s*\(\s*['\"]https?://(?:my\.gabia\.com|accounts\.gabia\.com)",
        "Gabia CDP login server-side 금지",
    ),
]

# SERVER_BROWSER_GUARD 검사 제외 경로
_BROWSER_GUARD_SKIP_PREFIXES = (
    "tests/",
    "docs/",
    "scripts/archive/",
    "data/",
    "tools/repo_gates/codebase_layer_audit.py",
)


def check_server_browser_guard(rows: list[ClassifiedFile], root: Path = ROOT) -> list[AuditIssue]:
    """SERVER_BROWSER_GUARD: 금지 사이트 server-side 브라우저 직접 실행 패턴 감지."""
    import re

    issues: list[AuditIssue] = []
    compiled = [
        (re.compile(pat, re.IGNORECASE | re.MULTILINE | re.DOTALL), msg)
        for pat, msg in _SERVER_BROWSER_FORBIDDEN_PATTERNS
    ]
    for row in rows:
        if not row.path.endswith(".py"):
            continue
        if any(row.path.startswith(p) for p in _BROWSER_GUARD_SKIP_PREFIXES):
            continue
        if row.path == "tools/repo_gates/codebase_layer_audit.py":
            continue
        path = root / row.path
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 레이어/순환참조/보안패턴 정적감사 스크립트 - 개별 파일 읽기 실패시 해당 파일만 continue 로 건너뛰고 감사 계속, 스키마/모델 검증 오류는 result.error 에 기록
            continue
        for pattern, msg in compiled:
            for m in pattern.finditer(source):
                lineno = source[: m.start()].count("\n") + 1
                issues.append(
                    AuditIssue(
                        "warn",
                        "SERVER_BROWSER_GUARD",
                        f"{row.path}:{lineno}",
                        msg,
                        row.layer,
                    )
                )
    return issues


def _is_package_containment(a: str, b: str) -> bool:
    """a 와 b 가 부모-자식(패키지 containment) 관계인가 (둘 중 하나가 다른 쪽의 조상 패키지)."""
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def check_circular_imports(rows: list[ClassifiedFile], root: Path = ROOT) -> dict:
    graph = parse_import_edges(rows, root)
    # 순환 탐지용 그래프: 패키지↔자기 서브모듈(부모-자식) 엣지 제외.
    # __init__ 가 서브모듈을 재노출하고 서브모듈이 패키지 이름을 import 하는 패턴은
    # cross-component 순환이 아니라 동일 패키지 내부 재노출이므로 false-positive 다.
    # 형제/무관 모듈 간 실제 순환은 그대로 탐지된다.
    cycle_graph = {
        module: {t for t in targets if not _is_package_containment(module, t)} for module, targets in graph.items()
    }
    cycles = find_cycles(cycle_graph)
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
            app = module.app
            schema = app.openapi()
            result.update(
                {
                    "ok": bool(schema.get("openapi") and schema.get("paths") is not None),
                    "title": str((schema.get("info") or {}).get("title", "")),
                    "path_count": len(schema.get("paths") or {}),
                }
            )
        except Exception as exc:  # noqa: BLE001 - 레이어/순환참조/보안패턴 정적감사 스크립트 - 개별 파일 읽기 실패시 해당 파일만 continue 로 건너뛰고 감사 계속, 스키마/모델 검증 오류는 result.error 에 기록
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
        except Exception as exc:  # noqa: BLE001 - 레이어/순환참조/보안패턴 정적감사 스크립트 - 개별 파일 읽기 실패시 해당 파일만 continue 로 건너뛰고 감사 계속, 스키마/모델 검증 오류는 result.error 에 기록
            result["error"] = f"{type(exc).__name__}: {exc}"
        results.append(result)
    return results


def _skip_jsonc_string(text: str, i: int, n: int) -> int:
    j = i + 1
    while j < n:
        if text[j] == "\\" and j + 1 < n:
            j += 2
            continue
        if text[j] == '"':
            j += 1
            break
        j += 1
    return j


def _strip_jsonc(text: str) -> str:
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = _skip_jsonc_string(text, i, n)
            out.append(text[i:j])
            i = j
            continue
        if c == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                j = text.find("\n", i)
                if j == -1:
                    break
                i = j
                continue
            if nxt == "*":
                j = text.find("*/", i + 2)
                if j == -1:
                    break
                i = j + 2
                continue
        out.append(c)
        i += 1
    result = "".join(out)
    return re.sub(r",(\s*[}\]])", r"\1", result)


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
                name = path.name.lower()
                is_jsonc = name.startswith("tsconfig") or name.endswith(".jsonc")
                if is_jsonc:
                    json.loads(_strip_jsonc(text))
                else:
                    json.loads(text)
            else:
                import yaml

                yaml.safe_load(text)
            item["ok"] = True
        except Exception as exc:  # noqa: BLE001 - 레이어/순환참조/보안패턴 정적감사 스크립트 - 개별 파일 읽기 실패시 해당 파일만 continue 로 건너뛰고 감사 계속, 스키마/모델 검증 오류는 result.error 에 기록
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


def tracked_residual_matches(item: dict, issue: AuditIssue) -> bool:
    code = str(item.get("code", ""))
    path = str(item.get("path", ""))
    if code != issue.code:
        return False
    if path == issue.path:
        return True
    if path == "root_legacy_scripts" and issue.code == "ROOT_PY_SCRIPT":
        return "/" not in issue.path and issue.path.endswith(".py")
    return False


def build_residual_audit(issues: list[AuditIssue], config: dict) -> dict:
    tracked = config.get("tracked_residuals") or []
    tracked_open = []
    resolved = []
    for item in tracked:
        row = dict(item)
        row["present"] = any(tracked_residual_matches(row, issue) for issue in issues)
        if row["present"]:
            tracked_open.append(row)
        else:
            resolved.append(row)

    untracked_warnings = [
        asdict(issue)
        for issue in issues
        if issue.severity == "warn" and not any(tracked_residual_matches(item, issue) for item in tracked)
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
    router_thinness_issues = check_router_thinness(rows, root)
    storage_boundary_issues = check_storage_boundary(rows, root)
    server_browser_guard_issues = check_server_browser_guard(rows, root)
    hardcoded_user_path_issues = check_hardcoded_user_path(rows, root)
    issues.extend(forbidden_import_issues)
    issues.extend(security_pattern_issues)
    issues.extend(router_thinness_issues)
    issues.extend(storage_boundary_issues)
    issues.extend(server_browser_guard_issues)
    issues.extend(hardcoded_user_path_issues)
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
            issues.append(AuditIssue("warn", "OPENAPI_SCHEMA_FAILED", item["module"], item["error"], "L8"))
    for item in schema_validation["pydantic"]:
        if not item["ok"]:
            issues.append(AuditIssue("warn", "PYDANTIC_SCHEMA_FAILED", item["module"], item["error"], "L1"))
    for item in schema_validation["documents"]:
        if not item["ok"]:
            issues.append(AuditIssue("warn", "DOCUMENT_SCHEMA_FAILED", item["path"], item["error"], "L1"))
    issues = sorted(issues, key=lambda x: ({"warn": 0, "info": 1}.get(x.severity, 2), x.code, x.path))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.layer] = counts.get(row.layer, 0) + 1
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
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
            "router_thinness": len(router_thinness_issues),
            "storage_boundary": len(storage_boundary_issues),
            "server_browser_guard": len(server_browser_guard_issues),
            "hardcoded_user_path": len(hardcoded_user_path_issues),
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
    residual_summary = (report.get("residual_audit") or {}).get("summary") or {}
    return 1 if residual_summary.get("untracked_warning_count", 0) or not report["consistency"]["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
