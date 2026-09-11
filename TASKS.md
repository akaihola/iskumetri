# Issue tracking for Iskumetri

Rules for TASKS.md usage are at the bottom of the file.

## Unverified proposals

## Ordered backlog

## Scheduled

## In progress

## Completed

---

## Rules

Here are the rules for TASKS.md usage:

### Invariant: one heading per issue

At any time, each issue's bullet must be under exactly one `##` heading
(for example `## Ordered backlog` or `## In progress`). It must never be
under two headings at the same time.

- Before you commit any change to TASKS.md, run:
  `python3 tools/check_tasks_md.py TASKS.md`
- The check must pass (exit code 0) before the commit.
- If the check fails, it prints the duplicated bullet. Remove the bullet
  from all but one heading before you commit.

### TASKS.md maintenance sessions

- Each issue bullet in every section must be prefixed with either
  - a numbered reference-style link (e.g. `[1]`) to a description file, or
  - `[*]` to indicate no description file is needed for a simple task.
- Link references are listed between `## Completed` and `## Rules`.
- If any issue is missing a link:
  - Create the first missing numbered description file in
    docs/tasks/<N-issue-description>.md and add the link

### Modifying issues

- Ensure dependencies between issues are correctly updated.
- State dependencies using
  - indented `- Depends on: [N]` bullets in TASKS.md, and
  - YAML frontmatter in description files.
- Ensure backlog order respects dependencies.
- When you move an issue to a different section, move its lines without
  a change. Keep the prefix, the bullet text and the line wrapping the same.
  This keeps moves identifiable in Git and reduces avoidable conflicts;
  concurrent moves can still conflict.

### Workflow for new issue completion

When TASKS.md conflicts during a rebase or merge:

- Use `main`'s version of every section as the base.
- Apply again only the move of your own issue.
- Never restore, add again or re-word another issue's bullet from your side of
  the conflict.
- After resolving the conflict, read the whole file and ensure that each
  bullet is under exactly one `##` heading.

1. Choose issue and schedule work (typically by a heartbeat)
- Pick the first backlog issue with no dependency to any uncompleted issue.
- Move it under `## Scheduled` in `TASKS.md` and remove it from `## Ordered
  backlog` in the `main` branch and commit.

2. Work on the issue (typically by a task workflow)
- From now on, ensure worktree feature branch is always rebased on `main`.
- Move the issue under `## In progress` in `TASKS.md` in the worktree branch,
  ensure it's not in `## Ordered backlog`, and commit.
- Create or update, review and refine a plan in
  docs/tasks/<N-issue-description>.md in `main` if more description is needed
  than nicely fits in a bullet point. If you created a plan document, link to it
  using a new `[N]` reference-style link.
- Commit the description file (if any) in `main`.
- Implement the plan, and lint, test, review and refine the implementation in
  the worktree feature branch.

3. Merge and deploy (typically by last steps of a task workflow)
- Merge the rebased branch on `main`, and remove the worktree and branch.
- Move the issue from `## In progress` to `## Completed` in TASKS.md and commit.
- Do any deployment steps if defined in the general development worklow.
