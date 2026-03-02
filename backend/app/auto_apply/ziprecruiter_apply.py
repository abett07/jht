"""ZipRecruiter auto-apply automation.

Handles ZipRecruiter's "1-Click Apply" and standard application flow.
"""
import os
import time
import logging
from typing import Dict

from ..scrapers.playwright_base import PlaywrightRunner
from .form_filler import (
    fill_form, upload_resume, click_submit,
    wait_for_page_load,
)
from .profile import get_profile

logger = logging.getLogger(__name__)

# ZipRecruiter selectors
_APPLY_BTN = 'button:has-text("Apply"), a:has-text("1-Click Apply"), a.apply_btn, button.apply_button'
_ONE_CLICK = 'a:has-text("1-Click Apply"), button:has-text("1-Click Apply")'
_SUBMIT_BTN = 'button:has-text("Submit"), button:has-text("Apply"), button[type="submit"]'


def _login_ziprecruiter(page) -> bool:
    """Attempt ZipRecruiter login."""
    email = os.getenv("ZIPRECRUITER_EMAIL")
    password = os.getenv("ZIPRECRUITER_PASSWORD")
    if not email or not password:
        return False
    try:
        page.goto("https://www.ziprecruiter.com/login", timeout=30000)
        wait_for_page_load(page)

        page.fill('input[name="email"], input[type="email"]', email)
        page.fill('input[name="password"], input[type="password"]', password)

        submit = page.query_selector('button[type="submit"]')
        if submit:
            submit.click()
            time.sleep(3)

        logger.info("ZipRecruiter login attempted")
        return True
    except Exception as e:
        logger.warning("ZipRecruiter login failed: %s", e)
        return False


def _try_one_click(page) -> bool:
    """Try ZipRecruiter's 1-Click Apply (pre-filled profile)."""
    try:
        btn = page.query_selector(_ONE_CLICK)
        if btn and btn.is_visible():
            btn.click()
            time.sleep(3)

            # Check for confirmation
            success = page.query_selector(
                'div:has-text("Application submitted"), '
                'div:has-text("Applied"), '
                'h2:has-text("Application Sent")'
            )
            if success:
                return True
        return False
    except Exception:
        return False


def _process_ziprecruiter_form(page, job: Dict) -> str:
    """Process ZipRecruiter standard application form.

    Returns: 'submitted' | 'failed'
    """
    max_steps = 5
    for step in range(max_steps):
        time.sleep(1)

        # Fill profile fields
        profile = get_profile()

        # ZipRecruiter often has simple name + email + resume form
        fill_result = fill_form(page, job=job)
        logger.debug("ZipRecruiter step %d: filled %d fields", step, fill_result["filled"])

        # Upload resume
        upload_resume(page)

        # Submit
        submit = page.query_selector(_SUBMIT_BTN)
        if submit and submit.is_visible() and submit.is_enabled():
            submit.click()
            time.sleep(3)

            success = page.query_selector(
                'div:has-text("Application submitted"), '
                'div:has-text("Application Sent"), '
                'h2:has-text("Applied")'
            )
            return "submitted"

        break

    return "failed"


def apply_ziprecruiter(job_url: str, job: Dict, proxy: str = None) -> Dict:
    """Apply to a ZipRecruiter job listing.

    Args:
        job_url: URL to the ZipRecruiter job.
        job: Job dict.
        proxy: Optional proxy URL.

    Returns:
        Dict: {status: 'submitted'|'failed'|'skipped', error: str|None}
    """
    if not job_url or "ziprecruiter.com" not in job_url:
        return {"status": "skipped", "error": "Not a ZipRecruiter URL"}

    try:
        with PlaywrightRunner(proxy=proxy, headless=True) as runner:
            page = runner.new_page()

            _login_ziprecruiter(page)

            page.goto(job_url, timeout=30000)
            wait_for_page_load(page)

            # Try 1-Click first
            if _try_one_click(page):
                return {"status": "submitted", "error": None}

            # Standard apply
            apply_btn = page.query_selector(_APPLY_BTN)
            if not apply_btn:
                return {"status": "skipped", "error": "No apply button found"}

            apply_btn.click()
            time.sleep(2)
            wait_for_page_load(page)

            result = _process_ziprecruiter_form(page, job)
            return {"status": result, "error": None if result == "submitted" else "Application failed"}

    except Exception as e:
        logger.error("ZipRecruiter auto-apply error for %s: %s", job_url, e)
        return {"status": "failed", "error": str(e)}
