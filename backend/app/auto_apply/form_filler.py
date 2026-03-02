"""Generic form filler engine — detects input fields and fills them intelligently.

Uses Playwright page object + applicant profile to auto-fill any web form.
Handles text inputs, textareas, selects, radio buttons, checkboxes, and file uploads.
"""
import os
import re
import time
import logging
from typing import Dict, List, Optional, Tuple

from .profile import get_profile, get_full_name, get_cover_letter_text

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Label → profile-key mapping (case-insensitive substring match)               #
# --------------------------------------------------------------------------- #
_FIELD_MAP: List[Tuple[List[str], str]] = [
    # Name fields
    (["first name", "first_name", "fname", "given name"], "first_name"),
    (["last name", "last_name", "lname", "surname", "family name"], "last_name"),
    (["full name", "your name", "name"], "_full_name"),
    # Contact
    (["email", "e-mail"], "email"),
    (["phone", "mobile", "telephone", "cell"], "phone"),
    # Online presence
    (["linkedin"], "linkedin_url"),
    (["github"], "github_url"),
    (["portfolio", "personal website", "website", "url", "web site"], "website"),
    # Location
    (["street", "address line 1", "address_line1"], "address.street"),
    (["city"], "address.city"),
    (["state", "province"], "address.state"),
    (["zip", "postal"], "address.zip"),
    (["country"], "address.country"),
    # Professional
    (["current title", "job title", "current position", "current role"], "current_title"),
    (["current company", "current employer", "company name"], "current_company"),
    (["years of experience", "years experience", "total experience"], "years_experience"),
    (["salary", "compensation", "desired salary", "expected salary"], "salary_expectation"),
    (["start date", "available date", "earliest start", "availability"], "start_date"),
    # Education
    (["degree", "level of education", "education level"], "education.degree"),
    (["major", "field of study", "area of study"], "education.major"),
    (["school", "university", "college", "institution"], "education.school"),
    (["graduation year", "grad year", "year of graduation"], "education.grad_year"),
    # Authorization / EEO
    (["authorized to work", "work authorization", "legally authorized", "eligible to work"], "work_authorization"),
    (["sponsorship", "visa sponsorship", "require sponsorship", "need sponsorship"], "sponsorship_needed"),
    (["relocat", "willing to relocate"], "willing_to_relocate"),
    (["gender"], "gender"),
    (["veteran"], "veteran_status"),
    (["disability", "disabled"], "disability_status"),
    (["race", "ethnicity"], "race_ethnicity"),
]


def _resolve_value(key: str, profile: Dict, job: Optional[Dict] = None) -> str:
    """Resolve a profile key to its string value."""
    if key == "_full_name":
        return get_full_name()
    if key == "_cover_letter":
        return get_cover_letter_text(job or {})

    # Support dot-notation for nested keys like "address.city"
    parts = key.split(".")
    val = profile
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p, "")
        else:
            return ""
    return str(val) if val else ""


def _match_field_label(label_text: str) -> Optional[str]:
    """Match a form field label to a profile key."""
    low = label_text.lower().strip()
    if not low:
        return None
    for patterns, key in _FIELD_MAP:
        for pat in patterns:
            if pat in low:
                return key
    return None


def _get_label_for_element(page, element) -> str:
    """Try to find the label text for a form element."""
    try:
        # Check aria-label
        aria = element.get_attribute("aria-label")
        if aria:
            return aria

        # Check placeholder
        placeholder = element.get_attribute("placeholder")

        # Check associated <label> via id
        el_id = element.get_attribute("id")
        if el_id:
            label_el = page.query_selector(f'label[for="{el_id}"]')
            if label_el:
                return label_el.inner_text().strip()

        # Check parent label
        parent_label = element.evaluate(
            """el => {
                let p = el.closest('label');
                if (p) return p.innerText;
                // Check previous sibling
                let prev = el.previousElementSibling;
                if (prev && prev.tagName === 'LABEL') return prev.innerText;
                // Check parent's previous sibling
                let parent = el.parentElement;
                if (parent) {
                    prev = parent.previousElementSibling;
                    if (prev && (prev.tagName === 'LABEL' || prev.tagName === 'SPAN' || prev.tagName === 'DIV'))
                        return prev.innerText;
                }
                return '';
            }"""
        )
        if parent_label:
            return parent_label.strip()

        # Check name attribute
        name = element.get_attribute("name")
        if name:
            # Convert name like "first_name" or "firstName" to readable form
            readable = re.sub(r"[_\-]", " ", name)
            readable = re.sub(r"([a-z])([A-Z])", r"\1 \2", readable)
            return readable

        return placeholder or ""
    except Exception:
        return ""


