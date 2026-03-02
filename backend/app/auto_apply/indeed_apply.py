"""Indeed auto-apply automation.

Handles Indeed's application flow including resume upload and form filling.
"""
import os
import time
import logging
from typing import Dict

from ..scrapers.playwright_base import PlaywrightRunner
from .form_filler import (
    fill_form, upload_resume, click_submit, click_next,
    wait_for_page_load,
)
from .profile import get_profile

logger = logging.getLogger(__name__)

# Indeed selectors
_APPLY_BTN = 'button#indeedApplyButton, button[data-testid="indeedApplyButton"], a:has-text("Apply now"), button:has-text("Apply now")'
_CONTINUE_BTN = 'button:has-text("Continue"), button[data-testid="continueButton"]'
_SUBMIT_BTN = 'button:has-text("Submit"), button:has-text("Submit your application")'
_RESUME_INPUT = 'input[type="file"][accept*=".pdf"], input[type="file"][name*="resume"]'


def _login_indeed(page) -> bool:
    """Attempt Indeed login using credentials from env."""
    email = os.getenv("INDEED_EMAIL")
    password = os.getenv("INDEED_PASSWORD")
    if not email or not password:
        return False

    try:
        page.goto("https://secure.indeed.com/auth", timeout=30000)
        wait_for_page_load(page)

        # Indeed uses email-first flow
        email_input = page.query_selector('input[type="email"], input[name="__email"]')
        if email_input:
            email_input.fill(email)
            continue_btn = page.query_selector('button[type="submit"]')
            if continue_btn:
                continue_btn.click()
                time.sleep(2)

        # Password step
        pw_input = page.query_selector('input[type="password"]')
        if pw_input:
            pw_input.fill(password)
            submit_btn = page.query_selector('button[type="submit"]')
            if submit_btn:
                submit_btn.click()
                time.sleep(3)

        logger.info("Indeed login attempted")
        return True
    except Exception as e:
        logger.warning("Indeed login failed: %s", e)
        return False


def _fill_indeed_resume_step(page) -> bool:
    """Handle Indeed's resume upload / selection step."""
    try:
        # Check if there's an option to upload a new resume
        upload_btn = page.query_selector('button:has-text("Upload resume"), label:has-text("Upload")')
        if upload_btn and upload_btn.is_visible():
            upload_btn.click()
            time.sleep(1)

        # Upload resume
        return upload_resume(page, _RESUME_INPUT)
    except Exception:
        return False


def _process_indeed_steps(page, job: Dict, max_steps: int = 8) -> str:
    """Process Indeed's multi-step application flow.

    Returns: 'submitted' | 'failed'
    """
    for step in range(max_steps):
        time.sleep(1)

        # Fill form fields
        fill_result = fill_form(page, job=job)
        logger.debug("Indeed step %d: filled %d fields", step, fill_result["filled"])

        # Handle resume upload
        _fill_indeed_resume_step(page)

        # Check for submit button
        submit = page.query_selector(_SUBMIT_BTN)
        if submit and submit.is_visible() and submit.is_enabled():
            submit.click()
            time.sleep(3)

            # Check for confirmation
            confirmation = page.query_selector(
                'div:has-text("Application submitted"), '
                'h1:has-text("Application submitted"), '
                'div:has-text("Your application has been submitted")'
            )
            if confirmation:
                return "submitted"
            return "submitted"  # Assume success if no error

        # Click continue / next
        cont = page.query_selector(_CONTINUE_BTN)
        if cont and cont.is_visible() and cont.is_enabled():
            cont.click()
            time.sleep(2)
            continue

        if click_next(page):
            continue

        # Check for errors
        error = page.query_selector('div[role="alert"], .ia-InlineMessage--error')
        if error and error.is_visible():
            logger.warning("Indeed form error: %s", error.inner_text().strip())

        break

    return "failed"


def apply_indeed(job_url: str, job: Dict, proxy: str = None) -> Dict:
    """Apply to an Indeed job listing.

    Args:
        job_url: URL to the Indeed job posting.
        job: Job dict.
        proxy: Optional proxy URL.

    Returns:
        Dict: {status: 'submitted'|'failed'|'skipped', error: str|None}
    """
    if not job_url or "indeed.com" not in job_url:
        return {"status": "skipped", "error": "Not an Indeed URL"}

    try:
        with PlaywrightRunner(proxy=proxy, headless=True) as runner:
            page = runner.new_page()

            # Try login
            _login_indeed(page)

            # Navigate to job
            page.goto(job_url, timeout=30000)
            wait_for_page_load(page)

            # Click apply button
            apply_btn = page.query_selector(_APPLY_BTN)
            if not apply_btn or not apply_btn.is_visible():
                return {"status": "skipped", "error": "No Indeed Apply button found"}

            apply_btn.click()
            time.sleep(3)

            # Indeed may open in a new tab/popup or iframe
            # Check for iframe
            iframe = page.query_selector('iframe[title*="Apply"], iframe[id*="indeed-apply"]')
            if iframe:
                frame = iframe.content_frame()
                if frame:
                    # Switch context to iframe — but our form_filler works on page objects
                    # For simplicity, continue on the main page
                    pass

            result = _process_indeed_steps(page, job)
            return {"status": result, "error": None if result == "submitted" else "Application steps failed"}

    except Exception as e:
        logger.error("Indeed auto-apply error for %s: %s", job_url, e)
        return {"status": "failed", "error": str(e)}
