"""A thin client for an eval-history service.

The whole product sits on top of [eval-history](https://github.com/egnaro9/eval-history):
it already stores eval runs, keeps them per suite, and compares two of them into a
regression verdict. prompt-regress adds the missing piece — *do that automatically
on a pull request, against the main-branch baseline, and block the merge if it
regressed* — which is the gap promptfoo leaves open (it doesn't store history or
compare across runs).

stdlib `urllib` only, so the gate has no dependency to install in CI. The client
is an interface, not a hardcoded call site, so the gate logic is tested against a
fake without a network.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import List, Optional, Protocol


class EvalHistory(Protocol):
    def post_run(self, run: dict, source: str, git_sha: Optional[str], label: Optional[str]) -> dict: ...
    def list_runs(self, suite: str, limit: int = 50) -> List[dict]: ...
    def compare(self, baseline_id: str, candidate_id: str) -> dict: ...


class HttpError(RuntimeError):
    pass


class HttpEvalHistory:
    """The real client, over HTTP."""

    def __init__(self, base_url: str, write_key: str = "", timeout: int = 90) -> None:
        self.base = base_url.rstrip("/")
        self.key = write_key
        self.timeout = timeout

    def _get(self, path: str):
        req = urllib.request.Request(f"{self.base}{path}", headers={"Accept": "application/json"})
        return self._send(req)

    def _send(self, req):
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise HttpError(f"{req.get_method()} {req.full_url} -> {e.code}: {e.read().decode()[:200]}")
        except urllib.error.URLError as e:
            raise HttpError(f"could not reach eval-history at {self.base} ({e.reason}) — "
                            "it's a free tier that may be waking up")

    def post_run(self, run, source, git_sha, label):
        payload = dict(run, source=source)
        if git_sha:
            payload["git_sha"] = git_sha[:40]
        if label:
            payload["label"] = label[:200]
        req = urllib.request.Request(
            f"{self.base}/runs", data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
        return self._send(req)

    def list_runs(self, suite, limit=50):
        from urllib.parse import quote
        return self._get(f"/runs?name={quote(suite)}&limit={limit}")

    def compare(self, baseline_id, candidate_id):
        return self._get(f"/runs/{baseline_id}/compare/{candidate_id}")


class ArchiveReadOnly(RuntimeError):
    """Raised when a write is attempted against the static archive."""


class ArchiveEvalHistory:
    """A read-only client for eval-history's STATIC ARCHIVE.

    The hosted service was retired (Render suspended it over an unpaid invoice);
    its read routes now live as files that mirror the API paths exactly, with a
    `.json` suffix, at https://erikhill.dev/eval-history/. See eval-history's
    `tools/export_static.py`. Two of the three interface methods answer from
    those files:

        list_runs  -> runs.json, filtered by suite here rather than server-side
        compare    -> runs/<a>/compare/<b>.json (a pure function of two runs,
                      exported by the same code that served it live)

    `post_run` cannot work: storing a run was the one genuinely-lost route. The
    gate calls it first, so it raises rather than pretending the run was kept.
    """

    def __init__(self, base_url: str, timeout: int = 30) -> None:
        self.base = base_url.rstrip("/")
        if self.base.endswith("/runs.json"):
            self.base = self.base[: -len("/runs.json")]
        self.timeout = timeout

    def _get(self, path: str):
        req = urllib.request.Request(f"{self.base}{path}", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise HttpError(f"GET {req.full_url} -> {e.code}")
        except urllib.error.URLError as e:
            raise HttpError(f"could not reach the archive at {self.base} ({e.reason})")

    def post_run(self, run, source, git_sha, label):
        raise ArchiveReadOnly(
            f"{self.base} is the static eval-history archive: it can be read but not written to. "
            "Point --api at a live eval-history deployment to store runs."
        )

    def list_runs(self, suite, limit=50):
        rows = [r for r in self._get("/runs.json") if r.get("name") == suite]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]

    def compare(self, baseline_id, candidate_id):
        return self._get(f"/runs/{baseline_id}/compare/{candidate_id}.json")


def client_for(base_url: str, write_key: str = "", timeout: int = 90):
    """Pick the right client for a URL: the static archive is read-only."""
    u = base_url.rstrip("/")
    if u.endswith(".json") or "/eval-history" in u:
        return ArchiveEvalHistory(u, timeout=min(timeout, 30))
    return HttpEvalHistory(u, write_key=write_key, timeout=timeout)