def _select_best_option(select_el, target_value: str) -> bool:
    """For a <select> element, pick the best matching <option>."""
    try:
        options = select_el.query_selector_all("option")
        target_low = target_value.lower()
        best_match = None
        best_score = 0

        for opt in options:
            text = (opt.inner_text() or "").strip().lower()
            val = (opt.get_attribute("value") or "").lower()

            if not text and not val:
                continue

            # Exact match
            if text == target_low or val == target_low:
                best_match = opt
                best_score = 100
                break

            # Substring match
            score = 0
            if target_low in text or target_low in val:
                score = 80
            elif any(w in text for w in target_low.split()):
                score = 60
            elif text in target_low:
                score = 50

            # "yes" / "no" shortcut
            if target_low in ("yes", "true") and text in ("yes", "true", "y"):
                score = 90
            elif target_low in ("no", "false") and text in ("no", "false", "n"):
                score = 90

            if score > best_score:
                best_score = score
                best_match = opt

        if best_match and best_score >= 50:
            value = best_match.get_attribute("value")
            if value is not None:
                select_el.select_option(value=value)
                return True
        return False
    except Exception as e:
        logger.debug("Select option matching failed: %s", e)
        return False


def _handle_radio_group(page, name_attr: str, target_value: str) -> bool:
    """Select the best matching radio button in a group."""
    try:
        radios = page.query_selector_all(f'input[type="radio"][name="{name_attr}"]')
        target_low = target_value.lower()

        for radio in radios:
            label = _get_label_for_element(page, radio)
            val = (radio.get_attribute("value") or "").lower()
            label_low = label.lower()

            if target_low in label_low or target_low in val:
                radio.check()
                return True
            # yes/no shortcut
            if target_low in ("yes", "true") and any(w in label_low for w in ["yes", "true"]):
                radio.check()
                return True
            if target_low in ("no", "false") and any(w in label_low for w in ["no", "false"]):
                radio.check()
                return True

        return False
    except Exception:
        return False


