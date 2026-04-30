"""Browser automation controller for local agent desktop tasks.

This module provides a Playwright-based browser controller with emphasis on:
- Isolated profiles (no cookie/session extraction)
- Dry-run planning (no actual execution until approved)
- Secret redaction (no password/OTP/token values exposed)
- Safe inspection (URL/title/DOM structure only)
"""

import asyncio
from pathlib import Path
from typing import Optional, Any, Dict, List
import logging
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class InspectResult:
    """Result of page inspection (url/title/inputs/clickables)."""
    url: str
    title: str
    inputs: List[Dict[str, Any]]
    clickables: List[Dict[str, Any]]
    login_required: bool = False
    otp_detected: bool = False


@dataclass
class PlanClickResult:
    """Result of dry-run click planning."""
    action: str = "browser_plan_click"
    selector: str = ""
    element_found: bool = False
    element_text: str = ""
    element_tag: str = ""
    dry_run: bool = True
    would_click: bool = False
    executed: bool = False
    next_step: str = "request_approval"


@dataclass
class PlanTypeResult:
    """Result of dry-run type planning."""
    action: str = "browser_plan_type"
    selector: str = ""
    element_found: bool = False
    field_type: str = ""
    text_length: int = 0
    text_preview: str = "[REDACTED]"
    dry_run: bool = True
    would_type: bool = False
    executed: bool = False
    next_step: str = "request_approval"


@dataclass
class PlanSubmitResult:
    """Result of submit planning (critical action)."""
    action: str = "browser_submit"
    selector: str = ""
    risk_level: str = "critical"
    final_approval_required: bool = True
    executed: bool = False


class BrowserControllerError(Exception):
    """Base exception for browser controller."""
    pass


