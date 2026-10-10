from scripts.eum import auth


def test_eum_terminal_company_subtype_is_distribution_company():
    assert auth._TERMINAL_COMPANY_SUBTYPE == "유통업체"
    assert auth._TERMINAL_COMPANY_SUBTYPE_SELECTOR_FALLBACK == "#radio_b2"


def test_eum_id_selectors_cover_placeholder_search_input():
    assert auth._ID_SELECTORS[0] == "#tab4 input[placeholder*='아이디']"
    assert "input[placeholder*='아이디']:not([type='hidden'])" in auth._ID_SELECTORS
    assert "input[type='search'][placeholder*='아이디']" in auth._ID_SELECTORS


def test_eum_password_selectors_prefer_active_terminal_company_tab():
    assert auth._PW_SELECTORS[0] == "#tab4 input[type='password']"


def test_eum_form_login_button_precedes_header_login_fallback():
    assert auth._BTN_SELECTORS[0] == "#tab4 button.btn_l:has-text('로그인')"
    form_button = auth._BTN_SELECTORS.index("button.btn_l:has-text('로그인')")
    generic_button = auth._BTN_SELECTORS.index("button:has-text('로그인')")
    assert form_button < generic_button


def test_eum_alert_message_selectors_are_documented_in_source():
    source = auth.login.__code__.co_consts
    joined = "\n".join(str(item) for item in source)
    assert "#alertMsg0" in joined
    assert ".pop_modal_alert .pop_msg" in joined
