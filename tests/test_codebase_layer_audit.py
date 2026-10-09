from pathlib import Path

from tools.repo_gates.codebase_layer_audit import (
    AuditIssue,
    ClassifiedFile,
    audit,
    build_residual_audit,
    check_consistency,
    check_hardcoded_user_path,
    check_security_patterns,
    classify_path,
    diff_snapshot,
    find_cycles,
    resolve_import_name,
    validate_config,
)


def test_classify_site_module_layers():
    assert classify_path("scripts/hiworks/router.py")[0] == "L5"
    assert classify_path("scripts/hiworks/mail_batch.py")[0] == "L6"
    assert classify_path("scripts/eum/sales_mail.py")[0] == "L6"


def test_classify_core_layers():
    assert classify_path("scripts/common/gate.py")[0] == "L2"
    assert classify_path("scripts/browser/page/web_connector.py")[0] == "L3"
    assert classify_path("scripts/browser/cdp_client.py")[0] == "L4"
    assert classify_path("scripts/browser/cdp/cdp_db.py")[0] == "L3"  # S1 정정: 저수준 IO 래퍼
    assert classify_path("admin-web/src/app/page.tsx")[0] == "L9"
    assert classify_path("agent/excel/workflows.py")[0] == "L10"
    assert classify_path("docs/layer_classification.md")[0] == "L12"


def test_audit_detects_root_python_script():
    rows = [
        ClassifiedFile("loose_script.py", "L4", "generic script automation", 10, 1.0),
    ]
    issues = audit(rows, root=Path())
    assert any(issue.code == "ROOT_PY_SCRIPT" for issue in issues)


def test_audit_detects_fat_hiworks_router():
    rows = [
        ClassifiedFile("scripts/hiworks/router.py", "L5", "site module", 13000, 1.0),
    ]
    issues = audit(rows, root=Path())
    assert (
        AuditIssue(
            "warn",
            "FAT_SITE_ROUTER",
            "scripts/hiworks/router.py",
            "Hiworks router contains too much logic; split into schemas/gates/explorer/mail/workflows.",
            "L5",
        )
        in issues
    )


def test_diff_snapshot_detects_added_modified_deleted():
    prev = {"a.py": (1.0, 10), "b.py": (1.0, 10)}
    cur = {"b.py": (2.0, 10), "c.py": (1.0, 10)}
    assert diff_snapshot(prev, cur) == ["deleted:a.py", "modified:b.py", "added:c.py"]


def test_find_cycles_detects_strong_components():
    graph = {
        "pkg.a": {"pkg.b"},
        "pkg.b": {"pkg.c"},
        "pkg.c": {"pkg.a"},
        "pkg.d": set(),
    }
    assert find_cycles(graph) == [["pkg.a", "pkg.b", "pkg.c"]]


def test_resolve_relative_import_name():
    assert resolve_import_name("pkg.site.router", "schemas", 1) == "pkg.site.schemas"
    assert resolve_import_name("pkg.site.sub.module", "utils", 2) == "pkg.site.utils"


def test_residual_audit_tracks_configured_issue():
    issues = [
        AuditIssue("warn", "CIRCULAR_IMPORT", "pkg.a", "cycle", "L4"),
        AuditIssue("warn", "ROOT_PY_SCRIPT", "x.py", "root", "L4"),
    ]
    config = {
        "tracked_residuals": [
            {"code": "CIRCULAR_IMPORT", "path": "pkg.a", "status": "open"},
            {"code": "FAT_SITE_ROUTER", "path": "scripts/hiworks/router.py", "status": "open"},
        ]
    }
    residual = build_residual_audit(issues, config)
    assert residual["summary"]["tracked_open_count"] == 1
    assert residual["summary"]["resolved_tracked_count"] == 1
    assert residual["summary"]["untracked_warning_count"] == 1


def test_residual_audit_tracks_root_script_group():
    issues = [
        AuditIssue("warn", "ROOT_PY_SCRIPT", "app.py", "root", "L4"),
        AuditIssue("warn", "ROOT_PY_SCRIPT", "executor.py", "root", "L4"),
    ]
    config = {
        "tracked_residuals": [
            {"code": "ROOT_PY_SCRIPT", "path": "root_legacy_scripts", "status": "accepted"},
        ]
    }

    residual = build_residual_audit(issues, config)

    assert residual["summary"]["tracked_open_count"] == 1
    assert residual["summary"]["untracked_warning_count"] == 0


