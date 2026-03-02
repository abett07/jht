"""Tests for the auto_apply.engine module — board/ATS detection and routing."""
import os
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("APPLICANT_FIRST_NAME", "Jane")
os.environ.setdefault("APPLICANT_LAST_NAME", "Doe")
os.environ.setdefault("APPLICANT_EMAIL", "jane@example.com")

from backend.app.auto_apply.engine import (
    _detect_board,
    _detect_ats_route,
    apply_to_job,
    batch_apply,
)
from backend.app.auto_apply.profile import reset_profile


class TestDetectBoard:
    """Test _detect_board — URL → board detection."""

    def test_linkedin(self):
        result = _detect_board("https://www.linkedin.com/jobs/view/123")
        assert result is not None
        assert result[0] == "linkedin"

    def test_indeed(self):
        result = _detect_board("https://www.indeed.com/viewjob?jk=abc")
        assert result is not None
        assert result[0] == "indeed"

    def test_dice(self):
        result = _detect_board("https://www.dice.com/job-detail/123")
        assert result is not None
        assert result[0] == "dice"

    def test_ziprecruiter(self):
        result = _detect_board("https://www.ziprecruiter.com/c/Company/Job/Title/-in-City,ST")
        assert result is not None
        assert result[0] == "ziprecruiter"

    def test_builtin(self):
        result = _detect_board("https://builtin.com/job/software-engineer")
        assert result is not None
        assert result[0] == "builtin"

    def test_wellfound(self):
        result = _detect_board("https://wellfound.com/jobs")
        assert result is not None
        assert result[0] == "wellfound"

    def test_unknown_url(self):
        assert _detect_board("https://example.com/jobs") is None

    def test_none_url(self):
        assert _detect_board(None) is None

    def test_empty_url(self):
        assert _detect_board("") is None


class TestDetectATSRoute:
    """Test _detect_ats_route — URL → ATS detection."""

    def test_greenhouse(self):
        result = _detect_ats_route("https://boards.greenhouse.io/company/jobs/123")
        assert result is not None
        assert result[0] == "greenhouse"

    def test_greenhouse_short_url(self):
        result = _detect_ats_route("https://grnh.se/abc123")
        assert result is not None
        assert result[0] == "greenhouse"

    def test_lever(self):
        result = _detect_ats_route("https://jobs.lever.co/company/id")
        assert result is not None
        assert result[0] == "lever"

    def test_workday(self):
        result = _detect_ats_route("https://company.wd5.myworkdayjobs.com/jobs")
        assert result is not None
        assert result[0] == "workday"

    def test_unknown_ats(self):
        assert _detect_ats_route("https://icims.com/jobs/123") is None

    def test_none(self):
        assert _detect_ats_route(None) is None


class TestApplyToJob:
    """Test apply_to_job — routing and error handling."""

    def setup_method(self):
        reset_profile()

    def test_no_url(self):
        result = apply_to_job({"title": "Dev", "company": "Co"})
        assert result["status"] == "skipped"
        assert result["error"] == "No job URL available"

    def test_incomplete_profile(self):
        with patch.dict(os.environ, {"APPLICANT_FIRST_NAME": "", "APPLICANT_EMAIL": ""}):
            reset_profile()
            result = apply_to_job({"url": "https://example.com", "title": "Dev", "company": "Co"})
            assert result["status"] == "failed"
            assert "profile incomplete" in result["error"].lower()
            # Restore
            os.environ["APPLICANT_FIRST_NAME"] = "Jane"
            os.environ["APPLICANT_EMAIL"] = "jane@example.com"
            reset_profile()

    def test_dry_run_linkedin(self):
        result = apply_to_job(
            {"url": "https://www.linkedin.com/jobs/view/123", "title": "Dev", "company": "Co"},
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert result["method"] == "linkedin"

    def test_dry_run_greenhouse(self):
        result = apply_to_job(
            {"url": "https://boards.greenhouse.io/co/jobs/123", "title": "Dev", "company": "Co"},
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert result["method"] == "greenhouse"
        assert result["ats_detected"] == "greenhouse"

    def test_dry_run_generic(self):
        result = apply_to_job(
            {"url": "https://example.com/apply", "title": "Dev", "company": "Co"},
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert result["method"] == "generic"

    def test_dry_run_lever(self):
        result = apply_to_job(
            {"url": "https://jobs.lever.co/company/id", "title": "Dev", "company": "Co"},
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert result["method"] == "lever"

    def test_dry_run_workday(self):
        result = apply_to_job(
            {"url": "https://company.wd5.myworkdayjobs.com/External/job/Title/123", "title": "Dev", "company": "Co"},
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert result["method"] == "workday"

    def test_result_structure(self):
        result = apply_to_job(
            {"url": "https://example.com", "title": "Dev", "company": "Co"},
            dry_run=True,
        )
        assert "status" in result
        assert "method" in result
        assert "ats_detected" in result
        assert "error" in result
        assert "applied_at" in result


class TestBatchApply:
    """Test batch_apply — batch processing and rate limiting."""

    def test_empty_list(self):
        results = batch_apply([], dry_run=True)
        assert results == []

    def test_dry_run_batch(self):
        jobs = [
            {"url": "https://www.linkedin.com/jobs/view/1", "title": "Dev 1", "company": "Co1"},
            {"url": "https://boards.greenhouse.io/co/jobs/2", "title": "Dev 2", "company": "Co2"},
            {"url": "https://example.com/apply", "title": "Dev 3", "company": "Co3"},
        ]
        results = batch_apply(jobs, dry_run=True)
        assert len(results) == 3
        assert results[0]["method"] == "linkedin"
        assert results[1]["method"] == "greenhouse"
        assert results[2]["method"] == "generic"

    def test_max_per_run_limit(self):
        # All dry_run should pass, but we limit to 1
        # In dry_run mode, status is "dry_run" not "submitted", so limit doesn't apply
        # Let's test that all are processed in dry_run mode
        jobs = [
            {"url": f"https://example.com/job/{i}", "title": f"Dev {i}", "company": f"Co{i}"}
            for i in range(5)
        ]
        results = batch_apply(jobs, dry_run=True, max_per_run=2)
        assert len(results) == 5  # dry_run doesn't count toward limit

    def test_result_includes_job_info(self):
        jobs = [{"url": "https://example.com/job/1", "title": "SWE", "company": "ACME"}]
        results = batch_apply(jobs, dry_run=True)
        assert results[0]["job_title"] == "SWE"
        assert results[0]["job_company"] == "ACME"
