"""Read-side resolution layer for historical AgentX isolated worktrees.

The eight 2026-10-23 AgentX worktrees were merged into main and are being
removed.  This module is the resolver used by current analysis and offline
mock scripts.  Historical manifests, plans, approvals and reports keep their
original path strings; nothing here rewrites or refreshes them.

Mapping: a path under an old worktree root maps to ROOT when the subtree is
tracked (env/reports/scripts), and to ROOT/data/raw/<batch> when it was
ignored raw input.  Missing targets raise at read time so callers cannot
silently read deleted worktrees.  No execution authorization.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OLD_ROOTS = {
    'replay_smoke':        Path('/home/lcq/agentx_replay_smoke_20261023'),
    'pilot':               Path('/home/lcq/agentx_deepseek_pilot_20261023'),
    'branches':            Path('/home/lcq/agentx_deepseek_branches_20261023'),
    'coverage':            Path('/home/lcq/agentx_deepseek_coverage_20261023'),
    'repeats':             Path('/home/lcq/agentx_deepseek_repeats_20261023'),
    'five_repeats':        Path('/home/lcq/agentx_deepseek_five_repeats_20261023'),
    'main_integration':    Path('/home/lcq/agentx_main_integration_20261023'),
    'state_option_tests':  Path('/home/lcq/agentx_state_option_tests_20261023'),
}

# Migrated ignored raw input batches (git-ignored under data/raw/).
RAW_BATCH = {
    'replay_smoke': ROOT/'data/raw/agentx-replay-smoke-01',
    'pilot':        ROOT/'data/raw/agentx-deepseek-pilot-01',
    'branches':     ROOT/'data/raw/agentx-deepseek-branches-01',
    'coverage':     ROOT/'data/raw/agentx-deepseek-coverage-01',
    'repeats':      ROOT/'data/raw/agentx-deepseek-repeats-01',
    'five_repeats': ROOT/'data/raw/agentx-deepseek-five-repeats-01',
}


def resolve(path):
    """Map a historical path into the current main checkout.

    Old worktree absolute paths resolve to ROOT (tracked subtrees) or to
    ROOT/data/raw/<batch> (ignored raw inputs).  Already-current paths are
    returned unchanged.  A missing target is returned as a Path and only
    fails when actually read, preserving read-only call semantics.
    """
    path = Path(path)
    text = str(path)
    for name, old in OLD_ROOTS.items():
        prefix = str(old) + '/'
        if text.startswith(prefix):
            rel = path.relative_to(old)
            parts = rel.parts
            if len(parts) >= 2 and parts[0] == 'data' and parts[1] == 'raw':
                return ROOT / 'data' / 'raw' / Path(*parts[2:])
            return ROOT / Path(*parts)
    return path


def batch(name):
    """Return the migrated ignored raw data directory for a logical worktree."""
    if name not in RAW_BATCH:
        raise KeyError('unknown AgentX logical worktree: ' + name)
    return RAW_BATCH[name]


REPLAY_RAW   = batch('replay_smoke')
PILOT_RAW    = batch('pilot')
BRANCHES_RAW = batch('branches')
COVERAGE_RAW = batch('coverage')
REPEATS_RAW  = batch('repeats')
FIVE_RAW     = batch('five_repeats')
