"""core.agent_runtime.tools.file_scanner 검증 (read-only Stage 1).

테스트는 pytest tmp_path 만 사용한다. 실제 사용자 폴더 / OneDrive / Downloads /
C:/Users 등은 절대 스캔하지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def sample_tree(tmp_path: Path) -> Path:
    """기본 스캔 검증용 파일 트리 구성."""
    root = tmp_path / "workspace"
    root.mkdir()

    (root / "readme.txt").write_text("hello", encoding="utf-8")
    (root / "notes.log").write_text("log data", encoding="utf-8")
    (root / "temp.bak").write_text("bak", encoding="utf-8")
    (root / "Thumbs.db").write_text("thumb", encoding="utf-8")
    (root / "desktop.ini").write_text("ini", encoding="utf-8")
    (root / "~$draft.docx").write_text("lock", encoding="utf-8")
    (root / "empty.dat").write_text("", encoding="utf-8")

    (root / "docs").mkdir()
    (root / "docs" / "계약서_2026.pdf").write_bytes(b"PDF-BYTES")
    (root / "docs" / "기성청구.xlsx").write_bytes(b"XLSX")

    (root / "keys").mkdir()
    (root / "keys" / "prod.pem").write_text("PEM", encoding="utf-8")
    (root / "keys" / "id_rsa.key").write_text("KEY", encoding="utf-8")

    (root / "dwg").mkdir()
    (root / "dwg" / "plan.dwg").write_bytes(b"DWG")

    # 제외 디렉터리
    (root / "node_modules").mkdir()
    (root / "node_modules" / "pkg.js").write_text("x", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "mod.pyc").write_text("b", encoding="utf-8")

    return root


# ─── 기본 스캔 ──────────────────────────────────────────────────────────────


def test_basic_scan_returns_expected_shape(sample_tree: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    report = scan_file_tree(str(sample_tree))
    assert report["ok"] is True
    assert isinstance(report["items"], list)
    assert report["scanned_files"] >= 8
    assert report["preserve_count"] >= 4  # pdf, xlsx, pem, key, dwg
    assert report["delete_candidate_count"] >= 4  # .bak, .log, Thumbs.db, desktop.ini, ~$, empty
    assert "warnings" in report
    assert isinstance(report["warnings"], list)


def test_items_contain_no_absolute_path(sample_tree: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    report = scan_file_tree(str(sample_tree))
    for item in report["items"]:
        assert "absolute_path" not in item
        # relative_path 는 root 이름 / 절대경로 구분자 포함 금지
        assert ":" not in item["relative_path"]
        assert not item["relative_path"].startswith("/")
        assert not item["relative_path"].startswith("\\")
    # root_display 는 폴더명만 (사용자 홈 경로 노출 금지)
    assert str(sample_tree) not in report["root_display"]
    assert str(sample_tree.parent) not in report["root_display"]


# ─── 탐색 제한 ──────────────────────────────────────────────────────────────


def test_max_depth_limit(tmp_path: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    root = tmp_path / "deep"
    cur = root
    for i in range(5):
        cur.mkdir()
        (cur / f"level{i}.txt").write_text("x", encoding="utf-8")
        cur = cur / f"sub{i}"
    cur.mkdir()
    (cur / "deepest.txt").write_text("x", encoding="utf-8")

    shallow = scan_file_tree(str(root), max_depth=1)
    deep = scan_file_tree(str(root), max_depth=10)

    assert shallow["ok"] is True
    assert deep["ok"] is True
    # max_depth=1 은 root 직속 + 1단계까지만
    assert shallow["scanned_files"] < deep["scanned_files"]
    # 깊은 파일은 얕은 스캔에 안 들어가야 함
    names_shallow = {i["file_name"] for i in shallow["items"]}
    assert "deepest.txt" not in names_shallow


def test_max_files_limit(tmp_path: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    root = tmp_path / "many"
    root.mkdir()
    for i in range(30):
        (root / f"f{i}.txt").write_text("x", encoding="utf-8")

    report = scan_file_tree(str(root), max_files=5)
    assert report["ok"] is True
    assert report["scanned_files"] == 5
    assert any("max_files_reached" in w for w in report["warnings"])


# ─── 제외 디렉터리 ──────────────────────────────────────────────────────────


def test_excluded_directories(sample_tree: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    report = scan_file_tree(str(sample_tree))
    rels = {i["relative_path"] for i in report["items"]}

    assert not any(r.startswith("node_modules/") for r in rels)
    assert not any(r.startswith(".git/") for r in rels)
    assert not any(r.startswith("__pycache__/") for r in rels)
    assert report["excluded_count"] >= 3


# ─── preserve 분류 ──────────────────────────────────────────────────────────


def test_preserve_by_extension(sample_tree: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    report = scan_file_tree(str(sample_tree))
    by_name = {i["file_name"]: i for i in report["items"]}

    for target in ("plan.dwg", "prod.pem", "id_rsa.key", "계약서_2026.pdf", "기성청구.xlsx"):
        assert target in by_name, f"missing {target}"
        assert by_name[target]["category"] == "preserve"


def test_preserve_by_keyword(tmp_path: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    root = tmp_path / "kwd"
    root.mkdir()
    (root / "계약_abc.txt").write_text("x", encoding="utf-8")
    (root / "기성_def.dat").write_text("x", encoding="utf-8")
    (root / "서버_접속정보.txt").write_text("x", encoding="utf-8")
    (root / "my_api_key_notes.md").write_text("x", encoding="utf-8")
    (root / "SECRET_token.ini").write_text("x", encoding="utf-8")

    report = scan_file_tree(str(root))
    cats = {i["file_name"]: i["category"] for i in report["items"]}
    assert cats["계약_abc.txt"] == "preserve"
    assert cats["기성_def.dat"] == "preserve"
    assert cats["서버_접속정보.txt"] == "preserve"
    assert cats["my_api_key_notes.md"] == "preserve"
    assert cats["SECRET_token.ini"] == "preserve"


# ─── candidate_delete 분류 ──────────────────────────────────────────────────


def test_candidate_delete_categories(sample_tree: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    report = scan_file_tree(str(sample_tree))
    cats = {i["file_name"]: i["category"] for i in report["items"]}

    assert cats["temp.bak"] == "candidate_delete"
    assert cats["notes.log"] == "candidate_delete"
    assert cats["Thumbs.db"] == "candidate_delete"
    assert cats["desktop.ini"] == "candidate_delete"
    assert cats["~$draft.docx"] == "candidate_delete"
    assert cats["empty.dat"] == "candidate_delete"


def test_preserve_priority_over_candidate_delete(tmp_path: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    root = tmp_path / "prio"
    root.mkdir()
    # .log 는 삭제 후보지만 "서버" 키워드가 있으므로 preserve 가 우선
    (root / "서버_운영.log").write_text("x", encoding="utf-8")
    # .xlsx 는 preserve — 0 바이트여도 preserve
    (root / "계약내역.xlsx").write_text("", encoding="utf-8")

    report = scan_file_tree(str(root))
    cats = {i["file_name"]: i["category"] for i in report["items"]}
    assert cats["서버_운영.log"] == "preserve"
    assert cats["계약내역.xlsx"] == "preserve"


# ─── 중복 후보 ──────────────────────────────────────────────────────────────


def test_strong_duplicate_same_name_and_size(tmp_path: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    root = tmp_path / "dup"
    root.mkdir()
    (root / "a").mkdir()
    (root / "b").mkdir()
    (root / "a" / "report.txt").write_text("same", encoding="utf-8")
    (root / "b" / "report.txt").write_text("same", encoding="utf-8")

    report = scan_file_tree(str(root))
    dups = [i for i in report["items"] if i["file_name"] == "report.txt"]
    assert len(dups) == 2
    assert all(i["duplicate_candidate"] is True for i in dups)
    assert all(i["duplicate_strength"] == "strong" for i in dups)
    assert all("duplicate_group_key" in i for i in dups)


def test_weak_duplicate_same_ext_and_size(tmp_path: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    root = tmp_path / "dup_weak"
    root.mkdir()
    (root / "alpha.tmp").write_text("1234567890", encoding="utf-8")
    (root / "beta.tmp").write_text("abcdefghij", encoding="utf-8")
    (root / "gamma.doc").write_text("x", encoding="utf-8")

    report = scan_file_tree(str(root))
    by_name = {i["file_name"]: i for i in report["items"]}
    assert by_name["alpha.tmp"]["duplicate_candidate"] is True
    assert by_name["beta.tmp"]["duplicate_candidate"] is True
    assert by_name["alpha.tmp"]["duplicate_strength"] == "weak"
    assert by_name["beta.tmp"]["duplicate_strength"] == "weak"
    # 단일 .doc 은 중복 아님
    assert by_name["gamma.doc"]["duplicate_candidate"] is False


# ─── 해시 ──────────────────────────────────────────────────────────────────


def test_hash_absent_by_default(sample_tree: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    report = scan_file_tree(str(sample_tree))
    for item in report["items"]:
        assert "hash_sha256" not in item


def test_hash_present_when_enabled(tmp_path: Path) -> None:
    import hashlib

    from core.agent_runtime.tools.file_scanner import scan_file_tree

    root = tmp_path / "h"
    root.mkdir()
    data = b"hello world"
    (root / "a.txt").write_bytes(data)

    report = scan_file_tree(str(root), compute_hash=True)
    item = next(i for i in report["items"] if i["file_name"] == "a.txt")
    assert item["hash_sha256"] == hashlib.sha256(data).hexdigest()


def test_hash_skipped_for_large_file(tmp_path: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    root = tmp_path / "big"
    root.mkdir()
    # max_hash_size_mb=0 이면 어떤 파일도 한도 초과로 취급
    (root / "big.bin").write_bytes(b"x" * 10)

    report = scan_file_tree(str(root), compute_hash=True, max_hash_size_mb=0)
    item = next(i for i in report["items"] if i["file_name"] == "big.bin")
    # 0MB 한도 < 10B 파일 → hash 생략
    assert "hash_sha256" not in item
    assert item.get("hash_skipped_reason", "").startswith("size_over_")


# ─── 안전 에러 / 차단 ──────────────────────────────────────────────────────


def test_missing_root_returns_safe_error(tmp_path: Path) -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    report = scan_file_tree(str(tmp_path / "does_not_exist"))
    assert report["ok"] is False
    assert report["error_code"] == "ROOT_NOT_FOUND"
    assert report["items"] == []


def test_drive_root_blocked() -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    for raw in ("C:/", "C:\\", "D:/", "c:"):
        report = scan_file_tree(raw)
        assert report["ok"] is False, f"expected block for {raw!r}"
        assert report["error_code"] == "ROOT_BLOCKED_DRIVE_ROOT"


def test_system_folder_blocked() -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    for raw in ("C:/Windows", "C:/Windows/System32", "c:/programdata", "C:\\Program Files"):
        report = scan_file_tree(raw)
        assert report["ok"] is False, f"expected block for {raw!r}"
        assert report["error_code"] == "ROOT_BLOCKED_SYSTEM"


def test_empty_root_path_rejected() -> None:
    from core.agent_runtime.tools.file_scanner import scan_file_tree

    report = scan_file_tree("")
    assert report["ok"] is False
    assert report["error_code"] == "ROOT_INVALID"


# ─── core.agent_runtime.connection.actions 통합 ──────────────────────────────────────────────


def test_execute_action_scan_file_tree(sample_tree: Path) -> None:
    from core.agent_runtime.connection.actions import execute_action

    result = execute_action("scan_file_tree", {"root_path": str(sample_tree)})
    assert result.success is True
    assert "scanned_files=" in result.summary
    # 서버 전송 가능한 data — absolute_path 없음
    for item in result.data["items"]:
        assert "absolute_path" not in item


def test_execute_action_scan_file_tree_missing_root() -> None:
    from core.agent_runtime.connection.actions import execute_action

    result = execute_action("scan_file_tree", {})
    assert result.success is False
    assert result.error_code == "MISSING_ROOT_PATH"


def test_execute_action_scan_file_tree_blocks_drive_root() -> None:
    from core.agent_runtime.connection.actions import execute_action

    result = execute_action("scan_file_tree", {"root_path": "C:/"})
    assert result.success is False
    assert result.error_code == "ROOT_BLOCKED_DRIVE_ROOT"


# ─── 금지 API 정적 검사 ────────────────────────────────────────────────────


def test_no_forbidden_mutation_apis_in_new_code() -> None:
    """새 코드에서 파일 변형/삭제/이동 API 호출 문자열이 전혀 없는지 검사."""
    from pathlib import Path as _P

    import core.agent_runtime.tools.file_scanner as fs

    scanner_src = _P(fs.__file__).read_text(encoding="utf-8")
    action_src = (_P(fs.__file__).parent.parent / "connection" / "actions.py").read_text(encoding="utf-8")

    forbidden_tokens = (
        "os.remove",
        "os.unlink",
        "Path.unlink",
        ".unlink(",
        "shutil.rmtree",
        "shutil.move",
        "os.rename",
        ".rename(",
        "send2trash",
    )

    # scanner 에는 금지 API 자체가 없어야 함
    for token in forbidden_tokens:
        assert token not in scanner_src, f"forbidden token {token!r} found in file_scanner.py"

    # actions.py 는 scan_file_tree 블록 범위 내에 금지 토큰이 없어야 함
    # (capture_screenshot 등 기존 구현은 mkdir / save 는 사용하지만
    #  unlink/rename/rmtree/move/send2trash 는 쓰지 않음)
    for token in (
        "os.remove",
        "os.unlink",
        "shutil.rmtree",
        "shutil.move",
        "os.rename",
        "send2trash",
        ".unlink(",
        ".rename(",
    ):
        assert token not in action_src, f"forbidden token {token!r} found in actions.py"
