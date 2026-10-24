# Main-branch workflow and project-state protection

This repository may be used by several conversations concurrently. Preserve
changes that do not belong to the current task, including uncommitted state.

## Before editing

- Read `git status --short` and the current `project_state.json`.
- The user's default is to work in this original repository on `main` and
  keep local `main` synchronized with remote `main` for published files.
  Do not automatically create additional branches or worktrees. Use one only
  when the user explicitly requests or approves it. Existing worktrees and
  branches belonging to other conversations must not be removed or altered.
- With multiple conversations, keep file ownership explicit, coordinate
  overlapping edits, and serialize Git index/ref mutations and push operations.
  Keep using the cooperative state lock below. Before synchronizing `main`,
  inspect local changes, retain a recoverable snapshot, and preserve newer
  local work while merging remote updates; never blindly overwrite it.
- Ignored raw data, credentials, archives, models and runtime payloads stay
  local. Published code, documentation and small configuration/manifest files
  use normal commits and non-forced pushes on `main`.
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
Coordinated edits, automatic snapshots, scoped changes and frequent reviewed
commits protect the shared `main` workflow. A Git push backs up committed files
only, not ignored raw data, credentials or local archives. State-only
checkpoints may retain local evidence references; state clearly what the
remote repository contains.

## Commit scope

Use an explicit path list or inspect staged hunks; never `git add .` in this
shared checkout. Inspect `git diff --cached` for unrelated files, large assets,
private logs and credentials. Do not run experiments, agents, API calls,
containers or benchmarks just to validate a documentation/state checkpoint.
