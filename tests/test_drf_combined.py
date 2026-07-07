"""
Tests for optional DRF combined authentication helpers.

These tests do not require djangorestframework to be installed. They patch the
lazy DRF availability flag and use fake authentication classes so the routing
behavior stays covered in the base test environment.
"""

import pytest
from django.test import RequestFactory

from django_clerk_users.authentication import (
    ClerkSessionAuthentication,
    CsrfExemptSessionAuthentication,
)
from django_clerk_users.authentication import drf


def test_combined_auth_imports_without_drf():
    """Combined auth classes should be importable without DRF installed."""
    assert ClerkSessionAuthentication is drf.ClerkSessionAuthentication
    assert CsrfExemptSessionAuthentication is drf.CsrfExemptSessionAuthentication


def test_combined_auth_routes_bearer_token_to_clerk(monkeypatch):
    calls = []

    class FakeClerkAuthentication:
        def authenticate(self, request):
            calls.append("clerk")
            return ("clerk-user", {"sub": "user_123"})

    class FakeSessionAuthentication:
        def authenticate(self, request):
            calls.append("session")
            return ("session-user", None)

    monkeypatch.setattr(drf, "_drf_available", True)
    monkeypatch.setattr(
        drf.ClerkSessionAuthentication,
        "clerk_authentication_class",
        FakeClerkAuthentication,
    )
    monkeypatch.setattr(
        drf.ClerkSessionAuthentication,
        "session_authentication_class",
        FakeSessionAuthentication,
    )

    auth = drf.ClerkSessionAuthentication()
    request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer token")

    assert auth.authenticate(request) == ("clerk-user", {"sub": "user_123"})
    assert calls == ["clerk"]


def test_combined_auth_routes_missing_bearer_token_to_session(monkeypatch):
    calls = []

    class FakeClerkAuthentication:
        def authenticate(self, request):
            calls.append("clerk")
            return ("clerk-user", {"sub": "user_123"})

    class FakeSessionAuthentication:
        def authenticate(self, request):
            calls.append("session")
            return ("session-user", None)

    monkeypatch.setattr(drf, "_drf_available", True)
    monkeypatch.setattr(
        drf.ClerkSessionAuthentication,
        "clerk_authentication_class",
        FakeClerkAuthentication,
    )
    monkeypatch.setattr(
        drf.ClerkSessionAuthentication,
        "session_authentication_class",
        FakeSessionAuthentication,
    )

    auth = drf.ClerkSessionAuthentication()
    request = RequestFactory().get("/")

    assert auth.authenticate(request) == ("session-user", None)
    assert calls == ["session"]


def test_combined_auth_does_not_hide_bearer_token_errors(monkeypatch):
    calls = []

    class FakeClerkAuthentication:
        def authenticate(self, request):
            calls.append("clerk")
            raise RuntimeError("invalid token")

    class FakeSessionAuthentication:
        def authenticate(self, request):
            calls.append("session")
            return ("session-user", None)

    monkeypatch.setattr(drf, "_drf_available", True)
    monkeypatch.setattr(
        drf.ClerkSessionAuthentication,
        "clerk_authentication_class",
        FakeClerkAuthentication,
    )
    monkeypatch.setattr(
        drf.ClerkSessionAuthentication,
        "session_authentication_class",
        FakeSessionAuthentication,
    )

    auth = drf.ClerkSessionAuthentication()
    request = RequestFactory().get("/", HTTP_AUTHORIZATION="Bearer bad-token")

    with pytest.raises(RuntimeError, match="invalid token"):
        auth.authenticate(request)

    assert calls == ["clerk"]


def test_csrf_exempt_session_authentication_skips_csrf(monkeypatch):
    monkeypatch.setattr(drf, "_drf_available", True)

    auth = drf.CsrfExemptSessionAuthentication()

    assert auth.enforce_csrf(RequestFactory().get("/")) is None
