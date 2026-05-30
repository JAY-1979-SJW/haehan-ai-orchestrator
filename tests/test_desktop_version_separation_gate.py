"""데스크톱 구버전/신버전 분리 게이트 테스트.

게이트 자체가 PASS(현재 트리에 구버전 잔재 없음 + 모듈 구조 충족)인지 검증하고,
구버전 잔재 패턴이 들어오면 FAIL 로 잡히는지(가드 동작) 검증한다.
"""
from scripts.ops.desktop_version_separation_gate import (
    FORBIDDEN_FILES,
    OLD_SHELL_MARKERS,
    REQUIRED_MODULES,
    run_gate,
)


def test_current_tree_passes_gate():
    """현재 작업트리는 분리 게이트를 통과해야 한다."""
    result = run_gate()
    assert not result.failed, (
        "분리 게이트 위반:\n" + "\n".join(f"[{f.category}] {f.detail}" for f in result.findings)
    )


def test_old_google_hub_is_removed():
    """구버전 google-hub.html 은 트리에서 제거되어 있어야 한다."""
    for f in FORBIDDEN_FILES:
        assert not f.exists(), f"구버전 파일 잔존: {f}"


def test_required_modules_present():
    """신버전 필수 모듈이 모두 존재해야 한다."""
    from scripts.ops.desktop_version_separation_gate import LIB

    for mod in REQUIRED_MODULES:
        assert (LIB / mod).exists(), f"필수 모듈 누락: lib/{mod}"


def test_old_shell_markers_absent():
    """shell.html 에 구버전 네비바 마커가 없어야 한다."""
    from scripts.ops.desktop_version_separation_gate import ELECTRON, _read

    shell = _read(ELECTRON / "shell.html")
    for marker in OLD_SHELL_MARKERS:
        assert marker not in shell, f"shell.html 구버전 마커 잔존: {marker!r}"
