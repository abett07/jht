"""Tests for the auto_apply.profile module."""
import os
import json
import tempfile
import pytest

# Patch env vars before importing profile module
os.environ.setdefault("APPLICANT_FIRST_NAME", "Jane")
os.environ.setdefault("APPLICANT_LAST_NAME", "Doe")
os.environ.setdefault("APPLICANT_EMAIL", "jane@example.com")
os.environ.setdefault("APPLICANT_PHONE", "555-1234")
os.environ.setdefault("APPLICANT_LINKEDIN_URL", "https://linkedin.com/in/janedoe")
os.environ.setdefault("APPLICANT_GITHUB_URL", "https://github.com/janedoe")
os.environ.setdefault("APPLICANT_CITY", "Austin")
os.environ.setdefault("APPLICANT_STATE", "TX")

from backend.app.auto_apply.profile import (
    get_profile,
    get_full_name,
    reset_profile,
    _load_from_env,
    _load_from_file,
    EEO_ANSWERS,
)


class TestLoadFromEnv:
    """Test _load_from_env populates all expected fields."""

    def test_basic_fields(self):
        data = _load_from_env()
        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Doe"
        assert data["email"] == "jane@example.com"
        assert data["phone"] == "555-1234"

    def test_linkedin_url_env_key(self):
        """Verify that the correct env var is used (APPLICANT_LINKEDIN_URL, not APPLICANT_LINKEDIN)."""
        data = _load_from_env()
        assert data["linkedin_url"] == "https://linkedin.com/in/janedoe"

    def test_github_url_env_key(self):
        data = _load_from_env()
        assert data["github_url"] == "https://github.com/janedoe"

    def test_address_nested_structure(self):
        data = _load_from_env()
        assert isinstance(data["address"], dict)
        assert data["address"]["city"] == "Austin"
        assert data["address"]["state"] == "TX"
        assert data["address"]["country"] == "United States"  # default


class TestGetProfile:
    """Test profile caching and merging logic."""

    def setup_method(self):
        reset_profile()

    def test_singleton_caching(self):
        p1 = get_profile()
        p2 = get_profile()
        assert p1 is p2

    def test_reset_clears_cache(self):
        p1 = get_profile()
        reset_profile()
        p2 = get_profile()
        assert p1 is not p2

    def test_file_overrides_env(self):
        reset_profile()
        profile_data = {"first_name": "Override", "phone": "999-9999"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(profile_data, f)
            f.flush()
            os.environ["APPLICANT_PROFILE_PATH"] = f.name
            try:
                reset_profile()
                p = get_profile()
                assert p["first_name"] == "Override"
                assert p["phone"] == "999-9999"
                assert p["last_name"] == "Doe"  # env default preserved
            finally:
                os.environ.pop("APPLICANT_PROFILE_PATH", None)
                os.unlink(f.name)
                reset_profile()

    def test_nested_dict_merging(self):
        reset_profile()
        profile_data = {"address": {"city": "NYC"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(profile_data, f)
            f.flush()
            os.environ["APPLICANT_PROFILE_PATH"] = f.name
            try:
                reset_profile()
                p = get_profile()
                assert p["address"]["city"] == "NYC"
                assert p["address"]["state"] == "TX"  # env default preserved
            finally:
                os.environ.pop("APPLICANT_PROFILE_PATH", None)
                os.unlink(f.name)
                reset_profile()


class TestGetFullName:
    def setup_method(self):
        reset_profile()

    def test_full_name(self):
        name = get_full_name()
        assert name == "Jane Doe"


class TestEEOAnswers:
    def test_structure(self):
        assert "gender" in EEO_ANSWERS
        assert "veteran" in EEO_ANSWERS
        assert "disability" in EEO_ANSWERS

    def test_gender_keys(self):
        assert "male" in EEO_ANSWERS["gender"]
        assert "female" in EEO_ANSWERS["gender"]
