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


# ---- 변이체 사멸용 보강(정확한 출력) ----
import builtins  # noqa: E402
from pathlib import Path  # noqa: E402

HEAD = "## 변이 검증(mutmut)\n\n"
NODECIDED = "- ⚠ **실행된 변이체 0 — 설정 확인 필요**(패턴이 변이체 이름과 안 맞거나 source_paths 범위 문제)\n"
NOFILE = "## 변이 검증(mutmut)\n\n통계 파일이 없습니다(대상 함수 없음 또는 실행 실패).\n"


def test_render_exact_full_text(monkeypatch):
    monkeypatch.delenv("MUTMUT_RUN_FAILED", raising=False)
    full = sm.render({"killed": 1, "survived": 3, "no_tests": 5, "timeout": 2, "suspicious": 4, "skipped": 6, "total": 100})
    assert full == (
        HEAD + "- 점수(killed/(killed+survived)): **25.0%** (1/4)\n"
        "- survived: 3\n- timeout: 2\n- suspicious: 4\n- skipped: 6\n"
        "- 시험이 없는 변이체(no_tests): 5\n"
    )


def test_render_missing_keys_default_to_zero(monkeypatch):
    monkeypatch.delenv("MUTMUT_RUN_FAILED", raising=False)
    zeros = "- survived: 0\n- timeout: 0\n- suspicious: 0\n- skipped: 0\n- 시험이 없는 변이체(no_tests): 0\n"
    assert sm.render({}) == HEAD + "- 점수(killed/(killed+survived)): **n/a** (0/0)\n" + zeros + NODECIDED
    assert sm.render({"killed": 0, "survived": 0}) == sm.render({})
    assert sm.render({"killed": 2}) == HEAD + "- 점수(killed/(killed+survived)): **100.0%** (2/2)\n" + zeros
    assert sm.render({"survived": 2}) == HEAD + "- 점수(killed/(killed+survived)): **0.0%** (0/2)\n" + zeros.replace("survived: 0", "survived: 2")
    assert "**68.2%** (300/440)" in sm.render({"killed": 300, "survived": 140})


def test_render_failure_and_truncation_lines_exact(monkeypatch):
    monkeypatch.setenv("MUTMUT_RUN_FAILED", "1")
    text = sm.render({"killed": 1, "survived": 1}, total_targets=41, limit=40)
    assert text.endswith(
        "- 🔴 **mutmut 실행 자체 실패**(통계 수집/시험 수집 오류) — 점수는 의미 없음, 로그 확인\n"
        "- ⚠ 대상 함수 41개 중 40개만 검사함(상한 절삭)\n"
    )
    assert NODECIDED not in text
    monkeypatch.setenv("MUTMUT_RUN_FAILED", "")
    assert "실행 자체 실패" not in sm.render({"killed": 1})
    monkeypatch.delenv("MUTMUT_RUN_FAILED")
    t2 = sm.render({}, total_targets=5, limit=2)
    assert t2.endswith(NODECIDED + "- ⚠ 대상 함수 5개 중 2개만 검사함(상한 절삭)\n")


def test_main_defaults_when_env_missing(tmp_path, monkeypatch, capsys):
    stats = tmp_path / "s.json"
    stats.write_text(json.dumps({"killed": 1, "survived": 1}), encoding="utf-8")
    monkeypatch.setattr(sm, "STATS", stats)
    for k in ("GITHUB_STEP_SUMMARY", "TOTAL_TARGETS", "TARGET_LIMIT", "MUTMUT_RUN_FAILED"):
        monkeypatch.delenv(k, raising=False)
    assert sm.main() == 0
    assert capsys.readouterr().out == sm.render({"killed": 1, "survived": 1}, 0, 0)
    monkeypatch.setenv("TOTAL_TARGETS", "")
    monkeypatch.setenv("TARGET_LIMIT", "")
    assert sm.main() == 0
    assert "절삭" not in capsys.readouterr().out
    monkeypatch.setenv("TARGET_LIMIT", "40")
    monkeypatch.delenv("TOTAL_TARGETS")
    sm.main()
    assert "절삭" not in capsys.readouterr().out
    monkeypatch.setenv("TOTAL_TARGETS", "50")
    monkeypatch.delenv("TARGET_LIMIT")
    sm.main()
    assert "절삭" not in capsys.readouterr().out
    monkeypatch.setenv("TARGET_LIMIT", "40")
    sm.main()
    assert "- ⚠ 대상 함수 50개 중 40개만 검사함(상한 절삭)\n" in capsys.readouterr().out


def test_main_missing_or_corrupt_stats_message_exact(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(sm, "STATS", tmp_path / "none.json")
    assert sm.main() == 0
    out = capsys.readouterr()
    assert out.out == NOFILE and out.err == ""
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(sm, "STATS", bad)
    assert sm.main() == 0
    assert capsys.readouterr().out == NOFILE
    bad.write_bytes(b"\xff\xfe\x00")  # UnicodeDecodeError 는 ValueError
    assert sm.main() == 0
    assert capsys.readouterr().out == NOFILE


def test_main_appends_to_summary_file_utf8(tmp_path, monkeypatch, capsys):
    stats = tmp_path / "s.json"
    stats.write_text(json.dumps({"killed": 1, "survived": 1}), encoding="utf-8")
    summary = tmp_path / "sum.md"
    summary.write_text("앞 내용\n", encoding="utf-8")
    monkeypatch.setattr(sm, "STATS", stats)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("TOTAL_TARGETS", raising=False)
    monkeypatch.delenv("TARGET_LIMIT", raising=False)
    monkeypatch.delenv("MUTMUT_RUN_FAILED", raising=False)
    opens, reads = [], []
    real_open, real_read = builtins.open, Path.read_text

    def spy_open(*a, **k):
        opens.append((a, k))
        return real_open(*a, **k)

    def spy_read(self, *a, **k):
        reads.append((self.name, a, k))
        return real_read(self, *a, **k)

    monkeypatch.setattr(sm, "open", spy_open, raising=False)
    monkeypatch.setattr(Path, "read_text", spy_read)
    assert sm.main() == 0
    assert capsys.readouterr().out == ""
    assert opens == [((str(summary), "a"), {"encoding": "utf-8"})]
    assert reads == [("s.json", (), {"encoding": "utf-8"})]
    assert summary.read_text(encoding="utf-8") == "앞 내용\n" + sm.render({"killed": 1, "survived": 1})
    monkeypatch.setattr(sm, "STATS", tmp_path / "none.json")
    summary.write_text("", encoding="utf-8")
    assert sm.main() == 0
    assert summary.read_text(encoding="utf-8") == NOFILE


def test_stats_path_constant():
    assert sm.STATS == Path("mutants/mutmut-cicd-stats.json")


def test_main_empty_limit_env_means_no_limit(tmp_path, monkeypatch, capsys):
    stats = tmp_path / "s.json"
    stats.write_text(json.dumps({"killed": 1, "survived": 1}), encoding="utf-8")
    monkeypatch.setattr(sm, "STATS", stats)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setenv("TOTAL_TARGETS", "50")
    monkeypatch.setenv("TARGET_LIMIT", "")
    assert sm.main() == 0
    assert capsys.readouterr().out == sm.render({"killed": 1, "survived": 1}, 50, 0)
    monkeypatch.setenv("TARGET_LIMIT", "0")
    assert sm.main() == 0
    assert "절삭" not in capsys.readouterr().out


def test_render_default_limit_is_unlimited():
    assert "절삭" not in sm.render({"killed": 1}, total_targets=5)
    assert "절삭" not in sm.render({"killed": 1}, 5)
