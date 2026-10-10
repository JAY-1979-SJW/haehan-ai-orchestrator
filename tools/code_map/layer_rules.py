"""경로 → 층(layer) 분류 규칙과 금지 import 쌍 — 코드맵(scripts/ops/code_map)과 층 감사(scripts/ops/codebase_layer_audit)가 함께 쓴다.

원래 codebase_layer_audit.py 안에 있었으나, 코드맵이 이 규칙을 쓰려고 ops 의 감사 스크립트를 import 하면
scripts/ops ↔ scripts/ops/code_map 순환이 생겨 이쪽(하위)으로 옮겼다. 감사 스크립트는 같은 이름으로 다시 가져다 쓴다(방향: ops → code_map).
"""

from __future__ import annotations

from pathlib import Path

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

# S1 라벨 정정 (2026-09-24): 이름 부분문자열 추측이 실제 역할과 어긋난 파일. 근거는 docs/specs/2026-09-24_repair_s1_dryrun.md
LAYER_OVERRIDES: dict[str, tuple[str, str]] = {
    "ai_orchestrator/core/config.py": ("L1", "shared env/config helper (used by 22 files across layers)"),
    "ai_orchestrator/audit/audit_logger.py": ("L3", "low-level audit log writer, IO wrapper"),
    "scripts/common/op_log.py": ("L3", "low-level operation log writer, IO wrapper"),
    "scripts/common/realtime_audit.py": ("L3", "low-level realtime audit log helper"),
    "scripts/browser/cdp/cdp_db.py": ("L3", "low-level CDP sqlite IO wrapper"),
    "scripts/browser/agent/audit_log.py": ("L3", "low-level audit log writer"),
    "scripts/common/cdp_audit.py": ("L3", "low-level CDP audit log helper"),
    "logging_utils.py": ("L3", "shared logging facade, IO wrapper"),
    "ai_orchestrator/contracts/local_task_protocol.py": ("L1", "task protocol DTO/contract"),
    "ai_orchestrator/safety_policy/secret_redaction.py": ("L1", "redaction helper (L1 per layer definition)"),
    "core/agent_runtime/runtime/result_sanitizer.py": ("L1", "result sanitizer/redaction helper"),
    "core/agent_runtime/common/desktop_config.py": ("L1", "desktop config helper"),
    "core/agent_runtime/connection/network_bypass.py": ("L3", "low-level network IO helper"),
}


def _classify_overrides_and_special(p: str, name: str) -> tuple[str, str] | None:
    if p in LAYER_OVERRIDES:
        return LAYER_OVERRIDES[p]
    if name in {".gitignore", ".gitattributes", ".dockerignore"}:
        return "L1", "repository configuration or policy"
    if p.startswith(("docs/", "scripts/archive/")) or name.startswith(("BOOTSTRAP", "HANDOVER")):
        return "L12", "documentation/report/archive path"
    return None


def _classify_root_level_python(p: str, name: str, suffix: str) -> tuple[str, str] | None:
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
    return None


def _classify_tests(p: str, parts: list[str]) -> tuple[str, str] | None:
    if parts[0] in {"tests"} or "/tests/" in p or "/__tests__/" in p:
        return "L11", "test path"
    if p.startswith("agent/tests/") or p.startswith("ai_orchestrator/tests/"):
        return "L11", "test path"
    return None


def _classify_ui_and_persistence(p: str, name: str) -> tuple[str, str] | None:
    if p.startswith(("admin-web/", "ui/")):
        return "L9", "admin or desktop UI path"
    if p.startswith(("migrations/",)) or "audit" in name or "cdp_db" in name or "op_log" in name:
        return "L7", "persistence or audit path"
    return None


