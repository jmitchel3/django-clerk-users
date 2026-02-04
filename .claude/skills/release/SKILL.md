---
name: release
description: Release a new version by bumping version, tagging, and pushing to GitHub.
argument-hint: "[patch|minor|major|X.Y.Z]"
---

# Release Skill

Release a new version of django-clerk-users to PyPI via GitHub Actions.

## Arguments (optional)

- `$ARGUMENTS` - Bump type: `patch` (default), `minor`, or `major`. Or a specific version like `0.5.0`.

## Steps

1. Get the current version from `pyproject.toml`:
   ```bash
   grep '^version = ' pyproject.toml
   ```

2. Determine the new version:
   - If no argument or `patch`: increment patch (0.1.3 -> 0.1.4)
   - If `minor`: increment minor, reset patch (0.1.3 -> 0.2.0)
   - If `major`: increment major, reset minor and patch (0.1.3 -> 1.0.0)
   - If specific version provided (X.Y.Z format): use that version

3. Confirm the version bump with the user using AskUserQuestion:
   - Show current version and new version
   - Ask for confirmation before proceeding

4. Update the version in `pyproject.toml`:
   - Edit the `version = "X.Y.Z"` line to the new version

5. Commit the version change:
   ```bash
   git add pyproject.toml
   git commit -m "Release vX.Y.Z"
   ```
   Note: Do NOT use `[skip ci]` - this would prevent the tag-triggered release workflow from running.

6. Push to main:
   ```bash
   git push origin main
   ```

7. Create and push the git tag:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

8. Report success with the new version number and a link to the GitHub releases page.

## Important

- Do NOT include a co-authored-by line in commits
- The version should be in format `X.Y.Z` (e.g., `0.1.4`)
- Tags should be prefixed with `v` (e.g., `v0.1.4`)
- The version in `pyproject.toml` must match the tag (without the `v` prefix)
- Ensure working directory is clean before starting (except for the version bump)
- The `release.yaml` workflow runs tests and publishes to PyPI when a tag is pushed
- The `ci.yaml` workflow runs tests on main branch pushes and PRs (separate from releases)
