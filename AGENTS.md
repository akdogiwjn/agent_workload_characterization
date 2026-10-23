# Shared workspace and project-state protection

This repository may be used by several conversations concurrently. Preserve
changes that do not belong to the current task, including uncommitted state.

## Before editing

- Read `git status --short` and the current `project_state.json`.
- For parallel tasks, use separate Git worktrees and branches. Do not move,
  reset, or clean another conversation's existing worktree. Ignored raw data,
  credentials and archives are not copied by Git; use existing read-only data
  locations deliberately, never copy credentials into a worktree or commit.
- Update only the files and state entries needed by the user's task. Preserve
  any exclusions the user gave, including exclusions for video-related work.

## Never discard unknown work

Do not use `git checkout -- <file>`, `git restore <file>`, `git reset --hard`,
`git clean`, or a blanket `git stash` to make the tree clean or to undo changes
whose ownership is uncertain. This includes `project_state.json`. A user's
explicit request to discard specified changes takes precedence, but first
save a recoverable snapshot of affected current files and inspect the scope.

Untracked files and ignored evidence may be the only copies. Do not delete
them during routine cleanup or replace them with the Git HEAD version.

## State updates

Use `scripts/update_project_state.py` for routine state writes:

1. Read the state and retain its SHA256 as the expected base.
2. Supply a JSON object containing only task-specific additions/updates.
   The helper recursively merges dictionaries and preserves unrelated keys.
3. Apply with `--expected-sha256`; stale bases are rejected, not overwritten.
   The helper takes a cooperative lock, creates an exact local snapshot,
   regenerates the three current status blocks and checks evidence hashes.
4. Run `python3 -B scripts/check_project_state.py` before committing.

Do not replace the whole state from an earlier snapshot, Git HEAD, or a stale
in-memory JSON value. Recovery must merge missing entries and preserve newer
entries. The execution-authorization field must never be changed by the helper.
Do not refresh historical evidence hashes merely to make validation pass.

The lock is cooperative: arbitrary editors and Git commands can bypass it.
Separate worktrees, automatic snapshots, scoped changes and frequent reviewed
commits are all needed. A Git push backs up committed files only, not ignored
raw data, credentials or local archives. State-only checkpoints may retain
local evidence references; state clearly what the remote repository contains.

## Commit scope

Use an explicit path list or inspect staged hunks; never `git add .` in this
shared checkout. Inspect `git diff --cached` for unrelated files, large assets,
private logs and credentials. Do not run experiments, agents, API calls,
containers or benchmarks just to validate a documentation/state checkpoint.
