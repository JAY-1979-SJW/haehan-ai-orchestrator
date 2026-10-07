"""설치형(NSIS) 앱 자동 업데이트 설정 정적 점검.

electron-updater 는 설치된 앱 안에서 돌아야 하므로 devDependencies 가 아니라 dependencies 에 있어야 하고,
설치 파일 이름은 NAS 게시 도구 glob(HaehanAI-*.exe)에 맞아야 하며, 포터블·자동 점검에서는 꺼져 있어야 한다.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ELECTRON = ROOT / "admin-web" / "electron"


def _pkg() -> dict:
    return json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))


def test_updater_is_runtime_dependency():
    pkg = _pkg()
    assert "electron-updater" in pkg.get("dependencies", {})
    assert "electron-updater" not in pkg.get("devDependencies", {})


def test_installer_name_matches_publish_glob():
    name = _pkg()["build"]["nsis"]["artifactName"]
    assert re.fullmatch(r"HaehanAI-\$\{env\.HAEHAN_BUILD_VERSION\}-setup\.exe", name)


def test_installers_are_never_published_to_github():
    # 대표님 결정(2026-10-08): 설치 파일은 GitHub 에 올리지 않는다 — 출처는 실행 때 받는 generic 주소뿐
    publish = _pkg()["build"]["publish"]
    assert [p["provider"] for p in publish] == ["generic"]
    wf = (ROOT / ".github" / "workflows" / "desktop-release.yml").read_text(encoding="utf-8")
    assert "gh release" not in wf
    assert "contents: write" not in wf
    assert "--publish never" in wf


def test_per_user_install_so_updates_need_no_admin():
    assert _pkg()["build"]["nsis"]["perMachine"] is False


def test_updater_off_for_portable_e2e_and_dev():
    src = (ELECTRON / "lib" / "updater.js").read_text(encoding="utf-8")
    for guard in ("app.isPackaged", "PORTABLE_EXECUTABLE_DIR", 'HAEHAN_E2E === "1"', "HAEHAN_DISABLE_UPDATE", "no-update-url"):
        assert guard in src, guard
    assert 'setFeedURL({ provider: "generic", url: updateUrl() })' in src


def test_main_starts_updater_after_shell_loaded():
    main = (ELECTRON / "main.js").read_text(encoding="utf-8")
    shell_loaded = main.index('stage("shell-loaded")')
    start = main.index("startAutoUpdate(getMainWindow)")
    assert start > shell_loaded

