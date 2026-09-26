from scripts.ops import py311_gate as g


def test_missing_interpreter_reports_unverified(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "find_py311", lambda: None)
    assert g.run_gate(tmp_path, ["a.py"]) == [g.UNVERIFIED]


def test_compile_error_reported(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(g, "find_py311", lambda: [sys.executable])
    (tmp_path / "bad.py").write_text("def (:\n")
    (tmp_path / "ok.py").write_text("x=1\n")
    probs = g.run_gate(tmp_path, ["bad.py", "ok.py"])
    assert len(probs) == 1 and "bad.py" in probs[0]
