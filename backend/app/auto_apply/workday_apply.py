"""Workday ATS auto-apply automation.

Workday is widely used by large enterprises. Application pages follow patterns like:
  company.wd5.myworkdayjobs.com/en-US/External/job/Location/Title_ID/apply
"""
import os
import time
import logging
from typing import Dict

from ..scrapers.playwright_base import PlaywrightRunner
from .form_filler import (
    fill_form, upload_resume, click_next, click_submit,
    wait_for_page_load,
)
from .profile import get_profile, get_full_name

logger = logging.getLogger(__name__)

# Workday-specific selectors
_CREATE_ACCOUNT_BTN = 'button:has-text("Create Account"), a:has-text("Create Account")'
_SIGN_IN_BTN = 'button:has-text("Sign In"), a:has-text("Sign In")'
_APPLY_BTN = 'a:has-text("Apply"), button:has-text("Apply")'
_AUTOFILL_RESUME_BTN = 'button:has-text("Autofill with Resume"), button[data-automation-id="autofillWithResume"]'
_RESUME_INPUT = 'input[type="file"][data-automation-id*="resume"], input[type="file"]'
_NEXT_BTN = 'button[data-automation-id="bottom-navigation-next-button"], button:has-text("Next"), button:has-text("Save and Continue")'
_SUBMIT_BTN = 'button[data-automation-id="bottom-navigation-next-button"]:has-text("Submit"), button:has-text("Submit")'
_ERROR_MSG = 'div[data-automation-id="errorMessage"], div[role="alert"]'

# Workday specific field selectors
_WD_EMAIL = 'input[data-automation-id="email"], input[aria-label*="Email"]'
_WD_PHONE = 'input[data-automation-id="phone-number"], input[aria-label*="Phone"]'
_WD_FIRST_NAME = 'input[data-automation-id="legalNameSection_firstName"], input[aria-label*="First Name"]'
_WD_LAST_NAME = 'input[data-automation-id="legalNameSection_lastName"], input[aria-label*="Last Name"]'
_WD_COUNTRY = 'select[data-automation-id="countryDropdown"], button[data-automation-id="countryDropdown"]'
_WD_ADDRESS = 'input[data-automation-id="addressSection_addressLine1"]'
_WD_CITY = 'input[data-automation-id="addressSection_city"]'
_WD_STATE = 'input[data-automation-id="addressSection_region"], select[data-automation-id="addressSection_region"]'
_WD_ZIP = 'input[data-automation-id="addressSection_postalCode"]'


def _create_workday_account(page, profile: Dict) -> bool:
    """Create a Workday account or sign in."""
    try:
        # Check if create account option exists
        create_btn = page.query_selector(_CREATE_ACCOUNT_BTN)
        if create_btn and create_btn.is_visible():
            create_btn.click()
            time.sleep(2)

            # Fill email and password
            email_input = page.query_selector(
                'input[data-automation-id="createAccountEmail"], input[type="email"]'
            )
            if email_input:
                email_input.fill(profile.get("email", ""))

            pw_input = page.query_selector(
                'input[data-automation-id="createAccountPassword"], input[type="password"]'
            )
            if pw_input:
                pw = os.getenv("WORKDAY_PASSWORD", "")
                if pw:
                    pw_input.fill(pw)

            verify_input = page.query_selector(
                'input[data-automation-id="createAccountVerifyPassword"]'
            )
            if verify_input and os.getenv("WORKDAY_PASSWORD"):
                verify_input.fill(os.getenv("WORKDAY_PASSWORD", ""))

            submit = page.query_selector('button[data-automation-id="createAccountSubmitButton"], button[type="submit"]')
            if submit:
                submit.click()
                time.sleep(3)

            return True

        # Try sign-in
        sign_in = page.query_selector(_SIGN_IN_BTN)
        if sign_in and sign_in.is_visible():
            sign_in.click()
            time.sleep(2)

            email_input = page.query_selector('input[type="email"], input[data-automation-id="email"]')
            if email_input:
                email_input.fill(profile.get("email", ""))

            pw_input = page.query_selector('input[type="password"]')
            if pw_input:
                pw_input.fill(os.getenv("WORKDAY_PASSWORD", ""))

            submit = page.query_selector('button[type="submit"]')
            if submit:
                submit.click()
                time.sleep(3)

            return True

        return True  # Already signed in or no auth required
    except Exception as e:
        logger.warning("Workday account setup failed: %s", e)
        return False


