"""Render a comparison as the PR comment. Plain markdown — GitHub renders it,
and a human skims it in five seconds: verdict first, then what moved.
"""
from __future__ import annotations

from typing import Optional

_ICON = {"regressed": "🔴", "improved": "🟢", "unchanged": "⚪", "no-baseline": "🔎"}


def _sha(run: Optional[dict]) -> str:
    return (run or {}).get("git_sha") or (run or {}).get("id", "?")[:7]


def render(comparison: Optional[dict], candidate: dict, baseline: Optional[dict], suite: str) -> str:
    if comparison is None:
        return (f"### 🔎 prompt-regress · `{suite}`\n\n"
                f"No baseline run to compare against yet — stored this run "
                f"(`{_sha(candidate)}`) as the first. The next PR will be gated against it.")

    verdict = comparison["verdict"]
    icon = _ICON.get(verdict, "•")
    regs = comparison.get("regressions", [])
    imps = comparison.get("improvements", [])
    flagged = comparison.get("newly_flagged", [])
    added, removed = comparison.get("added", []), comparison.get("removed", [])

    head = "**blocks merge**" if comparison.get("is_regression") else "no regression"
    lines = [
        f"### {icon} prompt-regress · `{suite}` — **{verdict}** ({head})",
        "",
        f"baseline `{_sha(baseline)}` → this PR `{_sha(candidate)}`",
        "",
        f"- **{len(regs)}** regression(s) · **{len(imps)}** improvement(s)",
    ]
    if flagged:
        lines.append(f"- 🚩 **{len(flagged)}** case(s) newly flagged: {', '.join(flagged[:5])}")
    if added or removed:
        lines.append(f"- suite changed: {len(added)} added, {len(removed)} removed "
                     f"(reported, not scored)")

    if regs:
        lines += ["", "| case | metric | before | after | Δ |", "| --- | --- | --- | --- | --- |"]
        for d in regs[:8]:
            lines.append(f"| {d['q'][:48]} | {d['metric']} | {d['before']} | {d['after']} | {d['delta']:+.3f} |")

    metric_deltas = comparison.get("metric_deltas") or {}
    if metric_deltas:
        lines += ["", "<sub>metric deltas: "
                  + " · ".join(f"{k} {v:+.3f}" for k, v in metric_deltas.items()) + "</sub>"]

    lines += ["", "<sub>stored in [eval-history](https://github.com/egnaro9/eval-history); "
              "PR runs never become the baseline.</sub>"]
    return "\n".join(lines)
