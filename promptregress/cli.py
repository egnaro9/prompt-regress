"""prompt-regress — a "does-my-prompt-still-work" merge gate.

    prompt-regress gate --run eval_run.json --suite my-suite \
        --api https://your-eval-history.example.com

Runs on a pull request: stores the run, compares it to the main-branch baseline
in eval-history, writes a markdown verdict for a PR comment, and exits non-zero
if it regressed — so a prompt or model change that quietly makes answers worse
can't merge silently. `eval_run.json` is whatever your eval produces in
[rag-eval-lab](https://github.com/egnaro9/rag-eval-lab)'s shape.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from .client import ArchiveReadOnly, HttpError, client_for
from .gate import run_gate


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="prompt-regress", description=__doc__)
    sub = p.add_subparsers(dest="cmd")
    g = sub.add_parser("gate", help="gate a PR against the baseline")
    g.add_argument("--run", required=True, help="eval_run.json produced by your eval")
    g.add_argument("--suite", required=True, help="suite name (the run's `run` field / your project)")
    g.add_argument("--api", default=os.environ.get("EVAL_HISTORY_API", ""),
                   help="eval-history base URL (or $EVAL_HISTORY_API). The public instance was "
                        "retired; https://erikhill.dev/eval-history/ is its read-only archive.")
    g.add_argument("--key-env", default="EVAL_HISTORY_WRITE_KEY",
                   help="env var holding the write key (forks have none → the gate skips)")
    g.add_argument("--git-sha", default=os.environ.get("GITHUB_SHA"))
    g.add_argument("--label", default=None, help="defaults to the PR title / commit subject")
    g.add_argument("--comment-file", default=None, help="write the markdown verdict here (for a PR comment)")
    g.add_argument("--no-fail", action="store_true", help="report but never exit non-zero")
    args = p.parse_args(argv)

    if args.cmd != "gate":
        p.print_help()
        return 1

    if not args.api.strip():
        print("prompt-regress: --api is required (or set $EVAL_HISTORY_API). The old public "
              "instance at eval-history.onrender.com was retired; point this at your own "
              "eval-history deployment. https://erikhill.dev/eval-history/ is a read-only "
              "archive of the original data and works for comparisons but cannot store runs.",
              file=sys.stderr)
        return 2

    key = os.environ.get(args.key_env, "").strip()
    if not key:
        print(f"no {args.key_env} set — skipping the gate (forks and unconfigured repos have no key)")
        return 0

    run = json.load(open(args.run, encoding="utf-8"))
    client = client_for(args.api, write_key=key)

    try:
        result = run_gate(client, run, suite=args.suite, git_sha=args.git_sha, label=args.label)
    except ArchiveReadOnly as e:
        # The archive can be compared against but not written to. Report, don't block.
        print(f"prompt-regress: {e}", file=sys.stderr)
        return 0
    except HttpError as e:
        # A store that's down must not wedge every PR. Report and pass.
        print(f"prompt-regress: eval-history unavailable ({e}); not blocking.", file=sys.stderr)
        return 0

    print(result.markdown)
    if args.comment_file:
        with open(args.comment_file, "w", encoding="utf-8") as fh:
            fh.write(result.markdown)

    if args.no_fail:
        return 0
    if result.is_regression:
        print(f"\nprompt-regress: {result.verdict} — blocking merge.", file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
