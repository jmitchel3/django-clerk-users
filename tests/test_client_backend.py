"""
Tests for explicit Clerk client backend selection.

The central property under test is that the backend is chosen by setting and
*never* by what happens to be importable. ``get_clerk_client`` is public API,
so implicit selection would make response models, error types, retries, and
available methods depend on which packages a deployment happened to pull in,
and would silently restore the SDK's ``cryptography`` ceiling for anyone who
acquired ``clerk-backend-api`` transitively.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from django_clerk_users.client import (
    DEFAULT_CLERK_CLIENT_BACKEND,
    get_clerk_client,
    get_clerk_client_backend,
)
from django_clerk_users.clerk_api import ClerkClient
from django_clerk_users.exceptions import ClerkConfigurationError

SECRET = "sk_test_unit_backend_secret"


@pytest.fixture(autouse=True)
def _clear_client_cache():
    get_clerk_client.cache_clear()
    yield
    get_clerk_client.cache_clear()


class TestBackendResolution:
    def test_defaults_to_the_thin_client(self):
        assert DEFAULT_CLERK_CLIENT_BACKEND == "thin"

    def test_unset_setting_resolves_to_thin(self):
        assert get_clerk_client_backend() == "thin"

    @pytest.mark.parametrize("value", ["sdk", "SDK", " sdk ", "Sdk"])
    def test_sdk_selection_is_case_and_whitespace_tolerant(self, value):
        with override_settings(CLERK_CLIENT_BACKEND=value):
            assert get_clerk_client_backend() == "sdk"

    def test_unknown_backend_is_rejected(self):
        with override_settings(CLERK_CLIENT_BACKEND="official"):
            with pytest.raises(ClerkConfigurationError, match="CLERK_CLIENT_BACKEND"):
                get_clerk_client_backend()

    def test_empty_backend_falls_back_to_default(self):
        with override_settings(CLERK_CLIENT_BACKEND=""):
            assert get_clerk_client_backend() == "thin"


class TestClientConstruction:
    def test_default_returns_the_thin_client(self):
        with override_settings(CLERK_SECRET_KEY=SECRET):
            assert isinstance(get_clerk_client(), ClerkClient)

    def test_thin_client_needs_no_sdk_import(self, monkeypatch):
        """The default path must not touch clerk_backend_api at all."""
        import builtins

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.startswith("clerk_backend_api"):
                raise AssertionError(
                    "the thin backend must not import clerk_backend_api"
                )
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked)

        with override_settings(CLERK_SECRET_KEY=SECRET):
            assert isinstance(get_clerk_client(), ClerkClient)

    def test_sdk_backend_returns_the_sdk_client(self):
        clerk_backend_api = pytest.importorskip("clerk_backend_api")

        with override_settings(CLERK_SECRET_KEY=SECRET, CLERK_CLIENT_BACKEND="sdk"):
            assert isinstance(get_clerk_client(), clerk_backend_api.Clerk)

    def test_installed_sdk_does_not_change_the_default(self):
        """The property the request is really about.

        clerk-backend-api is installed in the dev environment. That must not be
        enough to change which client you get.
        """
        pytest.importorskip("clerk_backend_api")

        with override_settings(CLERK_SECRET_KEY=SECRET):
            assert isinstance(get_clerk_client(), ClerkClient)

    def test_missing_secret_key_still_raises_for_the_thin_backend(self):
        with override_settings(CLERK_SECRET_KEY="sk_test_mock_secret_key"):
            with pytest.raises(ClerkConfigurationError, match="CLERK_SECRET_KEY"):
                get_clerk_client()

    def test_unknown_backend_raises_from_get_clerk_client(self):
        with override_settings(CLERK_SECRET_KEY=SECRET, CLERK_CLIENT_BACKEND="nope"):
            with pytest.raises(ClerkConfigurationError, match="CLERK_CLIENT_BACKEND"):
                get_clerk_client()

    def test_get_clerk_sdk_alias_follows_the_same_selection(self):
        from django_clerk_users.client import get_clerk_sdk

        with override_settings(CLERK_SECRET_KEY=SECRET):
            assert isinstance(get_clerk_sdk(), ClerkClient)


class TestPackagingContract:
    def test_sdk_is_not_a_runtime_dependency(self):
        """A base install must not pull in clerk-backend-api."""
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        runtime = data["project"]["dependencies"]

        assert not [d for d in runtime if d.startswith("clerk-backend-api")]

    def test_sdk_extra_declares_the_sdk(self):
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        extra = data["project"]["optional-dependencies"]["sdk"]

        assert any(d.startswith("clerk-backend-api") for d in extra)

    def test_no_runtime_dependency_caps_cryptography(self):
        """The whole point: a default install has no cryptography ceiling."""
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        crypto = [
            d for d in data["project"]["dependencies"] if d.startswith("cryptography")
        ]

        assert crypto == ["cryptography>=45"]

    def test_notice_records_the_ported_upstream_version(self):
        from pathlib import Path

        notice = (Path(__file__).resolve().parents[1] / "NOTICE").read_text()

        assert "clerk-backend-api" in notice
        assert "6.0.1" in notice
        assert "MIT" in notice
