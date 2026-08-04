"""
Watch the upstream ``cryptography`` ceiling imposed by ``clerk-backend-api``.

This package declares ``cryptography>=45`` with no upper bound, so it never
blocks a new ``cryptography`` release on its own. ``clerk-backend-api`` does
pin an upper bound, and that pin is what decides which ``cryptography`` a
resolver actually installs.

Run this to answer two questions:

1. Does the newest ``clerk-backend-api`` still cap ``cryptography`` below the
   newest ``cryptography`` release?
2. If it does, how far behind are we?

With ``--fail-when-lifted`` the script exits non-zero once the cap admits the
newest ``cryptography``. That is the signal to raise the ``clerk-backend-api``
floor in ``pyproject.toml`` and re-lock.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"

PYPI_URL = "https://pypi.org/pypi/{name}/json"
TIMEOUT_SECONDS = 30

TARGET = "cryptography"
GATEKEEPER = "clerk-backend-api"


def _pypi_metadata(name: str) -> dict:
    url = PYPI_URL.format(name=name)
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit(f"Could not reach PyPI for {name!r}: {exc}") from exc


def _latest_version(metadata: dict) -> Version:
    return Version(metadata["info"]["version"])


def _target_requirement(metadata: dict) -> Requirement | None:
    """Return the gatekeeper's own requirement on the target package."""
    for raw in metadata["info"].get("requires_dist") or []:
        requirement = Requirement(raw)
        if requirement.name.lower() == TARGET:
            return requirement
    return None


def _declared_requirement() -> Requirement | None:
    """Return this project's own declared requirement on the target package."""
    data = tomllib.loads(PYPROJECT.read_text())
    for raw in data["project"]["dependencies"]:
        requirement = Requirement(raw)
        if requirement.name.lower() == TARGET:
            return requirement
    return None


def _emit_summary(lines: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-when-lifted",
        action="store_true",
        help=(
            f"Exit non-zero once {GATEKEEPER} allows the newest {TARGET}, "
            "so a scheduled run turns red and the floor can be raised."
        ),
    )
    args = parser.parse_args()

    declared = _declared_requirement()
    if declared is None:
        raise SystemExit(
            f"{TARGET!r} is not declared in [project].dependencies; "
            "this watcher assumes it is."
        )
    if any(spec.operator in {"<", "<=", "=="} for spec in declared.specifier):
        raise SystemExit(
            f"This project declares {declared} which caps {TARGET}. "
            "The whole point of the unbounded floor is that we never cap it."
        )

    latest_target = _latest_version(_pypi_metadata(TARGET))

    gatekeeper_metadata = _pypi_metadata(GATEKEEPER)
    latest_gatekeeper = _latest_version(gatekeeper_metadata)
    gatekeeper_requirement = _target_requirement(gatekeeper_metadata)

    lines = [
        f"## {TARGET} ceiling watch",
        "",
        f"- Newest `{TARGET}`: **{latest_target}**",
        f"- This package declares: `{declared}` (no upper bound)",
        f"- Newest `{GATEKEEPER}`: **{latest_gatekeeper}**",
        f"- `{GATEKEEPER}` requires: "
        f"`{gatekeeper_requirement or 'no ' + TARGET + ' requirement'}`",
    ]

    if gatekeeper_requirement is None:
        lines += [
            "",
            f"`{GATEKEEPER}` no longer depends on `{TARGET}` at all. Nothing "
            f"upstream constrains `{TARGET}` any more.",
        ]
        lifted = True
    elif gatekeeper_requirement.specifier.contains(latest_target, prereleases=False):
        lines += [
            "",
            f"**The ceiling has lifted.** `{GATEKEEPER}` {latest_gatekeeper} "
            f"accepts `{TARGET}` {latest_target}. Raise the `{GATEKEEPER}` "
            f"floor in `pyproject.toml` to `>={latest_gatekeeper}` and run "
            "`uv lock --upgrade-package clerk-backend-api "
            "--upgrade-package cryptography`.",
        ]
        lifted = True
    else:
        allowed = [
            candidate
            for candidate in _pypi_metadata(TARGET)["releases"]
            if _is_final(candidate)
            and gatekeeper_requirement.specifier.contains(candidate)
        ]
        best = max((Version(v) for v in allowed), default=None)
        lines += [
            "",
            f"Ceiling still in place. `{GATEKEEPER}` {latest_gatekeeper} caps "
            f"`{TARGET}` at `{gatekeeper_requirement.specifier}`, so resolvers "
            f"install **{best}** rather than {latest_target}.",
        ]
        lifted = False

    report = "\n".join(lines)
    print(report)
    _emit_summary(lines)

    if lifted and args.fail_when_lifted:
        return 1
    return 0


def _is_final(raw_version: str) -> bool:
    try:
        return not Version(raw_version).is_prerelease
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(main())
