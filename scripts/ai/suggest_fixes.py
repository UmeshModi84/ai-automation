#!/usr/bin/env python3
"""
Explain CI/build failures and suggest fixes from a log file (stdout/stderr capture).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from openai import OpenAI

from openai_chat import chat_completion
from github_utils import (
    append_step_summary,
    post_issue_comment,
    resolve_openai_model,
    skip_ai_without_api_key,
)
from structured_logging import get_logger, log_json

logger = get_logger("ai.suggest_fixes")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("log_file", help="Path to build/CI log")
    p.add_argument("--title", default="AI suggestions for failed build")
    p.add_argument("--post-pr", action="store_true", help="Post as PR comment when PR_NUMBER set")
    p.add_argument("--output-json", type=Path, default=Path("ci-artifacts/suggest_fixes.json"))
    args = p.parse_args()

    if skip_ai_without_api_key("AI failure analysis"):
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps({"status": "skipped"}, indent=2), encoding="utf-8")
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
    resp = chat_completion(
        client,
        task_label="AI failure analysis",
        model=resolve_openai_model(),
        messages=[
            {"role": "system", "content": "You are a DevOps engineer helping debug CI failures."},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=4096,
    )
    if resp is None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps({"status": "skipped_quota"}, indent=2), encoding="utf-8")
        return 0
    text = (resp.choices[0].message.content or "").strip()
    body = f"## {args.title}\n\n{text}"
    record = {
        "status": "ok",
        "title": args.title,
        "root_cause_markdown": text,
        "log_bytes": min(len(log), 80_000),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(record, indent=2), encoding="utf-8")
    log_json(logger, "suggest_fixes_done", path=str(args.output_json))
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
