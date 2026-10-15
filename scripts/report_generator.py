#!/usr/bin/env python3
"""
Shipyard CI Report Generator.

Renders the Markdown summary used for PR comments, job summaries and local
inspection from the v0.0.2 run artifacts:

  * a suite ``results.json`` (``--results``), written by
    ``shipyard run --report markdown,json,junit`` to
    ``<target>/rollouts/<run-id>/results.json``; or
  * a legacy scan of a ``rollouts/`` tree for per-rollout ``metrics.json``
    files (``--rollout-dir``). Only ``metrics.json`` files are read -- never
    rubrics, trajectories or conversations.

Optional extras:

  * ``--compare shipyard-compare.json`` renders the delta table from the
    ``shipyard compare --json`` output (the gate's own decision).
  * ``--baseline baselines/main.json`` renders an informational delta when no
    compare file is available.
  * ``--junit-file path`` writes JUnit XML mirroring the CLI's report: one
    testsuite per eval, one testcase per repeat, ``failure`` for failed and
    ``error`` for errored repeats.

Gating is ``shipyard compare``'s job: this script always exits 0.
"""

import argparse
import json
import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

VERDICT_EMOJI = {
    "passed": "\u2705",
    "failed": "\u274c",
    "flaked": "\U0001f3b2",
    "errored": "\u26a0\ufe0f",
}

STATUS_EMOJI = {
    "improved": "\U0001f7e2",
    "same": "\u26aa",
    "regressed": "\U0001f534",
    "flaked": "\U0001f3b2",
    "errored": "\u26a0\ufe0f",
    "skipped": "\u23ed\ufe0f",
}

KNOWN_VERDICTS = tuple(VERDICT_EMOJI)

# Fallbacks kept out of f-string expressions for compatibility with older Python.
EMOJI_UNKNOWN = "\u2754"
EMOJI_STATUS_DEFAULT = "\u26aa"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate the Shipyard CI report")
    parser.add_argument(
        "--rollout-dir",
        default="rollouts",
        help="Directory containing eval rollouts (legacy fallback: scans for metrics.json only)",
    )
    parser.add_argument(
        "--results",
        default="",
        help="Path to a suite results.json (preferred over --rollout-dir)",
    )
    parser.add_argument(
        "--baseline",
        default="",
        help="Path to a baseline JSON for an informational delta table",
    )
    parser.add_argument(
        "--compare",
        default="",
        help="Path to a `shipyard compare --json` report; renders its delta table",
    )
    parser.add_argument(
        "--junit-file",
        default="",
        help="Write JUnit XML to this path",
    )
    parser.add_argument(
        "--output",
        default="shipyard-report.md",
        help="Output markdown file path ('-' prints to stdout)",
    )
    return parser.parse_args()


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001 - a bad input must not fail CI
        print(f"report_generator: could not read {path}: {exc}", file=sys.stderr)
        return None


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def pick_float(primary, fallback):
    return to_float(primary) if primary is not None else fallback


def explicit_verdict(value):
    verdict = str(value or "").strip().lower()
    return verdict if verdict in KNOWN_VERDICTS else ""


def short_digest(digest):
    digest = str(digest or "").removeprefix("sha256:")
    if len(digest) > 12:
        return digest[:12]
    return digest or "\u2014"


def first_line(text):
    text = str(text or "")
    line = text.splitlines()[0] if text else ""
    return line[:200]


def xml_escape(value):
    return _xml_escape(str(value), {'"': "&quot;", "'": "&apos;"})


# --------------------------------------------------------------------------- #
# Normalization: results.json, metrics.json, aggregation
# --------------------------------------------------------------------------- #

