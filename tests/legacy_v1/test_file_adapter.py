import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

from orchestrator_v1.tasks.file_adapter import file_exists, list_dir, preview_patch, read_file

_TMPDIR = tempfile.gettempdir()
_ALLOWED = [_TMPDIR]
_BLOCKED = ["/etc/", "/var/lib/"]


def test_read_file_success():
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False, dir=_TMPDIR) as f:
        f.write("hello world")
        path = f.name

    result = read_file(path, _ALLOWED, _BLOCKED)
    assert result["status"] == "OK", result
    assert "hello world" in result["content"]
    Path(path).unlink()


def test_list_dir_success():
    with tempfile.TemporaryDirectory(dir=_TMPDIR) as d:
        (Path(d) / "a.txt").open("w").close()
        (Path(d) / "b.txt").open("w").close()
        result = list_dir(d, _ALLOWED, _BLOCKED)
    assert result["status"] == "OK", result
    assert result["count"] == 2


def test_blocked_path_fails():
    # Use a custom blocked list with a temp subdir to test blocking on any OS
    with tempfile.TemporaryDirectory(dir=_TMPDIR) as blocked_dir:
        test_file = Path(blocked_dir) / "secret.txt"
        test_file.open("w").close()
        result = read_file(test_file, _ALLOWED, [blocked_dir])
    assert result["status"] == "BLOCKED"


def test_preview_patch_does_not_modify_file():
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False, dir=_TMPDIR) as f:
        f.write("original content")
        path = f.name

    result = preview_patch(path, "new content", _ALLOWED, _BLOCKED)
    assert result["status"] == "PREVIEW_ONLY", result
    assert result.get("note") and "NOT modified" in result["note"]

    with Path(path).open(encoding="utf-8") as f:
        assert f.read() == "original content"
    Path(path).unlink()


def test_file_exists_in_allowed():
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False, dir=_TMPDIR) as f:
        path = f.name

    result = file_exists(path, _ALLOWED, _BLOCKED)
    assert result["status"] == "OK", result
    assert result["exists"] is True
    Path(path).unlink()


def test_preview_patch_has_diff():
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False, dir=_TMPDIR) as f:
        f.write("line1\nline2\n")
        path = f.name

    result = preview_patch(path, "line1\nline3\n", _ALLOWED, _BLOCKED)
    assert result["status"] == "PREVIEW_ONLY", result
    assert "-line2" in result["diff"] or "+line3" in result["diff"]
    Path(path).unlink()
