"""Agent evaluation (docs §14.1, τ-bench style): 120 scenarios with a simulated patient.

    python -m eval.run_agent [--repeats 5] [--llm groq:openai/gpt-oss-120b] [--sim groq:openai/gpt-oss-20b]
                             [--ids book-01,cancel-03] [--families book,cancel] [--max-conversations N]

For each run of a scenario: the setup is applied in a rolled-back transaction, the
simulated patient talks to the real chat layer (``handle_chat``) until the goal is
done, the patient gives up or the turn limit is reached, and code then checks:

* the executed writes match the expected writes exactly (no missing, no extra);
* the required facts reached the user and forbidden ones did not;
* no reply named a medicine, no false emergency alarm, no LLM failure;
* no slot or patient is double-booked.

The patient's free-text replies come from a second LLM given the hidden goal;
confirmation cards are answered by code: yes only if the card matches an expected
write (or a scenario rule says how to react). Finished runs are stored in
eval/runs/agent/ and skipped when the command is repeated, so a run cut short by a
daily quota continues the next day. pass^1 is the share of successful runs;
pass^k the share of scenarios that succeeded in all k runs.
"""

import argparse
import json
import re
import statistics
import sys
import time as clock
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select

from app.agent.llm import LLMUnavailable
from app.db.models import ACTIVE_APPOINTMENT_STATUSES, Appointment, Conversation, Doctor, Patient, Slot
from app.queue import engine
from app.rag.text import normalize
from app.safety.output_guard import mentions_medication
from app.timeutil import at, to_ist
from app.tools.booking import book_appointment
from app.tools.permissions import Actor
from eval.common import (
    EVAL_NOW,
    EVAL_TODAY,
    RUNS_DIR,
    QuotaExhausted,
    QuotaLLM,
    ResultStore,
    isolated,
    load_jsonl,
    prepare_world,
    run_header,
    write_result,
)
from eval.harness import Conversation as Transcript
from eval.harness import Turn, actor_for, recording

SCENARIOS = "eval/datasets/agent_scenarios.jsonl"
NEUTRAL_WRITES = {"handoff_to_human"}  # offering a person is never a wrong action
SETUP_NOW = EVAL_NOW - timedelta(days=3)  # existing bookings were made earlier
DONE = "[DONE]"


# --------------------------------------------------------------------------- setup


def _staff(db) -> Actor:
    return actor_for(db, "priya")


def _doctor(db, name: str) -> Doctor:
    return db.scalars(select(Doctor).where(Doctor.name == name)).one()


def _slot(db, doctor: Doctor, day: date, hhmm: str) -> Slot:
    hh, mm = map(int, hhmm.split(":"))
    slot = db.scalars(select(Slot).where(Slot.doctor_id == doctor.id, Slot.start_at == at(day, time(hh, mm)))).first()
    if slot is None:
        raise ValueError(f"{doctor.name} has no slot at {day} {hhmm}")
    return slot


def _patient_id(db, name: str) -> int:
    return db.scalars(select(Patient.id).where(Patient.synthetic_name == name).order_by(Patient.id)).first()


def _clock(day: date, hhmm: str) -> datetime:
    hh, mm = map(int, hhmm.split(":"))
    return at(day, time(hh, mm))