def aggregate_repeats(repeats):
    """Mirror of shipyard-core's stats.Aggregate over repeats."""
    k = len(repeats)
    passed = sum(1 for r in repeats if r["verdict"] == "passed")
    errored = sum(1 for r in repeats if r["verdict"] == "errored")
    failed = k - passed - errored
    scores = [r["score"] for r in repeats]
    mean = sum(scores) / k if k else 0.0
    sigma = 0.0
    if k > 1:
        variance = sum((s - mean) ** 2 for s in scores) / (k - 1)
        sigma = math.sqrt(variance)
    if errored:
        verdict = "errored"
    elif passed and failed:
        verdict = "flaked"
    elif k and passed == k:
        verdict = "passed"
    else:
        verdict = "failed"
    return {
        "k": k,
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "verdict": verdict,
        "pass_at_k": 1.0 if passed else 0.0,
        "pass_pow_k": 1.0 if k and passed == k else 0.0,
        "mean": mean,
        "sigma": sigma,
    }


def add_usage(total, usage):
    """Sum usage honestly: cost only when both sides report one."""
    if not usage:
        return total
    if total is None:
        return {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "cost_usd": usage.get("cost_usd"),
            "partial": True,
        }
    total = dict(total)
    total["input_tokens"] = int(total.get("input_tokens") or 0) + int(usage.get("input_tokens") or 0)
    total["output_tokens"] = int(total.get("output_tokens") or 0) + int(usage.get("output_tokens") or 0)
    total["total_tokens"] = int(total.get("total_tokens") or 0) + int(usage.get("total_tokens") or 0)
    if total.get("cost_usd") is not None and usage.get("cost_usd") is not None:
        total["cost_usd"] = to_float(total["cost_usd"]) + to_float(usage["cost_usd"])
    else:
        total["cost_usd"] = None
        total["partial"] = True
    return total


def normalize_repeat(raw, index):
    return {
        "index": int(raw.get("repeat_index") or index),
        "verdict": explicit_verdict(raw.get("verdict"))
        or ("passed" if raw.get("passed") else "failed"),
        "score": to_float(raw.get("score")),
        "duration_ms": int(raw.get("duration_ms") or 0),
        "rollout_dir": raw.get("rollout_dir") or "",
        "error_kind": raw.get("error_kind") or "",
        "error": raw.get("error") or "",
        "usage": raw.get("usage") or None,
    }


def normalize_eval(raw):
    repeats = [normalize_repeat(r, i) for i, r in enumerate(raw.get("repeats") or [])]
    agg = aggregate_repeats(repeats)
    usage = raw.get("usage") or None
    if usage is None:
        for repeat in repeats:
            usage = add_usage(usage, repeat.get("usage"))
    return {
        "name": raw.get("eval_name") or raw.get("name") or "(unnamed)",
        "path": raw.get("path") or "",
        "k": int(raw.get("k") or 0) or agg["k"],
        "verdict": explicit_verdict(raw.get("verdict")) or agg["verdict"],
        "pass_at_k": pick_float(raw.get("pass_at_k"), agg["pass_at_k"]),
        "pass_pow_k": pick_float(raw.get("pass_pow_k"), agg["pass_pow_k"]),
        "mean": pick_float(raw.get("mean_score"), agg["mean"]),
        "sigma": pick_float(raw.get("sigma_score"), agg["sigma"]),
        "usage": usage,
        "repeats": repeats,
        "failed_count": int(raw["failed_count"]) if raw.get("failed_count") is not None else agg["failed"],
        "errored_count": int(raw["errored_count"]) if raw.get("errored_count") is not None else agg["errored"],
    }


def aggregate_verdict(evals):
    verdicts = {e["verdict"] for e in evals}
    if not verdicts:
        return "unknown"
    if "errored" in verdicts:
        return "errored"
    if "flaked" in verdicts:
        return "flaked"
    if verdicts == {"passed"}:
        return "passed"
    return "failed"


def compute_totals(evals):
    counts = {"passed": 0, "failed": 0, "flaked": 0, "errored": 0}
    usage = None
    mean = 0.0
    for ev in evals:
        if ev["verdict"] in counts:
            counts[ev["verdict"]] += 1
        usage = add_usage(usage, ev.get("usage"))
        mean += ev["mean"]
    if evals:
        mean /= len(evals)
    return {
        "passed": counts["passed"],
        "failed": counts["failed"],
        "flaked": counts["flaked"],
        "errored": counts["errored"],
        "mean": mean,
        "usage": usage,
    }


