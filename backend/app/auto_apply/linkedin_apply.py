"""LinkedIn Easy Apply automation.

Handles LinkedIn's multi-step Easy Apply modal flow.
Requires LinkedIn session cookies or credentials.
"""
import os
import time
import logging
from typing import Dict, Optional

from ..scrapers.playwright_base import PlaywrightRunner
from .form_filler import (
    fill_form, upload_resume,
    wait_for_page_load,
)
from .profile import get_profile, get_full_name

logger = logging.getLogger(__name__)

# LinkedIn Easy Apply selectors
_EASY_APPLY_BTN = 'button.jobs-apply-button, button[aria-label*="Easy Apply"], button:has-text("Easy Apply")'
_MODAL = 'div.jobs-easy-apply-modal, div[data-test-modal], div.artdeco-modal'
_NEXT_BTN = 'button[aria-label="Continue to next step"], button:has-text("Next"), button:has-text("Review")'
_REVIEW_BTN = 'button:has-text("Review"), button[aria-label="Review your application"]'
_SUBMIT_BTN = 'button:has-text("Submit application"), button[aria-label="Submit application"]'
_DISMISS_BTN = 'button[aria-label="Dismiss"], button:has-text("Dismiss")'


def _load_linkedin_cookies(page) -> bool:
    """Load LinkedIn session cookies from env or file."""
    cookie_path = os.getenv("LINKEDIN_COOKIES_PATH")
    if not cookie_path or not os.path.exists(cookie_path):
        return False
    try:
        import json
        with open(cookie_path, "r") as f:
            cookies = json.load(f)
        page.context.add_cookies(cookies)
        return True
    except Exception as e:
        logger.warning("Failed to load LinkedIn cookies: %s", e)
        return False


def _login_linkedin(page) -> bool:
    """Attempt LinkedIn login using credentials from env."""
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    if not email or not password:
        logger.warning("LINKEDIN_EMAIL / LINKEDIN_PASSWORD not set — cannot log in")
        return False

    try:
        page.goto("https://www.linkedin.com/login", timeout=30000)
        wait_for_page_load(page)

        page.fill('#username', email)
        page.fill('#password', password)
        page.click('button[type="submit"]')

        # Wait for redirect to feed
        page.wait_for_url("**/feed/**", timeout=30000)
        logger.info("LinkedIn login successful")
        return True
    except Exception as e:
        logger.warning("LinkedIn login failed: %s", e)
        return False


def _is_easy_apply_available(page) -> bool:
    """Check if the current job page has an Easy Apply button."""
    try:
        btn = page.query_selector(_EASY_APPLY_BTN)
        return btn is not None and btn.is_visible()
    except Exception:
        return False


def _fill_easy_apply_step(page, job: Dict) -> bool:
    """Fill all fields in the current Easy Apply step."""
    time.sleep(1)

    # Fill standard form fields
    fill_result = fill_form(page, job=job)
    logger.debug("Easy Apply step filled: %d fields", fill_result["filled"])

    # Upload resume if file input present
    upload_resume(page)

    return True


def _process_multi_step(page, job: Dict, max_steps: int = 10) -> str:
    """Process LinkedIn's multi-step Easy Apply modal.

    Returns: 'submitted' | 'failed' | 'review_needed'
    """
    for step in range(max_steps):
        _fill_easy_apply_step(page, job)
        time.sleep(0.5)

        # Check if we're at the submit step
        submit_btn = page.query_selector(_SUBMIT_BTN)
        if submit_btn and submit_btn.is_visible():
            try:
                # Check for unsubmitted checkbox (e.g., "Follow company")
                follow_cb = page.query_selector('input[type="checkbox"][id*="follow"]')
                if follow_cb and follow_cb.is_checked():
                    follow_cb.uncheck()  # Don't auto-follow

                submit_btn.click()
                time.sleep(3)

                # Check for success
                success = page.query_selector('div:has-text("Application submitted"), span:has-text("Application sent")')
                if success:
                    # Dismiss the success modal
                    dismiss = page.query_selector(_DISMISS_BTN)
                    if dismiss:
                        dismiss.click()
                    return "submitted"
                return "submitted"
            except Exception as e:
                logger.warning("Submit click failed: %s", e)
                return "failed"

        # Check for Review button
        review_btn = page.query_selector(_REVIEW_BTN)
        if review_btn and review_btn.is_visible():
            review_btn.click()
            time.sleep(1)
            continue

        # Click next
        next_btn = page.query_selector(_NEXT_BTN)
        if next_btn and next_btn.is_visible():
            next_btn.click()
            time.sleep(1.5)
            continue

        # No next or submit found — check if there's an error
        error_el = page.query_selector('.artdeco-inline-feedback--error, div[role="alert"]')
        if error_el and error_el.is_visible():
            error_text = error_el.inner_text().strip()
            logger.warning("Easy Apply validation error: %s", error_text)
            return "failed"

        # Nothing to click — stuck
        logger.warning("Easy Apply step %d: no next/submit button found", step)
        break

    return "failed"


def apply_linkedin(job_url: str, job: Dict, proxy: str = None) -> Dict:
    """Apply to a LinkedIn job via Easy Apply.

    Args:
        job_url: Direct URL to the LinkedIn job posting.
        job: Job dict with title, company, description, etc.
        proxy: Optional proxy URL.

    Returns:
        Dict: {status: 'submitted'|'failed'|'skipped', error: str|None}
    """
    if not job_url or "linkedin.com" not in job_url:
        return {"status": "skipped", "error": "Not a LinkedIn URL"}

    try:
        with PlaywrightRunner(proxy=proxy, headless=True) as runner:
            page = runner.new_page()

            # Authenticate
            if not _load_linkedin_cookies(page):
                if not _login_linkedin(page):
                    return {"status": "failed", "error": "LinkedIn authentication failed"}

            # Navigate to job
            page.goto(job_url, timeout=30000)
            wait_for_page_load(page)

            # Check Easy Apply availability
            if not _is_easy_apply_available(page):
                return {"status": "skipped", "error": "No Easy Apply — external application required"}

            # Click Easy Apply
            easy_btn = page.query_selector(_EASY_APPLY_BTN)
            if not easy_btn or not easy_btn.is_visible():
                return {"status": "skipped", "error": "Easy Apply button disappeared before click"}
            easy_btn.click()
            time.sleep(2)

            # Wait for modal
            try:
                page.wait_for_selector(_MODAL, timeout=5000)
            except Exception:
                return {"status": "failed", "error": "Easy Apply modal did not open"}

            # Process multi-step form
            result = _process_multi_step(page, job)
            return {"status": result, "error": None if result == "submitted" else "Multi-step failed"}

    except Exception as e:
        logger.error("LinkedIn auto-apply error for %s: %s", job_url, e)
        return {"status": "failed", "error": str(e)}
