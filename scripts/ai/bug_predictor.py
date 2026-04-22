#!/usr/bin/env python3
"""
AI / heuristic bug predictor: estimates change risk from a git diff or file list.
Outputs JSON with risk tier (low | medium | high) and numeric score.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from github_utils import resolve_openai_model
from structured_logging import get_logger, log_json

logger = get_logger("ai.bug_predictor")

HIGH_RISK_PATTERNS = (
    r"eval\s*\(",
    r"child_process",
    r"exec\s*\(",
    r"password\s*[:=]",
    r"BEGIN (RSA |OPENSSH )?PRIVATE KEY",
    r"process\.env\.\w+\s*\+",  # naive concat env
)
RISK_PATHS = ("auth", "security", "payment", "crypto", "deploy", "terraform", ".github/workflows")


def heuristic_risk(diff_text: str, changed_files: list[str]) -> tuple[str, float, list[str]]:
    """
    Return (tier, score_0_1, reasons) using cheap heuristics when OpenAI is unavailable.
    """
    reasons: list[str] = []
    score = 0.15
    text = diff_text.lower()
    if len(diff_text) > 50_000:
        score += 0.15
        reasons.append("large_diff")
    for pat in HIGH_RISK_PATTERNS:
        if re.search(pat, diff_text, re.I):
            score += 0.2
            reasons.append(f"pattern:{pat[:40]}")
    for f in changed_files:
        fl = f.lower()
        if any(k in fl for k in RISK_PATHS):
            score += 0.12
            reasons.append(f"sensitive_path:{f}")
    if any("test" not in f for f in changed_files) and any(f.endswith(".js") for f in changed_files):
        if not any("test" in f for f in changed_files):
            score += 0.05
            reasons.append("no_test_files_touched")
    score = min(1.0, score)
    if score >= 0.65:
        tier = "high"
    elif score >= 0.35:
        tier = "medium"
    else:
        tier = "low"
    return tier, round(score, 3), reasons


def openai_risk(diff_text: str) -> dict | None:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        return None
    try:
        from openai import OpenAI

        from openai_chat import chat_completion
    except ImportError:
        return None
    client = OpenAI()
    snippet = diff_text[:60_000]
    resp = chat_completion(
        client,
        task_label="AI bug predictor",
        model=resolve_openai_model(),
        messages=[
            {
                "role": "system",
                "content": "You assess regression risk from a unified diff. Reply with ONLY compact JSON: "
                '{"risk_tier":"low|medium|high","risk_score":0.0-1.0,"reasons":["..."]}',
            },
            {"role": "user", "content": f"Diff:\n```diff\n{snippet}\n```"},
        ],
        temperature=0.1,
        max_tokens=512,
    )
    if resp is None:
        return None
    raw = (resp.choices[0].message.content or "").strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log_json(logger, "openai_json_parse_failed", raw=raw[:500])
        return None


def main() -> int:
    p = argparse.ArgumentParser(description="Predict failure risk from diff / changed files.")
    p.add_argument("--diff-file", type=Path, default=Path("ci-artifacts/diff.txt"))
    p.add_argument("--changed-files", type=Path, help="Optional newline-separated paths")
    p.add_argument("--output-json", type=Path, default=Path("ci-artifacts/bug_predict.json"))
    p.add_argument("--fail-on-high", action="store_true", help="Exit 1 if risk_tier is high")
    args = p.parse_args()

    diff_text = ""
    if args.diff_file.is_file():
        diff_text = args.diff_file.read_text(encoding="utf-8", errors="replace")
    changed: list[str] = []
    if args.changed_files and args.changed_files.is_file():
        changed = [ln.strip() for ln in args.changed_files.read_text().splitlines() if ln.strip()]
    if not changed and diff_text:
        changed = list({m.group(1) for m in re.finditer(r"^\+\+\+ b/(.+)$", diff_text, re.M)})

    tier_h, score_h, reasons_h = heuristic_risk(diff_text, changed)
    result: dict = {
        "source": "heuristic",
        "risk_tier": tier_h,
        "risk_score": score_h,
        "reasons": reasons_h,
        "changed_files_count": len(changed),
    }

    ai = openai_risk(diff_text) if diff_text.strip() else None
    if isinstance(ai, dict) and "risk_tier" in ai:
        result["source"] = "heuristic+openai"
        result["risk_tier"] = ai.get("risk_tier", tier_h)
        try:
            result["risk_score"] = float(ai.get("risk_score", score_h))
        except (TypeError, ValueError):
            result["risk_score"] = score_h
        result["reasons"] = list(dict.fromkeys(reasons_h + list(ai.get("reasons") or [])))

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log_json(logger, "bug_predict_complete", **result)
    print(json.dumps({"ok": True, "output": str(args.output_json), **result}))
    if args.fail_on_high and result.get("risk_tier") == "high":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
