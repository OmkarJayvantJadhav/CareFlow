"""Build eval/results/README.md and the docs §14 results table from the result files.

    python -m eval.report

Nothing in the table is typed by hand: every cell is read from a JSON file written by
a run, with its sample size. A metric that has not been run says so.
"""

import json
from pathlib import Path

RESULTS = Path("eval/results")


def load(name: str) -> dict | None:
    path = RESULTS / name
    return json.loads(path.read_text()) if path.exists() else None


def pct(x: float | None, digits: int = 1) -> str:
    return "not run" if x is None else f"{100 * x:.{digits}f}%"


def date_of(d: dict | None, key: str = "header") -> str:
    if not d:
        return "—"
    run_at = (d.get(key) or {}).get("run_at") or d.get("run_at") or ""
    return run_at[:10] or "—"


def build() -> str:
    ml = load("ml_wait_time.json")
    rag = load("rag.json")
    safety = load("safety.json")
    safety_v1 = load("safety_emergency_v1.json")
    agent = load("agent.json")
    baseline_agent = load("agent_baseline.json")
    rows = []

    a = (agent or {}).get("summary") or {}
    b = (baseline_agent or {}).get("summary") or {}
    repeats = (agent or {}).get("header", {}).get("repeats", 5)
    n_runs = f"{a.get('runs', 0)} runs of {a.get('scenarios_run', 0)}/{a.get('scenarios_total', 120)} scenarios"
    rows.append(("Agent pass^1", pct(b.get("pass_1")), f"{pct(a.get('pass_1'))} ({n_runs})" if a else "not run",
                 date_of(agent)))  # fmt: skip
    k_key = f"pass_{repeats}"
    rows.append((f"Agent pass^{repeats}", pct(b.get(k_key)),
                 f"{pct(a.get(k_key))} ({a.get(f'scenarios_with_{repeats}_runs', 0)} scenarios with {repeats} runs)"
                 if a.get(k_key) is not None else "not run (needs 5 runs per scenario)", date_of(agent)))  # fmt: skip
    rows.append(("Wrong-action rate", pct(b.get("wrong_action_rate")),
                 f"{pct(a.get('wrong_action_rate'))} ({a.get('runs', 0)} runs)" if a else "not run", date_of(agent)))  # fmt: skip

    if rag:
        r = rag["retrieval"]
        base = r["fixed"]["dense"]["recall_at_5"]
        cv = r.get("threshold_cv", {}).get("cross_validated", {})
        rows.append(("RAG recall@5", f"{pct(base)} (fixed chunks, dense only)",
                     f"{pct(cv.get('recall_at_5'))} (structure chunks, hybrid + re-ranker, threshold by 5-fold CV)",
                     date_of(rag)))  # fmt: skip
        answers = rag.get("answers") or {}
        rows.append(("RAG faithfulness", "not run",
                     f"{pct(answers.get('faithfulness'))} ({answers.get('graded', 0)} answers, judge {answers.get('judge_llm')})"
                     if answers else "not run", date_of(rag)))  # fmt: skip
    if ml:
        t = ml["test"]
        rows.append(("Wait-time MAE (min)", f"{t['position_x_10']['mae']} (position × 10 min)", f"{t['model']['mae']} (LightGBM)",
                     ml["run_at"][:10]))  # fmt: skip
        rows.append(("Range coverage", "—", pct(t["model"]["range_coverage"]), ml["run_at"][:10]))
    if safety:
        s = safety["sets"]
        held = s.get("emergency_holdout2", {}).get("summary", {})
        v1 = (safety_v1 or {}).get("sets", {}).get("emergency", {}).get("summary", {})
        rows.append(("Emergency redirect recall",
                     f"{pct(v1.get('redirect_recall'))} (gate v1, 40 dev cases; gate alone {pct(v1.get('gate_recall'))})"
                     if v1 else "—",
                     f"{pct(held.get('redirect_recall'))} (held-out set 2, {held.get('run', 0)} cases; gate alone "
                     f"{pct(held.get('gate_recall'))})", date_of(safety)))  # fmt: skip
    rows.append(("Median latency (s)", "—", f"{a['median_turn_latency_s']} per chat turn" if a.get("median_turn_latency_s")
                 else "not run", date_of(agent)))  # fmt: skip
    rows.append(("Cost per conversation", "—",
                 f"${a['mean_cost_per_conversation_usd']:.5f} at paid list prices (the demo runs on free tiers)"
                 if a.get("mean_cost_per_conversation_usd") is not None else "not run", date_of(agent)))  # fmt: skip

    table = ["| Metric | Baseline version | Final version | Date |", "| --- | --- | --- | --- |"]
    table += [f"| {m} | {base} | {final} | {d} |" for m, base, final, d in rows]

    safety_lines = []
    if safety:
        names = {
            "emergency": "Emergency phrasings (development set)",
            "emergency_holdout": "Emergency, held-out set 1 (used for development after its first run)",
            "emergency_holdout2": "Emergency, held-out set 2 (final, unseen)",
            "medical_advice": "Medical-advice bait",
            "permission": "Permission attacks",
            "injection": "Prompt injection (chat and documents)",
            "analytics": "Unsafe analytics requests",
            "emergency_negatives": "Non-emergencies (development) — false alarms",
            "emergency_holdout_negatives": "Non-emergencies, held-out set 1 — false alarms",
            "emergency_holdout2_negatives": "Non-emergencies, held-out set 2 — false alarms",
        }
        safety_lines = ["| Set | Cases | Passed | Notes |", "| --- | --- | --- | --- |"]
        for key, label in names.items():
            summary = s.get(key, {}).get("summary")
            if not summary:
                continue
            note = ""
            if "redirect_recall" in summary:
                note = (
                    f"redirect shown {pct(summary['redirect_recall'])}, by the gate alone {pct(summary['gate_recall'])}"
                )
            if "false_alarm_rate" in summary:
                note = f"false alarm rate {pct(summary['false_alarm_rate'])}"
            safety_lines.append(
                f"| {label} | {summary['run']} | {summary['passed']} ({pct(summary['pass_rate'])}) | {note} |"
            )

    parts = [
        "# Results",
        "",
        "Generated by `python -m eval.report` from the JSON files in this folder; every number comes from a run",
        "recorded there (with its date, configuration and git commit). See `eval/README.md` for the method.",
        "",
        "## Results table (docs §14)",
        "",
        *table,
        "",
    ]
    if safety_lines:
        parts += ["## Safety sets (`safety.json`)", "", *safety_lines, ""]
    return "\n".join(parts)


def main() -> None:
    text = build()
    readme = RESULTS / "README.md"
    previous = readme.read_text() if readme.exists() else ""
    marker = "<!-- details below are kept -->"
    tail = previous.split(marker, 1)[1] if marker in previous else ""
    readme.write_text(text + "\n" + marker + tail)
    print(text)


if __name__ == "__main__":
    main()
