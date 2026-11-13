"""
Executable checks for docs/recipes/hybrid-auth.md.

The authenticators under test are loaded from
docs/recipes/hybrid_auth_authentication.py, the same file the recipe tells
readers to copy, so the documentation cannot drift from what is tested.
"""

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("rest_framework")

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.cache import cache  # noqa: E402
from django.http import HttpResponse  # noqa: E402
from django.urls import path  # noqa: E402
from django.views.decorators.csrf import ensure_csrf_cookie  # noqa: E402
from rest_framework.permissions import IsAuthenticated  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

DOCS = Path(__file__).resolve().parent.parent / "docs" / "recipes"
RECIPE_FILE = DOCS / "hybrid_auth_authentication.py"

_spec = importlib.util.spec_from_file_location("hybrid_auth_recipe", RECIPE_FILE)
recipe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recipe)

VALID_TOKEN = "valid.clerk.token"
INVALID_TOKEN = "invalid.clerk.token"
CLERK_ID = "user_recipe_bearer"


def _view(authenticator):
    class WhoAmI(APIView):
        authentication_classes = [authenticator]
        permission_classes = [IsAuthenticated]

        def get(self, request):
            return Response(self._who(request))

        def post(self, request):
            return Response(self._who(request))

        @staticmethod
        def _who(request):
            kind = "clerk" if isinstance(request.auth, dict) else "session"
            return {"email": request.user.email, "via": kind}

    return WhoAmI.as_view()


@ensure_csrf_cookie
def csrf_view(request):
    return HttpResponse("ok")


urlpatterns = [
    path("csrf/", csrf_view),
    path("strict/", _view(recipe.StrictClerkSessionAuthentication)),
    path("default/", _view(recipe.CsrfClerkSessionAuthentication)),
    path("package/", _view(recipe.ClerkSessionAuthentication)),
]

pytestmark = pytest.mark.django_db


def fake_authenticate_session_token(token, **kwargs):
    if token == VALID_TOKEN:
        return SimpleNamespace(
            is_signed_in=True, payload={"sub": CLERK_ID, "exp": 4102444800}
        )
    return SimpleNamespace(is_signed_in=False, payload=None, reason="bad token")


@pytest.fixture(autouse=True)
def clerk_configured(settings):
    cache.clear()
    settings.ROOT_URLCONF = __name__
    settings.CLERK_SECRET_KEY = "sk_test_recipe_secret"
    with patch(
        "django_clerk_users.authentication.utils.authenticate_session_token",
        side_effect=fake_authenticate_session_token,
    ):
        yield
    cache.clear()


@pytest.fixture
def bearer_user():
    return get_user_model().objects.create_user(
        clerk_id=CLERK_ID, email="bearer@example.com"
    )


@pytest.fixture
def session_user():
    return get_user_model().objects.create_user(
        email="staff@example.com", password="pw-unused"
    )


@pytest.fixture
def cookie_client(session_user):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(session_user)
    return client


def csrf_token(client):
    client.get("/csrf/")
    return client.cookies["csrftoken"].value


BOTH = pytest.mark.parametrize("url", ["/strict/", "/default/"])


@BOTH
def test_valid_bearer(url, bearer_user):
    client = APIClient(enforce_csrf_checks=True)
    response = client.post(url, HTTP_AUTHORIZATION=f"Bearer {VALID_TOKEN}")
    assert response.status_code == 200
    assert response.json() == {"email": "bearer@example.com", "via": "clerk"}


@BOTH
def test_bearer_scheme_is_case_and_whitespace_tolerant(url, bearer_user):
    response = APIClient().get(url, HTTP_AUTHORIZATION=f"  bEaReR   {VALID_TOKEN} ")
    assert response.status_code == 200


@BOTH
def test_valid_cookie_safe_method(url, cookie_client):
    response = cookie_client.get(url)
    assert response.status_code == 200
    assert response.json()["via"] == "session"


@BOTH
def test_valid_cookie_with_csrf(url, cookie_client):
    token = csrf_token(cookie_client)
    response = cookie_client.post(url, HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200
    assert response.json() == {"email": "staff@example.com", "via": "session"}


@BOTH
def test_unsafe_cookie_request_without_csrf_is_rejected(url, cookie_client):
    response = cookie_client.post(url)
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_package_default_is_csrf_exempt_for_cookies(cookie_client):
    """Why the recipe overrides session_authentication_class."""
    response = cookie_client.post("/package/")
    assert response.status_code == 200
    assert response.json()["via"] == "session"


@BOTH
def test_invalid_bearer_fails_even_with_session_cookie(url, cookie_client):
    response = cookie_client.get(url, HTTP_AUTHORIZATION=f"Bearer {INVALID_TOKEN}")
    assert response.status_code == 401


@pytest.mark.parametrize(
    "header", ["Basic dXNlcjpwYXNz", "Bearer", "Bearer    ", "Token abc"]
)
def test_strict_malformed_credentials_fail(header, cookie_client):
    response = cookie_client.get("/strict/", HTTP_AUTHORIZATION=header)
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["", " ", " \t "])
@pytest.mark.parametrize("method", ["get", "post"])
def test_strict_empty_authorization_never_uses_session(header, method, cookie_client):
    headers = {"HTTP_AUTHORIZATION": header}
    if method == "post":
        headers["HTTP_X_CSRFTOKEN"] = csrf_token(cookie_client)

    response = getattr(cookie_client, method)("/strict/", **headers)

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"


def test_default_non_bearer_scheme_falls_back_to_session(cookie_client):
    """DRF's normal multi-scheme behavior, for contrast with the strict class."""
    response = cookie_client.get("/default/", HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz")
    assert response.status_code == 200
    assert response.json()["via"] == "session"


def test_default_empty_bearer_is_anonymous_not_session(cookie_client):
    """A Bearer scheme always routes to Clerk; with no token it is anonymous."""
    response = cookie_client.get("/default/", HTTP_AUTHORIZATION="Bearer")
    assert response.status_code == 401


@pytest.mark.parametrize("secret", [None, "", "sk_test_mock_secret_key"])
def test_strict_unconfigured_clerk_fails(settings, secret, cookie_client):
    settings.CLERK_SECRET_KEY = secret
    settings.CLERK_JWT_KEY = None
    response = cookie_client.get("/strict/", HTTP_AUTHORIZATION=f"Bearer {VALID_TOKEN}")
    assert response.status_code == 401
    assert "not configured" in response.json()["detail"]


def test_default_unconfigured_clerk_falls_through(settings, bearer_user):
    """Without the strict class, a bearer request is simply unauthenticated."""
    settings.CLERK_SECRET_KEY = None
    settings.CLERK_JWT_KEY = None
    response = APIClient().get("/default/", HTTP_AUTHORIZATION=f"Bearer {VALID_TOKEN}")
    assert response.status_code == 401


def test_password_sync_setting_replaces_set_password_patch(settings, bearer_user):
    settings.CLERK_SYNC_PASSWORDS = False
    with patch("django_clerk_users.client.get_clerk_client") as get_client:
        bearer_user.set_password("local-only")
    get_client.assert_not_called()
    assert bearer_user.check_password("local-only")


def test_recipe_doc_embeds_the_tested_module():
    doc = (DOCS / "hybrid-auth.md").read_text()
    blocks = re.findall(r"```python\n(.*?)```", doc, re.S)
    assert RECIPE_FILE.read_text() in blocks
