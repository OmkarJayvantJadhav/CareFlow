"""Answer quality for the RAG set: each question goes through the real chat; a judge model grades it.

Correctness compares the reply with the reference answer; faithfulness checks that every claim
in the reply is supported by the sources the reply cites (the text the model actually saw).
Unanswerable questions must be declined. The judge is a different model from the one answering.
A 20% sample is written to eval/results/rag_spot_check.jsonl for a person to review; the judge's
grades are not presented as human review.
"""

import json
import re
import sys

from app.agent.chat import handle_chat
from eval.common import EVAL_NOW, RUNS_DIR, QuotaExhausted, QuotaLLM, ResultStore, isolated
from eval.harness import Conversation as Transcript
from eval.harness import Turn, actor_for, recording

JUDGE_PROMPT = """You grade an answer given by a hospital information assistant. Reply with JSON only:
{{"correct": "yes" | "partly" | "no", "faithful": "yes" | "no", "declined": "yes" | "no", "reason": "<one sentence>"}}

- correct: does the answer give the facts in the reference answer? "partly" if some key facts are missing or one is wrong.
- faithful: is every factual claim in the answer supported by the SOURCES below? General courtesy text needs no support.
  If the answer makes no factual claim, "yes".
- declined: does the answer say it does not know / could not find the information (instead of answering)?

QUESTION: {question}
REFERENCE ANSWER: {reference}
ANSWER: {answer}
SOURCES:
{sources}"""
NO_REFERENCE = "(none: the hospital documents do not contain this information)"


def _sources_text(transcript: Transcript, reply: str) -> str:
    seen = [s for c in transcript.tool_calls if c["name"] == "search_knowledge" for s in c.get("sources", [])]
    if not seen:
        return "(no sources were retrieved)"
    # The reply cites [n] by the ref numbers the model saw.
    cited = {int(n) for n in re.findall(r"\[(\d{1,2})\]", reply)}
    chosen = [s for s in seen if s["ref"] in cited] or seen
    return "\n".join(f"[{s['ref']}] {s['title']} — {s['section']}: {s['text']}" for s in chosen)


def _parse(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return {}


def answer_one(question: dict, llm) -> dict:
    with isolated() as db:
        actor = actor_for(db, "asha")
        transcript = Transcript()
        with recording(transcript):
            reply = handle_chat(db, actor, f"rag-{question['id']}", question["question"], llm, now=EVAL_NOW,
                                language_hint=question["language"])  # fmt: skip
        transcript.turns.append(
            Turn(
                question["question"],
                reply.reply,
                reply.language,
                reply.emergency,
                reply.handoff,
                None,
                reply.actions,
                reply.citations,
                0.0,
            )  # fmt: skip
        )
        return {
            "reply": reply.reply,
            "citations": [f"{c['doc_key'] if 'doc_key' in c else c.get('source_path')}" for c in reply.citations],
            "searched": any(c["name"] == "search_knowledge" for c in transcript.tool_calls),
            "sources": _sources_text(transcript, reply.reply),
            "grounding_guard": any(
                s.get("kind") == "grounding_guard" for t in transcript.traces for s in t.get("spans", [])
            ),
            "emergency": reply.emergency,
            "usage": transcript.usage(),
        }


def grade_answers(questions: list[dict], llm_spec: str, judge_spec: str) -> dict:
    store = ResultStore(RUNS_DIR / "rag_answers.jsonl")
    llm, judge = QuotaLLM(llm_spec), QuotaLLM(judge_spec)
    stopped = None
    for q in questions:
        key = f"{q['id']}|{llm_spec}|{judge_spec}"
        if store.done(key):
            continue
        try:
            answer = answer_one(q, llm.with_salt(q["id"]))
            prompt = JUDGE_PROMPT.format(
                question=q["question"], reference=q["reference_answer"] or NO_REFERENCE, answer=answer["reply"],
                sources=answer["sources"],
            )  # fmt: skip
            verdict = _parse(judge.chat([{"role": "user", "content": prompt}], [], 400).text)
        except QuotaExhausted as err:
            stopped = str(err)
            break
        store.add({"key": key, "id": q["id"], "language": q["language"], "answerable": q["answerable"], **answer,
                   "verdict": verdict})  # fmt: skip
        print(
            f"{q['id']} {verdict.get('correct')}/{verdict.get('faithful')}/{verdict.get('declined')}", file=sys.stderr
        )
    rows = [r for r in store.records.values() if r["key"].endswith(f"|{llm_spec}|{judge_spec}")]
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    answered = [r for r in rows if r["verdict"].get("declined") == "no"]
    score = {"yes": 1.0, "partly": 0.5, "no": 0.0}

    def rate(xs, ok):
        return round(sum(ok(x) for x in xs) / len(xs), 4) if xs else None

    spot = rows[::5]
    with open("eval/results/rag_spot_check.jsonl", "w") as f:
        for r in spot:
            f.write(
                json.dumps({k: r[k] for k in ("id", "language", "reply", "sources", "verdict")}, ensure_ascii=False)
                + "\n"
            )
    return {
        "answering_llm": llm_spec,
        "judge_llm": judge_spec,
        "graded": len(rows),
        "stopped_early": stopped,
        "answer_correctness": round(
            sum(score.get(r["verdict"].get("correct"), 0) for r in answerable) / len(answerable), 4
        )
        if answerable
        else None,
        "faithfulness": rate(answered, lambda r: r["verdict"].get("faithful") == "yes"),
        "unanswerable_declined": rate(unanswerable, lambda r: r["verdict"].get("declined") == "yes"),
        "answerable_declined": rate(answerable, lambda r: r["verdict"].get("declined") == "yes"),
        "grounding_guard_fired": rate(rows, lambda r: r["grounding_guard"]),
        "false_emergencies": sum(r["emergency"] for r in rows),
        "judge_unparsed": sum(not r["verdict"] for r in rows),
        "human_spot_check": "not done: eval/results/rag_spot_check.jsonl lists a 20% sample for a person to review",
    }
