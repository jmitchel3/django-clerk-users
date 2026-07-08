"""
Validate built distribution artifacts for the current project version.
"""

from __future__ import annotations

import os
import tarfile
import tomllib
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _project_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text())
    return data["project"]["version"]


def _check_release_tag(version: str) -> None:
    ref_type = os.environ.get("GITHUB_REF_TYPE")
    ref_name = os.environ.get("GITHUB_REF_NAME")
    if ref_type != "tag" or not ref_name:
        return

    expected_tag = f"v{version}"
    if ref_name != expected_tag:
        raise AssertionError(
            f"Release tag {ref_name!r} does not match project version {version!r}; "
            f"expected {expected_tag!r}."
        )


def _assert_entries(entries: set[str], required: set[str], artifact: Path) -> None:
    missing = sorted(required - entries)
    if missing:
        joined = "\n  - ".join(missing)
        raise AssertionError(f"{artifact.name} is missing:\n  - {joined}")


def _assert_no_forbidden_entries(entries: set[str], artifact: Path) -> None:
    forbidden_suffixes = (
        ".pyc",
        ".pyo",
        ".sqlite",
        ".sqlite3",
        ".db",
        ".log",
    )
    forbidden_parts = (
        "/__pycache__/",
        "/.pytest_cache/",
        "/.ruff_cache/",
        "/.tox/",
        "/htmlcov/",
    )
    forbidden_names = {".DS_Store", ".coverage"}

    forbidden = sorted(
        entry
        for entry in entries
        if entry.endswith(forbidden_suffixes)
        or any(part in f"/{entry}/" for part in forbidden_parts)
        or Path(entry).name in forbidden_names
        or Path(entry).name.startswith(".coverage.")
    )
    if forbidden:
        joined = "\n  - ".join(forbidden)
        raise AssertionError(f"{artifact.name} includes forbidden files:\n  - {joined}")


def _check_wheel(version: str) -> None:
    wheel = DIST_DIR / f"django_clerk_users-{version}-py3-none-any.whl"
    if not wheel.exists():
        raise AssertionError(f"Missing wheel: {wheel}")

    dist_info = f"django_clerk_users-{version}.dist-info"
    required_entries = {
        "django_clerk_users/__init__.py",
        "django_clerk_users/admin.py",
        "django_clerk_users/apps.py",
        "django_clerk_users/checks.py",
        "django_clerk_users/models.py",
        "django_clerk_users/py.typed",
        "django_clerk_users/server_api.py",
        "django_clerk_users/authentication/drf.py",
        "django_clerk_users/management/commands/sync_clerk_users.py",
        "django_clerk_users/migrations/0001_initial.py",
        "django_clerk_users/migrations/0005_remove_clerkuser_django_cler_clerk_i_d591b6_idx_and_more.py",
        "django_clerk_users/organizations/admin.py",
        "django_clerk_users/organizations/webhooks.py",
        "django_clerk_users/organizations/migrations/0001_initial.py",
        "django_clerk_users/organizations/migrations/0002_remove_organization_clerk_organ_clerk_i_b2b811_idx_and_more.py",
        f"{dist_info}/METADATA",
        f"{dist_info}/WHEEL",
        f"{dist_info}/RECORD",
    }

    with zipfile.ZipFile(wheel) as archive:
        entries = set(archive.namelist())
        _assert_entries(entries, required_entries, wheel)
        _assert_no_forbidden_entries(entries, wheel)

        metadata = archive.read(f"{dist_info}/METADATA").decode()
        expected_metadata = {
            "Name: django-clerk-users",
            f"Version: {version}",
            "Author: Justin Mitchel",
            "Keywords: authentication,clerk,django,jwt,webhooks",
            "Requires-Python: >=3.12",
            "License-Expression: MIT",
            "Project-URL: Changelog, https://github.com/jmitchel3/django-clerk-users/blob/main/CHANGELOG.md",
            "Project-URL: Issues, https://github.com/jmitchel3/django-clerk-users/issues",
            "Project-URL: Repository, https://github.com/jmitchel3/django-clerk-users",
            "Classifier: Development Status :: 5 - Production/Stable",
            "Classifier: Framework :: Django :: 4.2",
            "Classifier: Framework :: Django :: 5.2",
            "Classifier: Framework :: Django :: 6.0",
            "Requires-Dist: clerk-backend-api>=1",
            "Requires-Dist: django<7.0,>=4.2",
            "Requires-Dist: svix>=1",
            "Provides-Extra: drf",
            "Requires-Dist: djangorestframework>=3.14; extra == 'drf'",
        }
        missing_metadata = sorted(
            item for item in expected_metadata if item not in metadata
        )
        if missing_metadata:
            joined = "\n  - ".join(missing_metadata)
            raise AssertionError(f"{wheel.name} metadata is missing:\n  - {joined}")

        test_entries = sorted(entry for entry in entries if entry.startswith("tests/"))
        if test_entries:
            raise AssertionError(f"{wheel.name} unexpectedly includes tests/")


def _check_sdist(version: str) -> None:
    sdist = DIST_DIR / f"django_clerk_users-{version}.tar.gz"
    if not sdist.exists():
        raise AssertionError(f"Missing sdist: {sdist}")

    prefix = f"django_clerk_users-{version}/"
    required_entries = {
        f"{prefix}.env.example",
        f"{prefix}CHANGELOG.md",
        f"{prefix}LICENSE",
        f"{prefix}README.md",
        f"{prefix}pyproject.toml",
        f"{prefix}scripts/check_dist.py",
        f"{prefix}scripts/live_clerk_smoke.py",
        f"{prefix}scripts/smoke_installed_wheel.py",
        f"{prefix}src/django_clerk_users/__init__.py",
        f"{prefix}src/django_clerk_users/checks.py",
        f"{prefix}src/django_clerk_users/migrations/0005_remove_clerkuser_django_cler_clerk_i_d591b6_idx_and_more.py",
        f"{prefix}src/django_clerk_users/organizations/migrations/0002_remove_organization_clerk_organ_clerk_i_b2b811_idx_and_more.py",
        f"{prefix}src/django_clerk_users/organizations/webhooks.py",
        f"{prefix}src/django_clerk_users/py.typed",
        f"{prefix}tests/test_checks.py",
        f"{prefix}tests/test_admin.py",
        f"{prefix}tests/test_live_clerk_smoke.py",
        f"{prefix}tests/test_migrations.py",
        f"{prefix}tests/test_organization_webhooks.py",
        f"{prefix}tests/test_release_scripts.py",
    }

    with tarfile.open(sdist) as archive:
        entries = set(archive.getnames())
        _assert_entries(entries, required_entries, sdist)
        _assert_no_forbidden_entries(entries, sdist)


def main() -> int:
    version = _project_version()
    _check_release_tag(version)
    _check_wheel(version)
    _check_sdist(version)
    print(f"Distribution artifacts validated for django-clerk-users {version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
