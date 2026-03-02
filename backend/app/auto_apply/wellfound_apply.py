"""Wellfound (AngelList Talent) auto-apply automation.

Handles Wellfound's application modal with form filling.
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

_APPLY_BTN = 'button:has-text("Apply"), a:has-text("Apply Now"), button[data-test="apply-button"]'
_SUBMIT_BTN = 'button:has-text("Submit"), button:has-text("Send Application"), button[type="submit"]'


def _login_wellfound(page) -> bool:
    """Attempt Wellfound login."""
    email = os.getenv("WELLFOUND_EMAIL")
    password = os.getenv("WELLFOUND_PASSWORD")
    if not email or not password:
        return False
    try:
        page.goto("https://wellfound.com/login", timeout=30000)
        wait_for_page_load(page)

        page.fill('input[name="email"], input[type="email"]', email)
        page.fill('input[name="password"], input[type="password"]', password)

        submit = page.query_selector('button[type="submit"]')
        if submit:
            submit.click()
            time.sleep(3)

        logger.info("Wellfound login attempted")
        return True
    except Exception as e:
        logger.warning("Wellfound login failed: %s", e)
        return False


def apply_wellfound(job_url: str, job: Dict, proxy: str = None) -> Dict:
    """Apply to a Wellfound job listing.

    Wellfound applications typically include a note/cover letter and resume upload
    in a modal dialog.

    Args:
        job_url: URL to the Wellfound job posting.
        job: Job dict.
        proxy: Optional proxy URL.

    Returns:
        Dict: {status: 'submitted'|'failed'|'skipped', error: str|None}
    """
    if not job_url or "wellfound.com" not in job_url:
        return {"status": "skipped", "error": "Not a Wellfound URL"}

    try:
        with PlaywrightRunner(proxy=proxy, headless=True) as runner:
            page = runner.new_page()

            _login_wellfound(page)

            page.goto(job_url, timeout=30000)
            wait_for_page_load(page)

            # Click apply
            apply_btn = page.query_selector(_APPLY_BTN)
            if not apply_btn:
                return {"status": "skipped", "error": "No apply button on Wellfound"}

            apply_btn.click()
            time.sleep(2)

            # Wait for application modal
            try:
                page.wait_for_selector(
                    'div[role="dialog"], div[class*="modal"], form[class*="application"]',
                    timeout=5000,
                )
            except Exception:
                pass

            # Fill form fields (cover letter note, etc.)
            fill_result = fill_form(page, job=job)
            logger.debug("Wellfound: filled %d fields", fill_result["filled"])

            # Upload resume
            upload_resume(page)

            # Fill cover letter / note textarea
            note_textarea = page.query_selector(
                'textarea[name*="note"], textarea[name*="cover"], '
                'textarea[placeholder*="note"], textarea[placeholder*="why"]'
            )
            if note_textarea and note_textarea.is_visible():
                from .profile import get_cover_letter_text
                note = get_cover_letter_text(job)
                note_textarea.fill(note)

            # Submit
            submit = page.query_selector(_SUBMIT_BTN)
            if submit and submit.is_visible() and submit.is_enabled():
                submit.click()
                time.sleep(3)

                success = page.query_selector(
                    'div:has-text("Application submitted"), '
                    'div:has-text("Applied"), '
                    'span:has-text("applied")'
                )
                return {"status": "submitted", "error": None}

            return {"status": "failed", "error": "Could not submit application"}

    except Exception as e:
        logger.error("Wellfound auto-apply error for %s: %s", job_url, e)
        return {"status": "failed", "error": str(e)}
