"""The gate: store the PR's run, find the baseline, compare, decide.

Kept pure of I/O beyond the injected client, so the interesting logic — *which*
run is the baseline, and *what* counts as a regression worth blocking a merge —
is tested directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .client import EvalHistory


@dataclass
class GateResult:
    verdict: str                 # "regressed" | "improved" | "unchanged" | "no-baseline"
    is_regression: bool
    comparison: Optional[dict]   # the eval-history comparison, or None
    baseline: Optional[dict]     # the baseline run summary, or None
    candidate: dict              # the stored PR run
    markdown: str

    @property
    def exit_code(self) -> int:
        return 1 if self.is_regression else 0


def _pick_baseline(runs: List[dict], candidate_sha: Optional[str]) -> Optional[dict]:
    """The newest CI run of this suite that isn't the candidate itself.

    Only `source == 'ci'` runs are eligible — a PR run or an ablation is never a
    baseline, so a merge gate compares against what's actually on main, not
    against another open PR. Same-sha runs are skipped so re-running a PR doesn't
    end up comparing it to itself.
    """
    for r in runs:  # eval-history returns newest first
        if r.get("source", "ci") != "ci":
            continue
        if candidate_sha and r.get("git_sha") == candidate_sha:
            continue
        return r
    return None


def run_gate(client: EvalHistory, run: dict, suite: str,
             git_sha: Optional[str] = None, label: Optional[str] = None) -> GateResult:
    from .render import render

    candidate = client.post_run(run, source="pr", git_sha=git_sha, label=label or "pull request")
    baseline = _pick_baseline(client.list_runs(suite), git_sha)

    if baseline is None:
        md = render(None, candidate, None, suite)
        return GateResult("no-baseline", False, None, None, candidate, md)

    comparison = client.compare(baseline["id"], candidate["id"])
    verdict = comparison["verdict"]
    is_regression = bool(comparison.get("is_regression"))
    md = render(comparison, candidate, baseline, suite)
    return GateResult(verdict, is_regression, comparison, baseline, candidate, md)