def load_results(path):
    suite = read_json(path) or {}
    evals = [normalize_eval(e) for e in suite.get("evals") or []]
    raw_totals = suite.get("totals") or {}
    totals = compute_totals(evals) if not raw_totals else {
        "passed": int(raw_totals.get("passed") or 0),
        "failed": int(raw_totals.get("failed") or 0),
        "flaked": int(raw_totals.get("flaked") or 0),
        "errored": int(raw_totals.get("errored") or 0),
        "mean": to_float(raw_totals.get("mean_score")),
        "usage": raw_totals.get("usage") or None,
    }
    return {
        "target_name": suite.get("target_name") or suite.get("target_type") or "eval",
        "run_id": suite.get("run_id") or "",
        "k": int(suite.get("k") or 0) or max((e["k"] for e in evals), default=1),
        "suite_digest": suite.get("suite_digest") or "",
        "verdict": explicit_verdict(suite.get("verdict")) or aggregate_verdict(evals),
        "totals": totals,
        "evals": evals,
    }


def repeat_from_metrics(data, index):
    verdict = explicit_verdict(data.get("verdict"))
    if not verdict:
        status = str(data.get("status") or "").lower()
        kind = str(data.get("error_kind") or "").lower()
        if data.get("passed"):
            verdict = "passed"
        elif status in ("timeout", "error", "failed") or kind in ("infra", "rubric"):
            verdict = "errored"
        else:
            verdict = "failed"
    return {
        "index": int(data.get("repeat_index") or index),
        "verdict": verdict,
        "score": to_float(data.get("score")),
        "duration_ms": int(data.get("duration_ms") or 0),
        "rollout_dir": str(data.get("rollout_dir") or ""),
        "error_kind": data.get("error_kind") or "",
        "error": data.get("error") or "",
        "usage": data.get("usage") or None,
    }


def load_metrics(rollout_dir):
    root = Path(rollout_dir)
    per_eval = {}
    if root.is_dir():
        # ONLY metrics.json: rubrics/trajectory/conversation files are not
        # per-repeat verdicts and must never be counted as evals.
        for metrics_file in sorted(root.rglob("metrics.json")):
            data = read_json(metrics_file)
            if not isinstance(data, dict):
                continue
            name = data.get("eval_name") or metrics_file.parent.name
            per_eval.setdefault(name, []).append(repeat_from_metrics(data, len(per_eval[name])))
    evals = []
    for name in sorted(per_eval):
        repeats = sorted(per_eval[name], key=lambda r: r["index"])
        agg = aggregate_repeats(repeats)
        usage = None
        for repeat in repeats:
            usage = add_usage(usage, repeat.get("usage"))
        evals.append({
            "name": name,
            "path": "",
            "k": agg["k"],
            "verdict": agg["verdict"],
            "pass_at_k": agg["pass_at_k"],
            "pass_pow_k": agg["pass_pow_k"],
            "mean": agg["mean"],
            "sigma": agg["sigma"],
            "usage": usage,
            "repeats": repeats,
            "failed_count": agg["failed"],
            "errored_count": agg["errored"],
        })
    return {
        "target_name": root.resolve().name if root.is_dir() else "eval",
        "run_id": "",
        "k": max((e["k"] for e in evals), default=1),
        "suite_digest": "",
        "verdict": aggregate_verdict(evals),
        "totals": compute_totals(evals),
        "evals": evals,
    }


def empty_model():
    return {
        "target_name": "eval",
        "run_id": "",
        "k": 1,
        "suite_digest": "",
        "verdict": "unknown",
        "totals": {"passed": 0, "failed": 0, "flaked": 0, "errored": 0, "mean": 0.0, "usage": None},
        "evals": [],
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def usage_line(usage):
    if not usage:
        return "n/a (harness did not report tokens)"
    parts = [
        f"{int(usage.get('input_tokens') or 0)} in / "
        f"{int(usage.get('output_tokens') or 0)} out tokens"
    ]
    if usage.get("cost_usd") is not None:
        parts.append(f"~${to_float(usage.get('cost_usd')):.4f} (est.)")
    if usage.get("partial"):
        parts.append("partial")
    return " \u00b7 ".join(parts)


def eval_cost_line(usage):
    if not usage:
        return "n/a"
    if usage.get("cost_usd") is not None:
        prefix = "\u2265" if usage.get("partial") else ""
        return f"{prefix}~${to_float(usage.get('cost_usd')):.4f} (est.)"
    tokens = int(usage.get("total_tokens") or 0)
    if not tokens:
        tokens = int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)
    return f"{tokens} tok" if tokens else "n/a"