class BrowserController:
    """Browser controller using Playwright with isolated profiles."""

    def __init__(self, agent_id: str, profile_base_dir: Optional[Path] = None):
        """Initialize browser controller.

        Args:
            agent_id: Unique agent identifier
            profile_base_dir: Base directory for browser profiles (default: ~/.haehan-agent/browser-profiles)
        """
        self.agent_id = agent_id

        if profile_base_dir is None:
            profile_base_dir = Path.home() / ".haehan-agent" / "browser-profiles"

        self.profile_dir = profile_base_dir / agent_id
        self.browser = None
        self.page = None
        self._playwright = None

    async def launch(self, headless: bool = True) -> None:
        """Launch browser with isolated profile.

        Args:
            headless: Run in headless mode

        Raises:
            BrowserControllerError: If browser launch fails
        """
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            chromium = self._playwright.chromium

            # Create profile directory if needed
            self.profile_dir.mkdir(parents=True, exist_ok=True)

            # Launch with isolated context (no existing cookies/session)
            self.browser = await chromium.launch_persistent_context(
                str(self.profile_dir),
                headless=headless,
                args=["--disable-password-manager"]  # Prevent auto-fill
            )

            self.page = await self.browser.new_page()
            logger.info(f"Browser launched for agent {self.agent_id}")

        except ImportError:
            raise BrowserControllerError(
                "Playwright not installed. Install with: pip install playwright"
            )
        except Exception as e:
            raise BrowserControllerError(f"Failed to launch browser: {e}")

    async def close(self) -> None:
        """Close browser and clean up resources."""
        try:
            if self.page:
                await self.page.close()
                self.page = None

            if self.browser:
                await self.browser.close()
                self.browser = None

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            logger.info(f"Browser closed for agent {self.agent_id}")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

    async def navigate(self, url: str) -> None:
        """Navigate to URL.

        Args:
            url: URL to navigate to

        Raises:
            BrowserControllerError: If navigation fails
        """
        if not self.page:
            raise BrowserControllerError("Browser not launched")

        try:
            await self.page.goto(url, wait_until="domcontentloaded")
            logger.info(f"Navigated to {url}")
        except Exception as e:
            raise BrowserControllerError(f"Navigation failed: {e}")

    async def inspect_page(self) -> InspectResult:
        """Inspect current page (safe).

        Returns:
            InspectResult with url/title/inputs/clickables (no secrets)

        Raises:
            BrowserControllerError: If inspection fails
        """
        if not self.page:
            raise BrowserControllerError("Browser not launched")

        try:
            url = self.page.url
            title = await self.page.title()

            inputs = await self._list_input_fields()
            clickables = await self._list_clickable_elements()

            login_required = self._detect_login_required(url, title, inputs)
            otp_detected = self._detect_otp(inputs)

            return InspectResult(
                url=url,
                title=title,
                inputs=inputs,
                clickables=clickables,
                login_required=login_required,
                otp_detected=otp_detected
            )
        except Exception as e:
            raise BrowserControllerError(f"Inspection failed: {e}")

    async def list_inputs(self) -> List[Dict[str, Any]]:
        """List input fields (safe)."""
        if not self.page:
            raise BrowserControllerError("Browser not launched")
        return await self._list_input_fields()

    async def list_clickables(self) -> List[Dict[str, Any]]:
        """List clickable elements."""
        if not self.page:
            raise BrowserControllerError("Browser not launched")
        return await self._list_clickable_elements()

    async def plan_click(self, selector: str) -> PlanClickResult:
        """Plan click without executing (dry-run).

        Args:
            selector: CSS selector of element to click

        Returns:
            PlanClickResult with element info (not executed)
        """
        if not self.page:
            raise BrowserControllerError("Browser not launched")

        try:
            element = await self.page.query_selector(selector)

            if not element:
                return PlanClickResult(
                    selector=selector,
                    element_found=False,
                    would_click=False
                )

            # Get element info without clicking
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            text = await element.text_content()
            text = (text or "").strip()[:100]  # Truncate for safety

            return PlanClickResult(
                selector=selector,
                element_found=True,
                element_text=text,
                element_tag=tag,
                would_click=True
            )
        except Exception as e:
            logger.error(f"Plan click failed: {e}")
            return PlanClickResult(selector=selector, element_found=False)

    async def plan_type(self, selector: str, text: str) -> PlanTypeResult:
        """Plan type without executing (dry-run).

        Args:
            selector: CSS selector of input field
            text: Text to type (will be redacted in result)

        Returns:
            PlanTypeResult with field info (not executed, text redacted)
        """
        if not self.page:
            raise BrowserControllerError("Browser not launched")

        try:
            element = await self.page.query_selector(selector)

            if not element:
                return PlanTypeResult(
                    selector=selector,
                    element_found=False,
                    would_type=False
                )

            # Get input field info without typing
            field_type = await element.get_attribute("type") or "text"

            return PlanTypeResult(
                selector=selector,
                element_found=True,
                field_type=field_type,
                text_length=len(text),
                text_preview="[REDACTED]",
                would_type=True
            )
        except Exception as e:
            logger.error(f"Plan type failed: {e}")
            return PlanTypeResult(selector=selector, element_found=False)

    async def plan_submit(self, selector: str) -> PlanSubmitResult:
        """Plan submit without executing (critical action).

        Args:
            selector: CSS selector of submit button/form

        Returns:
            PlanSubmitResult (never executed, requires separate approval)
        """
        if not self.page:
            raise BrowserControllerError("Browser not launched")

        return PlanSubmitResult(
            selector=selector,
            risk_level="critical",
            final_approval_required=True
        )

    # Private methods

    async def _list_input_fields(self) -> List[Dict[str, Any]]:
        """List input fields with safe attributes only (no values)."""
        if not self.page:
            return []

        try:
            inputs = await self.page.evaluate(r"""
                () => {
                    const fields = [];
                    document.querySelectorAll('input, textarea, select').forEach((el, idx) => {
                        const field = {
                            selector: `${el.tagName.toLowerCase()}[${
                                el.id ? `id="${el.id}"` :
                                el.name ? `name="${el.name}"` :
                                `data-index="${idx}"`
                            }]`,
                            name: el.name || '',
                            type: el.type || el.tagName.toLowerCase(),
                            placeholder: el.placeholder || '',
                            aria_label: el.getAttribute('aria-label') || '',
                            // NEVER include: value, password content, hidden values
                        };
                        fields.push(field);
                    });
                    return fields;
                }
            """)
            return inputs
        except Exception as e:
            logger.error(f"Failed to list inputs: {e}")
            return []

    async def _list_clickable_elements(self) -> List[Dict[str, Any]]:
        """List clickable elements (buttons, links, etc)."""
        if not self.page:
            return []

        try:
            clickables = await self.page.evaluate(r"""
                () => {
                    const elements = [];
                    document.querySelectorAll('button, a[href], [role="button"]').forEach((el, idx) => {
                        const tag = el.tagName.toLowerCase();
                        let selector = '';

                        if (el.id) {
                            selector = `#${el.id}`;
                        } else if (el.className) {
                            selector = `${tag}.${el.className.split(/\s+/).join('.')}`;
                        } else {
                            selector = `${tag}:nth-of-type(${idx + 1})`;
                        }

                        const elem = {
                            selector: selector,
                            tag: tag,
                            text: (el.textContent || '').trim().substring(0, 100),
                            href: el.getAttribute('href') || '',
                            role: el.getAttribute('role') || ''
                        };
                        elements.push(elem);
                    });
                    return elements;
                }
            """)
            return clickables
        except Exception as e:
            logger.error(f"Failed to list clickables: {e}")
            return []

    def _detect_login_required(self, url: str, title: str, inputs: List[Dict[str, Any]]) -> bool:
        """Detect if login is required based on heuristics."""
        # Check URL and title for login keywords
        login_keywords = ["login", "signin", "sign-in", "로그인", "auth"]
        text = f"{url} {title}".lower()

        if any(kw in text for kw in login_keywords):
            return True

        # Check for password input field
        if any(inp.get("type") == "password" for inp in inputs):
            return True

        return False

    def _detect_otp(self, inputs: List[Dict[str, Any]]) -> bool:
        """Detect if OTP/2FA field is present."""
        otp_keywords = ["otp", "2fa", "인증번호", "보안코드", "verification", "code"]

        for inp in inputs:
            name = (inp.get("name") or "").lower()
            placeholder = (inp.get("placeholder") or "").lower()
            aria_label = (inp.get("aria_label") or "").lower()

            text = f"{name} {placeholder} {aria_label}"
            if any(kw in text for kw in otp_keywords):
                return True

        return False


# Convenience functions for common operations

async def create_and_inspect(agent_id: str, url: str) -> Optional[InspectResult]:
    """Create controller, launch, navigate, and inspect.

    Args:
        agent_id: Agent identifier
        url: URL to inspect

    Returns:
        InspectResult or None if failed
    """
    controller = BrowserController(agent_id)
    try:
        await controller.launch()
        await controller.navigate(url)
        result = await controller.inspect_page()
        return result
    except BrowserControllerError as e:
        logger.error(f"Failed to inspect {url}: {e}")
        return None
    finally:
        await controller.close()