def fill_form(page, job: Optional[Dict] = None, dry_run: bool = False) -> Dict:
    """Auto-fill all detected form fields on the current page.

    Args:
        page: Playwright page object.
        job: Job dict for context-aware filling (cover letter, etc.).
        dry_run: If True, detect fields but don't actually fill them.

    Returns:
        Dict with keys: filled (int), skipped (int), fields (list of field info).
    """
    profile = get_profile()
    result = {"filled": 0, "skipped": 0, "fields": []}

    # 1. Handle text inputs and textareas
    inputs = page.query_selector_all(
        'input[type="text"], input[type="email"], input[type="tel"], '
        'input[type="url"], input[type="number"], input:not([type]), textarea'
    )

    for inp in inputs:
        try:
            # Skip hidden / disabled / already-filled
            if not inp.is_visible():
                continue
            if inp.is_disabled():
                continue

            label = _get_label_for_element(page, inp)
            if not label:
                continue

            key = _match_field_label(label)
            if not key:
                # Check if it's a cover letter field
                if any(w in label.lower() for w in ["cover letter", "cover_letter", "coverletter", "message to"]):
                    key = "_cover_letter"
                else:
                    result["skipped"] += 1
                    result["fields"].append({"label": label, "status": "unrecognized"})
                    continue

            value = _resolve_value(key, profile, job)
            if not value:
                result["skipped"] += 1
                result["fields"].append({"label": label, "key": key, "status": "no_value"})
                continue

            if not dry_run:
                # Clear existing value and type new one
                inp.click()
                inp.fill("")
                inp.fill(value)
                time.sleep(0.1)

            result["filled"] += 1
            result["fields"].append({"label": label, "key": key, "status": "filled"})

        except Exception as e:
            logger.debug("Error filling input '%s': %s", label if 'label' in dir() else '?', e)
            result["skipped"] += 1

    # 2. Handle <select> elements
    selects = page.query_selector_all("select")
    for sel in selects:
        try:
            if not sel.is_visible():
                continue
            label = _get_label_for_element(page, sel)
            if not label:
                continue

            key = _match_field_label(label)
            if not key:
                result["skipped"] += 1
                continue

            value = _resolve_value(key, profile, job)
            if not value:
                result["skipped"] += 1
                continue

            if not dry_run:
                ok = _select_best_option(sel, value)
                if ok:
                    result["filled"] += 1
                    result["fields"].append({"label": label, "key": key, "status": "filled"})
                else:
                    result["skipped"] += 1
                    result["fields"].append({"label": label, "key": key, "status": "no_match"})
            else:
                result["filled"] += 1

        except Exception as e:
            logger.debug("Error filling select '%s': %s", label if 'label' in dir() else '?', e)
            result["skipped"] += 1

    # 3. Handle radio button groups
    processed_radios = set()
    radios = page.query_selector_all('input[type="radio"]')
    for radio in radios:
        try:
            name = radio.get_attribute("name")
            if not name or name in processed_radios:
                continue
            processed_radios.add(name)

            if not radio.is_visible():
                continue

            # Get label for the radio group
            label = _get_label_for_element(page, radio)
            key = _match_field_label(label) if label else None
            if not key:
                continue

            value = _resolve_value(key, profile, job)
            if not value:
                continue

            if not dry_run:
                ok = _handle_radio_group(page, name, value)
                if ok:
                    result["filled"] += 1
                    result["fields"].append({"label": label, "key": key, "status": "filled"})
                else:
                    result["skipped"] += 1
            else:
                result["filled"] += 1

        except Exception:
            result["skipped"] += 1

    # 4. Handle checkboxes (e.g., "I agree to terms")
    checkboxes = page.query_selector_all('input[type="checkbox"]')
    for cb in checkboxes:
        try:
            if not cb.is_visible():
                continue
            label = _get_label_for_element(page, cb)
            low = label.lower() if label else ""
            # Auto-check agreement / terms / privacy checkboxes
            if any(w in low for w in ["agree", "terms", "privacy", "consent", "acknowledge", "confirm"]):
                if not dry_run:
                    if not cb.is_checked():
                        cb.check()
                result["filled"] += 1
                result["fields"].append({"label": label, "status": "checked"})
        except Exception:
            pass

    return result


def upload_resume(page, selector: str = None) -> bool:
    """Upload resume file to a file input on the page.

    Args:
        page: Playwright page object.
        selector: Optional CSS selector for the file input.

    Returns:
        True if upload succeeded.
    """
    resume_path = os.getenv("RESUME_PATH", "")
    if not resume_path or not os.path.exists(resume_path):
        logger.warning("RESUME_PATH not set or file missing — cannot upload resume")
        return False

    try:
        if selector:
            file_input = page.query_selector(selector)
        else:
            # Find file inputs
            file_inputs = page.query_selector_all('input[type="file"]')
            if not file_inputs:
                logger.debug("No file input found on page")
                return False

            # Prefer the first visible file input, or one labeled "resume"
            file_input = None
            for fi in file_inputs:
                label = _get_label_for_element(page, fi)
                if label and any(w in label.lower() for w in ["resume", "cv", "curriculum"]):
                    file_input = fi
                    break
            if not file_input:
                file_input = file_inputs[0]

        if file_input:
            file_input.set_input_files(os.path.abspath(resume_path))
            logger.info("Resume uploaded: %s", os.path.basename(resume_path))
            return True
        return False
    except Exception as e:
        logger.warning("Resume upload failed: %s", e)
        return False


