"""Work through the remaining evaluation within today's free LLM quotas, then rebuild the results table.

    python -m eval.nightly

Steps, in priority order; each resumes where it stopped and is skipped once complete or when
a model it needs has used up its daily quota (the next run continues):

1. agent, first run of all 120 scenarios
2. RAG answers: 150 questions through the chat, graded by a judge from another provider
3. agent, runs 2-5 of every scenario (pass^5)
4. baseline agent (no code-level safeguards), first run of all scenarios
5. baseline agent, runs 2-5
6. safety sets on the current code (mostly answered from the response cache)
"""

import json
import sys

from eval import report, run_agent, run_rag, run_safety
from eval.common import RESULTS_DIR, RUNS_DIR, load_jsonl

AGENT = "groq:openai/gpt-oss-120b"
SIMULATOR = "groq:openai/gpt-oss-20b"
JUDGE = "gemini:gemini-3.5-flash-lite"
SAFETY_SETS = (
    "emergency", "emergency_negatives", "emergency_holdout", "emergency_holdout_negatives", "emergency_holdout2",
    "emergency_holdout2_negatives", "analytics", "medical_advice", "permission", "injection",
)  # fmt: skip
SCENARIOS = len(load_jsonl(run_agent.SCENARIOS))
QUESTIONS = len(load_jsonl(run_rag.QUESTIONS))


def _store_keys(name: str) -> set[str]:
    path = RUNS_DIR / name
    return (
        {json.loads(line)["key"] for line in path.read_text().splitlines() if line.strip()} if path.exists() else set()
    )


def agent_done(repeats: int, baseline: bool) -> bool:
    keys = _store_keys(f"agent/{run_agent.slug(AGENT)}{'-baseline' if baseline else ''}.jsonl")
    return sum(int(k.rsplit("#", 1)[1]) < repeats for k in keys) >= SCENARIOS * repeats


def rag_done() -> bool:
    return sum(k.endswith(f"|{AGENT}|{JUDGE}") for k in _store_keys("rag_answers.jsonl")) >= QUESTIONS


def _stopped(result_file: str, *path: str) -> str:
    data = json.loads((RESULTS_DIR / result_file).read_text())
    for key in path:
        data = (data or {}).get(key) or {}
    return data if isinstance(data, str) else ""


def main() -> int:
    exhausted: set[str] = set()

    def note(stopped: str) -> None:
        for model in (AGENT, SIMULATOR, JUDGE):
            if model in stopped and ("daily quota" in stopped or "rate limited for" in stopped):
                exhausted.add(model)

    steps = [
        ("agent run 1", {AGENT, SIMULATOR}, lambda: agent_done(1, False),
         lambda: (run_agent.main(["--repeats", "1"]), note(_stopped("agent.json", "header", "stopped_early")))),
        ("RAG answers", {AGENT, JUDGE}, rag_done,
         lambda: (run_rag.main(["--answers", "--llm", AGENT, "--judge", JUDGE]),
                  note(_stopped("rag.json", "answers", "stopped_early")))),
        ("agent runs 2-5", {AGENT, SIMULATOR}, lambda: agent_done(5, False),
         lambda: (run_agent.main(["--repeats", "5"]), note(_stopped("agent.json", "header", "stopped_early")))),
        ("baseline run 1", {AGENT, SIMULATOR}, lambda: agent_done(1, True),
         lambda: (run_agent.main(["--baseline", "--repeats", "1"]),
                  note(_stopped("agent_baseline.json", "header", "stopped_early")))),
        ("baseline runs 2-5", {AGENT, SIMULATOR}, lambda: agent_done(5, True),
         lambda: (run_agent.main(["--baseline", "--repeats", "5"]),
                  note(_stopped("agent_baseline.json", "header", "stopped_early")))),
    ]  # fmt: skip
    pending = []
    for name, models, done, run in steps:
        if done():
            continue
        if models & exhausted:
            pending.append(name)
            print(f"[nightly] {name}: waiting for quota ({', '.join(sorted(models & exhausted))})", file=sys.stderr)
            continue
        print(f"[nightly] {name}: running", file=sys.stderr)
        run()
        if not done():
            pending.append(name)
    if not pending:
        print("[nightly] all LLM evaluations complete; re-checking the safety sets on this code", file=sys.stderr)
        run_safety.main(["--sets", ",".join(SAFETY_SETS)])
    report.main()
    print(json.dumps({"pending": pending, "exhausted_today": sorted(exhausted)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
