import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adapters.file_adapter import file_exists, list_dir, preview_patch, read_file

_TMPDIR = tempfile.gettempdir()
_ALLOWED = [_TMPDIR]
_BLOCKED = ["/etc/", "/var/lib/"]


def test_read_file_success():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir=_TMPDIR) as f:
        f.write("hello world")
        path = f.name

    result = read_file(path, _ALLOWED, _BLOCKED)
    assert result["status"] == "OK", result
    assert "hello world" in result["content"]
    os.unlink(path)


def test_list_dir_success():
    with tempfile.TemporaryDirectory(dir=_TMPDIR) as d:
        open(os.path.join(d, "a.txt"), "w").close()
        open(os.path.join(d, "b.txt"), "w").close()
        result = list_dir(d, _ALLOWED, _BLOCKED)
    assert result["status"] == "OK", result
    assert result["count"] == 2


def test_blocked_path_fails():
    # Use a custom blocked list with a temp subdir to test blocking on any OS
    with tempfile.TemporaryDirectory(dir=_TMPDIR) as blocked_dir:
        test_file = os.path.join(blocked_dir, "secret.txt")
        open(test_file, "w").close()
        result = read_file(test_file, _ALLOWED, [blocked_dir])
    assert result["status"] == "BLOCKED"


def test_preview_patch_does_not_modify_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir=_TMPDIR) as f:
        f.write("original content")
        path = f.name

    result = preview_patch(path, "new content", _ALLOWED, _BLOCKED)
    assert result["status"] == "PREVIEW_ONLY", result
    assert result.get("note") and "NOT modified" in result["note"]

    with open(path) as f:
        assert f.read() == "original content"
    os.unlink(path)


def test_file_exists_in_allowed():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir=_TMPDIR) as f:
        path = f.name

    result = file_exists(path, _ALLOWED, _BLOCKED)
    assert result["status"] == "OK", result
    assert result["exists"] is True
    os.unlink(path)


def test_preview_patch_has_diff():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir=_TMPDIR) as f:
        f.write("line1\nline2\n")
        path = f.name

    result = preview_patch(path, "line1\nline3\n", _ALLOWED, _BLOCKED)
    assert result["status"] == "PREVIEW_ONLY", result
    assert "-line2" in result["diff"] or "+line3" in result["diff"]
    os.unlink(path)
