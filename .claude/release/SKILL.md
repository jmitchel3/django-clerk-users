---
name: release
description: Release a new version by bumping version, tagging, and pushing to GitHub.
argument-hint: "[patch|minor|major|X.Y.Z]"
---

# Release Skill

Release a new version of this Copier template to GitHub.

## Arguments (optional)

- `$ARGUMENTS` - Bump type: `patch` (default), `minor`, or `major`. Or a specific version like `0.5.0`.

## Steps

1. Get the current version from the latest git tag:
   ```bash
   git describe --tags --abbrev=0
   ```

2. Determine the new version:
   - If no argument or `patch`: increment patch (0.2.4 -> 0.2.5)
   - If `minor`: increment minor, reset patch (0.2.4 -> 0.3.0)
   - If `major`: increment major, reset minor and patch (0.2.4 -> 1.0.0)
   - If specific version provided (X.Y.Z format): use that version

3. Confirm the version bump with the user using AskUserQuestion:
   - Show current version and new version
   - Ask for confirmation before proceeding

4. Create a git tag: `v{version}`
   ```bash
   git tag v{version}
   ```

5. Push the tag to origin:
   ```bash
   git push origin v{version}
   ```

6. Report success with the new version number and a link to the GitHub releases page.

## Important

- Do NOT include a co-authored-by line in commits
- The version should be in format `X.Y.Z` (e.g., `0.2.5`)
- Tags should be prefixed with `v` (e.g., `v0.2.5`)
- This template uses git tags as the version source (no version file to update)
- Ensure working directory is clean before tagging
