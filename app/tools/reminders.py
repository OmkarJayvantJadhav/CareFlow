"""Appointment reminders (feature 7): one the day before and one about two hours before, each sent
once (a unique index guards against duplicates), in the patient's language. Mocked like every
notification: stored, never actually sent."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import ACTIVE_APPOINTMENT_STATUSES, Appointment, Notification, Slot
from app.timeutil import resolve_now, to_ist
from app.tools.notify import notify
from app.tools.receipts import reference_code

DAY_BEFORE = timedelta(hours=24)
SOON = timedelta(hours=2)

TEMPLATES = {
    "reminder_day": {
        "en": "Reminder: {doctor} ({department}) tomorrow, {date} at {time}. Please arrive 15 minutes early. Ref {ref}.",
        "hi": "याद दिलाना: कल {date} को {time} बजे {doctor} ({department})। कृपया 15 मिनट पहले आएँ। संदर्भ {ref}।",
        "mr": "आठवण: उद्या {date} रोजी {time} वाजता {doctor} ({department}). कृपया 15 मिनिटे आधी या. संदर्भ {ref}.",
    },
    "reminder_soon": {
        "en": "Your appointment with {doctor} is at {time} today. Check in at the reception desk. Ref {ref}.",
        "hi": "आज {time} बजे {doctor} के साथ आपका अपॉइंटमेंट है। रिसेप्शन पर चेक-इन करें। संदर्भ {ref}।",
        "mr": "आज {time} वाजता {doctor} यांच्यासोबत तुमची अपॉइंटमेंट आहे. रिसेप्शनवर चेक-इन करा. संदर्भ {ref}.",
    },
}


def send_due_reminders(db: Session, now: datetime | None = None) -> int:
    """Send every reminder that is due and not yet sent; returns how many were sent."""
    now = resolve_now(now)
    upcoming = db.scalars(
        select(Appointment)
        .join(Slot, Slot.id == Appointment.slot_id)
        .where(
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
            Slot.start_at > now,
            Slot.start_at <= now + DAY_BEFORE,
        )
        .order_by(Slot.start_at)
    ).all()
    if not upcoming:
        return 0
    already = set(
        db.execute(
            select(Notification.appointment_id, Notification.kind).where(
                Notification.appointment_id.in_([a.id for a in upcoming]),
                Notification.kind.in_(tuple(TEMPLATES)),
            )
        ).all()
    )
    from app.tools.registration import consent_state

    sent = 0
    for appt in upcoming:
        if not consent_state(db, appt.patient_id)["reminders"]:
            continue  # the patient asked for no reminders (feature 35)
        start = to_ist(appt.slot.start_at)
        kind = "reminder_soon" if start - now <= SOON else "reminder_day"
        # Booked less than a day ahead: the day-before reminder is skipped, not sent late.
        if kind == "reminder_day" and appt.created_at and start - to_ist(appt.created_at) < DAY_BEFORE:
            continue
        if (appt.id, kind) in already:
            continue
        lang = appt.patient.preferred_language
        text = (
            TEMPLATES[kind]
            .get(lang, TEMPLATES[kind]["en"])
            .format(
                doctor=appt.doctor.name,
                department=appt.doctor.department.name,
                date=f"{start:%d %b}",
                time=f"{start:%H:%M}",
                ref=reference_code(appt.id),
            )
        )
        try:
            with db.begin_nested():
                notify(db, appt.patient_id, text, now, kind=kind, appointment_id=appt.id)
            sent += 1
        except IntegrityError:  # another process sent it a moment ago
            continue
    return sent
