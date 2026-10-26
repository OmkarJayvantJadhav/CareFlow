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
    queue = load("agent_queue_actions.json")
    if queue:
        q = queue["summary"]
        parts += [
            "## Assistant queue actions (`agent_queue_actions.json`)",
            "",
            "Check in, join a queue online and leave it by chat (10 scenarios, family `queue_action`). Run 1 found",
            "one wrong answer (the assistant gave the online-joining time from the documents instead of today's",
            "queue tool); the tool description was then changed and run 2 made. Both runs are counted.",
            "",
            "| Measure | Result |",
            "| --- | --- |",
            f"| pass^1 | {pct(q.get('pass_1'))} ({q.get('runs', 0)} runs) |",
            f"| pass^2 (both runs passed) | {pct(q.get('pass_2'))} ({q.get('scenarios_with_2_runs', 0)} scenarios) |",
            f"| Wrong-action rate | {pct(q.get('wrong_action_rate'))} |",
            f"| False emergencies | {q.get('false_emergencies', 0)} |",
            f"| Median turn latency | {q.get('median_turn_latency_s')} s |",
            "",
        ]
    rag_now, rag_queue = load("rag_kb363.json"), load("rag_queue.json")
    if rag_now or rag_queue:
        lines = ["| Question set | Documents | recall@5 (production) | Cross-validated recall@5 | Unanswerable left without a source |",
                 "| --- | --- | --- | --- | --- |"]  # fmt: skip
        for label, d in (("Original questions", rag_now), ("New queue questions", rag_queue)):
            if not d:
                continue
            prod = d["summary"]["structure"]["hybrid+rerank"]
            cv = d["retrieval"]["threshold_cv"]["cross_validated"]
            lines.append(f"| {label} ({d['header']['questions']}) | 363 | {pct(prod['recall_at_5'])} | "
                         f"{pct(cv['recall_at_5'])} | {pct(prod['unanswerable_no_source'])} |")  # fmt: skip
        parts += [
            "## Retrieval after the queue documents (`rag_kb363.json`, `rag_queue.json`)",
            "",
            "Retrieval only (no LLM) on the 363-document knowledge base. The results table above is from",
            "`rag.json` (357 documents). The 24 queue questions were written by the developer after the documents",
            "(not by a separate author like the original set) and were not used to tune anything.",
            "",
            *lines,
            "",
        ]
    gate = load("emergency_gate_v3.json")
    if gate:
        g, cv = gate["sets"], gate["training_cv"]
        rows = [f"| {name} | {v['cases']} | {v['flagged']} | "
                f"{pct(v.get('gate_recall', v.get('false_alarm_rate')))} |" for name, v in g.items()]  # fmt: skip
        parts += [
            "## Emergency gate after the queue retrain (`emergency_gate_v3.json`)",
            "",
            "The gate alone (no LLM), after queue-management messages were added to its training data. The",
            "safety table above was measured with the previous gate. Recall for emergency sets, false-alarm rate",
            "for the negative sets.",
            "",
            "| Set | Cases | Flagged | Rate |",
            "| --- | --- | --- | --- |",
            *rows,
            "",
            f"Classifier, 5-fold cross-validation on its {cv['examples']} training examples at threshold "
            f"{cv['threshold']}: recall {pct(cv['recall'])}, false alarms {pct(cv['false_alarm_rate'])}.",
            "",
        ]
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
