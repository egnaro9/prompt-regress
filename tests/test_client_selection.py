"""The archive is read-only, and a URL alone decides which client you get.

eval-history's hosted instance was retired; its read routes survive as static
files. A gate pointed at the archive must compare happily and refuse to pretend
it stored anything.
"""
import pytest

from promptregress.client import (
    ArchiveEvalHistory,
    ArchiveReadOnly,
    HttpEvalHistory,
    client_for,
)


@pytest.mark.parametrize("url", [
    "https://erikhill.dev/eval-history/",
    "https://erikhill.dev/eval-history",
    "https://erikhill.dev/eval-history/runs.json",
])
def test_archive_urls_get_the_read_only_client(url):
    assert isinstance(client_for(url), ArchiveEvalHistory)


@pytest.mark.parametrize("url", [
    "https://my-eval-history.fly.dev",
    "http://localhost:8000",
])
def test_everything_else_gets_the_http_client(url):
    assert isinstance(client_for(url, write_key="k"), HttpEvalHistory)


def test_runs_json_suffix_is_stripped_so_paths_still_mirror_the_api():
    c = ArchiveEvalHistory("https://erikhill.dev/eval-history/runs.json")
    assert c.base == "https://erikhill.dev/eval-history"


def test_storing_into_the_archive_raises_rather_than_lying():
    c = ArchiveEvalHistory("https://erikhill.dev/eval-history/")
    with pytest.raises(ArchiveReadOnly) as e:
        c.post_run({"run": "x"}, source="ci", git_sha=None, label=None)
    assert "not written to" in str(e.value)
    assert "erikhill.dev/eval-history" in str(e.value)
