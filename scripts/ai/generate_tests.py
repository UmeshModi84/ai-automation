#!/usr/bin/env python3
"""
Suggest additional Jest test cases for Node.js sources using the OpenAI API.
Writes suggestions to an artifact file and optionally posts a PR comment.
"""
from __future__ import annotations

import argparse
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


def read_sources(root: Path) -> str:
    parts: list[str] = []
    src = root / "src"
    if not src.is_dir():
        return ""
    for path in src.rglob("*.js"):
        if "node_modules" in path.parts:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parts.append(f"--- {path.relative_to(root)} ---\n{content}\n")
    return "\n".join(parts)[:120_000]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--app-root", type=Path, default=Path("app"))
    p.add_argument("--out", type=Path, default=Path("ai-generated-tests.md"))
    p.add_argument("--no-post", action="store_true")
    args = p.parse_args()

    if skip_ai_without_api_key("AI test suggestions"):
        stub = (
            "## AI-generated test ideas\n\n"
            "*(Skipped — set repository secret `OPENAI_API_KEY` to enable OpenAI suggestions.)*\n"
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(stub, encoding="utf-8")
        print(f"Wrote stub {args.out}")
        return 0

    src = read_sources(args.app_root)
    if not src.strip():
        print("No sources found under app/src", file=sys.stderr)
        return 1

    client = OpenAI()
    prompt = (
        "Given the following Node.js (CommonJS) application source, propose NEW Jest + supertest "
        "test cases that improve coverage and catch edge cases. Output markdown with:\n"
        "1) Bullet list of test scenarios\n"
        "2) One fenced javascript code block with a sample `describe`/`test` you would add "
        "(do not repeat existing trivial tests).\n"
        f"\n{src}"
    )
    resp = chat_completion(
        client,
        task_label="AI test suggestions",
        model=resolve_openai_model(),
        messages=[
            {"role": "system", "content": "You write excellent tests; be practical and minimal."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    if resp is None:
        stub = (
            "## AI-generated test ideas\n\n"
            "*(Skipped — OpenAI account hit **quota / billing** limit. "
            "Add credits: https://platform.openai.com/account/billing )*\n"
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(stub, encoding="utf-8")
        print(f"Wrote stub {args.out} (quota)")
        return 0
    text = (resp.choices[0].message.content or "").strip()
    out_body = "## AI-generated test ideas\n\n" + text
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(out_body, encoding="utf-8")
    append_step_summary(out_body)
    print(f"Wrote {args.out}")
    if not args.no_post:
        try:
            post_issue_comment(out_body)
        except Exception as e:
            print(f"Post comment failed (non-fatal): {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
