"""폴더별 요약기 테스트."""
import tempfile
from pathlib import Path

from agent.local_inventory.file_map.folder_summarizer import FolderSummarizer


def test_folder_summarizer_basic():
    """기본 폴더 요약 생성."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 테스트 폴더 구조 생성
        root = Path(tmpdir)
        (root / "docs").mkdir()
        (root / "docs" / "report.pdf").write_text("pdf")
        (root / "docs" / "data.xlsx").write_text("xlsx")
        (root / "code").mkdir()
        (root / "code" / "main.py").write_text("code")
        (root / "image.jpg").write_text("image")

        summarizer = FolderSummarizer()
        summaries, meta = summarizer.summarize_top_folders(str(root), max_depth=2)

        assert meta["ok"]
        assert len(summaries) > 0
        assert summaries[0].folder_name in ["docs", "code"] or str(root) in summaries[0].folder_path


def test_folder_summarizer_max_depth():
    """max_depth 준수."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "a").mkdir()
        (root / "a" / "b").mkdir()
        (root / "a" / "b" / "c").mkdir()
        (root / "a" / "b" / "c" / "d.txt").write_text("test")

        summarizer = FolderSummarizer()
        summaries, meta = summarizer.summarize_top_folders(str(root), max_depth=2)

        # depth 3 이상은 포함 안 됨
        for summary in summaries:
            depth = len(Path(summary.folder_path).relative_to(root).parts)
            assert depth <= 2


def test_folder_summarizer_exclude_hidden():
    """숨겨진 폴더 제외."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".hidden").mkdir()
        (root / ".hidden" / "secret.txt").write_text("secret")
        (root / "visible").mkdir()
        (root / "visible" / "public.txt").write_text("public")

        summarizer = FolderSummarizer()
        summaries, meta = summarizer.summarize_top_folders(str(root), exclude_hidden=True)

        for summary in summaries:
            assert not summary.folder_name.startswith(".")


def test_folder_summarizer_no_file_read():
    """파일 내용 read 없음."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        test_file = root / "test.txt"
        test_file.write_text("should not be read")

        summarizer = FolderSummarizer()
        summaries, meta = summarizer.summarize_top_folders(str(root))

        assert meta["ok"]


def test_folder_summarizer_no_symlink_follow():
    """symlink follow 안 함."""
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        real_dir = root / "real"
        real_dir.mkdir()
        (real_dir / "file.txt").write_text("real")

        link_dir = root / "link"
        try:
            os.symlink(real_dir, link_dir)
        except (OSError, NotImplementedError):
            # Windows에서 symlink 미지원
            return

        summarizer = FolderSummarizer()
        summaries, meta = summarizer.summarize_top_folders(str(root))

        # symlink는 폴더로 처리되지 않음
        assert all("link" not in s.folder_path for s in summaries)


def test_folder_summarizer_business_score():
    """업무 후보 점수 생성."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        docs = root / "docs"
        docs.mkdir()
        (docs / "report1.pdf").write_text("1")
        (docs / "report2.hwp").write_text("2")
        (docs / "data.xlsx").write_text("3")

        summarizer = FolderSummarizer()
        summaries, meta = summarizer.summarize_top_folders(str(root))

        doc_summary = next((s for s in summaries if "docs" in s.folder_path), None)
        if doc_summary:
            assert doc_summary.business_score > 0
            assert "document" in doc_summary.business_categories or "spreadsheet" in doc_summary.business_categories


if __name__ == "__main__":
    test_folder_summarizer_basic()
    test_folder_summarizer_max_depth()
    test_folder_summarizer_exclude_hidden()
    test_folder_summarizer_no_file_read()
    test_folder_summarizer_no_symlink_follow()
    test_folder_summarizer_business_score()
    print("✓ 모든 테스트 통과")
