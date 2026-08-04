"""
Tests for optional DRF combined authentication helpers.

These tests do not require djangorestframework to be installed. They patch the
lazy DRF availability flag and use fake authentication classes so the routing
behavior stays covered in the base test environment.
"""

import runpy
import sys
from types import ModuleType, SimpleNamespace

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


def test_combined_auth_routes_bearer_with_nonstandard_spacing_to_clerk(monkeypatch):
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
    request = RequestFactory().get("/", HTTP_AUTHORIZATION="bearer\ttoken")

    assert auth.authenticate(request) == ("clerk-user", {"sub": "user_123"})
    assert calls == ["clerk"]


def test_combined_auth_routes_bearer_bytes_header_to_clerk(monkeypatch):
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
    request.META["HTTP_AUTHORIZATION"] = b"Bearer token"

    assert auth.authenticate(request) == ("clerk-user", {"sub": "user_123"})
    assert calls == ["clerk"]


def test_combined_auth_routes_non_bearer_authorization_to_session(monkeypatch):
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
    request = RequestFactory().get("/", HTTP_AUTHORIZATION="Basic token")

    assert auth.authenticate(request) == ("session-user", None)
    assert calls == ["session"]


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


class AuthenticationFailed(Exception):
    """Small stand-in for DRF's exception in the dependency-light test env."""


@pytest.fixture
def drf_enabled(monkeypatch):
    monkeypatch.setattr(drf, "_drf_available", True)
    monkeypatch.setattr(
        drf,
        "exceptions",
        SimpleNamespace(AuthenticationFailed=AuthenticationFailed),
    )


def test_module_imports_real_base_classes_when_drf_is_available(monkeypatch):
    fake_rest_framework = ModuleType("rest_framework")
    fake_authentication = SimpleNamespace(
        BaseAuthentication=type("BaseAuthentication", (), {}),
        SessionAuthentication=type("SessionAuthentication", (), {}),
    )
    fake_exceptions = SimpleNamespace(AuthenticationFailed=AuthenticationFailed)
    fake_rest_framework.authentication = fake_authentication
    fake_rest_framework.exceptions = fake_exceptions
    monkeypatch.setitem(sys.modules, "rest_framework", fake_rest_framework)

    namespace = runpy.run_path(
        drf.__file__, run_name="django_clerk_users.authentication._drf_available_test"
    )

    assert namespace["_drf_available"] is True
    assert namespace["_BaseAuthentication"] is fake_authentication.BaseAuthentication
    assert (
        namespace["_SessionAuthentication"] is fake_authentication.SessionAuthentication
    )


@pytest.mark.parametrize(
    "authentication_class",
    [
        drf.ClerkAuthentication,
        drf.CsrfExemptSessionAuthentication,
        drf.ClerkSessionAuthentication,
    ],
)
def test_authentication_classes_explain_missing_optional_dependency(
    monkeypatch, authentication_class
):
    monkeypatch.setattr(drf, "_drf_available", False)
    monkeypatch.setattr(
        drf,
        "_drf_import_error",
        "Django REST Framework is required for ClerkAuthentication.",
    )

    with pytest.raises(ImportError, match="Django REST Framework is required"):
        authentication_class()


def test_clerk_authentication_returns_none_without_credentials(
    monkeypatch, drf_enabled
):
    monkeypatch.setattr(drf, "get_clerk_payload_from_request", lambda request: None)

    assert drf.ClerkAuthentication().authenticate(SimpleNamespace()) is None


def test_clerk_authentication_translates_token_errors(monkeypatch, drf_enabled):
    def invalid_token(request):
        from django_clerk_users.exceptions import ClerkTokenError

        raise ClerkTokenError("expired")

    monkeypatch.setattr(drf, "get_clerk_payload_from_request", invalid_token)

    with pytest.raises(AuthenticationFailed, match="expired"):
        drf.ClerkAuthentication().authenticate(SimpleNamespace())


def test_clerk_authentication_translates_user_sync_errors(monkeypatch, drf_enabled):
    from django_clerk_users.exceptions import ClerkAuthenticationError

    monkeypatch.setattr(
        drf, "get_clerk_payload_from_request", lambda request: {"sub": "user_123"}
    )

    def failed_sync(payload):
        raise ClerkAuthenticationError("sync failed")

    monkeypatch.setattr(drf, "get_or_create_user_from_payload", failed_sync)

    with pytest.raises(AuthenticationFailed, match="sync failed"):
        drf.ClerkAuthentication().authenticate(SimpleNamespace())


def test_clerk_authentication_rejects_inactive_users(monkeypatch, drf_enabled):
    monkeypatch.setattr(
        drf, "get_clerk_payload_from_request", lambda request: {"sub": "user_123"}
    )
    monkeypatch.setattr(
        drf,
        "get_or_create_user_from_payload",
        lambda payload: (SimpleNamespace(is_active=False), False),
    )

    with pytest.raises(AuthenticationFailed, match="inactive"):
        drf.ClerkAuthentication().authenticate(SimpleNamespace())


def test_clerk_authentication_attaches_payload_to_wrapped_request(
    monkeypatch, drf_enabled
):
    payload = {"sub": "user_123", "org_id": "org_123"}
    user = SimpleNamespace(is_active=True)
    underlying = SimpleNamespace()
    request = SimpleNamespace(_request=underlying)
    monkeypatch.setattr(drf, "get_clerk_payload_from_request", lambda request: payload)
    monkeypatch.setattr(
        drf, "get_or_create_user_from_payload", lambda payload: (user, False)
    )

    assert drf.ClerkAuthentication().authenticate(request) == (user, payload)
    assert request.clerk_payload == payload
    assert request.org == "org_123"
    assert underlying.org == "org_123"


def test_clerk_authentication_does_not_rewrite_same_underlying_request(
    monkeypatch, drf_enabled
):
    payload = {"sub": "user_123"}
    user = SimpleNamespace(is_active=True)
    request = SimpleNamespace()
    request._request = request
    monkeypatch.setattr(drf, "get_clerk_payload_from_request", lambda request: payload)
    monkeypatch.setattr(
        drf, "get_or_create_user_from_payload", lambda payload: (user, False)
    )

    assert drf.ClerkAuthentication().authenticate(request) == (user, payload)
    assert request.org is None


def test_drf_authentication_headers_advertise_bearer(monkeypatch, drf_enabled):
    class FakeClerkAuthentication:
        pass

    class FakeSessionAuthentication:
        pass

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

    assert drf.ClerkAuthentication().authenticate_header(SimpleNamespace()) == "Bearer"
    assert (
        drf.ClerkSessionAuthentication().authenticate_header(SimpleNamespace())
        == "Bearer"
    )
