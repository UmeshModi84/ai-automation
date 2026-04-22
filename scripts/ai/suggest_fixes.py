#!/usr/bin/env python3
"""
Explain CI/build failures and suggest fixes from a log file (stdout/stderr capture).
"""
from __future__ import annotations

import argparse
import os
import sys

from openai import OpenAI

from github_utils import append_step_summary, post_issue_comment, skip_ai_without_api_key


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("log_file", help="Path to build/CI log")
    p.add_argument("--title", default="AI suggestions for failed build")
    p.add_argument("--post-pr", action="store_true", help="Post as PR comment when PR_NUMBER set")
    args = p.parse_args()

    if skip_ai_without_api_key("AI failure analysis"):
        return 0

    try:
        with open(args.log_file, encoding="utf-8", errors="replace") as f:
            log = f.read()
    except OSError as e:
        print(e, file=sys.stderr)
        return 1

    client = OpenAI()
    user = (
        "The following is output from a failed CI/build step. "
        "Summarize the root cause in 2-4 bullets, then list concrete fix steps "
        "(commands, config changes, dependency pins). Use markdown.\n\n```\n"
        + log[:80_000]
        + "\n```"
    )
    resp = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": "You are a DevOps engineer helping debug CI failures."},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=4096,
    )
    text = (resp.choices[0].message.content or "").strip()
    body = f"## {args.title}\n\n{text}"
    append_step_summary(body)
    print(body)
    if args.post_pr and os.environ.get("PR_NUMBER"):
        try:
            post_issue_comment(body)
        except Exception as e:
            print(f"Post failed: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
