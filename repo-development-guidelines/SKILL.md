---
name: repo-development-guidelines
description: "Use before modifying any personal repository or work repository. Highest-priority development guardrail: enforce the Superpowers basic workflow for every repo change, including design/spec, isolated branch/worktree, bite-sized plan, TDD where applicable, subagent/review gates, verification, and finishing choices."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [development-guidelines, superpowers, repository, tdd, planning, code-review, high-priority]
    related_skills: [writing-plans, test-driven-development, subagent-driven-development, requesting-code-review, systematic-debugging]
---

# Repository Development Guidelines

## Priority

This is a high-priority guardrail skill.

When the task may modify any git repository owned by the user, maintained by the user, cloned for the user, or used for work, load and follow this skill before making changes.

This applies to both:

- Personal repositories, including skill repositories such as `~/gemili-skills`
- Work repositories, including NetEase repositories under `~/code/netease`

Do not bypass this workflow for convenience. If a requested change feels small, use the minimum viable version of the workflow instead of skipping it.

## Trigger

Use this skill before any action that can change a repository, including:

- `write_file`, `patch`, or generated files inside a git repo
- `git commit`, `git push`, `gh`, `glab`, or release operations
- package/config changes
- test, CI, deployment, cron, or skill script changes stored in a repo
- changes to local skill source repos that are later synced to runtime skills

If the task only reads files, inspects status, or answers a question without modifying anything, this skill is not required beyond normal read-only discovery.

## Required Superpowers Basic Workflow

For every repo modification, follow this sequence:

1. Brainstorm / clarify intent
   - Understand what the user is really trying to accomplish.
   - If requirements are ambiguous, ask focused questions.
   - If the user gave an exact, unambiguous change, treat that as design approval and state assumptions briefly.

2. Design / spec before code
   - Produce a short design for the change.
   - Include scope, non-goals, affected files, expected behavior, and risks.
   - For non-trivial changes, get user approval before editing.

3. Isolate work
   - Check `git status` before edits.
   - Prefer a dedicated branch or git worktree for personal/work repos.
   - Do not overwrite unrelated user changes.
   - If the repo already has uncommitted changes unrelated to the task, stop and ask before proceeding.

4. Write a bite-sized implementation plan
   - Use `writing-plans` for multi-step work.
   - Tasks should be small and ordered.
   - Include exact paths, commands, and verification steps.

5. Use TDD for behavior changes
   - Use `test-driven-development` for features, bug fixes, and refactors.
   - Write the failing test first, run it, implement minimal code, then run it green.
   - For docs-only or pure skill text changes where automated tests are not meaningful, use validator-style checks instead.

6. Implement in small steps
   - Make the minimum necessary change.
   - Avoid drive-by refactors.
   - Preserve DRY and YAGNI.

7. Review and verify
   - Use `requesting-code-review` for code changes, multi-file changes, security-sensitive changes, or before commit/push.
   - At minimum, inspect `git diff`, run relevant tests/validators, and ensure no unrelated files changed.
   - Evidence over claims: never say it is done without running verification appropriate to the repo.

8. Finish deliberately
   - Show final diff summary, verification results, and remaining risks.
   - Ask or present choices before merge, PR, push, or cleanup unless the user explicitly requested those actions.

## Minimum Viable Workflow for Tiny Changes

For a tiny, low-risk repo change such as a typo fix or a one-file documentation update, do not skip the workflow. Use this compressed version:

1. Confirm scope in one sentence.
2. Run `git status`.
3. Make the focused change.
4. Run the relevant validator or at least inspect the changed file.
5. Review `git diff`.
6. Commit/push only if explicitly requested or already part of the user's instruction.

## Personal vs Work Repository Rules

### Personal repositories

- The user's `~/gemili-skills` repository is a personal source-of-truth for skill maintenance.
- When runtime skills under `~/.hermes/skills` are changed and the same skill exists or should exist in `~/gemili-skills`, keep them synchronized unless the user says not to.
- Before pushing public personal repositories, scan for secrets and concrete delivery targets.

### Work repositories

- Treat NetEase repositories under `~/code/netease` as work repositories.
- Use GitLab-oriented tooling (`git`, `glab`) rather than GitHub tooling unless the repository remote proves otherwise.
- Do not use personal GitHub tokens for work repositories.
- Be extra careful with branch names, remotes, and unrelated local changes.

## Required Related Skills

Depending on the task, load these before implementation:

- `writing-plans` for implementation planning
- `test-driven-development` for behavior changes and bug fixes
- `systematic-debugging` for bugs or unclear failures
- `subagent-driven-development` for executing multi-task plans with agents
- `requesting-code-review` before commit/push or after substantial edits
- GitHub/GitLab repo skills according to the remote host

## Common Pitfalls

1. Jumping straight into edits because the change looks obvious.
   - Fix: write a short scope/design and check git status first.

2. Editing on a dirty repo with unrelated user changes.
   - Fix: stop, show the dirty files, and ask how to proceed.

3. Adding tests after implementation.
   - Fix: for behavior changes, follow RED-GREEN-REFACTOR strictly.

4. Claiming success from reasoning alone.
   - Fix: run tests, validators, or diff review and report the actual output.

5. Syncing runtime skills but forgetting the source repo.
   - Fix: update both `~/.hermes/skills/...` and `~/gemili-skills/...` when skill maintenance policy applies.

6. Pushing or merging without final consent.
   - Fix: present finish options unless the user explicitly requested push/merge.

## Verification Checklist

Before finalizing any repo modification:

- [ ] This skill was loaded and followed.
- [ ] Relevant supporting skills were loaded.
- [ ] `git status` was checked before edits.
- [ ] Unrelated user changes were not modified.
- [ ] A design/scope and plan existed before editing.
- [ ] TDD was used for behavior changes, or a clear non-code validator was used.
- [ ] Diff was reviewed.
- [ ] Tests/validators were run where applicable.
- [ ] Commit/push/merge happened only when requested or approved.
- [ ] Final response includes changed paths and verification evidence.
