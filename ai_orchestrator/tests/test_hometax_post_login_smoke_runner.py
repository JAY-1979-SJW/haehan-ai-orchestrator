"""F-4G-3B — 홈택스 post-login smoke runner 회귀 테스트.

검증 항목:
  A) runner 파일 존재 + 로드 가능.
  B) argparse 기본값 (URL, user_ready_seconds, dwell_after_capture_seconds,
     max_text_chars, out_dir).
  C) summary 카운트 계산 (observer/plan dict → summary dict).
  D) write_results 가 JSON / MD 두 파일을 정상 생성한다.
  E) AST 보안 회귀 — runner 모듈 자체가 금지된 Playwright API / cookie /
     storage / keyboard / mouse 등을 호출하지 않는다.

본 테스트는 실제 브라우저를 띄우지 않는다 (smoke 자체는 사용자 수동 실행).
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT_PATH = _REPO_ROOT / "scripts" / "run_hometax_post_login_smoke.py"


# ─── 모듈 동적 로드 (scripts/ 는 패키지가 아니라 importlib 사용) ──────────

def _load_runner_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "run_hometax_post_login_smoke", str(_SCRIPT_PATH),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def runner_module() -> Any:
    return _load_runner_module()


# ═════════════════════════════════════════════════════════════════════════
# A) 파일 존재 + 로드 가능
# ═════════════════════════════════════════════════════════════════════════

def test_runner_script_file_exists() -> None:
    assert _SCRIPT_PATH.exists(), (
        f"runner 스크립트가 존재하지 않음: {_SCRIPT_PATH}"
    )


def test_runner_module_loads(runner_module: Any) -> None:
    assert hasattr(runner_module, "main")
    assert hasattr(runner_module, "build_arg_parser")
    assert hasattr(runner_module, "build_summary")
    assert hasattr(runner_module, "build_result_payload")
    assert hasattr(runner_module, "write_results")
    assert hasattr(runner_module, "render_markdown")
    assert hasattr(runner_module, "classify_verdict")


# ═════════════════════════════════════════════════════════════════════════
# B) argparse 기본값
# ═════════════════════════════════════════════════════════════════════════

def test_argparse_defaults(runner_module: Any) -> None:
    parser = runner_module.build_arg_parser()
    args = parser.parse_args([])
    assert args.url == "https://www.hometax.go.kr/"
    assert args.user_ready_seconds == 120
    assert args.dwell_after_capture_seconds == 10
    assert args.max_text_chars == 10_000
    assert args.out_dir == os.path.join("runs", "local_agent")
    assert args.print_json is False


def test_argparse_overrides(runner_module: Any) -> None:
    parser = runner_module.build_arg_parser()
    args = parser.parse_args([
        "--url", "https://example.com/",
        "--user-ready-seconds", "30",
        "--dwell-after-capture-seconds", "5",
        "--max-text-chars", "5000",
        "--out-dir", "tmp/out",
        "--print-json",
    ])
    assert args.url == "https://example.com/"
    assert args.user_ready_seconds == 30
    assert args.dwell_after_capture_seconds == 5
    assert args.max_text_chars == 5000
    assert args.out_dir == "tmp/out"
    assert args.print_json is True


# ═════════════════════════════════════════════════════════════════════════
# C) summary / verdict 계산
# ═════════════════════════════════════════════════════════════════════════

def _make_observer(
    *,
    success: bool = True,
    title: str = "홈택스 - 마이홈택스",
    final_url_host_path: str = "www.hometax.go.kr/menu",
    page_state: str = "authenticated",
    text_length: int = 1234,
    links_count: int = 5,
    buttons_count: int = 3,
    forms_count: int = 1,
    inputs_count: int = 2,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "success": success,
        "title": title,
        "final_url_host_path": final_url_host_path,
        "page_state": page_state,
        "text_length": text_length,
        "links_count": links_count,
        "buttons_count": buttons_count,
        "forms_count": forms_count,
        "inputs_count": inputs_count,
        "warnings": list(warnings or []),
        "handoff": {
            "mode": "manual",
            "handoff_seconds": 120,
            "instruction": "user_completes_login_and_navigation_no_credentials",
            "captured_after_handoff": True,
        },
    }


def _make_plan(
    *,
    manual_action_required: bool = False,
    safe_read: int = 2,
    download: int = 1,
    blocked: int = 0,
    warnings: list[str] | None = None,
    page_state: str = "authenticated",
) -> dict[str, Any]:
    def _entries(n: int, kind: str) -> list[dict[str, Any]]:
        return [
            {
                "kind": kind,
                "text": f"{kind}-text-{i}",
                "href": f"/path/{kind}/{i}",
                "matched_tokens": ["조회"],
            }
            for i in range(n)
        ]

    return {
        "site_key": "hometax",
        "page_state": page_state,
        "manual_action_required": manual_action_required,
        "unrecoverable": False,
        "safe_read_candidates": _entries(safe_read, "link"),
        "download_candidates": _entries(download, "link"),
        "blocked_candidates": _entries(blocked, "link"),
        "dangerous_candidates": [],
        "warnings": list(warnings or []),
        "security_program_signals": {"detected": False},
        "login_candidates": {
            "candidate_count": 0,
            "auth_signals": {},
        },
    }


def test_build_summary_counts(runner_module: Any) -> None:
    obs = _make_observer(warnings=["ow"])
    plan = _make_plan(safe_read=4, download=2, blocked=1, warnings=["pw"])
    summary = runner_module.build_summary(
        target_url="https://www.hometax.go.kr/", observer=obs, plan=plan,
    )
    assert summary["success"] is True
    assert summary["title"] == "홈택스 - 마이홈택스"
    assert summary["final_url_host_path"] == "www.hometax.go.kr/menu"
    assert summary["page_state"] == "authenticated"
    assert summary["text_length"] == 1234
    assert summary["links_count"] == 5
    assert summary["buttons_count"] == 3
    assert summary["forms_count"] == 1
    assert summary["inputs_count"] == 2
    assert summary["manual_action_required"] is False
    assert summary["safe_read_candidates_count"] == 4
    assert summary["download_candidates_count"] == 2
    assert summary["blocked_candidates_count"] == 1
    assert summary["warnings_count"] == 2


def test_build_summary_handles_missing_fields(runner_module: Any) -> None:
    summary = runner_module.build_summary(
        target_url="https://www.hometax.go.kr/", observer={}, plan={},
    )
    assert summary["success"] is False
    assert summary["text_length"] == 0
    assert summary["links_count"] == 0
    assert summary["safe_read_candidates_count"] == 0
    assert summary["warnings_count"] == 0


def test_classify_verdict_pass(runner_module: Any) -> None:
    summary = runner_module.build_summary(
        target_url="https://www.hometax.go.kr/",
        observer=_make_observer(),
        plan=_make_plan(safe_read=1, download=0),
    )
    assert runner_module.classify_verdict(summary) == "PASS"


def test_classify_verdict_warn_when_no_candidates(
    runner_module: Any,
) -> None:
    summary = runner_module.build_summary(
        target_url="https://www.hometax.go.kr/",
        observer=_make_observer(),
        plan=_make_plan(safe_read=0, download=0, blocked=0),
    )
    assert runner_module.classify_verdict(summary) == "WARN"


def test_classify_verdict_fail_on_observer_failure(
    runner_module: Any,
) -> None:
    summary = runner_module.build_summary(
        target_url="https://www.hometax.go.kr/",
        observer=_make_observer(success=False),
        plan=_make_plan(safe_read=10),
    )
    assert runner_module.classify_verdict(summary) == "FAIL"


# ═════════════════════════════════════════════════════════════════════════
# D) write_results 가 JSON / MD 를 생성한다
# ═════════════════════════════════════════════════════════════════════════

def test_write_results_creates_json_and_md(
    runner_module: Any, tmp_path: Path,
) -> None:
    out_dir = tmp_path / "out"
    obs = _make_observer()
    plan = _make_plan(safe_read=2, download=1, blocked=1, warnings=["w1"])
    paths = runner_module.write_results(
        out_dir=str(out_dir),
        target_url="https://www.hometax.go.kr/",
        observer=obs,
        plan=plan,
        timestamp="20260425_120000",
    )
    json_path = Path(paths["json_path"])
    md_path = Path(paths["md_path"])
    assert json_path.exists()
    assert md_path.exists()
    assert json_path.name == "hometax_post_login_smoke_20260425_120000.json"
    assert md_path.name == "hometax_post_login_smoke_20260425_120000.md"
    assert paths["verdict"] == "PASS"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["target_url"] == "https://www.hometax.go.kr/"
    assert payload["observer"]["title"] == "홈택스 - 마이홈택스"
    assert payload["plan"]["site_key"] == "hometax"
    assert payload["summary"]["safe_read_candidates_count"] == 2
    assert payload["summary"]["download_candidates_count"] == 1
    assert payload["summary"]["blocked_candidates_count"] == 1

    md_text = md_path.read_text(encoding="utf-8")
    assert "홈택스 post-login smoke 결과" in md_text
    assert "verdict: PASS" in md_text
    assert "safe_read 후보" in md_text
    assert "download 후보" in md_text
    assert "blocked 후보" in md_text


def test_write_results_warn_no_candidates(
    runner_module: Any, tmp_path: Path,
) -> None:
    out_dir = tmp_path / "out"
    obs = _make_observer()
    plan = _make_plan(safe_read=0, download=0, blocked=0)
    paths = runner_module.write_results(
        out_dir=str(out_dir),
        target_url="https://www.hometax.go.kr/",
        observer=obs,
        plan=plan,
        timestamp="20260425_130000",
    )
    assert paths["verdict"] == "WARN"
    md_text = Path(paths["md_path"]).read_text(encoding="utf-8")
    assert "verdict: WARN" in md_text


# ═════════════════════════════════════════════════════════════════════════
# E) AST 보안 회귀 — runner 가 금지 API 를 호출하지 않는다
# ═════════════════════════════════════════════════════════════════════════

_FORBIDDEN_CALL_ATTRS = {
    # 입력/조작 금지.
    "fill", "press", "click", "type",
    "select_option", "set_input_files",
    # 쿠키 / storage_state 절대 금지.
    "cookies", "add_cookies", "storage_state",
    # JS 실행 금지.
    "evaluate", "evaluate_handle",
    # input value 수집 금지.
    "input_value",
    # 다운로드 수집 금지 (page.expect_download / .download).
    "expect_download", "download",
    "save_as", "suggested_filename",
}
_FORBIDDEN_ATTR_USAGE = {"keyboard", "mouse"}
_FORBIDDEN_NAMES = {"localStorage", "sessionStorage"}
_FORBIDDEN_STRING_LITERALS = (
    "--remote-debugging-port",
    "--headless",
    "GOOGLE_PASSWORD",
    "GOOGLE_LOGIN_PASSWORD",
    "GOOGLE_COOKIE",
    "GOOGLE_SESSION",
    "GOOGLE_STORAGE_STATE",
    "GOOGLE_OTP_SECRET",
    "localStorage",
    "sessionStorage",
    "document.cookie",
)


def _scan_runner_forbidden_apis(src: str) -> list[tuple[str, int]]:
    tree = ast.parse(src)
    offenders: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _FORBIDDEN_CALL_ATTRS:
                offenders.append((f"call:.{node.func.attr}(", node.lineno))
        if isinstance(node, ast.Attribute) and \
                node.attr in _FORBIDDEN_ATTR_USAGE:
            offenders.append((f"attr:.{node.attr}", node.lineno))
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            offenders.append((f"name:{node.id}", node.lineno))
    return offenders


def _collect_non_docstring_str_constants(src: str) -> list[str]:
    tree = ast.parse(src)
    docstring_nodes: set[int] = set()

    def _mark_docstring(body: list[ast.stmt]) -> None:
        if not body:
            return
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstring_nodes.add(id(first.value))

    _mark_docstring(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            _mark_docstring(node.body)

    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_nodes:
                continue
            out.append(node.value)
    return out


def test_runner_module_has_no_forbidden_apis() -> None:
    src = _SCRIPT_PATH.read_text(encoding="utf-8")
    offenders = _scan_runner_forbidden_apis(src)
    assert offenders == [], (
        f"forbidden API patterns in run_hometax_post_login_smoke: {offenders}"
    )


def test_runner_module_has_no_forbidden_string_literals() -> None:
    src = _SCRIPT_PATH.read_text(encoding="utf-8")
    code_strings = _collect_non_docstring_str_constants(src)
    offenders: list[tuple[str, str]] = []
    for s in code_strings:
        for lit in _FORBIDDEN_STRING_LITERALS:
            if lit in s and (s, lit) not in offenders:
                offenders.append((s, lit))
    assert offenders == [], (
        "forbidden literals in run_hometax_post_login_smoke code paths: "
        f"{offenders}"
    )


def test_runner_does_not_import_playwright_directly() -> None:
    """runner 자체는 playwright 를 직접 import 하지 않고
    local_agent.browser_manual_handoff 를 통해 간접적으로만 사용해야 한다."""
    src = _SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("playwright"):
                    bad.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").startswith("playwright"):
                bad.append(node.module or "")
    assert bad == [], f"runner must not import playwright directly: {bad}"


def test_runner_imports_observe_after_user_ready(runner_module: Any) -> None:
    """main() 이 observe_after_user_ready 와 build_hometax_controlled_action_plan
    을 사용하는지 정적 확인 (모듈 source 텍스트 기반)."""
    src = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "observe_after_user_ready" in src
    assert "build_hometax_controlled_action_plan" in src


# ═════════════════════════════════════════════════════════════════════════
# F) F-4G-3E — warmup / retry CLI 기본값 + summary 메타
# ═════════════════════════════════════════════════════════════════════════

def test_warmup_retry_defaults(runner_module: Any) -> None:
    parser = runner_module.build_arg_parser()
    args = parser.parse_args([])
    assert args.warmup_url == "https://example.com/"
    assert args.no_warmup is False
    assert args.goto_retries == 2
    assert args.goto_retry_delay_seconds == 1.5
    assert args.goto_timeout_ms == 90_000


def test_warmup_retry_overrides(runner_module: Any) -> None:
    parser = runner_module.build_arg_parser()
    args = parser.parse_args([
        "--warmup-url", "https://other.example.com/",
        "--goto-retries", "3",
        "--goto-retry-delay-seconds", "2.5",
        "--goto-timeout-ms", "60000",
    ])
    assert args.warmup_url == "https://other.example.com/"
    assert args.goto_retries == 3
    assert args.goto_retry_delay_seconds == 2.5
    assert args.goto_timeout_ms == 60_000


def test_no_warmup_flag(runner_module: Any) -> None:
    parser = runner_module.build_arg_parser()
    args = parser.parse_args(["--no-warmup"])
    assert args.no_warmup is True


def test_default_wait_until_remains_networkidle(runner_module: Any) -> None:
    """기본 wait_until 유지 — F-4G-3E 는 wait_until 변경이 아니라 warmup+retry."""
    assert runner_module.DEFAULT_WAIT_UNTIL == "networkidle"


def test_summary_includes_warmup_and_goto_retry_meta(
    runner_module: Any,
) -> None:
    obs = _make_observer()
    obs["warmup_attempted"] = True
    obs["warmup_success"] = True
    obs["warmup_url"] = "https://example.com/"
    obs["goto_attempts_used"] = 2
    plan = _make_plan(safe_read=1, download=0)
    cli = {
        "warmup_url": "https://example.com/",
        "goto_retries": 2,
        "goto_retry_delay_seconds": 1.5,
        "goto_timeout_ms": 90_000,
    }
    summary = runner_module.build_summary(
        target_url="https://www.hometax.go.kr/",
        observer=obs,
        plan=plan,
        cli_options=cli,
    )
    assert summary["warmup_attempted"] is True
    assert summary["warmup_success"] is True
    assert summary["warmup_url"] == "https://example.com/"
    assert summary["goto_attempts_used"] == 2
    assert summary["goto_retries"] == 2
    assert summary["goto_retry_delay_seconds"] == 1.5
    assert summary["goto_timeout_ms"] == 90_000


def test_summary_warmup_meta_defaults_when_observer_missing_keys(
    runner_module: Any,
) -> None:
    summary = runner_module.build_summary(
        target_url="https://www.hometax.go.kr/", observer={}, plan={},
    )
    assert summary["warmup_attempted"] is False
    assert summary["warmup_success"] is False
    assert summary["warmup_url"] == ""
    assert summary["goto_attempts_used"] == 0
    # cli 미주입이면 0/0.0.
    assert summary["goto_retries"] == 0
    assert summary["goto_retry_delay_seconds"] == 0.0
    assert summary["goto_timeout_ms"] == 0


def test_write_results_md_contains_warmup_section(
    runner_module: Any, tmp_path: Path,
) -> None:
    out_dir = tmp_path / "out"
    obs = _make_observer()
    obs["warmup_attempted"] = True
    obs["warmup_success"] = True
    obs["warmup_url"] = "https://example.com/"
    obs["goto_attempts_used"] = 1
    plan = _make_plan(safe_read=1)
    cli = {
        "warmup_url": "https://example.com/",
        "goto_retries": 2,
        "goto_retry_delay_seconds": 1.5,
        "goto_timeout_ms": 90_000,
    }
    paths = runner_module.write_results(
        out_dir=str(out_dir),
        target_url="https://www.hometax.go.kr/",
        observer=obs,
        plan=plan,
        timestamp="20260425_140000",
        cli_options=cli,
    )
    md_text = Path(paths["md_path"]).read_text(encoding="utf-8")
    assert "warmup / goto retry" in md_text
    assert "warmup_attempted: True" in md_text
    assert "goto_attempts_used: 1" in md_text
    assert "goto_retries: 2" in md_text
    assert "goto_timeout_ms: 90000" in md_text


def test_runner_main_passes_warmup_args_to_observe(
    runner_module: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """main() 이 CLI 옵션을 observe_after_user_ready 의 warmup/retry 인자로
    그대로 전달하는지 monkey-patch 로 검증."""
    captured: dict[str, Any] = {}

    def _fake_observe(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "success": True,
            "title": "ok",
            "final_url_host_path": "www.hometax.go.kr",
            "page_state": "authenticated",
            "warnings": [],
            "warmup_attempted": True,
            "warmup_success": True,
            "warmup_url": kwargs.get("warmup_url") or "",
            "goto_attempts_used": 1,
            "handoff": {
                "mode": "manual",
                "handoff_seconds": 0,
                "instruction": (
                    "user_completes_login_and_navigation_no_credentials"
                ),
                "captured_after_handoff": True,
            },
        }

    def _fake_plan(_obs: Any) -> dict[str, Any]:
        return {
            "site_key": "hometax",
            "page_state": "authenticated",
            "manual_action_required": False,
            "unrecoverable": False,
            "safe_read_candidates": [{"kind": "link", "text": "조회"}],
            "download_candidates": [],
            "blocked_candidates": [],
            "dangerous_candidates": [],
            "warnings": [],
            "security_program_signals": {"detected": False},
            "login_candidates": {"candidate_count": 0, "auth_signals": {}},
        }

    # monkeypatch 의 대상은 main() 내부에서 import 되는 심볼 — 모듈 레벨
    # import 가 아니라 main() 안에서 import 되므로, 원본 모듈 자체를 패치.
    import local_agent.browser_manual_handoff as _bmh
    import local_agent.site_adapters.hometax as _hxa
    monkeypatch.setattr(
        _bmh, "observe_after_user_ready", _fake_observe,
    )
    monkeypatch.setattr(
        _hxa, "build_hometax_controlled_action_plan", _fake_plan,
    )

    out_dir = tmp_path / "out"
    rc = runner_module.main([
        "--out-dir", str(out_dir),
        "--user-ready-seconds", "0",
        "--dwell-after-capture-seconds", "0",
        "--warmup-url", "https://example.com/",
        "--goto-retries", "2",
        "--goto-retry-delay-seconds", "1.5",
        "--goto-timeout-ms", "90000",
    ])
    assert rc == 0
    assert captured.get("warmup_url") == "https://example.com/"
    assert captured.get("goto_retries") == 2
    assert captured.get("goto_retry_delay_seconds") == 1.5
    assert captured.get("goto_timeout_ms") == 90_000
    assert captured.get("wait_until") == "networkidle"


def test_runner_main_no_warmup_passes_none_warmup_url(
    runner_module: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_observe(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "success": True,
            "title": "ok",
            "final_url_host_path": "www.hometax.go.kr",
            "page_state": "authenticated",
            "warnings": [],
            "warmup_attempted": False,
            "warmup_success": False,
            "warmup_url": "",
            "goto_attempts_used": 1,
            "handoff": {
                "mode": "manual",
                "handoff_seconds": 0,
                "instruction": (
                    "user_completes_login_and_navigation_no_credentials"
                ),
                "captured_after_handoff": True,
            },
        }

    def _fake_plan(_obs: Any) -> dict[str, Any]:
        return {
            "site_key": "hometax",
            "page_state": "authenticated",
            "manual_action_required": False,
            "unrecoverable": False,
            "safe_read_candidates": [{"kind": "link", "text": "x"}],
            "download_candidates": [],
            "blocked_candidates": [],
            "dangerous_candidates": [],
            "warnings": [],
            "security_program_signals": {"detected": False},
            "login_candidates": {"candidate_count": 0, "auth_signals": {}},
        }

    import local_agent.browser_manual_handoff as _bmh
    import local_agent.site_adapters.hometax as _hxa
    monkeypatch.setattr(
        _bmh, "observe_after_user_ready", _fake_observe,
    )
    monkeypatch.setattr(
        _hxa, "build_hometax_controlled_action_plan", _fake_plan,
    )

    out_dir = tmp_path / "out"
    rc = runner_module.main([
        "--out-dir", str(out_dir),
        "--user-ready-seconds", "0",
        "--dwell-after-capture-seconds", "0",
        "--no-warmup",
    ])
    assert rc == 0
    assert captured.get("warmup_url") is None