def upload_cover_letter(page, job: Dict, selector: str = None) -> bool:
    """Upload or paste a cover letter."""
    # Check if there's a cover letter file first
    cl_path = os.getenv("COVER_LETTER_PATH", "")
    if cl_path and os.path.exists(cl_path):
        try:
            file_inputs = page.query_selector_all('input[type="file"]')
            for fi in file_inputs:
                label = _get_label_for_element(page, fi)
                if label and any(w in label.lower() for w in ["cover letter", "cover_letter"]):
                    fi.set_input_files(os.path.abspath(cl_path))
                    return True
        except Exception:
            pass

    # Otherwise, try to find a cover letter text field and fill it
    try:
        textareas = page.query_selector_all("textarea")
        for ta in textareas:
            if not ta.is_visible():
                continue
            label = _get_label_for_element(page, ta)
            if label and any(w in label.lower() for w in ["cover letter", "cover_letter", "coverletter"]):
                cl_text = get_cover_letter_text(job)
                ta.fill(cl_text)
                return True
    except Exception as e:
        logger.debug("Cover letter fill failed: %s", e)

    return False


def detect_ats(url: str) -> Optional[str]:
    """Detect which ATS a job application URL belongs to.

    Returns ATS name or None.
    """
    url_low = url.lower() if url else ""

    ats_patterns = [
        ("greenhouse", ["greenhouse.io", "boards.greenhouse"]),
        ("lever", ["lever.co", "jobs.lever"]),
        ("workday", ["myworkdayjobs.com", "workday.com", "wd5.myworkdayjobs", "wd3.myworkdayjobs"]),
        ("icims", ["icims.com", "careers-icims"]),
        ("taleo", ["taleo.net", "taleo.com"]),
        ("successfactors", ["successfactors.com", "successfactors.eu"]),
        ("bamboohr", ["bamboohr.com"]),
        ("jazz", ["applytojob.com", "jazz.co"]),
        ("ashby", ["ashbyhq.com"]),
        ("rippling", ["rippling.com/careers"]),
        ("smartrecruiters", ["smartrecruiters.com"]),
        ("jobvite", ["jobvite.com", "jobs.jobvite"]),
    ]

    for name, patterns in ats_patterns:
        for pat in patterns:
            if pat in url_low:
                return name

    return None


def click_submit(page, dry_run: bool = False) -> bool:
    """Find and click the submit / apply button.

    Args:
        page: Playwright page object.
        dry_run: If True, find the button but don't click it.

    Returns:
        True if a submit button was found (and clicked if not dry_run).
    """
    submit_patterns = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Submit")',
        'button:has-text("Apply")',
        'button:has-text("Submit Application")',
        'button:has-text("Submit application")',
        'button:has-text("Send Application")',
        'button:has-text("Complete Application")',
        'a:has-text("Submit")',
        'a:has-text("Apply")',
    ]

    for selector in submit_patterns:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible() and btn.is_enabled():
                if not dry_run:
                    btn.click()
                    time.sleep(2)
                return True
        except Exception:
            continue

    return False


def click_next(page) -> bool:
    """Click 'Next' / 'Continue' button for multi-step forms."""
    next_patterns = [
        'button:has-text("Next")',
        'button:has-text("Continue")',
        'button:has-text("next")',
        'button:has-text("continue")',
        'a:has-text("Next")',
        'a:has-text("Continue")',
        'button[data-action="next"]',
        'button.next-btn',
    ]

    for selector in next_patterns:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible() and btn.is_enabled():
                btn.click()
                time.sleep(1.5)
                return True
        except Exception:
            continue

    return False


def wait_for_page_load(page, timeout: int = 10000):
    """Wait for page to reach a stable state."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass

