"""설치본 내용물 점검(scripts/ops/verify_desktop_bundle.py) — 빠진 파일을 실제로 잡는지 고정 입력으로 확인."""

import json

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


def test_dist_requires_setup_exe(tmp_path):
    # latest.yml(자동 업데이트 메타데이터) 점검은 electron-updater 연동과 함께 나중에
    # 추가한다(이번 이식 범위 밖, 2026-10-10 BUILD_PLAN 0' 보류분) — 지금은 setup.exe 만 본다.
    unpacked = _make_bundle(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    assert vdb.main([str(unpacked), "--dist", str(dist)]) == 1
    (dist / "HaehanAI-20261008-abc1234-setup.exe").write_bytes(b"x")
    assert vdb.main([str(unpacked), "--dist", str(dist)]) == 0