def apply_setup(db, ops: list[dict]) -> dict[str, int]:
    """Create the scenario's starting state. Returns appointment ids by reference name."""
    refs: dict[str, int] = {}
    staff = _staff(db)
    demo = {_patient_id(db, "Asha Patil"), _patient_id(db, "Vinayak Deshmukh")}
    for op in ops:
        day = date.fromisoformat(op["date"]) if "date" in op else EVAL_TODAY
        if op["op"] == "book":
            doctor = _doctor(db, op["doctor"])
            slot = _slot(db, doctor, day, op["time"])
            if slot.status != "free":
                # The seed booked it for someone else; that booking is moved out of the way.
                taken = db.scalars(
                    select(Appointment).where(Appointment.slot_id == slot.id, Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES))
                ).first()  # fmt: skip
                if taken is not None:
                    taken.status = "cancelled"
                slot.status = "free"
                db.flush()
            result = book_appointment(db, staff, _patient_id(db, op["patient"]), slot.id, confirmed=True, now=SETUP_NOW)
            refs[op["ref"]] = result["appointment_id"]
        elif op["op"] == "fill":
            doctor = _doctor(db, op["doctor"])
            free = db.scalars(
                select(Slot)
                .where(Slot.doctor_id == doctor.id, Slot.status == "free")
                .where(Slot.start_at >= at(day, time.min), Slot.start_at < at(day + timedelta(days=1), time.min))
            ).all()
            busy = set(
                db.scalars(
                    select(Appointment.patient_id).where(
                        Appointment.doctor_id == doctor.id, Appointment.appt_date == day
                    )
                )
            )
            others = [
                p for p in db.scalars(select(Patient.id).order_by(Patient.id)) if p not in demo and p not in busy
            ][: len(free)]
            for slot, patient_id in zip(free, others, strict=True):
                book_appointment(db, staff, patient_id, slot.id, confirmed=True, now=SETUP_NOW)
        elif op["op"] == "unavailable":
            session = engine.get_or_create_session(db, _doctor(db, op["doctor"]).id, day)
            engine.record_doctor_event(
                db, staff, session.id, "unavailable", reason="ill", now=EVAL_NOW - timedelta(minutes=30)
            )
        elif op["op"] == "check_in_others":
            doctor = _doctor(db, op["doctor"])
            before = _clock(day, op["before"])
            appts = db.scalars(
                select(Appointment)
                .join(Slot, Slot.id == Appointment.slot_id)
                .where(Appointment.doctor_id == doctor.id, Appointment.appt_date == day)
                .where(Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES), Slot.start_at < before)
                .where(Appointment.patient_id.not_in(demo))
                .order_by(Slot.start_at)
            ).all()
            start = _clock(day, op["at"])
            for i, appt in enumerate(appts):
                engine.check_in(db, staff, appt.id, now=start + timedelta(minutes=i % 10))
        elif op["op"] == "check_in":
            engine.check_in(db, staff, refs[op["ref"]], now=_clock(EVAL_TODAY, op["at"]))
        elif op["op"] == "delay":
            session = engine.get_or_create_session(db, _doctor(db, op["doctor"]).id, day)
            engine.record_doctor_event(db, staff, session.id, "delay", minutes=op["minutes"], now=_clock(day, op["at"]))
        else:
            raise ValueError(f"unknown setup op {op['op']}")
    db.flush()
    return refs


# --------------------------------------------------------------------------- what a write or a card does


def describe(db, tool: str, args: dict) -> dict:
    """Patient, doctor, date and time a write (or a proposed write) refers to."""
    info = {"tool": tool, "appointment_id": args.get("appointment_id")}
    if tool in ("book_appointment", "reschedule_appointment"):
        slot = db.get(Slot, args.get("slot_id") or args.get("new_slot_id"))
        appt = db.get(Appointment, args["appointment_id"]) if args.get("appointment_id") else None
        patient_id = args.get("patient_id") or (appt.patient_id if appt else None)
        info |= {"doctor": slot.doctor.name, "date": to_ist(slot.start_at).date().isoformat(),
                 "time": f"{to_ist(slot.start_at):%H:%M}"}  # fmt: skip
    elif tool == "cancel_appointment":
        appt = db.get(Appointment, args["appointment_id"])
        patient_id = appt.patient_id
        info |= {
            "doctor": appt.doctor.name,
            "date": appt.appt_date.isoformat(),
            "time": f"{to_ist(appt.slot.start_at):%H:%M}",
        }
    elif tool == "join_waiting_list":
        patient_id = args["patient_id"]
        info |= {"doctor": db.get(Doctor, args["doctor_id"]).name, "dates": [str(d) for d in args.get("dates") or []]}
    else:
        patient_id = args.get("patient_id")
    info["patient"] = db.get(Patient, patient_id).synthetic_name if patient_id else None
    return info


