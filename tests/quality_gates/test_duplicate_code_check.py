from pathlib import Path

from tools.hooks.duplicate_code_check import (
    find_basename_duplicates,
    find_body_duplicates,
    run,
)

FUNC_A = """
def compute_total(items):
    total = 0
    for item in items:
        total += item.price * item.qty
    return total
"""

FUNC_A_RENAMED_VARS = """
def compute_total(rows):
    total = 0
    for row in rows:
        total += row.price * row.qty
    return total
"""

FUNC_B_DIFFERENT = """
def compute_average(items):
    if not items:
        return 0
    total = sum(item.value for item in items)
    return total / len(items)
"""

TINY_FUNC = "def noop():\n    pass\n"


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_find_body_duplicates_detects_exact_copy(tmp_path):
    _write(tmp_path, "mod_a.py", FUNC_A)
    _write(tmp_path, "sub/mod_b.py", FUNC_A)
    files = list(tmp_path.rglob("*.py"))

    # run() uses ROOT-relative paths; call the lower-level function directly
    # against files under tmp_path is fine since it only needs Path objects.
    import tools.hooks.duplicate_code_check as mod

    original_root = mod.ROOT
    mod.ROOT = tmp_path
    try:
        dups = find_body_duplicates(files, min_lines=1)
    finally:
        mod.ROOT = original_root

    assert len(dups) == 1
    assert dups[0].kind == "function"
    assert dups[0].name == "compute_total"
    assert len(dups[0].locations) == 2


def test_find_body_duplicates_ignores_same_file_repeats(tmp_path):
    """같은 파일 안에서만 반복되면(오버로드/오버라이드 등) 신호가 아니다."""
    _write(tmp_path, "only_here.py", FUNC_A + "\n" + FUNC_A.replace("compute_total", "compute_total2"))
    files = list(tmp_path.rglob("*.py"))

    import tools.hooks.duplicate_code_check as mod

    original_root = mod.ROOT
    mod.ROOT = tmp_path
    try:
        dups = find_body_duplicates(files, min_lines=1)
    finally:
        mod.ROOT = original_root

    # 이름은 다르지만 본문 해시가 같은 두 함수가 "같은 파일"에만 있으므로 무시된다.
    assert dups == []


def test_find_body_duplicates_ignores_below_min_lines(tmp_path):
    _write(tmp_path, "a.py", TINY_FUNC)
    _write(tmp_path, "b.py", TINY_FUNC)
    files = list(tmp_path.rglob("*.py"))

    import tools.hooks.duplicate_code_check as mod

    original_root = mod.ROOT
    mod.ROOT = tmp_path
    try:
        dups = find_body_duplicates(files, min_lines=6)
    finally:
        mod.ROOT = original_root

    assert dups == []


def test_find_body_duplicates_does_not_flag_renamed_variables(tmp_path):
    """이 도구는 '완전 복붙' 탐지기다 — 변수명이 다르면 다른 것으로 본다(v1 한계)."""
    _write(tmp_path, "a.py", FUNC_A)
    _write(tmp_path, "b.py", FUNC_A_RENAMED_VARS)
    files = list(tmp_path.rglob("*.py"))

    import tools.hooks.duplicate_code_check as mod

    original_root = mod.ROOT
    mod.ROOT = tmp_path
    try:
        dups = find_body_duplicates(files, min_lines=1)
    finally:
        mod.ROOT = original_root

    assert dups == []


def test_find_body_duplicates_does_not_flag_different_functions(tmp_path):
    _write(tmp_path, "a.py", FUNC_A)
    _write(tmp_path, "b.py", FUNC_B_DIFFERENT)
    files = list(tmp_path.rglob("*.py"))

    import tools.hooks.duplicate_code_check as mod

    original_root = mod.ROOT
    mod.ROOT = tmp_path
    try:
        dups = find_body_duplicates(files, min_lines=1)
    finally:
        mod.ROOT = original_root

    assert dups == []


def test_find_basename_duplicates_detects_parallel_modules(tmp_path):
    _write(tmp_path, "site_a/actions.py", "x = 1\n")
    _write(tmp_path, "site_b/actions.py", "x = 2\n")
    _write(tmp_path, "site_a/unique.py", "x = 3\n")
    files = list(tmp_path.rglob("*.py"))

    import tools.hooks.duplicate_code_check as mod

    original_root = mod.ROOT
    mod.ROOT = tmp_path
    try:
        dups = find_basename_duplicates(files)
    finally:
        mod.ROOT = original_root

    names = {d.basename for d in dups}
    assert "actions.py" in names
    assert "unique.py" not in names


def test_find_basename_duplicates_ignores_init_py(tmp_path):
    _write(tmp_path, "site_a/__init__.py", "")
    _write(tmp_path, "site_b/__init__.py", "")
    files = list(tmp_path.rglob("*.py"))

    import tools.hooks.duplicate_code_check as mod

    original_root = mod.ROOT
    mod.ROOT = tmp_path
    try:
        dups = find_basename_duplicates(files)
    finally:
        mod.ROOT = original_root

    assert dups == []


def test_run_against_real_repo_smoke():
    """실제 저장소 대상으로 예외 없이 끝까지 돌아가는지만 확인 (스모크 테스트)."""
    result = run(["scripts/ops"], min_lines=6)
    assert result["scanned_files"] > 0
    assert isinstance(result["body_duplicates"], list)
    assert isinstance(result["basename_duplicates"], list)
