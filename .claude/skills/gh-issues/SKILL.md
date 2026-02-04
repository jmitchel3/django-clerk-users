---
name: gh-issues
description: Review open GitHub issues and start working on one. Lists issues, shows details, creates a branch, and sets up todos.
argument-hint: "[issue-number]"
---

# GitHub Issues Skill

Help the user review and start working on GitHub issues from the current repository.

## Workflow

### Step 1: List Open Issues

If no issue number was provided as an argument, list open issues:

```bash
gh issue list --state open --limit 20
```

Present the issues in a clear format and ask the user which one they'd like to work on using AskUserQuestion. Include issue number, title, and labels.

### Step 2: Get Issue Details

Once an issue is selected (either from argument or user selection), fetch the full details:

```bash
gh issue view <issue-number>
```

Display:
- Title and description
- Labels and assignees
- Any linked PRs or related issues
- Comments (if relevant)

### Step 3: Create a Working Branch

Always create a new branch for this issue:

```bash
git checkout -b <branch-name>
```

Suggest a branch name based on the issue (e.g., `fix/123-brief-description` or `feat/123-brief-description`).

### Step 4: Create Todo List

Based on the issue description and any acceptance criteria, use TodoWrite to create a structured task list. Break down the work into:
- Investigation/research tasks (if needed)
- Implementation tasks
- Testing tasks
- Documentation updates (if needed)

### Step 5: Start Working

Begin working on the first todo item. Use the codebase exploration tools to understand the relevant code before making changes.

## Important Notes

- Always check `git status` before creating a branch to ensure clean working state
- If the issue is unclear, ask clarifying questions before starting work
- Reference the issue number in commit messages (e.g., "Fix #123: description")
- Keep the user informed of progress by updating todos as you work
