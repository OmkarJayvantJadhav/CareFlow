"""Plain-dict views of records, shared by the REST API and the agent tools."""

from app.db.models import Appointment, Doctor, QueueEntry, Slot, WaitingList
from app.timeutil import iso, to_ist


def doctor_dict(d: Doctor) -> dict:
    return {
        "doctor_id": d.id,
        "name": d.name,
        "department": d.department.name,
        "languages": list(d.languages),
        "opd_days": list(d.opd_days),
        "slot_minutes": d.slot_minutes,
    }


def slot_dict(s: Slot) -> dict:
    start = to_ist(s.start_at)
    return {
        "slot_id": s.id,
        "doctor_id": s.doctor_id,
        "date": start.date().isoformat(),
        "time": start.strftime("%H:%M"),
        "start_at": iso(s.start_at),
        "end_at": iso(s.end_at),
    }


def appointment_dict(a: Appointment) -> dict:
    return {
        "appointment_id": a.id,
        "patient_id": a.patient_id,
        "patient_name": a.patient.name,
        "doctor_id": a.doctor_id,
        "doctor_name": a.doctor.name,
        "department": a.doctor.department.name,
        "slot_id": a.slot_id,
        "date": a.appt_date.isoformat(),
        "time": to_ist(a.slot.start_at).strftime("%H:%M"),
        "start_at": iso(a.slot.start_at),
        "status": a.status,
        "source": a.source,
    }


def waiting_list_dict(w: WaitingList) -> dict:
    return {
        "waiting_list_id": w.id,
        "patient_id": w.patient_id,
        "doctor_id": w.doctor_id,
        "preferred_dates": [d.isoformat() for d in w.preferred_dates],
        "status": w.status,
        "offered_slot_id": w.offered_slot_id,
        "offer_expires_at": iso(w.offer_expires_at),
    }


def entry_dict(e: QueueEntry) -> dict:
    return {
        "entry_id": e.id,
        "session_id": e.session_id,
        "token": e.token,
        "kind": e.kind,
        "patient_id": e.patient_id,
        "appointment_id": e.appointment_id,
        "position": e.position,
        "priority": e.priority,
        "status": e.status,
        "scheduled_at": iso(e.scheduled_at),
        "checked_in_at": iso(e.checked_in_at),
        "called_at": iso(e.called_at),
        "consult_start": iso(e.consult_start),
        "consult_end": iso(e.consult_end),
        "late_minutes": e.late_minutes,
        "joined_remotely": e.joined_remotely,
        "arrived_at": iso(e.arrived_at),
        "transferred_from_id": e.transferred_from_id,
    }