def test_security_patterns_ignore_auth_header_construction(tmp_path):
    source = tmp_path / "client.py"
    source.write_text(
        'headers = {"Authorization": f"Bearer {api_key}"}\nsafe = f"{username}:{password}"\n',
        encoding="utf-8",
    )
    rows = [ClassifiedFile("client.py", "L3", "test", 1, 1.0)]

    issues = check_security_patterns(rows, root=tmp_path)

    assert issues == []


def test_security_patterns_detect_secret_logging(tmp_path):
    source = tmp_path / "client.py"
    source.write_text(
        "logger.info('key %s', api_key)\nprint(f\"password: {result.get('password')}\")\n",
        encoding="utf-8",
    )
    rows = [ClassifiedFile("client.py", "L3", "test", 1, 1.0)]

    issues = check_security_patterns(rows, root=tmp_path)

    assert [issue.code for issue in issues] == ["SECURITY_PATTERN", "SECURITY_PATTERN"]


def test_validate_config_accepts_residual_schema():
    checks = validate_config(
        {
            "schema_version": 1,
            "thresholds": {},
            "tracked_residuals": [
                {"code": "X", "path": "pkg.x", "status": "planned"},
            ],
        }
    )
    assert all(check.ok for check in checks)


def test_check_consistency_validates_summary_counts():
    report = {
        "files": [{"path": "a.py", "layer": "L4"}],
        "issues": [{"severity": "warn", "code": "X", "path": "a.py"}],
        "counts": {"L4": 1, "UNKNOWN": 0},
        "summary": {"file_count": 1, "issue_count": 1, "warn_count": 1},
        "schema_validation": {"summary": {"openapi_failed": 0, "pydantic_failed": 0, "document_failed": 0}},
        "circular_imports": {"cycle_count": 0},
    }
    config = {
        "schema_version": 1,
        "thresholds": {
            "max_openapi_failed": 0,
            "max_pydantic_failed": 0,
            "max_document_failed": 0,
            "max_circular_imports": 0,
            "max_unknown_layer_files": 0,
        },
        "tracked_residuals": [],
    }
    result = check_consistency(report, config)
    assert result["ok"] is True


def test_strip_jsonc_line_and_block_comments():
    import json

    from tools.repo_gates.codebase_layer_audit import _strip_jsonc

    src = """// header comment
{
    /* block comment
       multi-line */
    "a": 1,  // trailing line comment
    "b": 2
}
"""
    data = json.loads(_strip_jsonc(src))
    assert data == {"a": 1, "b": 2}


def test_strip_jsonc_preserves_comment_like_strings():
    import json

    from tools.repo_gates.codebase_layer_audit import _strip_jsonc

    src = '{"url": "http://example.com/path", "alias": "@/*", "blk": "/* not a comment */"}'
    data = json.loads(_strip_jsonc(src))
    assert data["url"] == "http://example.com/path"
    assert data["alias"] == "@/*"
    assert data["blk"] == "/* not a comment */"


def test_strip_jsonc_allows_trailing_commas():
    import json

    from tools.repo_gates.codebase_layer_audit import _strip_jsonc

    src = '{"arr": [1, 2, 3,], "obj": {"k": "v",},}'
    data = json.loads(_strip_jsonc(src))
    assert data == {"arr": [1, 2, 3], "obj": {"k": "v"}}


# ── 순환 탐지 정확화 (모듈 분리 기준서) ──────────────────────────────────────


def test_import_time_nodes_excludes_function_local():
    """함수 본문 안 import 는 import-time 엣지로 세지 않는다(순환 false-positive 방지)."""
    import ast

    from tools.repo_gates.codebase_layer_audit import _import_time_nodes

    src = (
        "import a\n"
        "from b import x\n"
        "def f():\n"
        "    import c\n"
        "    from d import y\n"
        "class K:\n"
        "    import e\n"  # 클래스 본문은 import-time
    )
    names = []
    for n in _import_time_nodes(ast.parse(src)):
        if isinstance(n, ast.Import):
            names += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            names.append(n.module)
    assert "a" in names and "b" in names and "e" in names
    assert "c" not in names and "d" not in names  # 함수 내부 제외


def test_package_containment_excluded_from_cycles():
    """부모-자식(패키지 containment) 관계는 cross-component 순환에서 제외."""
    from tools.repo_gates.codebase_layer_audit import _is_package_containment

    assert _is_package_containment("a.b", "a.b.c") is True
    assert _is_package_containment("a.b.c", "a.b") is True
    assert _is_package_containment("a.b", "a.b") is True
    assert _is_package_containment("a.b", "a.c") is False  # 형제는 실제 순환으로 탐지
    assert _is_package_containment("a.b", "x.y") is False


_BS = chr(92)


