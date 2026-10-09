from tools.hooks import agent_usage as u


def test_record_summarize(tmp_path):
    log = tmp_path / "x" / "u.jsonl"
    u.record("s1", "implement", 100, 5, "1", log)
    u.record("s1", "implement", 50, 2, "1", log)
    u.record("s2", "review", 999, 1, "", log)
    s = u.summarize(u.load(log), "s1", budget=120)
    assert s["total_tokens"] == 150 and s["total_calls"] == 7
    assert s["by"][("1", "implement")]["n"] == 2
    assert s["over_budget"] is True
    assert u.summarize(u.load(log), "s1", budget=200)["over_budget"] is False
