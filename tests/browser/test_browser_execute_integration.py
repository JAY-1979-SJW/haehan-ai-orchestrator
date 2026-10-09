"""BROWSER-3B: Async-native Playwright integration tests."""
import asyncio
import tempfile
from pathlib import Path

import pytest

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

MOCK_HTML_COUNTER = """<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
    <span id="counter">0</span>
    <span id="danger-executed">false</span>
    <button id="increment-btn">Increment</button>
    <button id="submit-btn" onclick="window.dangerExecuted=true;">Submit</button>
    <button id="delete-btn" onclick="window.dangerExecuted=true;">Delete</button>
    <button id="comment-btn" onclick="window.dangerExecuted=true;">댓글 등록</button>
    <button id="register-btn" onclick="window.dangerExecuted=true;">가입</button>
    <button id="payment-btn" onclick="window.dangerExecuted=true;">결제</button>
    <input type="text" id="search-input" />
    <input type="email" id="email-input" />
    <input type="password" id="password-input" />
    <input type="hidden" id="hidden-input" />
    <input type="text" id="otp-input" name="otp_code" placeholder="인증번호" />
    <script>
        window.dangerExecuted = false;
        document.getElementById('increment-btn').addEventListener('click', function() {
            let c = document.getElementById('counter');
            c.innerText = String(parseInt(c.innerText) + 1);
        });
        setInterval(function() {
            document.getElementById('danger-executed').innerText = String(window.dangerExecuted);
        }, 100);
    </script>
</body>
</html>"""

@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestExecuteClickIntegration:
    def test_execute_click_normal_button_increments_counter(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--disable-password-manager"])
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    counter_before = await page.text_content("#counter")
                    assert counter_before == "0"
                    result = await controller.execute_click("#increment-btn", approval_token="test-token")
                    assert result.element_found is True
                    assert result.executed is True
                    counter_after = await page.text_content("#counter")
                    assert counter_after == "1"
                await browser.close()
        asyncio.run(run_test())

    def test_execute_click_without_approval_rejected(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    counter_before = await page.text_content("#counter")
                    result = await controller.execute_click("#increment-btn", approval_token=None)
                    assert result.executed is False
                    counter_after = await page.text_content("#counter")
                    assert counter_after == counter_before
                await browser.close()
        asyncio.run(run_test())

    def test_execute_click_submit_not_executed(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    result = await controller.execute_click("#submit-btn", approval_token="t", final_approval_token=None)
                    assert result.final_approval_required is True
                    assert result.executed is False
                    danger = await page.text_content("#danger-executed")
                    assert danger == "false"
                await browser.close()
        asyncio.run(run_test())

@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestExecuteTypeIntegration:
    def test_execute_type_normal_input_writes_value(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    result = await controller.execute_type("#search-input", "test", approval_token="t")
                    assert result.executed is True
                    value = await page.input_value("#search-input")
                    assert value == "test"
                await browser.close()
        asyncio.run(run_test())

    def test_execute_type_password_rejected(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    result = await controller.execute_type("#password-input", "s", approval_token="t")
                    assert result.executed is False
                    assert result.result == "sensitive_field"
                    value = await page.input_value("#password-input")
                    assert value == ""
                await browser.close()
        asyncio.run(run_test())

    def test_result_no_secrets(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    result = await controller.execute_type("#search-input", "secret", approval_token="token")
                    s = str(result)
                    assert "secret" not in s
                    assert "token" not in s
                await browser.close()
        asyncio.run(run_test())

    def test_execute_type_email_input_writes_value(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    result = await controller.execute_type("#email-input", "test@example.com", approval_token="t")
                    assert result.executed is True
                    value = await page.input_value("#email-input")
                    assert value == "test@example.com"
                await browser.close()
        asyncio.run(run_test())

    def test_execute_type_otp_rejected(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    result = await controller.execute_type("#otp-input", "123456", approval_token="t")
                    assert result.executed is False
                    assert result.result == "sensitive_field"
                    value = await page.input_value("#otp-input")
                    assert value == ""
                await browser.close()
        asyncio.run(run_test())

    def test_execute_type_hidden_rejected(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    result = await controller.execute_type("#hidden-input", "secret", approval_token="t")
                    assert result.executed is False
                    assert result.result == "sensitive_field"
                await browser.close()
        asyncio.run(run_test())

    def test_execute_click_delete_requires_final_approval_and_not_executed(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    result = await controller.execute_click("#delete-btn", approval_token="t", final_approval_token=None)
                    assert result.final_approval_required is True
                    assert result.executed is False
                    danger = await page.text_content("#danger-executed")
                    assert danger == "false"
                await browser.close()
        asyncio.run(run_test())

    def test_execute_click_comment_requires_final_approval_and_not_executed(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    result = await controller.execute_click("#comment-btn", approval_token="t", final_approval_token=None)
                    assert result.final_approval_required is True
                    assert result.executed is False
                    danger = await page.text_content("#danger-executed")
                    assert danger == "false"
                await browser.close()
        asyncio.run(run_test())

    def test_execute_click_register_requires_final_approval_and_not_executed(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    result = await controller.execute_click("#register-btn", approval_token="t", final_approval_token=None)
                    assert result.final_approval_required is True
                    assert result.executed is False
                    danger = await page.text_content("#danger-executed")
                    assert danger == "false"
                await browser.close()
        asyncio.run(run_test())

    def test_execute_click_payment_requires_final_approval_and_not_executed(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    result = await controller.execute_click("#payment-btn", approval_token="t", final_approval_token=None)
                    assert result.final_approval_required is True
                    assert result.executed is False
                    danger = await page.text_content("#danger-executed")
                    assert danger == "false"
                await browser.close()
        asyncio.run(run_test())

    def test_all_risky_buttons_keep_danger_executed_false(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    risky_buttons = ["#submit-btn", "#delete-btn", "#comment-btn", "#register-btn", "#payment-btn"]
                    for btn_selector in risky_buttons:
                        result = await controller.execute_click(btn_selector, approval_token="t", final_approval_token=None)
                        assert result.final_approval_required is True
                        assert result.executed is False
                        danger = await page.text_content("#danger-executed")
                        assert danger == "false"
                await browser.close()
        asyncio.run(run_test())

    def test_result_does_not_include_cookie_session_storage_or_base64_keywords(self):
        from core.agent_runtime.browser.browser_controller import BrowserController
        async def run_test():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(MOCK_HTML_COUNTER)
                with tempfile.TemporaryDirectory() as tmpdir:
                    controller = BrowserController("test-agent", Path(tmpdir))
                    controller.page = page
                    result = await controller.execute_click("#increment-btn", approval_token="t")
                    s = str(result)
                    forbidden_keywords = ["cookie", "session", "storage", "base64"]
                    for keyword in forbidden_keywords:
                        assert keyword.lower() not in s.lower()
                await browser.close()
        asyncio.run(run_test())