def _win(*parts):
    """테스트 입력용 윈도우 경로 문자열(역슬래시 이스케이프 혼동을 피하려고 조립한다)."""
    return _BS.join(parts)


def _hardcoded_rows_and_source(tmp_path, rel, lines):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [ClassifiedFile(rel, "L4", "test", 1, 1.0)]


def test_hardcoded_user_path_flags_new_file_as_warn(tmp_path):
    rows = _hardcoded_rows_and_source(
        tmp_path,
        "scripts/brand_new.py",
        ['A = "' + _win("C:", "Users", "someone", "Downloads", "x.pdf") + '"', 'B = "C:/work/old"'],
    )
    issues = check_hardcoded_user_path(rows, root=tmp_path)
    assert [i.severity for i in issues] == ["warn", "warn"]
    assert {i.code for i in issues} == {"HARDCODED_USER_PATH"}


def test_hardcoded_user_path_known_debt_is_info(tmp_path, monkeypatch):
    # 알려진 부채 목록은 현재 비어 있다(2026-10-01 전부 해소). 메커니즘만 검증하려고 임시 항목을 넣는다.
    from tools.repo_gates import codebase_layer_audit as audit_module

    monkeypatch.setattr(audit_module, "_HARDCODED_USER_PATH_KNOWN_DEBT", {"scripts/legacy_tool.py"})
    rows = _hardcoded_rows_and_source(
        tmp_path, "scripts/legacy_tool.py", ['A = "' + _win("C:", "Users", "someone", "x") + '"']
    )
    issues = check_hardcoded_user_path(rows, root=tmp_path)
    assert [i.severity for i in issues] == ["info"]


def test_hardcoded_user_path_known_debt_list_is_empty():
    # 신규 하드코딩은 전부 경고여야 한다 — 부채 목록이 다시 늘어나지 않게 고정
    from tools.repo_gates import codebase_layer_audit as audit_module

    assert audit_module._HARDCODED_USER_PATH_KNOWN_DEBT == set()


def test_hardcoded_user_path_ignores_placeholders_comments_and_os_locations(tmp_path):
    rows = _hardcoded_rows_and_source(
        tmp_path,
        "scripts/ok_file.py",
        [
            'A = "' + _win("C:", "Users", "<user>", "AppData") + '"',
            'B = "C:/Windows/Fonts"',
            'C = "' + _win("C:", "Program Files", "Google", "Chrome", "chrome.exe") + '"',
            '# D = "' + _win("C:", "Users", "bob", "a") + '"',
        ],
    )
    assert check_hardcoded_user_path(rows, root=tmp_path) == []


def test_hardcoded_user_path_skips_tests_and_archive(tmp_path):
    rows = _hardcoded_rows_and_source(
        tmp_path, "tests/test_x.py", ['A = "' + _win("C:", "Users", "someone", "x") + '"']
    )
    rows += _hardcoded_rows_and_source(tmp_path, "scripts/archive/old.py", ['A = "C:/work/x"'])
    assert check_hardcoded_user_path(rows, root=tmp_path) == []


def test_storage_boundary_known_debt_entries_still_match_a_pattern():
    """알려진 부채 목록의 각 파일은 실제로 금지 패턴(DB 직접 접근·세션 파일)을 포함해야 한다.

    파일이 옮겨지면 옛 경로엔 re-export stub 만 남아 있어(파일은 존재) 목록이 낡은 줄 모르고, 새 경로의 같은 부채가
    신규 위반(WARN)으로 잡힌다(2026-10-04 실측 7건) — 패턴이 없는 항목은 낡은 항목이다.
    """
    import re
    from pathlib import Path

    from tools.repo_gates import codebase_layer_audit as audit

    root = Path(audit.ROOT)
    patterns = [re.compile(pat, re.IGNORECASE | re.MULTILINE) for pat, _ in audit._DB_DIRECT_ACCESS_PATTERNS]
    patterns += [re.compile(pat, re.IGNORECASE | re.MULTILINE) for pat, _ in audit._STORAGE_FORBIDDEN_PATTERNS]
    declared = audit._STORAGE_BOUNDARY_KNOWN_DEBT | audit._STORAGE_BOUNDARY_TEST_KNOWN_DEBT
    assert declared, "알려진 부채 목록이 비어 있음"
    stale = sorted(
        p
        for p in declared
        if not (root / p).is_file()
        or not any(rx.search((root / p).read_text(encoding="utf-8", errors="replace")) for rx in patterns)
    )
    assert not stale, f"금지 패턴이 없는 낡은 항목(옮겨졌다면 새 경로로 갱신): {stale}"
