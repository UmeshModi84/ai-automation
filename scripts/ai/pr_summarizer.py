#!/usr/bin/env python3
"""
AI PR summarizer: change summary, risk notes, affected modules. Writes JSON (+ optional markdown).
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from github_utils import resolve_openai_model
from structured_logging import get_logger, log_json

logger = get_logger("ai.pr_summarizer")


def fallback_summary(diff_text: str) -> dict:
    modules = sorted({m.group(1).split("/")[0] for m in re.finditer(r"^\+\+\+ b/([^/\n]+)", diff_text, re.M)})
    return {
        "summary": "Automated fallback: inspect diff manually.",
        "risk_analysis": "Unknown without OpenAI.",
        "affected_modules": modules or ["(none detected)"],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--diff-file", type=Path, required=True)
    p.add_argument("--output-json", type=Path, default=Path("ci-artifacts/pr_summary.json"))
    p.add_argument("--output-md", type=Path, help="Optional markdown path")
    args = p.parse_args()

    diff_text = args.diff_file.read_text(encoding="utf-8", errors="replace") if args.diff_file.is_file() else ""
    if not diff_text.strip():
        out = {**fallback_summary(""), "error": "empty_diff"}
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "output": str(args.output_json)}))
        return 0

    structured: dict
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        structured = {**fallback_summary(diff_text), "skipped": True, "reason": "no_openai_key"}
    else:
        try:
            from openai import OpenAI

            from openai_chat import chat_completion
        except ImportError:
            structured = {**fallback_summary(diff_text), "skipped": True, "reason": "openai_not_installed"}
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(json.dumps(structured, indent=2), encoding="utf-8")
            print(json.dumps({"ok": True, "output": str(args.output_json)}))
            return 0
        client = OpenAI()
        resp = chat_completion(
            client,
            task_label="AI PR summarizer",
            model=resolve_openai_model(),
            messages=[
                {
                    "role": "system",
                    "content": "Summarize a PR diff. Reply ONLY JSON keys: summary (string), "
                    "risk_analysis (string), affected_modules (array of strings).",
                },
                {"role": "user", "content": diff_text[:100_000]},
            ],
            temperature=0.2,
            max_tokens=2048,
        )
        if resp is None:
            structured = fallback_summary(diff_text)
            structured["skipped"] = True
        else:
            raw = (resp.choices[0].message.content or "").strip()
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                structured = json.loads(raw)
            except json.JSONDecodeError:
                log_json(logger, "pr_summary_parse_failed", raw=raw[:400])
                structured = fallback_summary(diff_text)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(structured, indent=2), encoding="utf-8")
    if args.output_md:
        md = (
            f"## PR summary\n\n{structured.get('summary', '')}\n\n"
            f"## Risk\n\n{structured.get('risk_analysis', '')}\n\n"
            f"## Modules\n\n"
            + "\n".join(f"- `{m}`" for m in structured.get("affected_modules") or [])
        )
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(md, encoding="utf-8")

    log_json(logger, "pr_summarizer_done", path=str(args.output_json))
    print(json.dumps({"ok": True, "output": str(args.output_json)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
