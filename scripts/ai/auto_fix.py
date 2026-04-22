#!/usr/bin/env python3
"""
Attempt automatic fixes (eslint --fix) and write a patch file for review or PR automation.
Does not push by default — wire to `create-pull-request` action in CI for optional auto-fix flow.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--app-dir", type=Path, default=Path("app"))
    p.add_argument("--patch-out", type=Path, default=Path("auto-fix.patch"))
    args = p.parse_args()

    app = args.app_dir.resolve()
    if not (app / "package.json").is_file():
        print(f"No package.json in {app}", file=sys.stderr)
        return 1

    # Install deps if needed (CI usually did this already)
    code, log = run(["npm", "install"], app)
    if code != 0:
        print(log, file=sys.stderr)
        return code

    code, log = run(["npm", "run", "lint:fix"], app)
    print(log)
    if code != 0:
        print("lint:fix failed — may need manual fixes", file=sys.stderr)

    code, diff_out = run(["git", "diff", "--", "app/"], Path.cwd())
    if code != 0:
        print(diff_out, file=sys.stderr)
        return code

    if not diff_out.strip():
        print("No automatic fixes applied.")
        return 0

    args.patch_out.write_text(diff_out, encoding="utf-8")
    print(f"Wrote {args.patch_out}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Auto-fix\n\nESLint auto-fix produced changes — see `auto-fix.patch` artifact.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
