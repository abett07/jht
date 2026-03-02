"""BuiltIn.com auto-apply automation.

Handles BuiltIn's job application form with form filling and resume upload.
"""
import os
import time
import logging
from typing import Dict

from ..scrapers.playwright_base import PlaywrightRunner
from .form_filler import (
    fill_form, upload_resume,
    wait_for_page_load,
)

logger = logging.getLogger(__name__)

_APPLY_BTN = 'a:has-text("Apply"), button:has-text("Apply"), a.apply-button, a[data-id="apply-button"]'
_SUBMIT_BTN = 'button:has-text("Submit"), button[type="submit"]'


def apply_builtin(job_url: str, job: Dict, proxy: str = None) -> Dict:
    """Apply to a BuiltIn.com job listing.

    BuiltIn typically redirects to the company's ATS. This handler processes the
    BuiltIn application page or follows through to the ATS.

    Args:
        job_url: URL to the BuiltIn job posting.
        job: Job dict.
        proxy: Optional proxy URL.

    Returns:
        Dict: {status: 'submitted'|'failed'|'skipped', error: str|None, redirect_url: str|None}
    """
    if not job_url or "builtin.com" not in job_url:
        return {"status": "skipped", "error": "Not a BuiltIn URL"}

    try:
        with PlaywrightRunner(proxy=proxy, headless=True) as runner:
            page = runner.new_page()
            page.goto(job_url, timeout=30000)
            wait_for_page_load(page)

            # Click apply button
            apply_btn = page.query_selector(_APPLY_BTN)
            if not apply_btn:
                return {"status": "skipped", "error": "No apply button found on BuiltIn"}

            # Check if it redirects to external ATS
            href = apply_btn.get_attribute("href")
            target = apply_btn.get_attribute("target")

            if href and ("greenhouse" in href or "lever.co" in href or "workday" in href or "icims" in href):
                # External ATS — return redirect URL for the orchestrator to handle
                return {"status": "redirect", "error": None, "redirect_url": href}

            apply_btn.click()
            time.sleep(3)

            # Check if we navigated to a new page (external ATS)
            current_url = page.url
            if "builtin.com" not in current_url:
                return {"status": "redirect", "error": None, "redirect_url": current_url}

            # Fill BuiltIn's own application form
            fill_result = fill_form(page, job=job)
            upload_resume(page)

            # Submit
            submit = page.query_selector(_SUBMIT_BTN)
            if submit and submit.is_visible():
                submit.click()
                time.sleep(3)
                return {"status": "submitted", "error": None}

            return {"status": "failed", "error": "Could not find submit button"}

    except Exception as e:
        logger.error("BuiltIn auto-apply error for %s: %s", job_url, e)
        return {"status": "failed", "error": str(e)}
