import json
import subprocess

from scripts.ops.code_map import freshness as fr


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "a@b"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "a"], check=True)
    (tmp_path / "a.py").write_text("x=1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "i"], check=True)


def test_fingerprint_changes_on_edit(tmp_path):
    _repo(tmp_path)
    f1 = fr.fingerprint(tmp_path)
    (tmp_path / "a.py").write_text("x=2\n")
    assert fr.fingerprint(tmp_path) != f1


def test_is_fresh_and_refuse(tmp_path):
    _repo(tmp_path)
    mp = tmp_path / "map.json"
    mp.write_text(json.dumps({"meta": {"worktree_fingerprint": fr.fingerprint(tmp_path)}}))
    assert fr.is_fresh(mp, tmp_path)
    (tmp_path / "a.py").write_text("x=3\n")
    assert not fr.is_fresh(mp, tmp_path)
    try:
        fr.ensure_fresh(mp, mode="refuse", root=tmp_path)
    except SystemExit as e:
        assert e.code == fr.EXIT_STALE
    else:
        raise AssertionError
