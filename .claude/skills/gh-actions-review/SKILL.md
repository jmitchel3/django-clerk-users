---
name: gh-actions-review
description: Review recent GitHub Actions runs to diagnose failures and errors. Lists runs, shows logs, and helps fix CI issues.
argument-hint: "[run-id]"
---

# GitHub Actions Review Skill

Help the user review and diagnose GitHub Actions workflow runs from the current repository.

## Workflow

### Step 1: List Recent Runs

If no run ID was provided as an argument, list recent workflow runs:

```bash
gh run list --limit 15
```

To focus on failures:

```bash
gh run list --status failure --limit 10
```

Present the runs in a clear format showing:
- Run ID
- Workflow name
- Status (success/failure/in_progress)
- Branch
- Commit message (truncated)
- When it ran

Ask the user which run they'd like to investigate using AskUserQuestion.

### Step 2: Get Run Details

Once a run is selected (either from argument or user selection), fetch the details:

```bash
gh run view <run-id>
```

Display:
- Workflow name and run number
- Status and conclusion
- Branch and commit
- Jobs and their statuses
- Duration

### Step 3: Fetch Failed Logs

For failed runs, get the logs to diagnose the issue:

```bash
gh run view <run-id> --log-failed
```

If that's too verbose or you need full context:

```bash
gh run view <run-id> --log
```

Analyze the logs to identify:
- Which job(s) failed
- The specific error messages
- Root cause of the failure

### Step 4: Diagnose and Summarize

Provide a clear summary of:
- What failed and why
- The specific error(s) encountered
- Which files or code areas are involved
- Suggested fix approach

### Step 5: Create Fix Plan (if requested)

If the user wants to fix the issue:

1. Check git status for clean working state
2. Create a branch if needed: `git checkout -b fix/ci-<brief-description>`
3. Create a todo list with tasks to fix the issue
4. Begin working on the fix

## Useful Commands

```bash
# List all runs
gh run list --limit 20

# List only failures
gh run list --status failure --limit 10

# List runs for a specific workflow
gh run list --workflow "main.yaml" --limit 10

# List runs for a specific branch
gh run list --branch main --limit 10

# View run details
gh run view <run-id>

# View failed job logs only
gh run view <run-id> --log-failed

# View all logs
gh run view <run-id> --log

# View a specific job's logs
gh run view <run-id> --job <job-id> --log

# Re-run failed jobs
gh run rerun <run-id> --failed

# Re-run entire workflow
gh run rerun <run-id>

# Watch a run in progress
gh run watch <run-id>
```

## Important Notes

- Failed logs can be very long; focus on error messages and stack traces
- Look for patterns like "Error:", "FAILED", "exit code 1", assertion failures
- Check if the failure is flaky (intermittent) by looking at recent run history
- For test failures, identify the specific test(s) that failed
- Consider environment differences between local and CI
