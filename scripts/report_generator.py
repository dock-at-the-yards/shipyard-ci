#!/usr/bin/env python3
"""
Shipyard CI Report Generator
Parses rollout trajectory files (ATIF format) and produces a clean Markdown PR summary.
"""

import os
import sys
import json
import argparse
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Generate Shipyard CI Markdown Report")
    parser.add_argument("--rollout-dir", default="rollouts", help="Directory containing eval rollouts")
    parser.add_argument("--output", default="shipyard-report.md", help="Output markdown file path")
    return parser.parse_args()

def main():
    args = parse_args()
    rollout_path = Path(args.rollout_dir)

    results = []
    total_passed = 0
    total_failed = 0
    total_score = 0.0

    if rollout_path.exists():
        for json_file in rollout_path.glob("**/*.json"):
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)
                    
                    # Check for ATIF rollout structure or summary structure
                    eval_name = data.get("eval_name") or data.get("task_id") or json_file.stem
                    status = data.get("status") or ("pass" if data.get("passed", False) else "fail")
                    score = float(data.get("score", 1.0 if status == "pass" else 0.0))
                    duration = data.get("duration", "N/A")

                    if status == "pass":
                        total_passed += 1
                    else:
                        total_failed += 1
                    total_score += score

                    results.append({
                        "name": eval_name,
                        "status": status,
                        "score": score,
                        "duration": duration
                    })
            except Exception:
                continue

    total_evals = total_passed + total_failed
    mean_score = (total_score / total_evals) if total_evals > 0 else 0.0

    # Build Markdown Summary
    lines = [
        "## ⚓ Shipyard Agent Evaluation Report",
        "",
        f"**Summary:** {total_evals} evals evaluated · **{total_passed} passed** · **{total_failed} failed** · **Mean Score: {mean_score:.2f}**",
        "",
        "| Evaluation | Status | Score | Duration |",
        "| :--- | :---: | :---: | :---: |"
    ]

    if not results:
        lines.append("| *No evaluation rollouts found* | - | - | - |")
    else:
        for r in results:
            icon = "✅ Pass" if r["status"] == "pass" else "❌ Fail"
            lines.append(f"| `{r['name']}` | {icon} | `{r['score']:.2f}` | {r['duration']} |")

    lines.append("")
    if total_failed > 0:
        lines.append("> ⚠️ **Regression Warning:** One or more agent evaluations failed rubric criteria. Review attached ATIF trajectory rollouts.")
    else:
        lines.append("> 🎉 **All agent evaluations passed deterministic rubric thresholds!**")

    content = "\n".join(lines) + "\n"
    with open(args.output, "w") as out:
        out.write(content)
    
    print(f"Generated report at {args.output}")

if __name__ == "__main__":
    main()
