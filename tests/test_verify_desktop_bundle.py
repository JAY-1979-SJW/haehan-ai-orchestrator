"""설치본 내용물 점검(scripts/ops/verify_desktop_bundle.py) — 빠진 파일을 실제로 잡는지 고정 입력으로 확인."""

import json
import subprocess

import pytest

from scripts.ops import verify_desktop_bundle as vdb


def _make_bundle(root, *, skip: str = ""):
    """앱이 실행 때 찾는 경로를 모두 갖춘 가짜 win-unpacked. skip 으로 한 항목을 뺀다."""
    res = root / "win-unpacked" / "resources"
    for rel, kind in vdb.REQUIRED:
        if rel == skip or rel == "build-info.json":
            continue
        path = res / rel
        if kind == "file":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
        else:
            path.mkdir(parents=True, exist_ok=True)
            (path / ("chunk.js" if rel.endswith("static") else "f.txt")).write_bytes(b"x")
    if skip != "build-info.json":
        (res / "build-info.json").write_text(json.dumps({"version": "20261008-abc1234"}), encoding="utf-8")
    (res / "app.asar").write_bytes(b"x")
    return root / "win-unpacked"


def test_complete_bundle_passes(tmp_path):
    unpacked = _make_bundle(tmp_path)
    assert vdb.main([str(unpacked)]) == 0


@pytest.mark.parametrize(
    "missing",
    [
        "nextjs/.next/static",
        "nextjs/public",
        "server/haehan-server/haehan-server.exe",
    ],
)
def test_missing_item_fails(tmp_path, missing, capsys):
    # 2026-10-08 실제 결함(.next/static·public 누락)과 서버 exe 누락을 심으면 반드시 실패해야 한다
    unpacked = _make_bundle(tmp_path, skip=missing)
    assert vdb.main([str(unpacked)]) == 1
    assert missing in capsys.readouterr().out


def test_empty_static_folder_fails(tmp_path):
    unpacked = _make_bundle(tmp_path)
    static = unpacked / "resources" / "nextjs" / ".next" / "static"
    for f in static.iterdir():
        f.unlink()
    (static / "readme.txt").write_bytes(b"x")  # 파일은 있지만 화면 JS 가 없다
    problems = vdb.check_resources(unpacked / "resources")
    assert any(".js" in p for p in problems)


def test_bad_build_version_fails(tmp_path):
    unpacked = _make_bundle(tmp_path)
    (unpacked / "resources" / "build-info.json").write_text(json.dumps({"version": "dev"}), encoding="utf-8")
    assert vdb.main([str(unpacked)]) == 1


def _make_smoke_exes(unpacked):
    res = unpacked / "resources"
    local_agent = res / "local-agent" / "local-agent.exe"
    haehan_mcp = res / "mcp" / "haehan-mcp" / "haehan-mcp.exe"
    local_agent.parent.mkdir(parents=True, exist_ok=True)
    haehan_mcp.parent.mkdir(parents=True, exist_ok=True)
    local_agent.write_bytes(b"x")  # 실제 실행은 run() 을 모킹하므로 내용은 안 쓰임
    haehan_mcp.write_bytes(b"x")
    return local_agent, haehan_mcp


def test_smoke_passes_when_exes_behave_correctly(tmp_path):
    unpacked = _make_bundle(tmp_path)
    local_agent, haehan_mcp = _make_smoke_exes(unpacked)

    def fake_run(cmd, **kwargs):
        exe = cmd[0]
        if exe == str(local_agent):
            return subprocess.CompletedProcess(cmd, returncode=2, stdout=b"usage: local-agent.exe ...", stderr=b"")
        if exe == str(haehan_mcp):
            return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")
        raise AssertionError(f"unexpected exe: {exe}")

    problems = vdb.check_smoke(unpacked / "resources", run=fake_run)
    assert problems == []


def test_smoke_fails_when_mcp_prints_import_error(tmp_path):
    unpacked = _make_bundle(tmp_path)
    local_agent, haehan_mcp = _make_smoke_exes(unpacked)

    def fake_run(cmd, **kwargs):
        exe = cmd[0]
        if exe == str(local_agent):
            return subprocess.CompletedProcess(cmd, returncode=2, stdout=b"usage: local-agent.exe ...", stderr=b"")
        if exe == str(haehan_mcp):
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout=b"", stderr=b"ModuleNotFoundError: No module named 'ai_orchestrator'\n"
            )
        raise AssertionError(f"unexpected exe: {exe}")

    problems = vdb.check_smoke(unpacked / "resources", run=fake_run)
    assert any("ModuleNotFoundError" in p for p in problems)


def test_smoke_fails_when_local_agent_does_not_reach_argparse_usage(tmp_path):
    unpacked = _make_bundle(tmp_path)
    local_agent, haehan_mcp = _make_smoke_exes(unpacked)

    def fake_run(cmd, **kwargs):
        exe = cmd[0]
        if exe == str(local_agent):
            # shim 진입점이 정본 모듈 없이 즉시 죽는 경우 흔히 보이는 종료코드 1
            return subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"Traceback ...")
        if exe == str(haehan_mcp):
            return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")
        raise AssertionError(f"unexpected exe: {exe}")

    problems = vdb.check_smoke(unpacked / "resources", run=fake_run)
    assert any("종료코드 2" in p for p in problems)


def test_smoke_off_by_default(tmp_path, monkeypatch):
    """--smoke 를 안 주면 check_smoke 가 전혀 안 불려야 한다(기존 호출 안 깨짐)."""
    unpacked = _make_bundle(tmp_path)
    _make_smoke_exes(unpacked)
    called = []
    monkeypatch.setattr(vdb, "check_smoke", lambda *a, **k: (called.append(1), [])[1])
    assert vdb.main([str(unpacked)]) == 0
    assert called == []


def test_smoke_flag_invokes_check_smoke(tmp_path, monkeypatch):
    unpacked = _make_bundle(tmp_path)
    _make_smoke_exes(unpacked)
    called = []
    monkeypatch.setattr(vdb, "check_smoke", lambda *a, **k: (called.append(1), [])[1])
    assert vdb.main([str(unpacked), "--smoke"]) == 0
    assert called == [1]


def test_dist_requires_setup_exe(tmp_path):
    # latest.yml(자동 업데이트 메타데이터) 점검은 electron-updater 연동과 함께 나중에
    # 추가한다(이번 이식 범위 밖, 2026-10-10 BUILD_PLAN 0' 보류분) — 지금은 setup.exe 만 본다.
    unpacked = _make_bundle(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    assert vdb.main([str(unpacked), "--dist", str(dist)]) == 1
    (dist / "HaehanAI-20261008-abc1234-setup.exe").write_bytes(b"x")
    assert vdb.main([str(unpacked), "--dist", str(dist)]) == 0
