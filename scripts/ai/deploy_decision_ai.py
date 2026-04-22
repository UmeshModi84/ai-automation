#!/usr/bin/env python3
"""
Deployment gate: decide deploy | delay | rollback from signals (tests, risk, metrics).
Exit codes: 0=deploy, 2=delay, 3=rollback, 1=config/input error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from github_utils import resolve_openai_model
from structured_logging import get_logger, log_json

logger = get_logger("ai.deploy_decision")


def decide_rules(payload: dict[str, Any]) -> tuple[str, str]:
    """Return (decision, rationale) using deterministic rules first."""
    tests = payload.get("tests_passed", True)
    risk = (payload.get("risk_tier") or "low").lower()
    metrics_ok = payload.get("metrics_ok", True)
    anomaly = payload.get("anomaly_tier") or "ok"

    if not tests or risk == "high" or anomaly == "rollback_candidate":
        return "rollback", "failing_tests_or_high_risk_or_metric_anomaly"
    if risk == "medium" or anomaly == "investigate" or not metrics_ok:
        return "delay", "elevated_risk_or_metrics_or_investigate_anomaly"
    return "deploy", "all_signals_green"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-json", type=Path, help="Path to deploy_inputs.json")
    p.add_argument("--stdin", action="store_true", help="Read JSON object from stdin")
    p.add_argument("--output-json", type=Path, default=Path("ci-artifacts/deploy_decision.json"))
    p.add_argument("--stdout-json", action="store_true", help="Print decision JSON only to stdout")
    args = p.parse_args()

    if args.stdin:
        payload = json.load(sys.stdin)
    elif args.input_json and args.input_json.is_file():
        payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    else:
        print("Provide --input-json FILE or --stdin", file=sys.stderr)
        return 1

    decision, rationale = decide_rules(payload)
    out: dict[str, Any] = {
        "decision": decision,
        "rationale_rules": rationale,
        "inputs": payload,
    }

    if os.environ.get("OPENAI_API_KEY", "").strip():
        try:
            from openai import OpenAI

            from openai_chat import chat_completion
        except ImportError:
            pass
        else:
            client = OpenAI()
            resp = chat_completion(
                client,
                task_label="AI deploy decision",
                model=resolve_openai_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "You gate production deploys. Given JSON inputs, reply ONLY: "
                        '{"decision":"deploy|delay|rollback","rationale":"one sentence"}',
                    },
                    {"role": "user", "content": json.dumps(payload)[:8000]},
                ],
                temperature=0.1,
                max_tokens=256,
            )
            if resp:
                try:
                    raw = (resp.choices[0].message.content or "").strip()
                    raw = raw.removeprefix("```json").removesuffix("```").strip()
                    ai = json.loads(raw)
                    out["decision_ai"] = ai.get("decision", decision)
                    out["rationale_ai"] = ai.get("rationale", "")
                    sev = {"deploy": 0, "delay": 1, "rollback": 2}
                    ai_d = out["decision_ai"] if out["decision_ai"] in sev else decision
                    if sev[ai_d] > sev[decision]:
                        decision = ai_d
                except (json.JSONDecodeError, AttributeError, KeyError):
                    pass

    out["decision_final"] = decision
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log_json(logger, "deploy_decision", decision=decision)

    line = json.dumps({"decision": decision, "rationale": out.get("rationale_ai") or rationale})
    if args.stdout_json:
        print(line)
    else:
        print(json.dumps({"ok": True, "output": str(args.output_json), "decision": decision}))

    if decision == "rollback":
        return 3
    if decision == "delay":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
