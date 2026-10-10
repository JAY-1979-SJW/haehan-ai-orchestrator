from tools.verify import dry_run_manual_local_agent_browser_smoke as dry


def test_manual_local_agent_browser_smoke_dry_run_ready():
    result = dry.dry_run()
    assert result.passed is True
    assert result.verdict == "PASS_MANUAL_LOCAL_AGENT_BROWSER_SMOKE_DRY_RUN_READY"


def test_dry_run_script_does_not_start_runtime():
    script = dry.Path(dry.__file__).read_text(encoding="utf-8", errors="replace")
    forbidden = tuple(
        "".join(parts)
        for parts in (
            ("url", "open", "("),
            ("subprocess", ".", "Popen", "("),
            ("web", "browser", "."),
        )
    ) + tuple(
        " ".join(parts)
        for parts in (
            ("docker", "compose"),
            ("git", "push"),
            ("npm", "run", "build"),
        )
    )
    assert forbidden, "forbidden 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert [token for token in forbidden if token in script] == []