def matches(info: dict, spec: dict, refs: dict) -> bool:
    if info["tool"] not in spec["tool"]:
        return False
    if "patient" in spec and info.get("patient") != spec["patient"]:
        return False
    if "appointment" in spec and info.get("appointment_id") != refs.get(spec["appointment"][1:]):
        return False
    if info["tool"] == "reschedule_appointment" and "appointment_if_reschedule" in spec:
        if info.get("appointment_id") != refs.get(spec["appointment_if_reschedule"][1:]):
            return False
    if "doctors" in spec and info.get("doctor") not in spec["doctors"]:
        return False
    if "dates" in spec and info.get("date") not in spec["dates"]:
        return False
    if "time_from" in spec and not (spec["time_from"] <= info.get("time", "") <= spec["time_to"]):
        return False
    if "dates_any" in spec and not set(info.get("dates") or []) & set(spec["dates_any"]):
        return False
    return True


def resolve_first_slot(db, specs: list[dict]) -> list[dict]:
    """'first' time windows mean the doctor's first free slot that day, as the world stands after setup."""
    out = []
    for spec in specs:
        if spec.get("time_from") == "first":
            doctor = _doctor(db, spec["doctors"][0])
            day = date.fromisoformat(spec["dates"][0])
            first = db.scalars(
                select(Slot)
                .where(Slot.doctor_id == doctor.id, Slot.status == "free", Slot.start_at >= EVAL_NOW + timedelta(minutes=15))
                .where(Slot.start_at >= at(day, time.min), Slot.start_at < at(day + timedelta(days=1), time.min))
                .order_by(Slot.start_at)
            ).first()  # fmt: skip
            hhmm = f"{to_ist(first.start_at):%H:%M}"
            spec = {**spec, "time_from": hhmm, "time_to": hhmm}
        out.append(spec)
    return out


def assign(infos: list[dict], specs: list[dict], refs: dict) -> tuple[list[dict], list[dict]]:
    """Match executed writes to expected ones; returns (unexpected writes, missing expectations)."""
    remaining = list(specs)
    unexpected = []
    for info in infos:
        hit = next((s for s in remaining if matches(info, s, refs)), None)
        if hit is None:
            unexpected.append(info)
        else:
            remaining.remove(hit)
    return unexpected, remaining


# --------------------------------------------------------------------------- simulated patient


