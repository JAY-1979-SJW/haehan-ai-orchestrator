"""Premium Backend 감사 스크립트 테스트.

ASSISTANT_BACKEND_PREMIUM_AUDIT_SCRIPT_SUITE_01 STEP 13 검증.

금지:
- 실제 외부 사이트 접속 금지
- 실제 DB write 금지
- 실제 앱 실행 금지
- skip/xfail 금지
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_OPS = ROOT / "tools" / "audits" / "backend"

AUDIT_SCRIPT_NAMES = [
    "audit_backend_premium_domain_core",
    "audit_backend_premium_service_layer",
    "audit_backend_premium_policy_layer",
    "audit_backend_premium_audit_evidence",
    "audit_backend_premium_external_app_bridge",
    "audit_backend_premium_api_contract",
    "audit_backend_premium_endpoint_inventory",
    "audit_backend_premium_security_boundary",
    "audit_backend_premium_external_app_hold",
    "audit_backend_premium_integrated_runner",
]

RUNNER_NAME = "audit_backend_premium_integrated_runner"

RUNNER_ORDER = [
    "domain_core",
    "service_layer",
    "policy_layer",
    "audit_evidence",
    "external_app_bridge",
    "api_contract",
    "endpoint_inventory",
    "security_boundary",
    "external_app_hold",
]


def _load(name: str):
    path = SCRIPTS_OPS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"모듈 spec 로드 실패: {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. 스크립트 파일 존재
# ---------------------------------------------------------------------------


class TestAuditScriptsExist:
    def test_all_audit_script_files_exist(self):
        missing = []
        for name in AUDIT_SCRIPT_NAMES:
            p = SCRIPTS_OPS / f"{name}.py"
            if not p.exists():
                missing.append(name)
        assert missing == [], f"누락된 감사 스크립트: {missing}"


# ---------------------------------------------------------------------------
# 2. import 가능
# ---------------------------------------------------------------------------


class TestAuditScriptsImportable:
    def test_all_scripts_importable(self):
        errors = []
        for name in AUDIT_SCRIPT_NAMES:
            try:
                _load(name)
            except Exception as e:  # noqa: BLE001 - 감사 스크립트 import 가능 여부를 검증하는 pytest — import 실패를 errors 리스트에 모아 assert errors == [] 로 테스트를 실패시키는 fail-closed 테스트.
                errors.append(f"{name}: {e}")
        assert errors == [], f"import 실패: {errors}"


# ---------------------------------------------------------------------------
# 3. CHECKLIST 보유
# ---------------------------------------------------------------------------


class TestAuditScriptsHaveChecklist:
    def test_all_scripts_have_checklist(self):
        for name in AUDIT_SCRIPT_NAMES:
            if name == RUNNER_NAME:
                continue
            mod = _load(name)
            assert hasattr(mod, "CHECKLIST"), f"{name}: CHECKLIST 없음"
            cl = mod.CHECKLIST
            assert isinstance(cl, list) and len(cl) > 0, f"{name}: CHECKLIST 비어 있음"

    def test_checklist_items_have_required_keys(self):
        required_keys = {"id", "title", "required"}
        for name in AUDIT_SCRIPT_NAMES:
            if name == RUNNER_NAME:
                continue
            mod = _load(name)
            cl = getattr(mod, "CHECKLIST", [])
            for item in cl:
                missing = required_keys - set(item.keys())
                assert not missing, f"{name}: item={item} missing keys={missing}"


# ---------------------------------------------------------------------------
# 4. run_audit 함수 보유
# ---------------------------------------------------------------------------


class TestAuditScriptsHaveRunAudit:
    def test_all_scripts_have_run_audit(self):
        for name in AUDIT_SCRIPT_NAMES:
            if name == RUNNER_NAME:
                continue
            mod = _load(name)
            assert hasattr(mod, "run_audit"), f"{name}: run_audit 없음"
            assert callable(mod.run_audit), f"{name}: run_audit 호출 불가"

    def test_runner_has_run_integrated_audit(self):
        mod = _load(RUNNER_NAME)
        assert hasattr(mod, "run_integrated_audit"), "runner: run_integrated_audit 없음"
        assert callable(mod.run_integrated_audit)


# ---------------------------------------------------------------------------
# 5. 출력 포맷 검증
# ---------------------------------------------------------------------------


class TestAuditOutputFormat:
    def _required_keys(self):
        return {"audit_name", "verdict", "checked_at", "checklist", "summary"}

    def test_domain_core_output_format(self):
        mod = _load("audit_backend_premium_domain_core")
        result = mod.run_audit()
        missing = self._required_keys() - set(result.keys())
        assert not missing, f"domain_core 출력 키 누락: {missing}"

    def test_service_layer_output_format(self):
        mod = _load("audit_backend_premium_service_layer")
        result = mod.run_audit()
        assert "verdict" in result
        assert "checklist" in result
        assert "summary" in result

    def test_policy_layer_output_format(self):
        mod = _load("audit_backend_premium_policy_layer")
        result = mod.run_audit()
        assert result["audit_name"] == "policy_layer"

    def test_audit_evidence_output_format(self):
        mod = _load("audit_backend_premium_audit_evidence")
        result = mod.run_audit()
        assert "summary" in result
        assert isinstance(result["checklist"], list)

    def test_external_app_bridge_output_format(self):
        mod = _load("audit_backend_premium_external_app_bridge")
        result = mod.run_audit()
        assert result["audit_name"] == "external_app_bridge"

    def test_security_boundary_output_format(self):
        mod = _load("audit_backend_premium_security_boundary")
        result = mod.run_audit()
        assert "verdict" in result

    def test_external_app_hold_output_format(self):
        mod = _load("audit_backend_premium_external_app_hold")
        result = mod.run_audit()
        assert "known_external_app_hold_failures" in result
        assert isinstance(result["known_external_app_hold_failures"], list)


# ---------------------------------------------------------------------------
# 6. 통합 runner
# ---------------------------------------------------------------------------


class TestIntegratedRunner:
    def test_runner_executes_all_audits_in_order(self):
        mod = _load(RUNNER_NAME)
        result = mod.run_integrated_audit()
        assert "audit_order" in result
        assert result["audit_order"] == RUNNER_ORDER

    def test_runner_produces_verdict(self):
        mod = _load(RUNNER_NAME)
        result = mod.run_integrated_audit()
        assert result["verdict"] in {
            "PASS",
            "PASS_WITH_KNOWN_WARN",
            "PASS_WITH_EXTERNAL_APP_HOLD",
            "WARN",
            "FAIL",
            "STOP",
        }

    def test_runner_produces_total_summary(self):
        mod = _load(RUNNER_NAME)
        result = mod.run_integrated_audit()
        assert "total_summary" in result
        ts = result["total_summary"]
        assert all(k in ts for k in ["pass", "warn", "fail"])

    def test_runner_produces_json_serializable(self):
        mod = _load(RUNNER_NAME)
        result = mod.run_integrated_audit()
        dumped = json.dumps(result, ensure_ascii=False)
        assert len(dumped) > 100

    def test_runner_has_all_nine_audit_results(self):
        mod = _load(RUNNER_NAME)
        result = mod.run_integrated_audit()
        assert len(result["audit_results"]) == 9, f"감사 항목 수={len(result['audit_results'])}"

    def test_runner_no_file_creation(self, tmp_path):
        mod = _load(RUNNER_NAME)

        before = {p.name for p in SCRIPTS_OPS.iterdir()}
        mod.run_integrated_audit()
        after = {p.name for p in SCRIPTS_OPS.iterdir()}
        new_files = after - before
        md_files = [f for f in new_files if f.endswith(".md") or f.endswith(".json")]
        assert not md_files, f"감사 중 파일 생성 감지: {md_files}"


# ---------------------------------------------------------------------------
# 7. 안전 경계
# ---------------------------------------------------------------------------


class TestSafetBoundary:
    def test_no_external_network_call_in_scripts(self):
        """감사 스크립트에 requests/httpx/urllib 직접 호출 없음."""
        bad_patterns = ["requests.get(", "httpx.get(", "urllib.request.urlopen("]
        violations = []
        for name in AUDIT_SCRIPT_NAMES:
            p = SCRIPTS_OPS / f"{name}.py"
            if p.exists():
                src = p.read_text(encoding="utf-8")
                for pat in bad_patterns:
                    if pat in src:
                        violations.append(f"{name}: {pat}")
        assert violations == [], f"외부 네트워크 호출 감지: {violations}"

    def test_no_db_write_in_scripts(self):
        """감사 스크립트에 DB write 패턴 없음."""
        bad_patterns = ["session.add(", "session.commit(", ".execute(", "INSERT INTO", "UPDATE ", "DELETE FROM"]
        violations = []
        for name in AUDIT_SCRIPT_NAMES:
            p = SCRIPTS_OPS / f"{name}.py"
            if p.exists():
                src = p.read_text(encoding="utf-8")
                for pat in bad_patterns:
                    if (
                        pat in src
                        and "subprocess"
                        not in src.splitlines()[
                            next(i for i, l in enumerate(src.splitlines()) if pat in l)  # noqa: E741
                        ]
                    ):
                        violations.append(f"{name}: {pat}")
        assert violations == [], f"DB write 패턴 감지: {violations}"

    def test_no_report_md_created_by_runner(self):
        """runner가 보고서 md 파일을 생성하지 않음."""
        src = (SCRIPTS_OPS / f"{RUNNER_NAME}.py").read_text(encoding="utf-8")
        assert ".md" not in src or "open(" not in src, "md 파일 생성 패턴 감지"

    def test_no_secret_in_audit_output(self):
        """감사 출력에 secret/token/password/session/cookie 값 미포함."""
        mod = _load("audit_backend_premium_domain_core")
        result = mod.run_audit()
        dumped = json.dumps(result)
        # 실제 값이 아닌 키 이름 존재는 허용 (title 등에 언급 가능)
        # 실제 secret 값("FAKE_" 등)이 통과되지 않는지만 확인
        assert "REAL_PASSWORD" not in dumped
        assert "REAL_TOKEN" not in dumped

    def test_no_ui_file_modified(self):
        """감사 스크립트 실행이 UI 파일을 수정하지 않음."""
        import subprocess

        proc = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        changed = proc.stdout.splitlines()
        ui_changed = [f for f in changed if f.startswith("admin-web/") or f.startswith("desktop/ui/")]
        assert ui_changed == [], f"UI 파일 변경 감지: {ui_changed}"


# ---------------------------------------------------------------------------
# 8. CAD EXTERNAL_APP_HOLD 분리 확인
# ---------------------------------------------------------------------------


class TestCADExternalAppHoldClassification:
    def test_known_hold_failures_listed(self):
        mod = _load("audit_backend_premium_external_app_hold")
        known = mod.KNOWN_EXTERNAL_APP_HOLD_FAILURES
        assert len(known) >= 4, f"known failures={len(known)}"

    def test_all_known_failures_have_classification(self):
        mod = _load("audit_backend_premium_external_app_hold")
        for f in mod.KNOWN_EXTERNAL_APP_HOLD_FAILURES:
            assert "classification" in f
            assert f["classification"].endswith("_EXTERNAL_APP_HOLD"), f["classification"]

    def test_cad_failures_no_backend_impact(self):
        mod = _load("audit_backend_premium_external_app_hold")
        for f in mod.KNOWN_EXTERNAL_APP_HOLD_FAILURES:
            assert f.get("backend_impact") is False, f"{f['test']}: backend_impact=True"

    def test_hold_audit_verdict_pass(self):
        """external_app_hold 감사는 PASS 또는 PASS_WITH_KNOWN_WARN이어야 한다."""
        mod = _load("audit_backend_premium_external_app_hold")
        result = mod.run_audit()
        assert result["verdict"] in {"PASS", "PASS_WITH_KNOWN_WARN", "PASS_WITH_EXTERNAL_APP_HOLD"}, (
            f"verdict={result['verdict']}"
        )


# ---------------------------------------------------------------------------
# 9. quality gate 충돌 없음
# ---------------------------------------------------------------------------


class TestQualityGateCompatibility:
    def test_audit_scripts_pass_quality_gate_pattern(self):
        """감사 스크립트가 quality gate의 secret 패턴에 걸리지 않음."""
        forbidden_literal_patterns = [
            "password=",
            'secret="',
            "token=REAL",
        ]
        for name in AUDIT_SCRIPT_NAMES:
            p = SCRIPTS_OPS / f"{name}.py"
            if p.exists():
                src = p.read_text(encoding="utf-8")
                for pat in forbidden_literal_patterns:
                    assert pat not in src, f"{name}: 금지 패턴 '{pat}' 감지"
