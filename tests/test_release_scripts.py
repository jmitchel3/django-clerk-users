"""
Tests for release validation helper scripts.
"""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

from scripts import check_dist, smoke_installed_wheel


def test_check_dist_accepts_matching_release_tag(monkeypatch):
    """Test release tag validation accepts v-prefixed project versions."""
    monkeypatch.setenv("GITHUB_REF_TYPE", "tag")
    monkeypatch.setenv("GITHUB_REF_NAME", "v1.2.3")

    check_dist._check_release_tag("1.2.3")


def test_check_dist_rejects_mismatched_release_tag(monkeypatch):
    """Test release tag validation fails before publishing the wrong version."""
    monkeypatch.setenv("GITHUB_REF_TYPE", "tag")
    monkeypatch.setenv("GITHUB_REF_NAME", "v1.2.4")

    with pytest.raises(AssertionError, match="does not match project version"):
        check_dist._check_release_tag("1.2.3")


def test_check_dist_ignores_non_tag_refs(monkeypatch):
    """Test local and branch builds are not forced to have a release tag."""
    monkeypatch.setenv("GITHUB_REF_TYPE", "branch")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")

    check_dist._check_release_tag("1.2.3")


def test_check_dist_rejects_forbidden_artifact_entries(tmp_path):
    """Test artifact validation rejects generated caches and local databases."""
    artifact = tmp_path / "django_clerk_users-1.2.3.tar.gz"
    entries = {
        "django_clerk_users-1.2.3/src/django_clerk_users/__init__.py",
        "django_clerk_users-1.2.3/tests/ui_test.sqlite3",
        "django_clerk_users-1.2.3/tests/__pycache__/test_models.pyc",
        "django_clerk_users-1.2.3/.coverage.py312",
    }

    with pytest.raises(AssertionError, match="includes forbidden files"):
        check_dist._assert_no_forbidden_entries(entries, artifact)


def test_check_dist_accepts_clean_artifact_entries(tmp_path):
    """Test artifact validation accepts normal package and test source files."""
    artifact = tmp_path / "django_clerk_users-1.2.3.tar.gz"
    entries = {
        "django_clerk_users-1.2.3/.env.example",
        "django_clerk_users-1.2.3/src/django_clerk_users/__init__.py",
        "django_clerk_users-1.2.3/tests/test_models.py",
    }

    check_dist._assert_no_forbidden_entries(entries, artifact)


def test_installed_wheel_smoke_rejects_checkout_source_import(monkeypatch):
    """Test wheel smoke refuses to validate the checkout source tree."""
    import django_clerk_users

    monkeypatch.setattr(smoke_installed_wheel, "_project_version", lambda: "1.2.3")
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "1.2.3")
    monkeypatch.setattr(
        django_clerk_users,
        "__file__",
        str(smoke_installed_wheel.SRC_ROOT / "django_clerk_users" / "__init__.py"),
    )

    with pytest.raises(AssertionError, match="checkout source tree"):
        smoke_installed_wheel._verify_installed_distribution()


def test_installed_wheel_smoke_accepts_installed_distribution(monkeypatch, tmp_path):
    """Test wheel smoke accepts package imports outside the checkout src tree."""
    import django_clerk_users

    installed_file = tmp_path / "site-packages" / "django_clerk_users" / "__init__.py"
    installed_file.parent.mkdir(parents=True)
    installed_file.write_text("")

    monkeypatch.setattr(smoke_installed_wheel, "_project_version", lambda: "1.2.3")
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "1.2.3")
    monkeypatch.setattr(django_clerk_users, "__file__", str(installed_file))

    assert smoke_installed_wheel._verify_installed_distribution() == "1.2.3"


def test_cryptography_requirement_stays_unbounded():
    """Test nothing re-caps cryptography, so new releases stay usable.

    This package must never be the reason a consumer is held back from a newer
    ``cryptography``. Any upper bound in effect comes from ``clerk-backend-api``,
    which we do not control; see ``scripts/check_cryptography_ceiling.py``.
    """
    pyproject = tomllib.loads(
        (Path(check_dist.__file__).resolve().parents[1] / "pyproject.toml").read_text()
    )
    declared = [
        Requirement(raw)
        for raw in pyproject["project"]["dependencies"]
        if Requirement(raw).name.lower() == "cryptography"
    ]

    assert declared, "cryptography should stay an explicit dependency"

    capping = [
        str(spec)
        for spec in declared[0].specifier
        if spec.operator in {"<", "<=", "==", "==="}
    ]
    assert not capping, f"cryptography must not be capped, found {capping}"
