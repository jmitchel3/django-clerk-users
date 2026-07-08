"""
Tests for the live Clerk smoke-check helper script.
"""

from __future__ import annotations

import base64
import importlib.metadata
import os
import sys

import pytest
from django.test import override_settings

from scripts import live_clerk_smoke


def make_svix_secret() -> str:
    """Return a valid Svix-style signing secret for local verifier tests."""
    return "whsec_" + base64.b64encode(os.urandom(32)).decode()


def test_live_clerk_smoke_reports_missing_required_env(monkeypatch, capsys):
    """Test missing live credentials are reported clearly when skips are allowed."""
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    monkeypatch.delenv("CLERK_WEBHOOK_SIGNING_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["live_clerk_smoke.py", "--allow-missing-env"],
    )

    assert live_clerk_smoke.main() == 0

    output = capsys.readouterr().out
    assert "CLERK_SECRET_KEY must be a real Clerk secret key" in output
    assert "CLERK_WEBHOOK_SIGNING_KEY must be a real Svix signing secret" in output


def test_live_clerk_smoke_accepts_realistic_secret_shapes(monkeypatch):
    """Test configured live-looking secrets pass preflight validation."""
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_live_smoke_example")
    monkeypatch.setenv("CLERK_WEBHOOK_SIGNING_KEY", make_svix_secret())

    assert live_clerk_smoke._missing_reasons() == []


def test_live_clerk_smoke_trims_secret_env_values(monkeypatch):
    """Test whitespace around environment-provided secrets does not fail preflight."""
    monkeypatch.setenv("CLERK_SECRET_KEY", "  sk_test_live_smoke_example  ")
    monkeypatch.setenv("CLERK_WEBHOOK_SIGNING_KEY", f"  {make_svix_secret()}  ")

    assert live_clerk_smoke._missing_reasons() == []


def test_live_clerk_smoke_rejects_trimmed_placeholder_env_values(monkeypatch):
    """Test whitespace-wrapped placeholders are still rejected."""
    monkeypatch.setenv("CLERK_SECRET_KEY", "  sk_test_mock_secret_key  ")
    monkeypatch.setenv("CLERK_WEBHOOK_SIGNING_KEY", "  whsec_replace_me  ")

    reasons = live_clerk_smoke._missing_reasons()

    assert "CLERK_SECRET_KEY must be a real Clerk secret key" in reasons
    assert "CLERK_WEBHOOK_SIGNING_KEY must be a real Svix signing secret" in reasons


def test_live_clerk_smoke_env_int_falls_back_for_bad_values(monkeypatch):
    """Test invalid timeout env vars use the safe default."""
    monkeypatch.setenv("CLERK_API_TIMEOUT_MS", "not-an-int")

    assert live_clerk_smoke._env_int("CLERK_API_TIMEOUT_MS", 10000) == 10000


def test_live_clerk_smoke_configures_trimmed_secret_settings(monkeypatch):
    """Test Django configuration receives normalized secret env values."""
    monkeypatch.setenv("CLERK_SECRET_KEY", "  sk_test_live_smoke_example  ")
    monkeypatch.setenv("CLERK_WEBHOOK_SIGNING_KEY", f"  {make_svix_secret()}  ")

    kwargs = live_clerk_smoke._django_settings_kwargs()

    assert kwargs["CLERK_SECRET_KEY"] == "sk_test_live_smoke_example"
    assert kwargs["CLERK_WEBHOOK_SIGNING_KEY"].startswith("whsec_")
    assert not kwargs["CLERK_WEBHOOK_SIGNING_KEY"].startswith(" ")


def test_live_clerk_smoke_rejects_checkout_source_import(monkeypatch):
    """Test release smoke refuses to validate the checkout source tree."""
    import django_clerk_users

    monkeypatch.setattr(live_clerk_smoke, "_project_version", lambda: "1.2.3")
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "1.2.3")
    monkeypatch.setattr(
        django_clerk_users,
        "__file__",
        str(live_clerk_smoke.SRC_ROOT / "django_clerk_users" / "__init__.py"),
    )

    with pytest.raises(AssertionError, match="checkout source tree"):
        live_clerk_smoke._verify_installed_distribution()


def test_live_clerk_smoke_accepts_installed_distribution_import(monkeypatch, tmp_path):
    """Test release smoke accepts package imports outside the checkout src tree."""
    import django_clerk_users

    installed_file = tmp_path / "site-packages" / "django_clerk_users" / "__init__.py"
    installed_file.parent.mkdir(parents=True)
    installed_file.write_text("")

    monkeypatch.setattr(live_clerk_smoke, "_project_version", lambda: "1.2.3")
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "1.2.3")
    monkeypatch.setattr(django_clerk_users, "__file__", str(installed_file))

    live_clerk_smoke._verify_installed_distribution()


def test_live_clerk_smoke_verifies_signed_webhook(monkeypatch):
    """Test the smoke script signs and verifies payloads through package code."""
    secret = make_svix_secret()
    monkeypatch.setenv("CLERK_WEBHOOK_SIGNING_KEY", f"  {secret}  ")

    with override_settings(CLERK_WEBHOOK_SIGNING_KEY=secret):
        live_clerk_smoke._verify_signed_webhook()
