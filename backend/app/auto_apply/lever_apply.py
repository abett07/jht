"""Lever ATS auto-apply automation.

Lever application pages follow the pattern: jobs.lever.co/company/job-id/apply
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

# Lever-specific selectors
_NAME_INPUT = 'input[name="name"], input[placeholder*="Full name"]'
_EMAIL_INPUT = 'input[name="email"], input[type="email"]'
_PHONE_INPUT = 'input[name="phone"], input[type="tel"]'
_RESUME_INPUT = 'input[type="file"][name="resume"], input[name="resumeFile"]'
_LINKEDIN_INPUT = 'input[name="urls[LinkedIn]"], input[name*="linkedin"], input[placeholder*="LinkedIn"]'
_GITHUB_INPUT = 'input[name="urls[GitHub]"], input[name*="github"], input[placeholder*="GitHub"]'
_WEBSITE_INPUT = 'input[name="urls[Portfolio]"], input[name*="website"], input[name*="portfolio"], input[placeholder*="Website"]'
_COVER_LETTER_TEXTAREA = 'textarea[name="comments"], textarea[placeholder*="cover letter"], textarea[name="coverLetter"]'
_ADDITIONAL_INFO = 'textarea[name="comments"], textarea[placeholder*="Additional"]'
_SUBMIT_BTN = 'button:has-text("Submit application"), button:has-text("Submit"), button[type="submit"]'

# Lever uses a single-page form (not multi-step)


def _fill_lever_standard_fields(page, profile: Dict) -> int:
    """Fill Lever's standard application fields.

    Returns number of fields filled.
    """
    filled = 0
    name = get_full_name()

    field_map = [
        (_NAME_INPUT, name),
        (_EMAIL_INPUT, profile.get("email", "")),
        (_PHONE_INPUT, profile.get("phone", "")),
        (_LINKEDIN_INPUT, profile.get("linkedin_url", "")),
        (_GITHUB_INPUT, profile.get("github_url", "")),
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


def _fill_lever_additional_questions(page, job: Dict, profile: Dict) -> int:
    """Fill Lever's additional / custom questions."""
    # Lever custom questions appear as div.application-additional
    result = fill_form(page, job=job)
    return result["filled"]


def _upload_lever_resume(page) -> bool:
    """Upload resume to Lever."""
    resume_path = os.getenv("RESUME_PATH", "")
    if not resume_path or not os.path.exists(resume_path):
        return False

    try:
        # Lever has a button "Upload resume" that reveals the file input
        upload_btn = page.query_selector(
            'button:has-text("Upload resume"), label:has-text("Upload resume"), '
            'a:has-text("Upload resume"), div.resume-upload-btn'
        )
        if upload_btn and upload_btn.is_visible():
            upload_btn.click()
            time.sleep(0.5)

        file_input = page.query_selector(_RESUME_INPUT)
        if not file_input:
            file_input = page.query_selector('input[type="file"]')

        if file_input:
            file_input.set_input_files(os.path.abspath(resume_path))
            time.sleep(1)
            logger.info("Lever: resume uploaded")
            return True

        return upload_resume(page)
    except Exception as e:
        logger.warning("Lever resume upload failed: %s", e)
        return False


def _fill_lever_cover_letter(page, job: Dict) -> bool:
    """Fill Lever's cover letter / additional info textarea."""
    try:
        textarea = page.query_selector(_COVER_LETTER_TEXTAREA)
        if not textarea:
            textarea = page.query_selector(_ADDITIONAL_INFO)

        if textarea and textarea.is_visible():
            cl = get_cover_letter_text(job)
            textarea.fill(cl)
            return True
        return False
    except Exception:
        return False


def _handle_lever_eeo(page, profile: Dict):
    """Fill optional EEO survey on Lever."""
    eeo_fields = {
        "gender": profile.get("gender", ""),
        "race": profile.get("race_ethnicity", ""),
        "veteran": profile.get("veteran_status", ""),
    }

    for field_name, value in eeo_fields.items():
        if not value:
            continue
        try:
            selects = page.query_selector_all(f'select[name*="{field_name}"]')
            for sel in selects:
                if sel.is_visible():
                    options = sel.query_selector_all("option")
                    for opt in options:
                        text = (opt.inner_text() or "").strip().lower()
                        if value.lower() in text:
                            sel.select_option(value=opt.get_attribute("value"))
                            break
        except Exception:
            pass


def apply_lever(job_url: str, job: Dict, proxy: str = None) -> Dict:
    """Apply to a Lever-hosted job application.

    Args:
        job_url: URL to the Lever application page (e.g., jobs.lever.co/company/id/apply).
        job: Job dict.
        proxy: Optional proxy URL.

    Returns:
        Dict: {status: 'submitted'|'failed'|'skipped', error: str|None}
    """
    if not job_url:
        return {"status": "skipped", "error": "No URL provided"}

    url_low = job_url.lower()
    if "lever.co" not in url_low:
        return {"status": "skipped", "error": "Not a Lever URL"}

    # Ensure we're on the /apply page
    if "/apply" not in url_low:
        job_url = job_url.rstrip("/") + "/apply"

    try:
        with PlaywrightRunner(proxy=proxy, headless=True) as runner:
            page = runner.new_page()
            page.goto(job_url, timeout=30000)
            wait_for_page_load(page)

            profile = get_profile()

            # Fill standard fields
            std_filled = _fill_lever_standard_fields(page, profile)
            logger.info("Lever: filled %d standard fields", std_filled)

            # Upload resume
            _upload_lever_resume(page)

            # Fill cover letter
            _fill_lever_cover_letter(page, job)

            # Fill additional custom questions
            custom_filled = _fill_lever_additional_questions(page, job, profile)
            logger.info("Lever: filled %d custom fields", custom_filled)

            # Handle EEO
            _handle_lever_eeo(page, profile)

            # Submit
            submit = page.query_selector(_SUBMIT_BTN)
            if submit and submit.is_visible() and submit.is_enabled():
                submit.click()
                time.sleep(4)

                # Check for errors
                errors = page.query_selector_all('.application-error, div[class*="error"]')
                visible_errors = [e for e in errors if e.is_visible()]
                if visible_errors:
                    error_texts = [e.inner_text().strip() for e in visible_errors[:3]]
                    return {"status": "failed", "error": f"Validation: {'; '.join(error_texts)}"}

                # Check for success
                success = page.query_selector(
                    'div:has-text("Application submitted"), '
                    'h2:has-text("Thanks for applying"), '
                    'div:has-text("Thank you"), '
                    'div.application-confirmation'
                )
                if success:
                    return {"status": "submitted", "error": None}

                return {"status": "submitted", "error": None}

            return {"status": "failed", "error": "No submit button found"}

    except Exception as e:
        logger.error("Lever auto-apply error for %s: %s", job_url, e)
        return {"status": "failed", "error": str(e)}
