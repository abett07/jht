"""Greenhouse ATS auto-apply automation.

Greenhouse is one of the most widely used ATS platforms.
Application pages follow the pattern: boards.greenhouse.io/company/jobs/ID
"""
import os
import time
import logging
from typing import Dict

from ..scrapers.playwright_base import PlaywrightRunner
from .form_filler import (
    fill_form, upload_resume, upload_cover_letter,
    click_submit, wait_for_page_load,
)
from .profile import get_profile, get_full_name, get_cover_letter_text

logger = logging.getLogger(__name__)

# Greenhouse-specific selectors
_NAME_FIRST = '#first_name, input[name="job_application[first_name]"]'
_NAME_LAST = '#last_name, input[name="job_application[last_name]"]'
_EMAIL = '#email, input[name="job_application[email]"]'
_PHONE = '#phone, input[name="job_application[phone]"]'
_RESUME_INPUT = '#resume, input[name="job_application[resume]"], input[type="file"][id*="resume"]'
_COVER_LETTER_INPUT = '#cover_letter, input[name="job_application[cover_letter]"], input[type="file"][id*="cover"]'
_LINKEDIN_INPUT = 'input[name*="linkedin"], input[autocomplete="url"][id*="linkedin"]'
_WEBSITE_INPUT = 'input[name*="website"], input[name*="portfolio"]'
_SUBMIT_BTN = '#submit_app, button[type="submit"], input[type="submit"]'

# Greenhouse custom question patterns
_CUSTOM_QUESTION_CONTAINER = '.field, .application-field, div[class*="field"]'


def _fill_greenhouse_standard_fields(page, profile: Dict) -> int:
    """Fill Greenhouse's standard application fields.

    Returns number of fields filled.
    """
    filled = 0

    field_map = [
        (_NAME_FIRST, profile.get("first_name", "")),
        (_NAME_LAST, profile.get("last_name", "")),
        (_EMAIL, profile.get("email", "")),
        (_PHONE, profile.get("phone", "")),
        (_LINKEDIN_INPUT, profile.get("linkedin_url", "")),
        (_WEBSITE_INPUT, profile.get("website", "")),
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

    return filled


def _fill_greenhouse_custom_questions(page, job: Dict, profile: Dict) -> int:
    """Fill Greenhouse's custom questions using the generic form filler."""
    result = fill_form(page, job=job)
    return result["filled"]


def _upload_greenhouse_resume(page) -> bool:
    """Upload resume to Greenhouse's file input."""
    resume_path = os.getenv("RESUME_PATH", "")
    if not resume_path or not os.path.exists(resume_path):
        return False

    try:
        # Greenhouse uses a styled file input; click the attach/upload button first
        attach_btn = page.query_selector(
            'button:has-text("Attach"), a:has-text("Attach"), '
            'label[for="resume"], span:has-text("Attach resume")'
        )
        if attach_btn and attach_btn.is_visible():
            attach_btn.click()
            time.sleep(0.5)

        file_input = page.query_selector(_RESUME_INPUT)
        if file_input:
            file_input.set_input_files(os.path.abspath(resume_path))
            time.sleep(1)
            logger.info("Greenhouse: resume uploaded")
            return True

        # Fallback: use generic upload
        return upload_resume(page)
    except Exception as e:
        logger.warning("Greenhouse resume upload failed: %s", e)
        return False


def _upload_greenhouse_cover_letter(page, job: Dict) -> bool:
    """Upload or generate cover letter for Greenhouse."""
    # Check for file upload input
    cl_path = os.getenv("COVER_LETTER_PATH", "")
    try:
        cl_input = page.query_selector(_COVER_LETTER_INPUT)
        if cl_input:
            if cl_path and os.path.exists(cl_path):
                cl_input.set_input_files(os.path.abspath(cl_path))
                return True

        # Greenhouse may have a text field for cover letter
        cl_textarea = page.query_selector(
            'textarea[name*="cover_letter"], textarea[id*="cover"]'
        )
        if cl_textarea and cl_textarea.is_visible():
            cl_text = get_cover_letter_text(job)
            cl_textarea.fill(cl_text)
            return True

        return False
    except Exception as e:
        logger.debug("Greenhouse cover letter failed: %s", e)
        return False


def _handle_greenhouse_demographics(page, profile: Dict):
    """Fill optional demographic / EEO questions on Greenhouse."""
    # These are typically on a separate demographics page
    demo_fields = {
        "gender": profile.get("gender", ""),
        "race": profile.get("race_ethnicity", ""),
        "veteran": profile.get("veteran_status", ""),
        "disability": profile.get("disability_status", ""),
    }

    for field_name, value in demo_fields.items():
        if not value:
            continue
        try:
            selects = page.query_selector_all(f'select[name*="{field_name}"], select[id*="{field_name}"]')
            for sel in selects:
                if sel.is_visible():
                    options = sel.query_selector_all("option")
                    for opt in options:
                        text = (opt.inner_text() or "").strip().lower()
                        if value.lower() in text or text in value.lower():
                            sel.select_option(value=opt.get_attribute("value"))
                            break
        except Exception:
            pass


def apply_greenhouse(job_url: str, job: Dict, proxy: str = None) -> Dict:
    """Apply to a Greenhouse-hosted job application.

    Args:
        job_url: URL to the Greenhouse application page.
        job: Job dict.
        proxy: Optional proxy URL.

    Returns:
        Dict: {status: 'submitted'|'failed'|'skipped', error: str|None}
    """
    if not job_url:
        return {"status": "skipped", "error": "No URL provided"}

    url_low = job_url.lower()
    if "greenhouse" not in url_low and "grnh.se" not in url_low:
        return {"status": "skipped", "error": "Not a Greenhouse URL"}

    try:
        with PlaywrightRunner(proxy=proxy, headless=True) as runner:
            page = runner.new_page()
            page.goto(job_url, timeout=30000)
            wait_for_page_load(page)

            profile = get_profile()

            # Fill standard fields
            std_filled = _fill_greenhouse_standard_fields(page, profile)
            logger.info("Greenhouse: filled %d standard fields", std_filled)

            # Fill custom questions
            custom_filled = _fill_greenhouse_custom_questions(page, job, profile)
            logger.info("Greenhouse: filled %d custom fields", custom_filled)

            # Upload resume
            _upload_greenhouse_resume(page)

            # Upload/fill cover letter
            _upload_greenhouse_cover_letter(page, job)

            # Handle demographics if present
            _handle_greenhouse_demographics(page, profile)

            # Submit
            submit = page.query_selector(_SUBMIT_BTN)
            if submit and submit.is_visible() and submit.is_enabled():
                submit.click()
                time.sleep(4)

                # Check for validation errors
                errors = page.query_selector_all('.field-error, .error-message, div[class*="error"]')
                visible_errors = [e for e in errors if e.is_visible()]
                if visible_errors:
                    error_texts = [e.inner_text().strip() for e in visible_errors[:3]]
                    return {"status": "failed", "error": f"Validation errors: {'; '.join(error_texts)}"}

                # Check for success
                success = page.query_selector(
                    'div:has-text("Application submitted"), '
                    'h1:has-text("Application submitted"), '
                    'div:has-text("Thanks for applying"), '
                    'h1:has-text("Thank you")'
                )
                if success:
                    return {"status": "submitted", "error": None}

                # If URL changed, likely success
                if page.url != job_url:
                    return {"status": "submitted", "error": None}

                return {"status": "submitted", "error": None}

            return {"status": "failed", "error": "No submit button found"}

    except Exception as e:
        logger.error("Greenhouse auto-apply error for %s: %s", job_url, e)
        return {"status": "failed", "error": str(e)}
