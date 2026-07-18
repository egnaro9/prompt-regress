"""The gate logic, against a fake eval-history — no network.

The two things worth being right about a merge gate: it picks the *correct*
baseline (main, not another PR, not itself), and it exits non-zero exactly when
something regressed. Both are pinned here.
"""
from promptregress.gate import _pick_baseline, run_gate


class FakeHistory:
    """An in-memory eval-history: records the POST, serves a scripted list + compare."""

    def __init__(self, runs, comparison):
        self.runs = runs                # returned newest-first by list_runs
        self.comparison = comparison
        self.posted = None

    def post_run(self, run, source, git_sha, label):
        self.posted = {"run": run, "source": source, "git_sha": git_sha, "label": label}
        return {"id": "cand", "git_sha": git_sha, "source": source, "name": run["run"]}

    def list_runs(self, suite, limit=50):
        return self.runs

    def compare(self, baseline_id, candidate_id):
        self.compare_args = (baseline_id, candidate_id)
        return self.comparison


REGRESSED = {"verdict": "regressed", "is_regression": True,
             "regressions": [{"q": "is aspirin safe in pregnancy?", "metric": "faithfulness",
                              "before": 0.9, "after": 0.6, "delta": -0.3}],
             "improvements": [], "newly_flagged": ["is aspirin safe in pregnancy?"],
             "added": [], "removed": [], "metric_deltas": {"faithfulness": -0.3}}
CLEAN = {"verdict": "unchanged", "is_regression": False, "regressions": [], "improvements": [],
         "newly_flagged": [], "added": [], "removed": [], "metric_deltas": {}}

RUN = {"run": "my-suite", "metrics": {}, "cases": []}


def test_pr_run_is_stored_as_source_pr_not_ci():
    fake = FakeHistory([{"id": "b", "source": "ci", "git_sha": "main1"}], CLEAN)
    run_gate(fake, RUN, suite="my-suite", git_sha="pr1")
    assert fake.posted["source"] == "pr"   # must not pollute the baseline


def test_baseline_is_the_newest_ci_run():
    runs = [
        {"id": "otherPR", "source": "pr", "git_sha": "pr9"},      # another open PR — skip
        {"id": "ablation", "source": "ablation", "git_sha": "x"}, # a sweep — skip
        {"id": "main-new", "source": "ci", "git_sha": "main2"},   # ← this one
        {"id": "main-old", "source": "ci", "git_sha": "main1"},
    ]
    assert _pick_baseline(runs, candidate_sha="pr1")["id"] == "main-new"


def test_baseline_skips_the_candidates_own_sha():
    runs = [{"id": "self", "source": "ci", "git_sha": "pr1"},
            {"id": "real", "source": "ci", "git_sha": "main1"}]
    assert _pick_baseline(runs, candidate_sha="pr1")["id"] == "real"


def test_regression_exits_nonzero_and_blocks():
    fake = FakeHistory([{"id": "b", "source": "ci", "git_sha": "main1"}], REGRESSED)
    res = run_gate(fake, RUN, suite="my-suite", git_sha="pr1")
    assert res.is_regression and res.exit_code == 1
    assert fake.compare_args == ("b", "cand")  # baseline vs candidate, in that order
    assert "blocks merge" in res.markdown and "🚩" in res.markdown


def test_clean_run_passes():
    fake = FakeHistory([{"id": "b", "source": "ci", "git_sha": "main1"}], CLEAN)
    res = run_gate(fake, RUN, suite="my-suite", git_sha="pr1")
    assert not res.is_regression and res.exit_code == 0


def test_no_baseline_does_not_block_and_says_so():
    """First-ever run of a suite: store it, don't fail the PR."""
    fake = FakeHistory([], CLEAN)  # nothing stored yet
    res = run_gate(fake, RUN, suite="my-suite", git_sha="pr1")
    assert res.verdict == "no-baseline" and res.exit_code == 0
    assert "first" in res.markdown.lower()


def test_only_prs_and_ablations_present_means_no_baseline():
    fake = FakeHistory([{"id": "p", "source": "pr", "git_sha": "z"}], CLEAN)
    res = run_gate(fake, RUN, suite="my-suite", git_sha="pr1")
    assert res.verdict == "no-baseline"   # a PR run can't be a baseline
