"""Tests for the auto_apply.form_filler module — label matching, value resolution, ATS detection."""
import os
import pytest

os.environ.setdefault("APPLICANT_FIRST_NAME", "Jane")
os.environ.setdefault("APPLICANT_LAST_NAME", "Doe")
os.environ.setdefault("APPLICANT_EMAIL", "jane@example.com")
os.environ.setdefault("APPLICANT_PHONE", "555-1234")
os.environ.setdefault("APPLICANT_LINKEDIN_URL", "https://linkedin.com/in/janedoe")
os.environ.setdefault("APPLICANT_GITHUB_URL", "https://github.com/janedoe")
os.environ.setdefault("APPLICANT_CITY", "Austin")
os.environ.setdefault("APPLICANT_STATE", "TX")

from backend.app.auto_apply.form_filler import (
    _match_field_label,
    _resolve_value,
    detect_ats,
)
from backend.app.auto_apply.profile import get_profile, reset_profile


class TestMatchFieldLabel:
    """Test _match_field_label — label-to-profile-key mapping."""

    def test_first_name(self):
        assert _match_field_label("First Name") == "first_name"
        assert _match_field_label("first_name") == "first_name"
        assert _match_field_label("First name *") == "first_name"

    def test_last_name(self):
        assert _match_field_label("Last Name") == "last_name"
        assert _match_field_label("surname") == "last_name"

    def test_full_name(self):
        assert _match_field_label("Full Name") == "_full_name"
        assert _match_field_label("Your Name") == "_full_name"

    def test_name_no_longer_too_broad(self):
        """Bare 'name' was removed — 'Company Name' should NOT match _full_name."""
        # "Company Name" should match "current_company" (via "company name" pattern)
        result = _match_field_label("Company Name")
        assert result == "current_company"

    def test_email(self):
        assert _match_field_label("Email Address") == "email"
        assert _match_field_label("E-mail") == "email"

    def test_phone(self):
        assert _match_field_label("Phone Number") == "phone"
        assert _match_field_label("Mobile") == "phone"

    def test_linkedin(self):
        assert _match_field_label("LinkedIn URL") == "linkedin_url"
        assert _match_field_label("linkedin profile") == "linkedin_url"

    def test_github(self):
        assert _match_field_label("GitHub") == "github_url"

    def test_portfolio(self):
        assert _match_field_label("Portfolio URL") == "website"

    def test_city(self):
        assert _match_field_label("City") == "address.city"

    def test_state(self):
        assert _match_field_label("State") == "address.state"

    def test_zip_code(self):
        assert _match_field_label("Zip Code") == "address.zip"

    def test_country(self):
        assert _match_field_label("Country") == "address.country"

    def test_current_title(self):
        assert _match_field_label("Current Title") == "current_title"
        assert _match_field_label("Job Title") == "current_title"

    def test_current_company(self):
        assert _match_field_label("Current Company") == "current_company"
        assert _match_field_label("Current Employer") == "current_company"
        assert _match_field_label("Company Name") == "current_company"

    def test_years_experience(self):
        assert _match_field_label("Years of Experience") == "years_experience"

    def test_salary(self):
        assert _match_field_label("Desired Salary") == "salary_expectation"
        assert _match_field_label("Salary Expectations") == "salary_expectation"

    def test_start_date(self):
        assert _match_field_label("Start Date") == "start_date"
        assert _match_field_label("Earliest Start") == "start_date"

    def test_degree(self):
        assert _match_field_label("Degree") == "education.degree"

    def test_major(self):
        assert _match_field_label("Major") == "education.major"
        assert _match_field_label("Field of Study") == "education.major"

    def test_school(self):
        assert _match_field_label("School") == "education.school"
        assert _match_field_label("University") == "education.school"

    def test_grad_year(self):
        assert _match_field_label("Graduation Year") == "education.grad_year"

    def test_work_authorization(self):
        assert _match_field_label("Are you authorized to work in the US?") == "work_authorization"

    def test_sponsorship(self):
        assert _match_field_label("Do you require visa sponsorship?") == "sponsorship_needed"

    def test_relocate(self):
        assert _match_field_label("Willing to relocate?") == "willing_to_relocate"

    def test_gender(self):
        assert _match_field_label("Gender") == "gender"

    def test_veteran(self):
        assert _match_field_label("Veteran Status") == "veteran_status"

    def test_disability(self):
        assert _match_field_label("Do you have a disability?") == "disability_status"

    def test_race(self):
        assert _match_field_label("Race / Ethnicity") == "race_ethnicity"

    def test_empty_label(self):
        assert _match_field_label("") is None

    def test_unrecognized_label(self):
        assert _match_field_label("How did you hear about us?") is None


class TestResolveValue:
    """Test _resolve_value — profile key to value resolution."""

    def setup_method(self):
        reset_profile()

    def test_simple_key(self):
        profile = get_profile()
        assert _resolve_value("first_name", profile) == "Jane"

    def test_full_name_special(self):
        profile = get_profile()
        assert _resolve_value("_full_name", profile) == "Jane Doe"

    def test_dot_notation(self):
        profile = get_profile()
        assert _resolve_value("address.city", profile) == "Austin"
        assert _resolve_value("address.state", profile) == "TX"

    def test_deep_dot_notation(self):
        profile = get_profile()
        val = _resolve_value("education.degree", profile)
        assert isinstance(val, str)

    def test_missing_key(self):
        profile = get_profile()
        assert _resolve_value("nonexistent", profile) == ""

    def test_empty_key(self):
        profile = get_profile()
        result = _resolve_value("", profile)
        # empty string key → profile dict itself via empty split, returns empty str
        assert isinstance(result, str)


class TestDetectATS:
    """Test detect_ats — URL pattern matching."""

    def test_greenhouse(self):
        assert detect_ats("https://boards.greenhouse.io/company/jobs/123") == "greenhouse"
        assert detect_ats("https://boards.greenhouse.io/foo") == "greenhouse"

    def test_lever(self):
        assert detect_ats("https://jobs.lever.co/company/abc-def") == "lever"

    def test_workday(self):
        assert detect_ats("https://company.wd5.myworkdayjobs.com/en-US/External/job/Title_ID") == "workday"
        assert detect_ats("https://example.workday.com/jobs") == "workday"

    def test_icims(self):
        assert detect_ats("https://careers-icims.example.com/jobs/123") == "icims"
        assert detect_ats("https://icims.com/jobs/123") == "icims"

    def test_taleo(self):
        assert detect_ats("https://company.taleo.net/careers/apply") == "taleo"

    def test_successfactors(self):
        assert detect_ats("https://careers.successfactors.com/apply") == "successfactors"

    def test_bamboohr(self):
        assert detect_ats("https://company.bamboohr.com/jobs/view.php?id=1") == "bamboohr"

    def test_smartrecruiters(self):
        assert detect_ats("https://careers.smartrecruiters.com/Company/123") == "smartrecruiters"

    def test_jobvite(self):
        assert detect_ats("https://jobs.jobvite.com/company/job/abc") == "jobvite"

    def test_unknown(self):
        assert detect_ats("https://example.com/careers") is None
        assert detect_ats("https://google.com") is None

    def test_none_url(self):
        assert detect_ats(None) is None
        assert detect_ats("") is None

    def test_case_insensitive(self):
        assert detect_ats("https://BOARDS.GREENHOUSE.IO/jobs") == "greenhouse"
        assert detect_ats("https://Jobs.Lever.co/foo") == "lever"