def _classify_server_and_browser(p: str, name: str) -> tuple[str, str] | None:
    if p.startswith(("browser_api/", "ai_orchestrator/server/")):
        return "L8", "server API path"
    if p.startswith("ai_orchestrator/") and ("router" in name or name in {"app.py"}):
        return "L8", "platform API router/app"
    if p.startswith(("local_agent/cad/",)):
        return "L10", "local PC app automation path"
    if p.startswith(("ai_orchestrator/connectors/", "browser_worker/", "adapters/")):
        return "L3", "connector/adapter path"
    if p.startswith(("scripts/explorer/", "scripts/form/")) or name.startswith(
        ("cdp_", "navigator", "popup_", "page_")
    ):
        return "L4", "generic browser automation path"
    if p.startswith(("ai_orchestrator/local_agent/browser/", "scripts/browser/agent/")) or p.startswith(
        "local_agent/browser_"
    ):
        return (
            "L4",
            "local browser automation path",
        )  # CDP 엔진(T4 C12b 에서 scripts/browser/agent/ 로 이동)은 이전과 같은 층
    return None


def _classify_scripts(p: str, parts: list[str], name: str) -> tuple[str, str] | None:
    if not p.startswith("scripts/"):
        return None
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


def _classify_ai_orchestrator(p: str, name: str) -> tuple[str, str] | None:
    if not p.startswith("ai_orchestrator/"):
        return None
    if any(token in name for token in ("schema", "model")):
        return "L1", "platform contract/model"
    if any(token in name for token in ("policy", "gate", "approval", "auth")):
        return "L2", "platform policy/security"
    if any(token in name for token in ("connector", "client")):
        return "L3", "platform connector/client"
    return "L8", "platform application code"


def _classify_agent_and_service(p: str, name: str) -> tuple[str, str] | None:
    if p.startswith(("agent/", "local_agent/")):
        if any(token in name for token in ("policy", "approval")):
            return "L2", "agent policy"
        return "L10", "agent/local automation"
    if p.startswith("services/"):
        return "L8", "standalone service path"
    if p.startswith("apps/"):
        return "L10", "standalone local PC app (apps/*-standalone)"
    if p.startswith(".githooks/"):
        return "L7", "git hook tooling"
    if p.startswith("notice_radar/"):
        return "L6", "notice radar business workflow"
    return None


def _classify_by_suffix(suffix: str) -> tuple[str, str] | None:
    if suffix in {".md"}:
        return "L12", "markdown documentation"
    if suffix in {".yml", ".yaml", ".json", ".sql"}:
        return "L1", "configuration or structured contract"
    return None


def classify_path(path: str) -> tuple[str, str]:
    p = path.replace("\\", "/")
    name = Path(p).name
    suffix = Path(p).suffix.lower()
    parts = p.split("/")

    result = _classify_overrides_and_special(p, name)
    if result is not None:
        return result
    result = _classify_root_level_python(p, name, suffix)
    if result is not None:
        return result
    result = _classify_tests(p, parts)
    if result is not None:
        return result
    result = _classify_ui_and_persistence(p, name)
    if result is not None:
        return result
    result = _classify_server_and_browser(p, name)
    if result is not None:
        return result
    result = _classify_scripts(p, parts, name)
    if result is not None:
        return result
    result = _classify_ai_orchestrator(p, name)
    if result is not None:
        return result
    result = _classify_agent_and_service(p, name)
    if result is not None:
        return result
    result = _classify_by_suffix(suffix)
    if result is not None:
        return result
    return "UNKNOWN", "no matching layer rule"


# 절대 금지 import 패턴: (소스 모듈 prefix, 금지 import prefix, 이유)
_FORBIDDEN_IMPORT_PAIRS: list[tuple[str, str, str]] = [
    # core/domain은 API, UI, DB, 외부 호출 import 금지
    ("scripts.site_engine", "fastapi", "core must not import fastapi"),
    ("scripts.site_engine", "ai_orchestrator.server", "core must not import server layer"),
    ("scripts.site_engine", "ai_orchestrator.asgi", "core must not import server layer"),
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
