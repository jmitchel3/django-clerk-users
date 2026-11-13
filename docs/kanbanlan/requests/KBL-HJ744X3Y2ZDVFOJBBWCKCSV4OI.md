# Track Kanbanlan workflow setup in the repository

- Kanbanlan: `KBL-HJ744X3Y2ZDVFOJBBWCKCSV4OI`
- Canonical home: `github`
- Canonical request: [#52](https://github.com/jmitchel3/django-clerk-users/issues/52)

## Request

Commit the existing local Kanbanlan repository setup so new checkouts share the active GitHub Issues/Project 13 workflow. Include .kanbanlan.toml, AGENTS.md, CLAUDE.md coordination instructions, cache/worktree ignores, issue and PR templates, and docs/workflow/kanbanlan.md. Remove the guide reference to the absent worker.md and align any contradictory release guidance with the current PR-based workflow. Validate config/templates, internal references, and ignored local state. Deliver through a separate PR merged to main for inclusion in the next release; do not bump or publish a package version.

## Decisions

- Preserve the seven existing local workflow files/edits as shared repository
  configuration. The GitHub repository and Project binding contain no credentials;
  local cache and worktree state remain ignored.
- Keep the generated coordination instructions identical in AGENTS.md and
  CLAUDE.md. Correct the older release section to use the current workflow file,
  reviewed PRs, final-main verification, and an annotated release tag.
- Remove the reference to an absent worker guide rather than introducing a new
  document outside this request's scope.
- Record the setup under Unreleased. The package version remains 0.5.1; this
  request does not publish another release.

## Verification

- Live `kanbanlan ensure` and `kanbanlan reconcile` passed; no overlapping open
  requests or pull requests existed before this request was created.
- `kanbanlan doctor` passed for the worktree configuration: GitHub authentication,
  Project 13 Status field, and repository workflow labels were all valid.
- Parsed the TOML configuration and YAML issue form; checked the repository/branch
  binding, unique form IDs, expected fields, and intake label.
- Verified matching AGENTS.md/CLAUDE.md coordination blocks, valid release-workflow
  reference, removal of the missing worker-guide reference, and unchanged version.
- `git check-ignore` confirmed cache/worktree paths are ignored while shared
  configuration and workflow documentation remain trackable.
- `git diff --check` passed. CI runs for the Unreleased changelog update.

## Delivered result

The repository now versions its Kanbanlan configuration, agent instructions,
workflow guide, GitHub issue/PR templates, and local-state ignore rules. Release
guidance matches the current PR-based process, and the Unreleased changelog carries
this setup into the next release from main.
