"""HAEHAN_SINGLE_EXE_BUILD_01 — entrypoint rewire 회귀 테스트."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_launcher_uses_main_launcher():
    src = (ROOT / "build/webview_launcher.py").read_text(encoding="utf-8")
    assert "from desktop.main_launcher import main" in src, \
        "build/webview_launcher.py 는 main_launcher.main 을 import 해야 함"
    assert "sys.exit(main())" in src


def test_launcher_no_direct_webview_entry():
    """webview_app_pywebview.main 을 직접 import/호출하면 안됨.

    code line 만 검사하기 위해 docstring/주석 제거 후 비교.
    """
    src = (ROOT / "build/webview_launcher.py").read_text(encoding="utf-8")
    code_lines = []
    in_docstring = False
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            # toggle docstring; 같은 줄에 두 번 등장하면 inline docstring
            count = line.count('"""') + line.count("'''")
            if count == 2:
                continue
            in_docstring = not in_docstring
            continue
        if in_docstring or stripped.startswith("#"):
            continue
        code_lines.append(line)
    code = "\n".join(code_lines)
    assert "from desktop.webview_app_pywebview import main" not in code
    assert "webview_app_pywebview.main(" not in code


def test_spec_points_to_webview_launcher():
    src = (ROOT / "HaehanAI-Desktop.spec").read_text(encoding="utf-8")
    assert "webview_launcher.py" in src, \
        "HaehanAI-Desktop.spec 의 entry 는 build/webview_launcher.py 여야 함"


def _run_main_with_env(monkeypatch, tmp_path, role: str | None, agreed: bool = True):
    """main_launcher.main(['--admin']) 호출, consent/role 격리."""
    import sys
    import json
    sys.path.insert(0, str(ROOT))
    from desktop import main_launcher

    monkeypatch.setattr(main_launcher, "app_root", lambda: tmp_path)
    consent = tmp_path / "data" / "consent.json"
    consent.parent.mkdir(parents=True, exist_ok=True)
    consent.write_text(json.dumps({
        "agreed": agreed, "agreed_at": "x", "version": "1", "scope": "x",
    }), encoding="utf-8")

    monkeypatch.setenv("HAEHAN_SKIP_GUI", "1")
    if role is None:
        monkeypatch.delenv("HAEHAN_ROLE", raising=False)
    else:
        monkeypatch.setenv("HAEHAN_ROLE", role)

    # lock 격리 — user_data_dir 도 tmp_path 로 우회 (mkdir 포함)
    udir = tmp_path / "userdata"
    udir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(main_launcher, "user_data_dir", lambda: udir)

    return main_launcher.main(["--admin"])


def test_admin_role_env_owner_allows(monkeypatch, tmp_path):
    rc = _run_main_with_env(monkeypatch, tmp_path, "owner")
    assert rc == 0, f"HAEHAN_ROLE=owner 는 admin 허용 (rc=0) — got {rc}"


def test_admin_role_env_admin_allows(monkeypatch, tmp_path):
    rc = _run_main_with_env(monkeypatch, tmp_path, "admin")
    assert rc == 0, f"HAEHAN_ROLE=admin 는 admin 허용 (rc=0) — got {rc}"


def test_admin_role_env_any_blocks(monkeypatch, tmp_path):
    rc = _run_main_with_env(monkeypatch, tmp_path, "any")
    assert rc == 2, f"HAEHAN_ROLE=any 는 admin 차단 (rc=2) — got {rc}"


def test_admin_role_env_user_blocks(monkeypatch, tmp_path):
    rc = _run_main_with_env(monkeypatch, tmp_path, "user")
    assert rc == 2, f"HAEHAN_ROLE=user 는 admin 차단 (rc=2) — got {rc}"


def test_admin_role_env_viewer_blocks(monkeypatch, tmp_path):
    rc = _run_main_with_env(monkeypatch, tmp_path, "viewer")
    assert rc == 2, f"HAEHAN_ROLE=viewer 는 admin 차단 (rc=2) — got {rc}"
