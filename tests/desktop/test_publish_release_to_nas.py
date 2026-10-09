"""tools/publish_release_to_nas.py 시험 — 원격 호출은 전부 mock."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from tools.publish_release_to_nas import (
    PublishError,
    local_checksums,
    main,
    publish,
    validate_artifacts,
    validate_version,
)


def test_validate_version_accepts_correct_format():
    validate_version("20261007-abc1234")


@pytest.mark.parametrize(
    "bad",
    ["1.0.0", "20261007", "20261007-ABC1234", "2026-10-07-abc1234", ""],
)
def test_validate_version_rejects_bad_format(bad):
    with pytest.raises(PublishError):
        validate_version(bad)


def _make_artifact_dir(tmp_path: Path, *, with_notes: bool = False) -> Path:
    d = tmp_path / "out"
    d.mkdir()
    (d / "HaehanAI-20261007-abc1234-portable.exe").write_bytes(b"exe")
    (d / "checksums.txt").write_text("deadbeef  HaehanAI-20261007-abc1234-portable.exe\n", encoding="utf-8")
    if with_notes:
        (d / "RELEASE_NOTES.md").write_text("- 변경 요약\n", encoding="utf-8")
    return d


def test_validate_artifacts_requires_exe(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    (d / "checksums.txt").write_text("x", encoding="utf-8")
    with pytest.raises(PublishError):
        validate_artifacts(d)


def test_validate_artifacts_requires_checksums(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    (d / "HaehanAI-20261007-abc1234-portable.exe").write_bytes(b"exe")
    with pytest.raises(PublishError):
        validate_artifacts(d)


def test_validate_artifacts_includes_release_notes_when_present(tmp_path):
    d = _make_artifact_dir(tmp_path, with_notes=True)
    files = validate_artifacts(d)
    assert any(f.name == "RELEASE_NOTES.md" for f in files)


def test_validate_artifacts_includes_install_guide_when_present(tmp_path):
    """사용자 안내서(설치_및_사용_안내.md)도 있으면 함께 올린다. 필수 규칙(exe·checksums)은 그대로."""
    d = _make_artifact_dir(tmp_path, with_notes=True)
    (d / "설치_및_사용_안내.md").write_text("# 안내", encoding="utf-8")
    names = [f.name for f in validate_artifacts(d)]
    assert "RELEASE_NOTES.md" in names and "설치_및_사용_안내.md" in names
    assert any(n.startswith("HaehanAI-") and n.endswith(".exe") for n in names) and "checksums.txt" in names


def test_install_guide_alone_does_not_satisfy_required_files(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    (d / "설치_및_사용_안내.md").write_text("# 안내", encoding="utf-8")
    (d / "checksums.txt").write_text("x", encoding="utf-8")
    with pytest.raises(PublishError):  # exe 가 없으면 문서가 있어도 게시 불가(메인 exe 필수 규칙 유지)
        validate_artifacts(d)


def test_dry_run_plan_mentions_install_guide(tmp_path, capsys):
    d = _make_artifact_dir(tmp_path, with_notes=True)
    (d / "설치_및_사용_안내.md").write_text("# 안내", encoding="utf-8")
    assert publish(d, "20261007-abc1234", dry_run=True) == 0
    out = capsys.readouterr().out
    assert "설치_및_사용_안내.md" in out and "RELEASE_NOTES.md" in out and "HaehanAI-" in out


def test_validate_artifacts_missing_dir(tmp_path):
    with pytest.raises(PublishError):
        validate_artifacts(tmp_path / "missing")


def test_local_checksums_parses_sha256sum_format(tmp_path):
    d = _make_artifact_dir(tmp_path)
    parsed = local_checksums(d)
    assert parsed["HaehanAI-20261007-abc1234-portable.exe"] == "deadbeef"


def test_dry_run_does_not_call_subprocess_run(tmp_path):
    d = _make_artifact_dir(tmp_path)
    with mock.patch("tools.publish_release_to_nas.subprocess.run") as run:
        rc = publish(d, "20261007-abc1234", dry_run=True)
    assert rc == 0
    run.assert_not_called()


def test_cli_without_execute_flag_defaults_to_dry_run(tmp_path):
    """--execute 를 안 주면(옵션 없이 실행) 실제 업로드가 일어나면 안 된다."""
    d = _make_artifact_dir(tmp_path)
    with mock.patch("tools.publish_release_to_nas.subprocess.run") as run:
        rc = main([str(d), "--version", "20261007-abc1234"])
    assert rc == 0
    run.assert_not_called()


def test_cli_with_execute_flag_calls_subprocess(tmp_path):
    d = _make_artifact_dir(tmp_path)

    def _fake_run(cmd, check=False, **kw):
        if "test" in cmd:
            return mock.Mock(returncode=1)
        if "sha256sum" in cmd:
            return mock.Mock(stdout="deadbeef  /some/path/HaehanAI-20261007-abc1234-portable.exe\n")
        return mock.Mock(returncode=0)

    with mock.patch("tools.publish_release_to_nas.subprocess.run", side_effect=_fake_run) as run:
        rc = main([str(d), "--version", "20261007-abc1234", "--execute"])
    assert rc == 0
    run.assert_called()


def test_duplicate_version_aborts_before_any_upload(tmp_path):
    d = _make_artifact_dir(tmp_path)
    with mock.patch("tools.publish_release_to_nas.subprocess.run") as run:
        run.return_value = mock.Mock(returncode=0)  # test -d 성공 = 이미 존재
        rc = publish(d, "20261007-abc1234", dry_run=False)
    assert rc == 1
    # "존재 확인" 호출(subprocess.run) 한 번만 있어야 하고, scp/tar 등 이후 단계는 없어야 한다
    assert run.call_count == 1


def test_publish_uploads_when_version_is_new(tmp_path):
    d = _make_artifact_dir(tmp_path)

    def _fake_run(cmd, check=False, **kw):
        if cmd[:2] == ["ssh", "haehan-app"] and "test" in cmd:
            return mock.Mock(returncode=1)  # 존재하지 않음
        if "sha256sum" in cmd:
            return mock.Mock(stdout="deadbeef  /some/path/HaehanAI-20261007-abc1234-portable.exe\n")
        return mock.Mock(returncode=0)

    with mock.patch("tools.publish_release_to_nas.subprocess.run", side_effect=_fake_run) as run:
        rc = publish(d, "20261007-abc1234", dry_run=False)
    assert rc == 0
    assert run.call_count > 1


def test_publish_fails_on_checksum_mismatch(tmp_path):
    d = _make_artifact_dir(tmp_path)

    def _fake_run(cmd, check=False, **kw):
        if cmd[:2] == ["ssh", "haehan-app"] and "test" in cmd:
            return mock.Mock(returncode=1)
        if "sha256sum" in cmd:
            return mock.Mock(stdout="wrongsha  /some/path/HaehanAI-20261007-abc1234-portable.exe\n")
        return mock.Mock(returncode=0)

    with mock.patch("tools.publish_release_to_nas.subprocess.run", side_effect=_fake_run):
        rc = publish(d, "20261007-abc1234", dry_run=False)
    assert rc == 1
