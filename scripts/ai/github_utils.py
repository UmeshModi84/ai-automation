"""Post comments to GitHub PRs/issues using the REST API."""
from __future__ import annotations

import os
import sys
from typing import Any

import requests


def resolve_openai_model(default: str = "gpt-4o-mini") -> str:
    """OPENAI_MODEL from env/vars; empty string must fall back (GitHub `vars` can be set but blank)."""
    raw = (os.environ.get("OPENAI_MODEL") or "").strip()
    return raw if raw else default


def skip_ai_without_api_key(task_label: str) -> bool:
    """
    If OPENAI_API_KEY is unset, log a GitHub Actions annotation and summary; return True so the
    caller can exit 0 and avoid failing the workflow (optional AI until the secret is added).
    """
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return False
    msg = (
        f"{task_label} skipped: OPENAI_API_KEY is not set. "
        "Add repository secret OPENAI_API_KEY (Settings → Secrets and variables → Actions)."
    )
    print(f"::warning::{msg}", flush=True)
    append_step_summary(f"### {task_label} (skipped)\n\n{msg}\n")
    return True


def post_issue_comment(body: str) -> dict[str, Any]:
    """Post a comment on the PR (issue) for the current workflow run."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    pr = os.environ.get("PR_NUMBER") or os.environ.get("GITHUB_EVENT_PULL_REQUEST_NUMBER")
    if not token or not repo or not pr:
        print("Missing GITHUB_TOKEN, GITHUB_REPOSITORY, or PR_NUMBER — skipping comment.", file=sys.stderr)
        return {}
    owner, name = repo.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{name}/issues/{pr}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    r = requests.post(url, headers=headers, json={"body": body}, timeout=60)
    r.raise_for_status()
    return r.json()


def append_step_summary(markdown: str) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    with open(summary, "a", encoding="utf-8") as f:
        f.write(markdown)
        if not markdown.endswith("\n"):
            f.write("\n")
