"""Smart slot recommendations (features 3 and 14).

Every free slot that matches the request is scored in code, and the best few come back with the
reasons they were chosen. The score is a simple, explainable sum, not a model:

* sooner is better (one point less per day of waiting);
* +2 at the preferred time of day (morning before 12:00, afternoon from 12:00);
* +1.5 if the doctor speaks the patient's language;
* +2 if the patient has seen this doctor before (continuity of care);
* up to +1.5 on a quieter day (fewer of the doctor's slots already booked).

At most two slots per doctor and day are returned, so the list offers real choices.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import any_, literal, select
from sqlalchemy.orm import Session

from app.db.models import ACTIVE_APPOINTMENT_STATUSES, Appointment, Department, Doctor, Patient, Slot
from app.timeutil import at, resolve_now, to_ist
from app.tools import policy
from app.tools.calendar import consult_minutes
from app.tools.errors import ToolError
from app.tools.permissions import Actor, require_patient_access
from app.tools.vocab import normalize_language, normalize_specialty

DEFAULT_WINDOW_DAYS = 14
PER_DOCTOR_DAY = 2
TIMES_OF_DAY = ("any", "morning", "afternoon")


def _time_matches(start: datetime, time_of_day: str) -> bool:
    hour = to_ist(start).hour
    return time_of_day == "any" or (time_of_day == "morning") == (hour < 12)


def recommend_slots(
    db: Session,
    actor: Actor,
    patient_id: int,
    specialty: str | None = None,
    doctor_id: int | None = None,
    language: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    time_of_day: str = "any",
    limit: int = 6,
    now: datetime | None = None,
) -> dict:
    now = resolve_now(now)
    require_patient_access(db, actor, patient_id)
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise ToolError("NOT_FOUND", f"Patient {patient_id} does not exist.")
    if time_of_day not in TIMES_OF_DAY:
        raise ToolError("VALIDATION_ERROR", "Time of day must be any, morning or afternoon.")
    if not specialty and doctor_id is None:
        raise ToolError("VALIDATION_ERROR", "Choose a department or a doctor.")
    lang = normalize_language(language) if language else patient.preferred_language
    first = max(date_from or now.date(), now.date())
    last_allowed = (now + policy.BOOKING_HORIZON).date()
    last = min(date_to or first + timedelta(days=DEFAULT_WINDOW_DAYS - 1), last_allowed)
    if last < first:
        raise ToolError("VALIDATION_ERROR", "The date range is empty or outside the 30-day booking window.")

    doctors_q = select(Doctor).join(Department).order_by(Doctor.id)
    if doctor_id is not None:
        doctors_q = doctors_q.where(Doctor.id == doctor_id)
    else:
        doctors_q = doctors_q.where(Department.name == normalize_specialty(specialty))
    if language and doctor_id is None:
        doctors_q = doctors_q.where(literal(lang) == any_(Doctor.languages))
    doctors = {d.id: d for d in db.scalars(doctors_q)}
    if not doctors:
        return {"criteria": {"language": lang, "from": first.isoformat(), "to": last.isoformat()}, "slots": []}

    lo, hi = at(first, time.min), at(last + timedelta(days=1), time.min)
    earliest = now + policy.BOOKING_LEAD
    slots = list(
        db.scalars(
            select(Slot)
            .where(Slot.doctor_id.in_(doctors), Slot.start_at >= lo, Slot.start_at < hi, Slot.start_at >= earliest)
            .order_by(Slot.start_at)
        )
    )
    # Day load: the share of each doctor's slots that day that are already booked.
    load: dict[tuple[int, date], list[int]] = defaultdict(lambda: [0, 0])
    for s in slots:
        key = (s.doctor_id, to_ist(s.start_at).date())
        load[key][1] += 1
        load[key][0] += s.status == "booked"
    seen_before = set(
        db.scalars(
            select(Appointment.doctor_id).where(Appointment.patient_id == patient_id, Appointment.status == "completed")
        )
    )
    busy_days = {
        (doctor, day)
        for doctor, day in db.execute(
            select(Appointment.doctor_id, Appointment.appt_date).where(
                Appointment.patient_id == patient_id, Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES)
            )
        )
    }

    scored = []
    for s in slots:
        held_for_other = s.held_until is not None and s.held_until > now and s.held_for_patient_id != patient_id
        day = to_ist(s.start_at).date()
        if s.status != "free" or held_for_other or (s.doctor_id, day) in busy_days:
            continue
        doctor = doctors[s.doctor_id]
        booked, total = load[(s.doctor_id, day)]
        reasons, score = [], -float((day - now.date()).days)
        if time_of_day != "any" and _time_matches(s.start_at, time_of_day):
            score += 2
            reasons.append("preferred_time")
        if lang in doctor.languages:
            score += 1.5
            reasons.append("speaks_language")
        if doctor.id in seen_before:
            score += 2
            reasons.append("seen_before")
        quiet = 1 - booked / total if total else 1
        score += 1.5 * quiet
        if quiet >= 0.5:
            reasons.append("quieter_day")
        scored.append((score, s, reasons))

    scored.sort(key=lambda item: (-item[0], item[1].start_at, item[1].doctor_id))
    durations = consult_minutes(db, list(doctors), now)
    per_doctor_day: dict[tuple[int, date], int] = defaultdict(int)
    picked = []
    for score, s, reasons in scored:
        key = (s.doctor_id, to_ist(s.start_at).date())
        if per_doctor_day[key] >= PER_DOCTOR_DAY:
            continue
        per_doctor_day[key] += 1
        doctor = doctors[s.doctor_id]
        start = to_ist(s.start_at)
        picked.append(
            {
                "slot_id": s.id,
                "doctor_id": doctor.id,
                "doctor_name": doctor.name,
                "department": doctor.department.name,
                "languages": list(doctor.languages),
                "date": start.date().isoformat(),
                "time": start.strftime("%H:%M"),
                "start_at": start.isoformat(),
                "reasons": reasons,
                "expected_minutes": durations[doctor.id]["typical"],
                "score": round(score, 2),
            }
        )
        if len(picked) >= max(1, min(limit, 20)):
            break
    # The soonest of the recommended slots is marked as such.
    if picked:
        min(picked, key=lambda p: p["start_at"])["reasons"].insert(0, "earliest")
    return {
        "criteria": {"language": lang, "from": first.isoformat(), "to": last.isoformat(), "time_of_day": time_of_day},
        "slots": picked,
        "cancellation_policy": policy.CANCEL_POLICY,
    }
