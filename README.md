# prompt-regress

**A "does-my-prompt-still-work" merge gate. Run your eval on every PR, compare it to the main-branch baseline, and block the merge if answers got worse.**

[![ci](https://github.com/egnaro9/prompt-regress/actions/workflows/ci.yml/badge.svg)](https://github.com/egnaro9/prompt-regress/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org/)
[![tests](https://img.shields.io/badge/tests-7-brightgreen)](tests)

An LLM eval tells you how the system does *today*. What breaks a product is a prompt tweak or a model bump that quietly makes *some* answers worse while the average holds — and no error fires. [promptfoo](https://promptfoo.dev), the popular eval runner, [doesn't store history or compare across runs](https://www.promptfoo.dev/docs/configuration/parameters/) (its self-hosted store is "experimental, not recommended for production"). So there's a gap: **nothing gates a PR on "did this change make the evals worse?"**

prompt-regress fills it, on top of [eval-history](https://github.com/egnaro9/eval-history) (which already stores runs and computes a regression verdict). On a pull request it:

1. **stores** the PR's run (tagged `pr`, so it never becomes the baseline),
2. finds the **baseline** — the newest `ci` run of the suite on main,
3. **compares** them, and
4. writes a PR comment and **exits non-zero on a regression**, failing the check.

```
     PR eval_run.json ──►  eval-history  ──►  compare vs main baseline  ──►  🔴 blocks merge
```

<img src="https://raw.githubusercontent.com/egnaro9/rag-eval-lab/main/docs/demo.gif" alt="rag-eval-lab's harness catching a planted hallucination at faithfulness 0.5" width="100%">

*This gate blocks on a regression; it does not decide what a regression is. That judgement is made
upstream, and this is upstream: [rag-eval-lab](https://github.com/egnaro9/rag-eval-lab) grading a
suite and flagging the one answer its sources do not support. The run it produces is what
[eval-history](https://github.com/egnaro9/eval-history) stores and compares, and what this gate
reads a verdict from. [Play it as a terminal session](https://asciinema.org/a/k0m7dOqwWt1kdSlx).*

## Use it — GitHub Action

```yaml
# .github/workflows/eval-gate.yml
on: pull_request
permissions: { pull-requests: write, contents: read }
jobs:
  eval-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |            # produce eval_run.json however your project evals
          pip install -e .
          python -m ragevallab.cli eval --out eval_run.json
      - uses: egnaro9/prompt-regress@main
        with:
          run: eval_run.json
          suite: my-project
          write-key: ${{ secrets.EVAL_HISTORY_WRITE_KEY }}
```

On a regressing PR the check goes red and a comment appears:

> ### 🔴 prompt-regress · `my-project` — **regressed** (**blocks merge**)
> baseline `a1b2c3d` → this PR `e4f5g6h`
> - **2** regression(s) · **0** improvement(s)
> - 🚩 **1** case newly flagged: *is aspirin safe in pregnancy?*
>
> | case | metric | before | after | Δ |
> | --- | --- | --- | --- | --- |
> | is aspirin safe in pregnancy? | faithfulness | 0.9 | 0.6 | −0.300 |

Fork PRs (no secret) and suites with no baseline yet **skip cleanly** — the gate never fails a PR it can't fairly judge.

## Use it — CLI

```bash
pip install git+https://github.com/egnaro9/prompt-regress
EVAL_HISTORY_WRITE_KEY=... prompt-regress gate \
    --run eval_run.json --suite my-project \
    --api https://your-eval-history.example.com
# prints the markdown verdict; exit code is 1 on a regression
```

The public instance this was built against (`eval-history.onrender.com`) is retired.
Point `--api` at your own [eval-history](https://github.com/egnaro9/eval-history)
deployment, or set `$EVAL_HISTORY_API`. Its read routes also survive as a static
archive at <https://erikhill.dev/eval-history/>, which the client detects and reads
directly: baselines and comparisons work against it, storing a run does not.

## Why it's trustworthy

- **The baseline is chosen carefully, and it's tested.** Only `ci` runs are eligible, so a merge gate compares against what's actually on main — never another open PR (`pr`), never a config sweep (`ablation`), never the candidate's own commit. Get that wrong and you fail honest PRs or pass broken ones; [`test_gate.py`](tests/test_gate.py) pins it.
- **A down store doesn't wedge your PRs.** eval-history is on a free tier; if it's unreachable, the gate reports and *passes* rather than blocking every merge on infrastructure.
- **The verdict is eval-history's, not a reimplementation.** prompt-regress stores and asks; the comparison logic lives in one place. stdlib `urllib` only — nothing to install in CI beyond this.

---
MIT · by [Erik Hill](https://egnaro9.github.io) · pairs with [eval-history](https://github.com/egnaro9/eval-history) and [rag-eval-lab](https://github.com/egnaro9/rag-eval-lab)