def render_delta(report):
    """Delta table from a `shipyard compare --json` report (gate-accurate)."""
    lines = []
    title = report.get("baseline_name") or "baseline"
    parts = []
    if report.get("baseline_created_at"):
        parts.append(f"created {str(report['baseline_created_at'])[:10]}")
    if report.get("baseline_run_id"):
        parts.append(f"run `{report['baseline_run_id']}`")
    suffix = f" ({', '.join(parts)})" if parts else ""
    lines.append(f"### delta vs baseline `{title}`{suffix}")
    lines.append("")
    lines.append("| eval | status | baseline | candidate | delta | noise margin | cost |")
    lines.append("| :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
    for ev in report.get("evals") or []:
        status = str(ev.get("status") or "same")
        margin = "\u2014"
        if to_float(ev.get("noise_margin_pct")):
            margin = f"\u00b1{to_float(ev.get('noise_margin_pct')):.1f}%"
        elif to_float(ev.get("noise_margin_abs")):
            margin = f"\u00b1{to_float(ev.get('noise_margin_abs')):.3f}"
        cost = "\u2014"
        if ev.get("cost_delta_pct") is not None:
            cost = f"{to_float(ev.get('cost_delta_pct')):+.1f}%"
        lines.append(
            f"| `{ev.get('name', '?')}` | {STATUS_EMOJI.get(status, EMOJI_STATUS_DEFAULT)} {status} "
            f"| {to_float(ev.get('baseline_score')):.2f} | {to_float(ev.get('candidate_score')):.2f} "
            f"| {to_float(ev.get('delta')):+.2f} | {margin} | {cost} |"
        )
    lines.append("")
    if report.get("blocked"):
        blocked = ", ".join(report.get("blocked_evals") or []) or "(suite)"
        lines.append(f"**BLOCKED**: {blocked}")
    else:
        lines.append("**gate passed**")
    lines.append("")
    reasons = [
        f"- `{ev.get('name')}`: {ev['reason']}"
        for ev in report.get("evals") or []
        if ev.get("blocks") and ev.get("reason")
    ]
    if reasons:
        lines.extend(reasons)
        lines.append("")
    if report.get("suite_mismatch_note"):
        lines.append(f"> \u26a0\ufe0f {report['suite_mismatch_note']}")
        lines.append("")
    if report.get("refusal"):
        lines.append("> \u26a0\ufe0f suite-definition mismatch: compare refused to gate.")
        for refusal_line in str(report["refusal"]).splitlines():
            lines.append(f"> {refusal_line}")
        lines.append("")
    return "\n".join(lines) + "\n"


def baseline_status(base_verdict, cand_verdict, present):
    if not present:
        return "skipped"
    if cand_verdict == "errored":
        return "errored"
    if cand_verdict == "flaked":
        return "flaked"
    if base_verdict == "passed" and cand_verdict == "failed":
        return "regressed"
    if base_verdict in ("failed", "flaked") and cand_verdict == "passed":
        return "improved"
    return "same"


def render_baseline_delta(model, baseline):
    """Informational delta: no policy, no noise margin, no gate decision."""
    name = baseline.get("name") or "baseline"
    by_name = {}
    for ev in baseline.get("evals") or []:
        by_name[ev.get("eval_name") or ev.get("name") or "?"] = ev
    lines = [
        f"### delta vs baseline `{name}` (informational \u2014 `shipyard compare` is the gate)",
        "",
        "| eval | status | baseline | candidate | delta |",
        "| :--- | :--- | ---: | ---: | ---: |",
    ]
    if not model["evals"]:
        lines.append("| *No evaluation rollouts found* | - | - | - | - |")
    for ev in model["evals"]:
        base = by_name.get(ev["name"])
        base_score = to_float((base or {}).get("mean_score")) if base else 0.0
        delta = ev["mean"] - base_score if base else 0.0
        base_verdict = explicit_verdict((base or {}).get("verdict"))
        status = baseline_status(base_verdict, ev["verdict"], base is not None)
        lines.append(
            f"| `{ev['name']}` | {STATUS_EMOJI.get(status, EMOJI_STATUS_DEFAULT)} {status} "
            f"| {base_score:.2f} | {ev['mean']:.2f} | {delta:+.2f} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def conclusion_note(verdict):
    notes = {
        "passed": "> \U0001f389 All evals passed their rubric thresholds.",
        "failed": "> \u26a0\ufe0f One or more evals failed rubric criteria. Review the rollout artifacts.",
        "flaked": "> \U0001f3b2 Repeat outcomes disagreed (flake). The delta gate blocks flakes by default.",
        "errored": "> \u26a0\ufe0f Infra errors (never agent failures) failed this run closed.",
    }
    return notes.get(verdict, "> \u26a0\ufe0f No evaluation rollouts were found; nothing to report.")


def render_markdown(model, comparison=None, baseline=None):
    lines = []
    verdict = model["verdict"]
    emoji = VERDICT_EMOJI.get(verdict, EMOJI_UNKNOWN)
    lines.append(f"## {emoji} shipyard report \u2014 `{model['target_name']}`")
    lines.append("")
    meta = [f"**Verdict: {verdict.upper()}**"]
    if model["run_id"]:
        meta.append(f"run `{model['run_id']}`")
    meta.append(f"k={model['k']}")
    if model["suite_digest"]:
        meta.append(f"digest `{short_digest(model['suite_digest'])}`")
    lines.append(" \u00b7 ".join(meta))
    lines.append("")

    totals = model["totals"]
    lines.append(
        f"- evals: **{totals['passed']} passed**, {totals['failed']} failed, "
        f"{totals['flaked']} flaked, {totals['errored']} errored"
    )
    lines.append(f"- mean score: {totals['mean']:.2f}")
    lines.append(f"- usage: {usage_line(totals.get('usage'))}")
    lines.append("")

    if comparison:
        lines.append(render_delta(comparison))
    elif baseline:
        lines.append(render_baseline_delta(model, baseline))

    lines.append("| eval | verdict | k | pass@k | pass^k | mean \u00b1 \u03c3 | cost |")
    lines.append("| :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
    if not model["evals"]:
        lines.append("| *No evaluation rollouts found* | - | - | - | - | - | - |")
    for ev in model["evals"]:
        note = ""
        if ev["verdict"] == "flaked":
            passed = sum(1 for r in ev["repeats"] if r["verdict"] == "passed")
            note = f" ({passed}/{ev['k']} passed)"
        elif ev["verdict"] == "errored":
            note = " (infra)"
        emoji = VERDICT_EMOJI.get(ev["verdict"], EMOJI_UNKNOWN)
        lines.append(
            f"| `{ev['name']}` | {emoji} {ev['verdict']}{note} | {ev['k']} "
            f"| {ev['pass_at_k'] * 100:.0f}% | {ev['pass_pow_k'] * 100:.0f}% "
            f"| {ev['mean']:.2f} \u00b1 {ev['sigma']:.2f} | {eval_cost_line(ev['usage'])} |"
        )
    lines.append("")

    infra, failures = [], []
    for ev in model["evals"]:
        for repeat in ev["repeats"]:
            line = f"- `{ev['name']}` repeat {repeat['index']}: **{repeat['verdict']}**"
            if repeat["error_kind"]:
                line += f" ({repeat['error_kind']})"
            if repeat["error"]:
                line += ": " + first_line(repeat["error"])
            if repeat["verdict"] == "errored":
                infra.append(line)
            elif repeat["verdict"] == "failed":
                failures.append(line)
    if infra:
        lines.append("### \u26a0\ufe0f infra failures (not agent failures)")
        lines.append("")
        lines.extend(infra)
        lines.append("")
    if failures:
        lines.append("### failed repeats")
        lines.append("")
        lines.extend(failures)
        lines.append("")

    lines.append(conclusion_note(verdict))
    lines.append("")

    if comparison and comparison.get("noise_note"):
        lines.append(f"> {comparison['noise_note']}")
        lines.append("")
    elif model["k"] >= 3:
        lines.append(
            "> noise floor active (k>=3): `shipyard compare` requires a score move to exceed "
            "both the score budget and the 95% t-interval noise margin before it blocks."
        )
        lines.append("")

    dirs = sorted({
        repeat["rollout_dir"]
        for ev in model["evals"]
        for repeat in ev["repeats"]
        if repeat["rollout_dir"]
    })
    if dirs:
        lines.append("---")
        lines.append("")
        lines.append("rollouts: " + " \u00b7 ".join(f"`{d}`" for d in dirs))
        lines.append("")

    return "\n".join(lines) + "\n"


def write_junit(model, path):
    """JUnit XML mirroring the CLI: one suite per eval, one case per repeat."""
    total_tests = sum(max(ev["k"], len(ev["repeats"])) for ev in model["evals"])
    total_failures = sum(ev["failed_count"] for ev in model["evals"])
    total_errors = sum(ev["errored_count"] for ev in model["evals"])
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append(
        f'<testsuites name="shipyard" tests="{total_tests}" '
        f'failures="{total_failures}" errors="{total_errors}">'
    )
    for ev in model["evals"]:
        suite_time = sum(r["duration_ms"] for r in ev["repeats"]) / 1000.0
        lines.append(
            f'  <testsuite name="{xml_escape(ev["name"])}" tests="{max(ev["k"], len(ev["repeats"]))}" '
            f'failures="{ev["failed_count"]}" errors="{ev["errored_count"]}" time="{suite_time:.3f}">'
        )
        for repeat in ev["repeats"]:
            case_time = repeat["duration_ms"] / 1000.0
            lines.append(
                f'    <testcase classname="shipyard.{xml_escape(ev["name"])}" '
                f'name="repeat-{repeat["index"]}" time="{case_time:.3f}">'
            )
            detail = f"rollout: {repeat['rollout_dir']}\n{repeat['error']}".strip()
            score_message = f"score {repeat['score']:.2f}"
            if repeat["verdict"] == "failed":
                lines.append(
                    f'      <failure message="{xml_escape(score_message)}">'
                    f"{xml_escape(detail)}</failure>"
                )
            elif repeat["verdict"] == "errored":
                kind = repeat["error_kind"] or "infra"
                error_message = f"infra ({kind})"
                lines.append(
                    f'      <error message="{xml_escape(error_message)}">'
                    f"{xml_escape(detail)}</error>"
                )
            lines.append("    </testcase>")
        lines.append("  </testsuite>")
    lines.append("</testsuites>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def run(args):
    model = None
    source = ""

    if args.results:
        results_path = Path(args.results)
        if results_path.is_file():
            model = load_results(results_path)
            source = str(results_path)
        else:
            print(
                f"report_generator: --results {results_path} not found; "
                "falling back to --rollout-dir",
                file=sys.stderr,
            )

    if model is None and args.rollout_dir:
        model = load_metrics(args.rollout_dir)
        source = args.rollout_dir

    if model is None:
        model = empty_model()

    comparison = read_json(args.compare) if args.compare else None
    baseline = read_json(args.baseline) if args.baseline else None

    markdown = render_markdown(model, comparison=comparison, baseline=baseline)
    if args.output == "-":
        print(markdown, end="")
        destination = "<stdout>"
    else:
        output_path = Path(args.output)
        if str(output_path.parent) not in ("", "."):
            output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        destination = str(output_path)

    if args.junit_file and args.junit_file != "-":
        write_junit(model, Path(args.junit_file))

    print(f"Generated report at {destination}")
    if source:
        print(f"  source: {source}")
    if args.junit_file:
        print(f"  junit:  {args.junit_file}")
    return 0


def main():
    args = parse_args()
    try:
        return run(args)
    except Exception as exc:  # noqa: BLE001 - gating is compare's job; never fail here
        print(f"report_generator: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
