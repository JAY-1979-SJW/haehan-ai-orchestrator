import json

from scripts.ops import summarize_mutation as sm


def test_render_lists_each_count_and_no_tests_separately():
    text = sm.render({"killed": 1, "survived": 3, "no_tests": 5, "timeout": 2, "suspicious": 4, "skipped": 6})
    assert "25.0%" in text and "1/4" in text
    assert "- survived: 3" in text and "- timeout: 2" in text
    assert "- suspicious: 4" in text and "- skipped: 6" in text
    assert "시험이 없는 변이체(no_tests): 5" in text


def test_render_truncation_note_only_when_limit_exceeded():
    assert "절삭" in sm.render({"killed": 1}, total_targets=41, limit=40)
    assert "절삭" not in sm.render({"killed": 1}, total_targets=40, limit=40)
    assert "절삭" not in sm.render({"killed": 1}, total_targets=99, limit=0)


def test_render_run_failure_warning(monkeypatch):
    monkeypatch.setenv("MUTMUT_RUN_FAILED", "1")
    assert "실행 자체 실패" in sm.render({"killed": 1})
    monkeypatch.delenv("MUTMUT_RUN_FAILED")
    assert "실행 자체 실패" not in sm.render({"killed": 1})


def test_main_writes_summary_file_and_returns_zero(tmp_path, monkeypatch):
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps({"killed": 2, "survived": 2}), encoding="utf-8")
    out = tmp_path / "summary.md"
    monkeypatch.setattr(sm, "STATS", stats)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(out))
    monkeypatch.setenv("TOTAL_TARGETS", "50")
    monkeypatch.setenv("TARGET_LIMIT", "40")
    assert sm.main() == 0
    text = out.read_text(encoding="utf-8")
    assert "50.0%" in text and "50개 중 40개" in text


def test_main_without_stats_file_still_returns_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sm, "STATS", tmp_path / "missing.json")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert sm.main() == 0
    assert "통계 파일이 없습니다" in capsys.readouterr().out
