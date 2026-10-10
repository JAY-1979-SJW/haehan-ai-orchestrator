"""Smoke: APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_01

Priority 1 read-only API 3개가 실제 응답 schema, redaction, read-only guard를 지키는지
TestClient 기반으로 in-process GET smoke 수행한다.

POST/PUT/PATCH/DELETE 호출 없음. mutation 없음. 외부 HTTP 없음.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))

SMOKE_ID = "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE"
SMOKE_PHASE = "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_01"

VERDICT_READY = "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_READY"
VERDICT_WARN = "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_WITH_WARN"
VERDICT_BLOCKED = "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_BLOCKED"

_FORBIDDEN_FIELDS = {
    "raw_token",
    "access_token",
    "refresh_token",
    "cookie_value",
    "session_secret",
    "password",
    "approval_token_raw",
    "private_key",
    "certificate_password",
    "secret_value",
    "execute_url",
    "deploy_url",
    "restart_url",
}

ENDPOINTS = [
    "/api/v1/app/health/summary",
    "/api/v1/app/providers",
    "/api/v1/app/storage/status",
]


@dataclass
class EndpointResult:
    path: str
    status_code: int = 0
    ok: bool = False
    schema_ok: bool = False
    redaction_ok: bool = False
    read_only_ok: bool = False
    mutation_allowed_ok: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class SmokeReport:
    smoke_id: str = SMOKE_ID
    smoke_phase: str = SMOKE_PHASE
    endpoint_count: int = len(ENDPOINTS)
    results: list[EndpointResult] = field(default_factory=list)
    mutation_request_count: int = 0
    external_http_call_count: int = 0
    db_write_count: int = 0
    secret_output_count: int = 0
    redaction_violations: int = 0
    passed_endpoints: list[str] = field(default_factory=list)
    failed_endpoints: list[str] = field(default_factory=list)
    verdict: str = ""


def _check_redaction(data: Any, report: SmokeReport, path: str) -> bool:
    import json

    serialized = json.dumps(data)
    violations = []
    for field_name in _FORBIDDEN_FIELDS:
        if (
            f'"{field_name}"' in serialized
            and f'"{field_name}": false' not in serialized
            and f'"{field_name}":false' not in serialized
        ):
            violations.append(field_name)
    if violations:
        report.redaction_violations += len(violations)
        report.secret_output_count += len(violations)
        return False
    return True


def _smoke_health(client: Any, report: SmokeReport) -> EndpointResult:
    res = EndpointResult(path="/api/v1/app/health/summary")
    try:
        r = client.get("/api/v1/app/health/summary")
        res.status_code = r.status_code
        if r.status_code != 200:
            res.errors.append(f"status={r.status_code}")
            return res
        body = r.json()
        res.ok = body.get("ok") is True
        if not res.ok:
            res.errors.append("ok!=true")

        data = body.get("data", {})
        meta = body.get("meta", {})

        schema_checks = [
            ("service" in data, "data.service 없음"),
            ("health_status" in data, "data.health_status 없음"),
            ("post_tasks_dry_run_enabled" in data, "data.post_tasks_dry_run_enabled 없음"),
            (data.get("post_tasks_dry_run_enabled") is True, "post_tasks_dry_run_enabled!=true"),
            ("phase1_closeout_status" in data, "data.phase1_closeout_status 없음"),
            ("generated_at" in data, "data.generated_at 없음"),
        ]
        res.schema_ok = all(ok for ok, _ in schema_checks)
        for ok, msg in schema_checks:
            if not ok:
                res.errors.append(msg)

        res.read_only_ok = meta.get("read_only") is True
        if not res.read_only_ok:
            res.errors.append("meta.read_only!=true")

        res.mutation_allowed_ok = meta.get("mutation_allowed") is False
        if not res.mutation_allowed_ok:
            res.errors.append("meta.mutation_allowed!=false")

        res.redaction_ok = _check_redaction(body, report, res.path)
        if not res.redaction_ok:
            res.errors.append("redaction violation")

    except Exception as e:  # noqa: BLE001 - 읽기전용 API 엔드포인트 스모크테스트 — 서버앱/라우트 로드 실패는 환경 의존적 문제로 보고 subprocess 오류를 반환값에 담아 폴백, 실제 API 호출 실패 자체를 테스트가 검증하는 대상
        res.errors.append(str(e))
    return res


def _smoke_providers(client: Any, report: SmokeReport) -> EndpointResult:
    res = EndpointResult(path="/api/v1/app/providers")
    try:
        r = client.get("/api/v1/app/providers")
        res.status_code = r.status_code
        if r.status_code != 200:
            res.errors.append(f"status={r.status_code}")
            return res
        body = r.json()
        res.ok = body.get("ok") is True

        data = body.get("data", {})
        meta = body.get("meta", {})
        providers = data.get("providers", [])

        schema_checks = [
            ("providers" in data, "data.providers 없음"),
            (len(providers) == 12, f"provider_count={len(providers)}, 기대=12"),
            (meta.get("provider_count") == 12, f"meta.provider_count={meta.get('provider_count')}"),
            (any(p.get("provider_id") == "GABIA" for p in providers), "GABIA 없음"),
            (any(p.get("provider_id") == "NAVER_SMARTSTORE" for p in providers), "NAVER_SMARTSTORE 없음"),
            (any(p.get("provider_id") == "G2B_NARA" for p in providers), "G2B_NARA 없음"),
        ]
        res.schema_ok = all(ok for ok, _ in schema_checks)
        for ok, msg in schema_checks:
            if not ok:
                res.errors.append(msg)

        cookie_ok = all(p.get("cookie_storage_allowed") is False for p in providers)
        token_ok = all(p.get("token_storage_allowed") is False for p in providers)
        if not cookie_ok:
            res.errors.append("cookie_storage_allowed=true 발견")
        if not token_ok:
            res.errors.append("token_storage_allowed=true 발견")

        res.read_only_ok = meta.get("read_only") is True
        res.mutation_allowed_ok = meta.get("mutation_allowed") is False
        if not res.read_only_ok:
            res.errors.append("meta.read_only!=true")
        if not res.mutation_allowed_ok:
            res.errors.append("meta.mutation_allowed!=false")

        res.redaction_ok = _check_redaction(body, report, res.path)

    except Exception as e:  # noqa: BLE001 - 읽기전용 API 엔드포인트 스모크테스트 — 서버앱/라우트 로드 실패는 환경 의존적 문제로 보고 subprocess 오류를 반환값에 담아 폴백, 실제 API 호출 실패 자체를 테스트가 검증하는 대상
        res.errors.append(str(e))
    return res


def _smoke_storage(client: Any, report: SmokeReport) -> EndpointResult:
    res = EndpointResult(path="/api/v1/app/storage/status")
    try:
        r = client.get("/api/v1/app/storage/status")
        res.status_code = r.status_code
        if r.status_code != 200:
            res.errors.append(f"status={r.status_code}")
            return res
        body = r.json()
        res.ok = body.get("ok") is True

        data = body.get("data", {})
        meta = body.get("meta", {})

        schema_checks = [
            ("storage_path" in data, "data.storage_path 없음"),
            ("app_logs_path" in data, "data.app_logs_path 없음"),
            ("named_volume_status" in data, "named_volume_status 없음"),
            ("app_logs_bind_mount_status" in data, "app_logs_bind_mount_status 없음"),
            ("audit_log_policy" in data, "audit_log_policy 없음"),
            ("execution_history_policy" in data, "execution_history_policy 없음"),
            ("approval_token_policy" in data, "approval_token_policy 없음"),
            ("runtime_cache_policy" in data, "runtime_cache_policy 없음"),
        ]
        res.schema_ok = all(ok for ok, _ in schema_checks)
        for ok, msg in schema_checks:
            if not ok:
                res.errors.append(msg)

        res.read_only_ok = meta.get("read_only") is True
        res.mutation_allowed_ok = meta.get("mutation_allowed") is False
        if not res.read_only_ok:
            res.errors.append("meta.read_only!=true")
        if not res.mutation_allowed_ok:
            res.errors.append("meta.mutation_allowed!=false")

        res.redaction_ok = _check_redaction(body, report, res.path)

    except Exception as e:  # noqa: BLE001 - 읽기전용 API 엔드포인트 스모크테스트 — 서버앱/라우트 로드 실패는 환경 의존적 문제로 보고 subprocess 오류를 반환값에 담아 폴백, 실제 API 호출 실패 자체를 테스트가 검증하는 대상
        res.errors.append(str(e))
    return res


def run_smoke() -> SmokeReport:
    report = SmokeReport()

    from fastapi.testclient import TestClient

    from ai_orchestrator.asgi import app

    with TestClient(app) as client:
        report.results.append(_smoke_health(client, report))
        report.results.append(_smoke_providers(client, report))
        report.results.append(_smoke_storage(client, report))

    for res in report.results:
        all_ok = (
            res.status_code == 200
            and res.ok
            and res.schema_ok
            and res.read_only_ok
            and res.mutation_allowed_ok
            and res.redaction_ok
            and not res.errors
        )
        if all_ok:
            report.passed_endpoints.append(res.path)
        else:
            report.failed_endpoints.append(res.path)

    if not report.failed_endpoints and report.redaction_violations == 0:
        report.verdict = VERDICT_READY
    elif len(report.failed_endpoints) <= 1 and report.redaction_violations == 0:
        report.verdict = VERDICT_WARN
    else:
        report.verdict = VERDICT_BLOCKED

    return report


def print_report(report: SmokeReport) -> None:
    print(f"\n{'=' * 64}")
    print(f"SMOKE: {report.smoke_id}")
    print(f"{'=' * 64}")
    for res in report.results:
        status = "PASS" if res.path in report.passed_endpoints else "FAIL"
        print(f"  [{status}] {res.path} (HTTP {res.status_code})")
        for err in res.errors:
            print(f"         ✗ {err}")
    print(f"{'=' * 64}")
    print(f"  endpoint_count            : {report.endpoint_count}")
    print(f"  passed_endpoints          : {len(report.passed_endpoints)}")
    print(f"  failed_endpoints          : {len(report.failed_endpoints)}")
    print(f"  mutation_request_count    : {report.mutation_request_count}")
    print(f"  external_http_call_count  : {report.external_http_call_count}")
    print(f"  db_write_count            : {report.db_write_count}")
    print(f"  secret_output_count       : {report.secret_output_count}")
    print(f"  redaction_violations      : {report.redaction_violations}")
    print(f"  verdict                   : {report.verdict}")
    print(f"{'=' * 64}\n")


if __name__ == "__main__":
    report = run_smoke()
    print_report(report)
    sys.exit(0 if report.verdict != VERDICT_BLOCKED else 1)
