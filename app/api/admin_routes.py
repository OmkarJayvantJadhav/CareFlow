"""Staff and admin pages: today's front desk view (S6), the admin dashboard (S8, FR-29, FR-32)
and the demo reset (FR-34)."""

import json
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.agent.tracing import recent_traces
from app.api.deps import Auth, get_auth, get_db
from app.api.routes import chat_limiter
from app.config import get_settings
from app.db.models import ACTIVE_APPOINTMENT_STATUSES, Appointment, Department, Doctor, QueueEntry, QueueSession
from app.queue import engine
from app.timeutil import now_ist, to_ist
from app.tools.errors import ToolError
from app.tools.permissions import require_role

router = APIRouter(prefix="/api/v1")
RESULTS_DIR = Path(__file__).resolve().parents[2] / "eval" / "results"


# --------------------------------------------------------------------------- front desk (S6)


@router.get("/staff/today", tags=["staff"])
def staff_today(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """Doctors on duty today with their queue session (if one has started) and today's bookings."""
    require_role(auth.actor, "staff", "admin")
    now = now_ist()
    today = now.date()
    sessions = {s.doctor_id: s for s in db.scalars(select(QueueSession).where(QueueSession.date == today))}
    entries = {
        e.appointment_id: e
        for e in db.scalars(
            select(QueueEntry)
            .join(QueueSession)
            .where(QueueSession.date == today, QueueEntry.appointment_id.is_not(None))
        )
    }
    doctors = []
    for doctor in db.scalars(select(Doctor).order_by(Doctor.name)):
        if today.isoweekday() not in doctor.opd_days and doctor.id not in sessions:
            continue
        session = sessions.get(doctor.id)
        appts = db.scalars(
            select(Appointment).where(Appointment.doctor_id == doctor.id, Appointment.appt_date == today)
        ).all()
        bookings = []
        for a in sorted(appts, key=lambda a: a.slot.start_at):
            entry = entries.get(a.id)
            bookings.append(
                {
                    "appointment_id": a.id,
                    "time": f"{to_ist(a.slot.start_at):%H:%M}",
                    "patient_name": a.patient.synthetic_name,
                    "status": a.status,
                    "entry_id": entry.id if entry else None,
                    "token": entry.token if entry else None,
                    "entry_status": entry.status if entry else None,
                }
            )
        doctors.append(
            {
                "doctor_id": doctor.id,
                "doctor_name": doctor.name,
                "department": doctor.department.name,
                "session_id": session.id if session else None,
                "session_status": session.status if session else None,
                "doctor_status": session.doctor_status if session else "available",
                "delay_minutes": session.delay_minutes if session else 0,
                "bookings": bookings,
            }
        )
    return {"date": today.isoformat(), "doctors": doctors}


@router.post("/staff/doctors/{doctor_id}/session", tags=["staff"])
def open_session(doctor_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """Open today's queue session for a doctor, so doctor events (S7) can be recorded before anyone arrives."""
    require_role(auth.actor, "staff")
    if db.get(Doctor, doctor_id) is None:
        raise ToolError("NOT_FOUND", f"Doctor {doctor_id} does not exist.")
    session = engine.get_or_create_session(db, doctor_id, now_ist().date())
    db.commit()
    return {"session_id": session.id, "doctor_id": doctor_id, "status": session.status}


# --------------------------------------------------------------------------- dashboard (S8)


def _evaluation_summary() -> dict:
    """The latest evaluation results shipped with the app (FR-32). Nothing here is computed: it is
    read from the result files the evaluation runs wrote."""

    def load(name: str) -> dict | None:
        path = RESULTS_DIR / name
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return None

    out: dict = {}
    if agent := load("agent.json"):
        s = agent.get("summary", {})
        out["agent"] = {k: s.get(k) for k in ("runs", "scenarios_run", "scenarios_total", "pass_1", "wrong_action_rate",
                                              "median_turn_latency_s", "mean_cost_per_conversation_usd")}  # fmt: skip
        out["agent"]["run_at"] = agent.get("header", {}).get("run_at")
    if safety := load("safety.json"):
        out["safety"] = {name: data.get("summary") for name, data in safety.get("sets", {}).items()}
        out["safety_run_at"] = safety.get("header", {}).get("run_at")
    if rag := load("rag.json"):
        cv = rag.get("retrieval", {}).get("threshold_cv", {}).get("cross_validated", {})
        out["rag"] = {"recall_at_5": cv.get("recall_at_5"), "answers": rag.get("answers")}
    if ml := load("ml_wait_time.json"):
        test = ml.get("test", {})
        out["wait_time"] = {
            "model_mae": test.get("model", {}).get("mae"),
            "baseline_mae": test.get("position_x_10", {}).get("mae"),
            "range_coverage": test.get("model", {}).get("range_coverage"),
        }
    return out


def _operations() -> dict:
    """Latency, errors and cost of the recent chat turns in this process (NFR-14)."""
    traces = [t for t in recent_traces(200) if t.get("turn_type") == "agent"]
    llm_spans = [s for t in traces for s in t.get("spans", []) if s.get("kind") == "llm"]
    latencies = [t["latency_ms"] for t in traces if "latency_ms" in t]
    return {
        "turns": len(traces),
        "median_latency_s": round(statistics.median(latencies) / 1000, 2) if latencies else None,
        "llm_calls": len(llm_spans),
        "llm_errors": sum(1 for s in llm_spans if s.get("error")),
        "cost_usd": round(sum(t.get("cost_usd", 0) for t in traces), 6),
        "providers": dict(Counter(f"{s['provider']}:{s['model']}" for s in llm_spans if s.get("provider"))),
    }


@router.get("/admin/dashboard", tags=["admin"])
def dashboard(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """Live queues, delays and today's no-shows per department (FR-29), the latest evaluation
    results (FR-32), and recent latency and cost."""
    require_role(auth.actor, "admin")
    today: date = now_ist().date()
    sessions = db.scalars(select(QueueSession).where(QueueSession.date == today)).all()
    appointments = db.scalars(select(Appointment).where(Appointment.appt_date == today)).all()
    departments = []
    for dept in db.scalars(select(Department).order_by(Department.name)):
        dept_sessions = [s for s in sessions if s.doctor.department_id == dept.id]
        dept_appts = [a for a in appointments if a.doctor.department_id == dept.id]
        waiting = sum(1 for s in dept_sessions for e in s.entries if e.status in ("waiting", "called"))
        delays = [s.delay_minutes for s in dept_sessions if s.doctor_status == "delayed"]
        departments.append(
            {
                "department": dept.name,
                "sessions": len(dept_sessions),
                "waiting": waiting,
                "doctors_delayed": len(delays),
                "average_delay_min": round(statistics.mean(delays), 1) if delays else 0,
                "doctors_on_break": sum(1 for s in dept_sessions if s.doctor_status == "on_break"),
                "doctors_unavailable": sum(1 for s in dept_sessions if s.doctor_status == "unavailable"),
                "booked_today": sum(1 for a in dept_appts if a.status in (*ACTIVE_APPOINTMENT_STATUSES, "completed")),
                "no_shows_today": sum(1 for a in dept_appts if a.status == "no_show"),
            }
        )
    return {
        "date": today.isoformat(),
        "departments": departments,
        "evaluation": _evaluation_summary(),
        "operations": _operations(),
    }


# --------------------------------------------------------------------------- demo reset (FR-34)


@router.post("/admin/reset", tags=["admin"])
def demo_reset(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """Wipe every operational table and reload the simulator's seed data for today (TC-17)."""
    from simulator.seed import reset_demo

    require_role(auth.actor, "admin")
    settings = get_settings()
    if not settings.demo_mode:
        raise ToolError("FORBIDDEN", "Demo reset is only available in demo mode.")
    # TRUNCATE needs exclusive locks; fail with a clear error rather than wait behind a stuck transaction.
    db.execute(text("SET LOCAL lock_timeout = '15s'"))
    result = reset_demo(db, now_ist().date(), settings.simulator_seed)
    db.commit()
    chat_limiter.reset()
    return {"status": "reset", **result}
