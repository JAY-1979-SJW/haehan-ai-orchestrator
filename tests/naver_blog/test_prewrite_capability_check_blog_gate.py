"""prewrite_capability_check.py 훅의 네이버 블로그 안전 게이트 테스트 (2026-08-14 추가).

검증 대상:
  - BlogWriter를 검증된 경로 밖(스크래치패드 등)에서 직접 쓰면 차단
  - Ctrl+A 직후 set_font_size() 호출하는 위험 패턴 차단
  - 검증된 경로(ai_orchestrator/connectors/ 등)에서의 정상 사용은 통과
  - 절대경로/상대경로 모두 인식 (2026-08-14: startswith만으로는 절대경로에서
    게이트가 무력화되는 버그가 있었음)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "tools" / "hooks" / "prewrite_capability_check.py"


def _run_hook(file_path: str, content: str) -> subprocess.CompletedProcess:
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        encoding="utf-8",
    )


def test_blogwriter_direct_use_outside_reviewed_path_blocked():
    result = _run_hook(
        r"C:\Users\skyjw\AppData\Local\Temp\claude\scratch\post_toc.py",
        "from scripts.naver.blog.core.writer import BlogWriter\nbw = BlogWriter(page)\n",
    )
    assert result.returncode == 2
    assert "BlogWriter" in result.stdout
    assert "write-to-naver" in result.stdout


def test_blogwriter_direct_use_outside_reviewed_path_blocked_relative():
    """상대경로로 전달돼도 동일하게 차단돼야 한다."""
    result = _run_hook(
        "scratch/post_toc.py",
        "from scripts.naver.blog.core.writer import BlogWriter\nbw = BlogWriter(page)\n",
    )
    assert result.returncode == 2


def test_ctrl_a_then_font_size_blocked():
    result = _run_hook(
        r"C:\Users\skyjw\AppData\Local\Temp\claude\scratch\font.py",
        'page.keyboard.press("Control+A")\nbw.set_font_size(16)\n',
    )
    assert result.returncode == 2
    assert "본문 텍스트가 소실" in result.stdout


def test_ctrl_a_then_font_size_blocked_even_with_gap():
    """Ctrl+A와 set_font_size 사이에 다른 코드가 끼어 있어도 잡아야 한다."""
    result = _run_hook(
        r"C:\Users\skyjw\AppData\Local\Temp\claude\scratch\font2.py",
        ('page.keyboard.press("Control+A")\ntime.sleep(0.3)\nsome_unrelated_call()\nbw.set_font_size(16)\n'),
    )
    assert result.returncode == 2


def test_blogwriter_use_inside_reviewed_connector_path_allowed():
    # 저장소에 실제로 있는 검증된 경로를 ROOT 기준으로 쓴다(없는 경로는 '신규 파일 기존 구현 확인' 게이트가 따로 차단)
    result = _run_hook(
        str(ROOT / "ai_orchestrator" / "connectors" / "naver_blog" / "naver_blog_router.py"),
        "from scripts.naver.blog.core.writer import BlogWriter\n",
    )
    assert result.returncode == 0


def test_blogwriter_use_inside_reviewed_naver_scripts_path_allowed():
    # 이 시험은 블로그 안전 게이트만 본다. 없는 새 파일 경로를 쓰면 '신규 파일 기존 구현 확인' 게이트가
    # 별도로 차단하므로, 저장소에 실제로 있는 검증된 경로의 파일을 쓴다(저장소 폴더 위치에도 의존하지 않는다).
    result = _run_hook(
        str(ROOT / "scripts" / "naver" / "blog" / "core" / "writer.py"),
        "from scripts.naver.blog.core.writer import BlogWriter\n",
    )
    assert result.returncode == 0


def test_font_size_alone_without_ctrl_a_allowed():
    """set_font_size() 자체는 위험하지 않다 — Ctrl+A와 결합될 때만 차단."""
    result = _run_hook(
        r"C:\Users\skyjw\AppData\Local\Temp\claude\scratch\font3.py",
        "bw.set_font_size(16)\n",
    )
    assert result.returncode == 0


def test_ctrl_a_font_size_pattern_allowed_inside_test_file():
    """테스트 파일 안에 검증용 문자열 리터럴로 포함되는 건 차단하면 안 된다."""
    result = _run_hook(
        r"C:\work\01. haehan-ai-orchestrator\tests\test_something_else.py",
        "CONTENT = 'page.keyboard.press(\"Control+A\")\\nbw.set_font_size(16)\\n'\n",
    )
    assert result.returncode == 0


def test_unrelated_file_untouched():
    result = _run_hook(
        r"C:\Users\skyjw\AppData\Local\Temp\claude\scratch\unrelated.py",
        "print('hello world')\n",
    )
    assert result.returncode == 0


def test_non_write_tool_ignored():
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "scratch/post_toc.py", "content": "BlogWriter"},
    }
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        encoding="utf-8",
    )
    assert result.returncode == 0
