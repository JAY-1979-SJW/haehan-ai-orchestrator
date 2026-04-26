"""F-4S-13b check_ffmpeg_availability CLI 테스트."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from scripts.check_ffmpeg_availability import (
    check_ffmpeg_availability,
    render_availability_markdown,
    write_availability_files,
    main,
)


# ---------------------------------------------------------------------------
# ffmpeg 없음 상태
# ---------------------------------------------------------------------------


def test_ffmpeg_not_found():
    with patch("shutil.which", return_value=None):
        result = check_ffmpeg_availability()
    assert result["ffmpeg_found"] is False
    assert result["ffmpeg_path"] is None
    assert result["recommendation"] == "install_required"
    assert any("ffmpeg_not_found" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# ffmpeg 있음 상태
# ---------------------------------------------------------------------------


def test_ffmpeg_found():
    mock_proc = MagicMock()
    mock_proc.stdout = "ffmpeg version 6.1.1\nsome other line\n"
    mock_proc.stderr = ""

    with patch("shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "ffmpeg" else None), \
         patch("subprocess.run", return_value=mock_proc):
        result = check_ffmpeg_availability()

    assert result["ffmpeg_found"] is True
    assert result["ffmpeg_path"] == "/usr/bin/ffmpeg"
    assert result["ffmpeg_version_line"] == "ffmpeg version 6.1.1"
    assert result["recommendation"] == "ready_for_render_smoke"


# ---------------------------------------------------------------------------
# ffprobe 있음/없음
# ---------------------------------------------------------------------------


def test_ffprobe_found():
    mock_proc = MagicMock()
    mock_proc.stdout = "ffprobe version 6.1.1\n"
    mock_proc.stderr = ""

    def which_side(name):
        return f"/usr/bin/{name}" if name in ("ffmpeg", "ffprobe") else None

    with patch("shutil.which", side_effect=which_side), \
         patch("subprocess.run", return_value=mock_proc):
        result = check_ffmpeg_availability()

    assert result["ffprobe_found"] is True
    assert result["ffprobe_path"] == "/usr/bin/ffprobe"
    assert result["ffprobe_version_line"] == "ffprobe version 6.1.1"


def test_ffprobe_not_found():
    mock_proc = MagicMock()
    mock_proc.stdout = "ffmpeg version 6.1.1\n"
    mock_proc.stderr = ""

    with patch("shutil.which", side_effect=lambda n: "/usr/bin/ffmpeg" if n == "ffmpeg" else None), \
         patch("subprocess.run", return_value=mock_proc):
        result = check_ffmpeg_availability()

    assert result["ffprobe_found"] is False
    assert any("ffprobe_not_found" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# subprocess.run 호출 시 shell=False
# ---------------------------------------------------------------------------


def test_subprocess_called_with_shell_false():
    mock_proc = MagicMock()
    mock_proc.stdout = "ffmpeg version 6.1.1\n"
    mock_proc.stderr = ""

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("subprocess.run", return_value=mock_proc) as mock_run:
        check_ffmpeg_availability()

    for c in mock_run.call_args_list:
        assert c.kwargs.get("shell", False) is False


# ---------------------------------------------------------------------------
# 렌더링 인자 미사용 (-i, -c:v 등)
# ---------------------------------------------------------------------------


def test_no_render_args_in_subprocess():
    mock_proc = MagicMock()
    mock_proc.stdout = "ffmpeg version 6.1.1\n"
    mock_proc.stderr = ""

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("subprocess.run", return_value=mock_proc) as mock_run:
        check_ffmpeg_availability()

    for c in mock_run.call_args_list:
        cmd = c.args[0] if c.args else []
        assert "-i" not in cmd
        assert "-c:v" not in cmd
        assert "-vf" not in cmd


# ---------------------------------------------------------------------------
# JSON/MD 파일 생성
# ---------------------------------------------------------------------------


def test_write_availability_files_creates_json_and_md(tmp_path):
    result = {"ffmpeg_found": False, "ffprobe_found": False,
               "ffmpeg_path": None, "ffprobe_path": None,
               "ffmpeg_version_line": None, "ffprobe_version_line": None,
               "platform": "Windows", "recommendation": "install_required",
               "generated_at": "2026-04-26T00:00:00Z", "warnings": [], "notes": []}
    paths = write_availability_files(result, tmp_path / "out", timestamp="20260426_000000")
    assert Path(paths["json"]).exists()
    assert Path(paths["md"]).exists()
    data = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert "ffmpeg_found" in data


def test_cli_creates_json_and_md(tmp_path):
    with patch("shutil.which", return_value=None), \
         patch("sys.argv", ["check_ffmpeg_availability.py",
                             "--out-dir", str(tmp_path / "out")]):
        rc = main()
    assert rc == 0
    assert len(list((tmp_path / "out").glob("ffmpeg_availability_*.json"))) == 1
    assert len(list((tmp_path / "out").glob("ffmpeg_availability_*.md"))) == 1


# ---------------------------------------------------------------------------
# secret 문자열 없음
# ---------------------------------------------------------------------------


def test_no_secret_in_result():
    with patch("shutil.which", return_value=None):
        result = check_ffmpeg_availability()
    serialized = json.dumps(result).lower()
    for kw in ("api_key", "client_secret", "password", "bearer"):
        assert kw not in serialized


# ---------------------------------------------------------------------------
# os.system 없음 / shell=True 없음
# ---------------------------------------------------------------------------


def test_no_os_system_in_source():
    import scripts.check_ffmpeg_availability as m
    src = Path(m.__file__).read_text(encoding="utf-8")
    # 실제 호출 여부 확인 (docstring/주석의 언급 제외)
    # "os.system(" 패턴 또는 "shell=True" 실제 사용만 검사
    import re
    assert not re.search(r'\bos\.system\s*\(', src), "os.system() 호출 금지"
    # subprocess.run 호출에서 shell=True keyword 사용 여부만 검사
    # (문자열 리터럴/docstring 내 언급은 무시)
    # subprocess.run 호출 블록 추출 후 확인
    for m in re.finditer(r'subprocess\.run\s*\(([^)]*(?:\([^)]*\)[^)]*)*)\)', src, re.DOTALL):
        call_body = m.group(1)
        assert not re.search(r'shell\s*=\s*True', call_body), \
            f"subprocess.run에 shell=True 사용 금지: {call_body[:80]}"


# ---------------------------------------------------------------------------
# upload/OAuth/browser 없음
# ---------------------------------------------------------------------------


def test_no_upload_oauth_browser_in_source():
    import scripts.check_ffmpeg_availability as m
    src = Path(m.__file__).read_text(encoding="utf-8")
    code_lines = [l for l in src.splitlines()
                  if not l.strip().startswith("#") and '"""' not in l and "'''" not in l]
    code = "\n".join(code_lines).lower()
    assert "import playwright" not in code
    assert "chromium" not in code
    assert "requests_oauthlib" not in code
    assert ".upload(" not in code


# ---------------------------------------------------------------------------
# markdown 출력 검증
# ---------------------------------------------------------------------------


def test_markdown_contains_recommendation():
    result = {
        "generated_at": "2026-04-26T00:00:00Z",
        "platform": "Windows",
        "ffmpeg_found": False, "ffmpeg_path": None, "ffmpeg_version_line": None,
        "ffprobe_found": False, "ffprobe_path": None, "ffprobe_version_line": None,
        "recommendation": "install_required",
        "warnings": ["ffmpeg_not_found:install_required"],
        "notes": [],
    }
    md = render_availability_markdown(result)
    assert "install_required" in md
    assert "ffmpeg_not_found" in md
