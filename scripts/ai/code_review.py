#!/usr/bin/env python3
"""
AI-assisted PR review: reads a unified diff (or file list) and posts a structured review.
Requires: OPENAI_API_KEY, GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER (for posting).
"""
from __future__ import annotations

import argparse
import os
import sys

from openai import OpenAI

from github_utils import append_step_summary, post_issue_comment, skip_ai_without_api_key


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("diff_file", nargs="?", default="diff.txt", help="Path to unified diff")
    p.add_argument("--no-post", action="store_true", help="Print only; do not post to GitHub")
    args = p.parse_args()

    if skip_ai_without_api_key("AI code review"):
        return 0

    try:
        with open(args.diff_file, encoding="utf-8", errors="replace") as f:
            diff = f.read()
    except OSError as e:
        print(f"Cannot read diff: {e}", file=sys.stderr)
        return 1

    if len(diff) > 100_000:
        diff = diff[:100_000] + "\n\n[truncated for model context]"

    client = OpenAI()
    system = (
        "You are a senior staff engineer doing code review. "
        "Focus on correctness, security, performance, and maintainability. "
        "Be concise. Use markdown with ### sections: Summary, Bugs & Risks, "
        "Suggestions, Tests. If the diff is empty, say so briefly."
    )
    user = f"Review this pull request diff:\n\n```diff\n{diff}\n```"

    resp = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=4096,
    )
    text = (resp.choices[0].message.content or "").strip()
    body = "## AI code review\n\n" + text

    append_step_summary(body)
    print(body)
    if not args.no_post:
        try:
            post_issue_comment(body)
        except Exception as e:
            print(f"Post comment failed (non-fatal): {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
