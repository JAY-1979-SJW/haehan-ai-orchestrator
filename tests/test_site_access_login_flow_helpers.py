from scripts.site_engine import site_access


class _Spec:
    def __init__(self, states):
        self._states = list(states)

    def is_logged_in(self, page):
        if self._states:
            return self._states.pop(0)
        return False


def test_check_logged_in_with_retry_accepts_delayed_logged_in(monkeypatch):
    sleeps = []
    monkeypatch.setattr(site_access.time, "sleep", lambda seconds: sleeps.append(seconds))

    spec = _Spec([False, False, True])

    assert site_access._check_logged_in_with_retry(object(), spec, retries=5) is True
    assert sleeps == [
        site_access.PRE_LOGIN_CHECK_INTERVAL_S,
        site_access.PRE_LOGIN_CHECK_INTERVAL_S,
    ]


def test_registered_login_terminal_failure_blocks_universal_fallback():
    result = {
        "ok": False,
        "reason": "different_user_logged_in",
        "current_user": "other",
        "target_user": "target",
    }

    assert site_access._registered_login_failure_is_terminal(result) is True


def test_registered_login_form_failure_can_use_universal_fallback():
    result = {"ok": False, "reason": "form_not_found"}

    assert site_access._registered_login_failure_is_terminal(result) is False


def test_unknown_login_strategy_defaults_to_registered_only():
    class _StrategySpec:
        login_strategy = "surprising"

    assert site_access._login_strategy(_StrategySpec()) == site_access.LOGIN_STRATEGY_REGISTERED_ONLY


def test_universal_login_requires_explicit_strategy():
    class _RegisteredOnly:
        login_strategy = "registered_only"

    class _UniversalAllowed:
        login_strategy = "registered_then_universal"

    assert site_access._allows_universal_login(_RegisteredOnly()) is False
    assert site_access._allows_universal_login(_UniversalAllowed()) is True


def test_site_session_domains_include_base_login_and_parent_domain():
    class _DomainSpec:
        base_url = "https://www.naver.com"
        login_domain_hints = ("nid.naver.com", "/nidlogin")

    assert site_access._site_session_domains(_DomainSpec()) == [
        "naver.com",
        "nid.naver.com",
        "www.naver.com",
    ]


def test_dry_run_force_login_reports_reset(monkeypatch):
    class _DrySpec:
        base_url = "https://example.com"
        login_domain_hints = ()

    monkeypatch.setattr(site_access, "_has_credentials", lambda site: True)

    result = site_access._dry_run_open(
        "example",
        "https://example.com",
        _DrySpec(),
        ensure_login=True,
        force_login=True,
    )

    assert result["dry_run"] is True
    assert result["logged_in"] is True


def test_dry_run_manual_only_skips_credentials(monkeypatch):
    class _DrySpec:
        base_url = "https://example.com"
        login_domain_hints = ()
        login_strategy = site_access.LOGIN_STRATEGY_MANUAL_ONLY

    monkeypatch.setattr(site_access, "_has_credentials", lambda site: False)

    result = site_access._dry_run_open(
        "example",
        "https://example.com",
        _DrySpec(),
        ensure_login=True,
    )

    assert result["dry_run"] is True
