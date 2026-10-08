from scripts.browser.session.browser_task_session import (
    BrowserTaskPolicy,
    BrowserTaskTabLimitError,
    cleanup_task_pages,
    close_all_pages,
    get_or_create_task_page,
    host_matches,
)


class FakePage:
    def __init__(self, url: str):
        self.url = url
        self.closed = False
        self.goto_calls = []

    def goto(self, url: str, timeout: int = 30000):
        self.goto_calls.append((url, timeout))
        self.url = url

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, pages=None):
        self.pages = list(pages or [])
        self.created = 0

    def new_page(self):
        self.created += 1
        page = FakePage("about:blank")
        self.pages.append(page)
        return page


def test_host_matches_subdomains():
    assert host_matches("mail.google.com", ("google.com",))
    assert host_matches("google.com", ("google.com",))
    assert not host_matches("notgoogle.com", ("google.com",))


def test_reuses_matching_task_tab_without_creating_new_page():
    existing = FakePage("https://www.youtube.com/watch?v=1")
    context = FakeContext([FakePage("https://www.naver.com/"), existing])
    policy = BrowserTaskPolicy(task_id="youtube-search", allowed_hosts=("youtube.com",))

    page = get_or_create_task_page(context, policy)

    assert page is existing
    assert context.created == 0
    assert page._haehan_task_owned_page is False


def test_reuses_blank_tab_by_navigating_start_url():
    blank = FakePage("about:blank")
    context = FakeContext([blank])
    policy = BrowserTaskPolicy(
        task_id="google-home",
        allowed_hosts=("google.com",),
        start_url="https://www.google.com/",
    )

    page = get_or_create_task_page(context, policy)

    assert page is blank
    assert context.created == 0
    assert blank.goto_calls == [("https://www.google.com/", 30000)]
    assert page._haehan_task_owned_page is True


def test_creates_one_page_when_no_reusable_tab_exists():
    context = FakeContext([FakePage("https://www.naver.com/")])
    policy = BrowserTaskPolicy(
        task_id="youtube-search",
        allowed_hosts=("youtube.com",),
        start_url="https://www.youtube.com/",
    )

    page = get_or_create_task_page(context, policy)

    assert context.created == 1
    assert page.url == "https://www.youtube.com/"
    assert page._haehan_task_owned_page is True


def test_reuses_matching_tab_even_when_total_tab_limit_is_reached():
    existing = FakePage("https://www.youtube.com/watch?v=1")
    context = FakeContext([FakePage("https://www.naver.com/"), existing])
    policy = BrowserTaskPolicy(task_id="youtube-search", allowed_hosts=("youtube.com",), max_total_tabs=2)

    page = get_or_create_task_page(context, policy)

    assert page is existing
    assert context.created == 0


def test_reuses_blank_tab_even_when_total_tab_limit_is_reached():
    blank = FakePage("about:blank")
    context = FakeContext([FakePage("https://www.naver.com/"), blank])
    policy = BrowserTaskPolicy(
        task_id="google-home",
        allowed_hosts=("google.com",),
        start_url="https://www.google.com/",
        max_total_tabs=2,
    )

    page = get_or_create_task_page(context, policy)

    assert page is blank
    assert context.created == 0
    assert blank.url == "https://www.google.com/"


def test_blocks_new_page_when_total_tab_limit_is_reached():
    context = FakeContext([FakePage("https://www.naver.com/"), FakePage("https://www.google.com/")])
    policy = BrowserTaskPolicy(
        task_id="youtube-search",
        allowed_hosts=("youtube.com",),
        start_url="https://www.youtube.com/",
        max_total_tabs=2,
    )

    try:
        get_or_create_task_page(context, policy)
    except BrowserTaskTabLimitError as exc:
        assert "max total allowed is 2" in str(exc)
    else:
        raise AssertionError("expected BrowserTaskTabLimitError")
    assert context.created == 0


def test_cleanup_closes_blank_owned_and_duplicate_tabs_but_keeps_current_page():
    keep = FakePage("https://www.youtube.com/watch?v=1")
    duplicate = FakePage("https://m.youtube.com/watch?v=2")
    blank = FakePage("about:blank")
    owned = FakePage("https://accounts.google.com/")
    owned._haehan_task_owned_page = True
    context = FakeContext([keep, duplicate, blank, owned, FakePage("https://www.naver.com/")])
    policy = BrowserTaskPolicy(task_id="youtube-search", allowed_hosts=("youtube.com",), max_tabs=1)

    report = cleanup_task_pages(context, policy, keep_page=keep)

    assert report["closed"] == 3
    assert keep.closed is False
    assert duplicate.closed is True
    assert blank.closed is True
    assert owned.closed is True
    assert context.pages[-1].closed is False


def test_close_all_pages_closes_every_page_for_browser_shutdown():
    pages = [FakePage("https://a.test/"), FakePage("about:blank")]
    context = FakeContext(pages)

    assert close_all_pages(context) == 2
    assert all(page.closed for page in pages)
