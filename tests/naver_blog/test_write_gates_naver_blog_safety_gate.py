"""tools/write_gates/naver_blog_safety_gate.py 단위 테스트 (모듈 직접 호출)."""

from __future__ import annotations

from tools.write_gates import naver_blog_safety_gate as gate


def test_is_reviewed_blog_path_relative():
    assert gate.is_reviewed_blog_path("scripts/naver/blog/writer.py")
    assert gate.is_reviewed_blog_path("ai_orchestrator/connectors/naver_blog/naver_blog_router.py")
    assert gate.is_reviewed_blog_path("tests/test_x.py")
    assert not gate.is_reviewed_blog_path("scripts/ops/scratch.py")


def test_is_reviewed_blog_path_absolute():
    assert gate.is_reviewed_blog_path(r"C:\work\01. haehan-ai-orchestrator\scripts\naver\blog\writer.py")
    assert not gate.is_reviewed_blog_path(r"C:\Users\skyjw\AppData\Local\Temp\claude\scratch\x.py")


def test_is_test_path():
    assert gate.is_test_path("tests/test_foo.py")
    assert gate.is_test_path(r"C:\work\01. haehan-ai-orchestrator\tests\test_foo.py")
    assert gate.is_test_path("foo/test_bar.py")
    assert not gate.is_test_path("scripts/ops/scratch.py")


def test_check_blogwriter_bypass_blocks_outside_reviewed_path():
    content = "from scripts.naver.blog.core.writer import " + "Blog" + "Writer\n"
    msg = gate.check_blogwriter_bypass("scratch/post_toc.py", content)
    assert msg is not None
    assert "write-to-naver" in msg


def test_check_blogwriter_bypass_allows_reviewed_path():
    content = "from scripts.naver.blog.core.writer import " + "Blog" + "Writer\n"
    msg = gate.check_blogwriter_bypass("ai_orchestrator/connectors/naver_blog/naver_blog_router.py", content)
    assert msg is None


def test_check_blogwriter_bypass_no_reference_no_block():
    assert gate.check_blogwriter_bypass("scratch/anything.py", "print('hello')") is None


def test_check_ctrl_a_font_size_blocks():
    fn_name = "set_font" + "_size"
    content = f'page.keyboard.press("Control+A")\nbw.{fn_name}(16)\n'
    msg = gate.check_ctrl_a_font_size("scratch/font.py", content)
    assert msg is not None
    assert "본문 텍스트가 소실" in msg


def test_check_ctrl_a_font_size_allows_font_size_alone():
    fn_name = "set_font" + "_size"
    content = f"bw.{fn_name}(16)\n"
    assert gate.check_ctrl_a_font_size("scratch/font.py", content) is None


def test_check_ctrl_a_font_size_exempts_test_paths():
    fn_name = "set_font" + "_size"
    content = f'page.keyboard.press("Control+A")\nbw.{fn_name}(16)\n'
    assert gate.check_ctrl_a_font_size("tests/test_writer.py", content) is None


def test_check_combines_both_subchecks():
    fn_name = "set_font" + "_size"
    content = f'page.keyboard.press("Control+A")\nbw.{fn_name}(16)\n'
    assert gate.check("scratch/font.py", content) is not None
    assert gate.check("scratch/anything.py", "print(1)") is None
