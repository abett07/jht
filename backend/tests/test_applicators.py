"""Tests for individual board/ATS applicators — URL validation and early returns."""
import os
import pytest

os.environ.setdefault("APPLICANT_FIRST_NAME", "Jane")
os.environ.setdefault("APPLICANT_LAST_NAME", "Doe")
os.environ.setdefault("APPLICANT_EMAIL", "jane@example.com")

from backend.app.auto_apply.linkedin_apply import apply_linkedin
from backend.app.auto_apply.indeed_apply import apply_indeed
from backend.app.auto_apply.dice_apply import apply_dice
from backend.app.auto_apply.ziprecruiter_apply import apply_ziprecruiter
from backend.app.auto_apply.builtin_apply import apply_builtin
from backend.app.auto_apply.wellfound_apply import apply_wellfound
from backend.app.auto_apply.greenhouse_apply import apply_greenhouse
from backend.app.auto_apply.lever_apply import apply_lever
from backend.app.auto_apply.workday_apply import apply_workday


JOB = {"title": "Software Engineer", "company": "TestCo", "url": "https://example.com"}


class TestLinkedInApply:
    def test_skip_non_linkedin(self):
        result = apply_linkedin("https://example.com/job", JOB)
        assert result["status"] == "skipped"
        assert "Not a LinkedIn" in result["error"]

    def test_skip_none_url(self):
        result = apply_linkedin(None, JOB)
        assert result["status"] == "skipped"

    def test_skip_empty_url(self):
        result = apply_linkedin("", JOB)
        assert result["status"] == "skipped"


class TestIndeedApply:
    def test_skip_non_indeed(self):
        result = apply_indeed("https://example.com/job", JOB)
        assert result["status"] == "skipped"
        assert "Not an Indeed" in result["error"]

    def test_skip_none(self):
        result = apply_indeed(None, JOB)
        assert result["status"] == "skipped"


class TestDiceApply:
    def test_skip_non_dice(self):
        result = apply_dice("https://example.com/job", JOB)
        assert result["status"] == "skipped"
        assert "Not a Dice" in result["error"]

    def test_skip_none(self):
        result = apply_dice(None, JOB)
        assert result["status"] == "skipped"


class TestZipRecruiterApply:
    def test_skip_non_ziprecruiter(self):
        result = apply_ziprecruiter("https://example.com/job", JOB)
        assert result["status"] == "skipped"
        assert "Not a ZipRecruiter" in result["error"]


class TestBuiltInApply:
    def test_skip_non_builtin(self):
        result = apply_builtin("https://example.com/job", JOB)
        assert result["status"] == "skipped"
        assert "Not a BuiltIn" in result["error"]


class TestWellfoundApply:
    def test_skip_non_wellfound(self):
        result = apply_wellfound("https://example.com/job", JOB)
        assert result["status"] == "skipped"
        assert "Not a Wellfound" in result["error"]


class TestGreenhouseApply:
    def test_skip_no_url(self):
        result = apply_greenhouse("", JOB)
        assert result["status"] == "skipped"

    def test_skip_non_greenhouse(self):
        result = apply_greenhouse("https://example.com/job", JOB)
        assert result["status"] == "skipped"
        assert "Not a Greenhouse" in result["error"]

    def test_accepts_grnh_se(self):
        """grnh.se URLs should be accepted as Greenhouse."""
        # This would fail with PlaywrightRunner but validates the URL check passes
        result = apply_greenhouse("https://grnh.se/abc123", JOB)
        # Should not be skipped — would fail at Playwright level
        assert result["status"] != "skipped" or "Not a Greenhouse" not in (result.get("error") or "")


class TestLeverApply:
    def test_skip_no_url(self):
        result = apply_lever("", JOB)
        assert result["status"] == "skipped"

    def test_skip_non_lever(self):
        result = apply_lever("https://example.com/job", JOB)
        assert result["status"] == "skipped"
        assert "Not a Lever" in result["error"]


class TestWorkdayApply:
    def test_skip_no_url(self):
        result = apply_workday("", JOB)
        assert result["status"] == "skipped"

    def test_skip_non_workday(self):
        result = apply_workday("https://example.com/job", JOB)
        assert result["status"] == "skipped"
        assert "Not a Workday" in result["error"]