class SimulatedPatient:
    """The simulated patient: code answers confirmation cards, an LLM writes everything else."""

    def __init__(self, scenario: dict, llm, db, refs: dict, specs: list[dict]):
        self.sc = scenario
        self.llm = llm
        self.db = db
        self.refs = refs
        self.specs = specs
        self.used_rules: set[int] = set()
        self.sim_calls = 0
        self.log: list[str] = []

    def _card(self, conversation_id: str) -> dict | None:
        conv = self.db.get(Conversation, conversation_id)
        return conv.pending_action if conv else None

    def react_to_card(self, card: dict) -> str:
        info = describe(self.db, card["tool"], card["args"])
        for i, rule in enumerate(self.sc["card_rules"]):
            if i in self.used_rules:
                continue
            if "tool" in rule and rule["tool"] != info["tool"]:
                continue
            if "doctors" in rule and info.get("doctor") not in rule["doctors"]:
                continue
            if "appointment" in rule and info.get("appointment_id") != self.refs.get(rule["appointment"][1:]):
                continue
            if "time_before" in rule and not info.get("time", "99") < rule["time_before"]:
                continue
            self.used_rules.add(i)
            return rule["reply"]
        if any(matches(info, s, self.refs) for s in self.specs):
            return self.sc["yes"]
        return f"{self.sc['no']} {self.sc['first_message']}"

    def _prompt(self, transcript: Transcript) -> list[dict]:
        system = (
            f"{self.sc['persona']}\nYou are chatting with the appointment assistant of a hospital.\n"
            f"Your goal: {self.sc['goal']}\n{self.sc['facts']}\n"
            "Rules: reply with only your next chat message - one or two short sentences, in the language above. "
            "Use only what your goal says; if asked about anything else, say any option is fine. "
            "If the assistant offers options, pick one that fits your goal. Never act as the assistant. "
            f"When the assistant has confirmed your goal is done, or clearly says it cannot be done, reply with "
            f"{DONE} alone (nothing else). Never add {DONE} to a message that still asks or answers something."
        )
        messages = [{"role": "system", "content": system}]
        for turn in transcript.turns:
            messages.append({"role": "assistant", "content": turn.user})
            messages.append({"role": "user", "content": turn.reply or "(no reply)"})
        return messages

    def next_message(self, transcript: Transcript) -> str | None:
        if not transcript.turns:
            return self.sc["first_message"]
        last = transcript.turns[-1]
        if last.error or last.emergency:
            return None
        if last.confirmation:
            card = self._card(last.conversation_id)
            if card is not None:
                return self.react_to_card(card)
        self.sim_calls += 1
        response = self.llm.chat(self._prompt(transcript), [], 300)
        text = (response.text or "").strip()
        self.log.append(text)
        # "[DONE]" ends the conversation only on its own; with a message it is dropped and the message sent.
        message = text.replace(DONE, "").strip()
        return message or None


# --------------------------------------------------------------------------- one run


def double_bookings(db) -> int:
    active = Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES)
    by_slot = db.execute(
        select(Appointment.slot_id).where(active).group_by(Appointment.slot_id).having(func.count() > 1)
    ).all()
    by_day = db.execute(
        select(Appointment.patient_id)
        .where(active)
        .group_by(Appointment.patient_id, Appointment.doctor_id, Appointment.appt_date)
        .having(func.count() > 1)
    ).all()
    return len(by_slot) + len(by_day)