def _fill_workday_my_info(page, profile: Dict) -> int:
    """Fill Workday's 'My Information' step."""
    filled = 0

    field_map = [
        (_WD_FIRST_NAME, profile.get("first_name", "")),
        (_WD_LAST_NAME, profile.get("last_name", "")),
        (_WD_EMAIL, profile.get("email", "")),
        (_WD_PHONE, profile.get("phone", "")),
        (_WD_ADDRESS, profile.get("address", {}).get("street", "")),
        (_WD_CITY, profile.get("address", {}).get("city", "")),
        (_WD_ZIP, profile.get("address", {}).get("zip", "")),
    ]

    for selector, value in field_map:
        if not value:
            continue
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                el.fill(value)
                filled += 1
                time.sleep(0.1)
        except Exception:
            pass

    # Handle state dropdown (might be a select or custom dropdown)
    state = profile.get("address", {}).get("state", "")
    if state:
        try:
            state_el = page.query_selector(_WD_STATE)
            if state_el and state_el.is_visible():
                tag = state_el.evaluate("el => el.tagName")
                if tag == "SELECT":
                    state_el.select_option(label=state)
                else:
                    state_el.fill(state)
                filled += 1
        except Exception:
            pass

    return filled


def _upload_workday_resume(page) -> bool:
    """Upload resume to Workday, optionally using autofill."""
    resume_path = os.getenv("RESUME_PATH", "")
    if not resume_path or not os.path.exists(resume_path):
        return False

    try:
        # Try "Autofill with Resume" button first (parses resume and fills fields)
        autofill = page.query_selector(_AUTOFILL_RESUME_BTN)
        if autofill and autofill.is_visible():
            # This will open a file dialog
            pass

        # Direct file input
        file_input = page.query_selector(_RESUME_INPUT)
        if file_input:
            file_input.set_input_files(os.path.abspath(resume_path))
            time.sleep(2)
            logger.info("Workday: resume uploaded")
            return True

        return upload_resume(page)
    except Exception as e:
        logger.warning("Workday resume upload failed: %s", e)
        return False


def _process_workday_steps(page, job: Dict, profile: Dict, max_steps: int = 8) -> str:
    """Process Workday's multi-step application.

    Workday typically has steps: My Info → My Experience → Application Questions → Review → Submit

    Returns: 'submitted' | 'failed'
    """
    for step in range(max_steps):
        time.sleep(1.5)

        # Upload resume if on the right step
        _upload_workday_resume(page)

        # Fill standard fields
        _fill_workday_my_info(page, profile)

        # Fill generic form fields (custom questions)
        fill_result = fill_form(page, job=job)
        logger.debug("Workday step %d: filled %d fields", step, fill_result["filled"])

        # Check for errors
        error = page.query_selector(_ERROR_MSG)
        if error and error.is_visible():
            error_text = error.inner_text().strip()
            if error_text:
                logger.warning("Workday validation error: %s", error_text)

        # Check if Submit button is available
        submit = page.query_selector(_SUBMIT_BTN)
        if submit and submit.is_visible() and submit.is_enabled():
            submit_text = submit.inner_text().strip().lower()
            if "submit" in submit_text:
                submit.click()
                time.sleep(4)

                success = page.query_selector(
                    'div:has-text("Application submitted"), '
                    'h1:has-text("Application Submitted"), '
                    'div:has-text("Thank you for your application"), '
                    'div:has-text("Thank You")'
                )
                return "submitted"

        # Click Next / Save & Continue
        next_btn = page.query_selector(_NEXT_BTN)
        if next_btn and next_btn.is_visible() and next_btn.is_enabled():
            next_btn.click()
            time.sleep(2)
            wait_for_page_load(page)
            continue

        if click_next(page):
            continue

        break

    return "failed"


def apply_workday(job_url: str, job: Dict, proxy: str = None) -> Dict:
    """Apply to a Workday-hosted job application.

    Args:
        job_url: URL to the Workday job page.
        job: Job dict.
        proxy: Optional proxy URL.

    Returns:
        Dict: {status: 'submitted'|'failed'|'skipped', error: str|None}
    """
    if not job_url:
        return {"status": "skipped", "error": "No URL provided"}

    url_low = job_url.lower()
    if "workday" not in url_low and "myworkdayjobs" not in url_low:
        return {"status": "skipped", "error": "Not a Workday URL"}

    # Ensure we're on the /apply page
    if "/apply" not in url_low:
        job_url = job_url.rstrip("/") + "/apply"

    try:
        with PlaywrightRunner(proxy=proxy, headless=True) as runner:
            page = runner.new_page()
            page.goto(job_url, timeout=45000)
            wait_for_page_load(page)

            profile = get_profile()

            # Handle account creation / sign-in
            _create_workday_account(page, profile)

            # Process multi-step form
            result = _process_workday_steps(page, job, profile)
            return {"status": result, "error": None if result == "submitted" else "Multi-step failed"}

    except Exception as e:
        logger.error("Workday auto-apply error for %s: %s", job_url, e)
        return {"status": "failed", "error": str(e)}
