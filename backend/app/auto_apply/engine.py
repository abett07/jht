"""Auto-apply orchestrator — routes jobs to the correct board/ATS applicator.

Central engine that:
1. Detects the job board or ATS from the URL
2. Routes to the appropriate applicator module
3. Falls back to generic form filling for unknown ATS
4. Tracks application status and errors
"""
import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .form_filler import detect_ats, fill_form, upload_resume, click_submit, wait_for_page_load
from .profile import get_profile
from .linkedin_apply import apply_linkedin
from .indeed_apply import apply_indeed
from .dice_apply import apply_dice
from .ziprecruiter_apply import apply_ziprecruiter
from .builtin_apply import apply_builtin
from .wellfound_apply import apply_wellfound
from .greenhouse_apply import apply_greenhouse
from .lever_apply import apply_lever
from .workday_apply import apply_workday

logger = logging.getLogger(__name__)

# Board detection patterns: (board_name, url_substring, applicator_fn)
_BOARD_ROUTES = [
    ("linkedin", "linkedin.com", apply_linkedin),
    ("indeed", "indeed.com", apply_indeed),
    ("dice", "dice.com", apply_dice),
    ("ziprecruiter", "ziprecruiter.com", apply_ziprecruiter),
    ("builtin", "builtin.com", apply_builtin),
    ("wellfound", "wellfound.com", apply_wellfound),
]

# ATS detection patterns: (ats_name, url_patterns, applicator_fn)
_ATS_ROUTES = [
    ("greenhouse", ["greenhouse.io", "boards.greenhouse", "grnh.se"], apply_greenhouse),
    ("lever", ["lever.co", "jobs.lever"], apply_lever),
    ("workday", ["myworkdayjobs.com", "workday.com"], apply_workday),
]


def _detect_board(url: str) -> Optional[Tuple[str, callable]]:
    """Detect which job board a URL belongs to."""
    if not url:
        return None
    url_low = url.lower()
    for name, pattern, fn in _BOARD_ROUTES:
        if pattern in url_low:
            return name, fn
    return None


def _detect_ats_route(url: str) -> Optional[Tuple[str, callable]]:
    """Detect which ATS a URL belongs to."""
    if not url:
        return None
    url_low = url.lower()
    for name, patterns, fn in _ATS_ROUTES:
        for pat in patterns:
            if pat in url_low:
                return name, fn
    return None


def _apply_generic(job_url: str, job: Dict, proxy: str = None) -> Dict:
    """Generic auto-apply for unknown job boards / ATS.

    Opens the page, attempts to fill all form fields with profile data,
    uploads resume, and submits. Best-effort.

    Returns:
        Dict: {status: 'submitted'|'failed', error: str|None}
    """
    if not job_url:
        return {"status": "failed", "error": "No URL provided"}

    try:
        from ..scrapers.playwright_base import PlaywrightRunner

        with PlaywrightRunner(proxy=proxy, headless=True) as runner:
            page = runner.new_page()
            page.goto(job_url, timeout=30000)
            wait_for_page_load(page)

            # Fill form fields
            fill_result = fill_form(page, job=job)
            logger.info("Generic apply: filled %d fields, skipped %d",
                       fill_result["filled"], fill_result["skipped"])

            # Upload resume
            upload_resume(page)

            # Submit
            if click_submit(page):
                time.sleep(3)
                return {"status": "submitted", "error": None}

            return {"status": "failed", "error": "No submit button found"}

    except Exception as e:
        logger.error("Generic auto-apply error for %s: %s", job_url, e)
        return {"status": "failed", "error": str(e)}