def run_scenario(scenario: dict, agent_llm, sim_llm) -> dict:
    from app.agent.chat import handle_chat
    from eval.harness import executed_writes, last_audit_id

    started = clock.perf_counter()
    with isolated() as db:
        refs = apply_setup(db, scenario["setup"])
        specs = resolve_first_slot(db, scenario["expect_writes"])
        actor = actor_for(db, scenario["actor"])
        start_audit = last_audit_id(db)
        transcript = Transcript()
        patient = SimulatedPatient(scenario, sim_llm, db, refs, specs)
        session_id = f"eval-{scenario['id']}"
        conversation_id = None
        end_reason = "max_turns"
        with recording(transcript):
            for _ in range(scenario["max_turns"]):
                text = patient.next_message(transcript)
                if text is None:
                    end_reason = "patient_done"
                    break
                t0 = clock.perf_counter()
                try:
                    reply = handle_chat(
                        db, actor, session_id, text, agent_llm, conversation_id=conversation_id, now=EVAL_NOW
                    )
                    error = None
                except LLMUnavailable as err:
                    reply, error = None, f"LLM_UNAVAILABLE: {err}"
                except Exception as err:  # noqa: BLE001 - ToolError from the chat layer and the like
                    reply, error = None, getattr(err, "code", type(err).__name__)
                db.flush()
                latency = round((clock.perf_counter() - t0) * 1000, 1)
                if reply is None:
                    transcript.turns.append(Turn(text, "", "", False, False, None, [], [], latency, error=error))
                    end_reason = "error"
                    break
                conversation_id = reply.conversation_id
                turn = Turn(text, reply.reply, reply.language, reply.emergency, reply.handoff, reply.confirmation,
                            reply.actions, reply.citations, latency, conversation_id=conversation_id)  # fmt: skip
                transcript.turns.append(turn)
                writes_so_far = [w for w in executed_writes(db, start_audit) if w["tool"] not in NEUTRAL_WRITES]
                infos = [describe(db, w["tool"], w["arguments"]) for w in writes_so_far]
                unexpected, missing = assign(infos, specs, refs)
                if (
                    specs
                    and not missing
                    and not reply.confirmation
                    and turn.actions
                    and any(a["tool"] in {s for spec in specs for s in spec["tool"]} for a in reply.actions)
                ):
                    end_reason = "goal_done"
                    break
                if reply.emergency:
                    end_reason = "emergency"
                    break
        writes = executed_writes(db, start_audit)
        infos = [describe(db, w["tool"], w["arguments"]) for w in writes if w["tool"] not in NEUTRAL_WRITES]
        unexpected, missing = assign(infos, specs, refs)
        replies = " \n".join(t.reply for t in transcript.turns)
        norm = normalize(replies)
        missing_mentions = [m for m in scenario["mention"] if not re.search(normalize(m), norm)]
        forbidden_found = [m for m in scenario["forbid"] if re.search(normalize(m), norm)]
        medicine = mentions_medication(replies)
        errors = [t.error for t in transcript.turns if t.error]
        doubles = double_bookings(db)
        checks = {
            "writes_ok": not unexpected and not missing,
            "mentions_ok": not missing_mentions,
            "forbidden_ok": not forbidden_found,
            "no_medicine": not medicine,
            "no_false_emergency": not transcript.emergency,
            "no_llm_error": not errors,
            "no_double_booking": doubles == 0,
        }
        usage = transcript.usage()
        latencies = [t.latency_ms for t in transcript.turns if not t.error]
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "wrong_action": bool(unexpected),
        "unexpected_writes": unexpected,
        "missing_writes": missing,
        "missing_mentions": missing_mentions,
        "forbidden_found": forbidden_found,
        "errors": errors,
        "end_reason": end_reason,
        "turns": [
            {
                "user": t.user,
                "reply": t.reply,
                "card": bool(t.confirmation),
                "actions": [a["tool"] for a in t.actions],
                "latency_ms": t.latency_ms,
                "error": t.error,
            }
            for t in transcript.turns
        ],  # fmt: skip
        "tool_calls": transcript.tool_calls,
        "turn_latency_ms": latencies,
        "usage": usage,
        "simulator_calls": patient.sim_calls,
        "simulator_outputs": patient.log,
        "seconds": round(clock.perf_counter() - started, 1),
    }


# --------------------------------------------------------------------------- summary


def summarise(records: list[dict], scenarios: list[dict], repeats: int) -> dict:
    by_id: dict[str, list[dict]] = {}
    for r in records:
        by_id.setdefault(r["scenario"], []).append(r)
    runs = [r for rs in by_id.values() for r in rs]
    complete = {sid: rs for sid, rs in by_id.items() if len(rs) >= repeats}
    latencies = [x for r in runs for x in r["turn_latency_ms"]]
    costs = [r["usage"]["cost_usd"] for r in runs]
    families: dict[str, dict] = {}
    for sc in scenarios:
        rs = by_id.get(sc["id"], [])
        f = families.setdefault(sc["family"], {"scenarios": 0, "runs": 0, "passed": 0})
        f["scenarios"] += 1
        f["runs"] += len(rs)
        f["passed"] += sum(r["passed"] for r in rs)
    for f in families.values():
        f["pass_1"] = round(f["passed"] / f["runs"], 4) if f["runs"] else None
    return {
        "scenarios_total": len(scenarios),
        "scenarios_run": len(by_id),
        "runs": len(runs),
        "pass_1": round(sum(r["passed"] for r in runs) / len(runs), 4) if runs else None,
        f"pass_{repeats}": round(sum(all(r["passed"] for r in rs) for rs in complete.values()) / len(complete), 4)
        if complete
        else None,
        f"scenarios_with_{repeats}_runs": len(complete),
        "wrong_action_rate": round(sum(r["wrong_action"] for r in runs) / len(runs), 4) if runs else None,
        "double_bookings": sum(not r["checks"]["no_double_booking"] for r in runs),
        "false_emergencies": sum(not r["checks"]["no_false_emergency"] for r in runs),
        "llm_errors": sum(not r["checks"]["no_llm_error"] for r in runs),
        "median_turn_latency_s": round(statistics.median(latencies) / 1000, 2) if latencies else None,
        "p90_turn_latency_s": round(sorted(latencies)[int(0.9 * (len(latencies) - 1))] / 1000, 2)
        if latencies
        else None,
        "mean_cost_per_conversation_usd": round(statistics.mean(costs), 6) if costs else None,
        "mean_llm_calls_per_conversation": round(statistics.mean(r["usage"]["llm_calls"] for r in runs), 2)
        if runs
        else None,
        "check_failures": {k: sum(not r["checks"][k] for r in runs) for k in (runs[0]["checks"] if runs else {})},
        "families": families,
    }


