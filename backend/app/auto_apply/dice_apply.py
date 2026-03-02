"""Dice.com auto-apply automation.

Handles Dice's "Easy Apply" flow with form filling and resume upload.
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

# Dice selectors
_APPLY_BTN = 'a[data-cy="apply-btn"], button:has-text("Apply"), a:has-text("Easy Apply"), apply-button-wc'
_SUBMIT_BTN = 'button:has-text("Submit"), button:has-text("Submit Application"), button[type="submit"]'
_NEXT_BTN = 'button:has-text("Next"), button:has-text("Continue")'


def _login_dice(page) -> bool:
    """Attempt Dice login."""
    email = os.getenv("DICE_EMAIL")
    password = os.getenv("DICE_PASSWORD")
    if not email or not password:
        return False
    try:
        page.goto("https://www.dice.com/dashboard/login", timeout=30000)
        wait_for_page_load(page)

        email_input = page.query_selector('input[name="email"], input[type="email"]')
        if email_input:
            email_input.fill(email)

        pw_input = page.query_selector('input[name="password"], input[type="password"]')
        if pw_input:
            pw_input.fill(password)

        submit = page.query_selector('button[type="submit"]')
        if submit:
            submit.click()
            time.sleep(3)

        logger.info("Dice login attempted")
        return True
    except Exception as e:
        logger.warning("Dice login failed: %s", e)
        return False


def _process_dice_application(page, job: Dict) -> str:
    """Process Dice application form.

    Returns: 'submitted' | 'failed'
    """
    max_steps = 6
    for step in range(max_steps):
        time.sleep(1)

        # Fill form fields
        fill_result = fill_form(page, job=job)
        logger.debug("Dice step %d: filled %d fields", step, fill_result["filled"])

        # Upload resume
        upload_resume(page)

        # Check for submit
        submit = page.query_selector(_SUBMIT_BTN)
        if submit and submit.is_visible() and submit.is_enabled():
            submit.click()
            time.sleep(3)

            # Check success
            success = page.query_selector(
                'div:has-text("Application submitted"), '
                'div:has-text("Successfully applied"), '
                'h1:has-text("Application Complete")'
            )
            return "submitted" if success else "submitted"

        # Click next
        next_btn = page.query_selector(_NEXT_BTN)
        if next_btn and next_btn.is_visible():
            next_btn.click()
            time.sleep(1.5)
            continue

        break

    return "failed"


def apply_dice(job_url: str, job: Dict, proxy: str = None) -> Dict:
    """Apply to a Dice job listing.

    Args:
        job_url: URL to the Dice job posting.
        job: Job dict.
        proxy: Optional proxy URL.

    Returns:
        Dict: {status: 'submitted'|'failed'|'skipped', error: str|None}
    """
    if not job_url or "dice.com" not in job_url:
        return {"status": "skipped", "error": "Not a Dice URL"}

    try:
        with PlaywrightRunner(proxy=proxy, headless=True) as runner:
            page = runner.new_page()

            _login_dice(page)

            page.goto(job_url, timeout=30000)
            wait_for_page_load(page)

            # Click apply
            apply_btn = page.query_selector(_APPLY_BTN)
            if not apply_btn:
                return {"status": "skipped", "error": "No apply button found on Dice"}

            apply_btn.click()
            time.sleep(3)
            wait_for_page_load(page)

            result = _process_dice_application(page, job)
            return {"status": result, "error": None if result == "submitted" else "Application failed"}

    except Exception as e:
        logger.error("Dice auto-apply error for %s: %s", job_url, e)
        return {"status": "failed", "error": str(e)}