def apply_to_job(job: Dict, proxy: str = None, dry_run: bool = False) -> Dict:
    """Apply to a single job — detect board/ATS and route appropriately.

    Args:
        job: Job dict with at least 'url', 'title', 'company'.
        proxy: Optional proxy URL.
        dry_run: If True, detect method but don't actually apply.

    Returns:
        Dict: {
            status: 'submitted'|'failed'|'skipped',
            method: 'linkedin'|'indeed'|...|'generic',
            ats_detected: str|None,
            error: str|None,
            applied_at: str (ISO timestamp),
        }
    """
    url = job.get("url", "")
    result = {
        "status": "skipped",
        "method": None,
        "ats_detected": None,
        "error": None,
        "applied_at": None,
    }

    if not url:
        result["error"] = "No job URL available"
        return result

    # Validate profile is configured
    profile = get_profile()
    if not profile.get("first_name") or not profile.get("email"):
        result["error"] = "Applicant profile incomplete — set APPLICANT_FIRST_NAME and APPLICANT_EMAIL"
        result["status"] = "failed"
        return result

    # Ensure resume exists
    resume_path = os.getenv("RESUME_PATH", "")
    if not resume_path or not os.path.exists(resume_path):
        logger.warning("RESUME_PATH not set — applications may fail without resume upload")

    if dry_run:
        # Just detect the method
        board = _detect_board(url)
        if board:
            result["method"] = board[0]
        else:
            ats = _detect_ats_route(url)
            if ats:
                result["method"] = ats[0]
                result["ats_detected"] = ats[0]
            else:
                result["method"] = "generic"
        result["status"] = "dry_run"
        return result

    logger.info("Auto-applying to: %s at %s (%s)", job.get("title"), job.get("company"), url)

    # 1. Try job board-specific applicator
    board = _detect_board(url)
    if board:
        name, fn = board
        result["method"] = name
        try:
            apply_result = fn(url, job, proxy=proxy)
            result["status"] = apply_result.get("status", "failed")
            result["error"] = apply_result.get("error")

            # Handle redirect (e.g., BuiltIn → Greenhouse)
            if result["status"] == "redirect" and apply_result.get("redirect_url"):
                redirect_url = apply_result["redirect_url"]
                logger.info("Redirect from %s → %s", name, redirect_url)
                ats = _detect_ats_route(redirect_url)
                if ats:
                    ats_name, ats_fn = ats
                    result["ats_detected"] = ats_name
                    ats_result = ats_fn(redirect_url, job, proxy=proxy)
                    result["status"] = ats_result.get("status", "failed")
                    result["error"] = ats_result.get("error")
                    result["method"] = f"{name}→{ats_name}"
                else:
                    generic_result = _apply_generic(redirect_url, job, proxy=proxy)
                    result["status"] = generic_result.get("status", "failed")
                    result["error"] = generic_result.get("error")
                    result["method"] = f"{name}→generic"
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)

        if result["status"] == "submitted":
            result["applied_at"] = datetime.utcnow().isoformat()
        return result

    # 2. Try ATS-specific applicator
    ats = _detect_ats_route(url)
    if ats:
        name, fn = ats
        result["method"] = name
        result["ats_detected"] = name
        try:
            apply_result = fn(url, job, proxy=proxy)
            result["status"] = apply_result.get("status", "failed")
            result["error"] = apply_result.get("error")
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)

        if result["status"] == "submitted":
            result["applied_at"] = datetime.utcnow().isoformat()
        return result

    # 3. Check URL for known ATS patterns via detect_ats helper
    ats_name = detect_ats(url)
    if ats_name:
        result["ats_detected"] = ats_name
        for name, _, fn in _ATS_ROUTES:
            if name == ats_name:
                result["method"] = name
                try:
                    apply_result = fn(url, job, proxy=proxy)
                    result["status"] = apply_result.get("status", "failed")
                    result["error"] = apply_result.get("error")
                except Exception as e:
                    result["status"] = "failed"
                    result["error"] = str(e)

                if result["status"] == "submitted":
                    result["applied_at"] = datetime.utcnow().isoformat()
                return result

    # 4. Fallback to generic applicator
    result["method"] = "generic"
    try:
        apply_result = _apply_generic(url, job, proxy=proxy)
        result["status"] = apply_result.get("status", "failed")
        result["error"] = apply_result.get("error")
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)

    if result["status"] == "submitted":
        result["applied_at"] = datetime.utcnow().isoformat()
    return result


def batch_apply(jobs: List[Dict], proxy: str = None,
                max_per_run: int = 20, delay: float = 5.0,
                dry_run: bool = False) -> List[Dict]:
    """Apply to multiple jobs with rate limiting.

    Args:
        jobs: List of job dicts.
        proxy: Optional proxy URL.
        max_per_run: Maximum applications per batch.
        delay: Seconds to wait between applications.
        dry_run: If True, detect methods without applying.

    Returns:
        List of result dicts, one per job.
    """
    results = []
    applied = 0

    for job in jobs:
        if applied >= max_per_run:
            logger.info("Batch apply limit reached (%d)", max_per_run)
            break

        result = apply_to_job(job, proxy=proxy, dry_run=dry_run)
        result["job_title"] = job.get("title")
        result["job_company"] = job.get("company")
        results.append(result)

        if result["status"] == "submitted":
            applied += 1
            logger.info("  ✓ Applied: %s at %s via %s",
                       job.get("title"), job.get("company"), result.get("method"))
        elif result["status"] == "failed":
            logger.warning("  ✗ Failed: %s at %s — %s",
                          job.get("title"), job.get("company"), result.get("error"))
        else:
            logger.info("  → Skipped: %s at %s — %s",
                       job.get("title"), job.get("company"), result.get("error") or result.get("status"))

        # Rate limit between applications
        if not dry_run and applied < max_per_run:
            time.sleep(delay)

    logger.info("Batch apply complete: %d/%d submitted", applied, len(results))
    return results