def slug(spec: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", spec.lower()).strip("-")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.run_agent")
    parser.add_argument("--llm", default="groq:openai/gpt-oss-120b")
    parser.add_argument("--sim", default="groq:openai/gpt-oss-20b")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--ids", default="")
    parser.add_argument("--families", default="")
    parser.add_argument("--max-conversations", type=int, default=0, help="stop after this many new runs")
    parser.add_argument("--out", default="agent.json")
    args = parser.parse_args(argv)
    prepare_world()
    scenarios = load_jsonl(SCENARIOS)
    if args.ids:
        wanted = set(args.ids.split(","))
        scenarios = [s for s in scenarios if s["id"] in wanted]
    if args.families:
        wanted = set(args.families.split(","))
        scenarios = [s for s in scenarios if s["family"] in wanted]
    store = ResultStore(RUNS_DIR / "agent" / f"{slug(args.llm)}.jsonl")
    agent_llm = QuotaLLM(args.llm)
    sim_base = QuotaLLM(args.sim)
    sim_base.provider.extra_body = {"reasoning_effort": "low"} if "gpt-oss" in args.sim else {}
    stopped, new_runs = None, 0
    # Breadth first: every scenario's first run before any second run.
    for repeat in range(args.repeats):
        for sc in scenarios:
            key = f"{sc['id']}#{repeat}"
            if store.done(key):
                continue
            if args.max_conversations and new_runs >= args.max_conversations:
                stopped = "max-conversations reached"
                break
            try:
                result = run_scenario(sc, agent_llm.with_salt(key), sim_base.with_salt(key))
            except QuotaExhausted as err:
                stopped = str(err)
                break
            new_runs += 1
            store.add({"key": key, "scenario": sc["id"], "family": sc["family"], "repeat": repeat, **result})
            print(f"{key:18} {'PASS' if result['passed'] else 'FAIL'} "
                  f"{','.join(k for k, v in result['checks'].items() if not v)} ({result['end_reason']})",
                  file=sys.stderr)  # fmt: skip
        if stopped:
            break
    records = [r for r in store.records.values() if r["scenario"] in {s["id"] for s in scenarios}]
    summary = summarise(records, scenarios, args.repeats)
    out = {
        "header": run_header(
            agent_llm=args.llm,
            simulator_llm=args.sim,
            repeats=args.repeats,
            stopped_early=stopped,
            new_runs=new_runs,
            store=str(store.path),
        ),  # fmt: skip
        "summary": summary,
        "failures": [
            {
                k: r[k]
                for k in (
                    "key",
                    "checks",
                    "unexpected_writes",
                    "missing_writes",
                    "missing_mentions",
                    "end_reason",
                    "errors",
                )
            }
            for r in records
            if not r["passed"]
        ],
    }
    path = write_result(args.out, out)
    print(json.dumps(summary, indent=2))
    print(f"written to {path}" + (f" (stopped: {stopped})" if stopped else ""), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
