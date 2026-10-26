"""Messages to patients by SMS or e-mail (phase 7E), off by default.

Every notification is shown in the app as before. When an admin has turned sending on, and the message's
kind is one the hospital sends, the notification is also queued ("pending") and the delivery worker sends
it on the patient's chosen channel (``contact_by``), or on the other one when that is not possible. The full
number or address is decrypted only at that moment and is never logged. A message that fails is tried
three times; one that has waited too long to be useful (a "your turn is near" an hour later) is skipped.
"""

import logging
import time as clock
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import NOTIFICATION_KINDS, AppUser, MessagingSetting, Notification, Patient
from app.safety.pii import decrypt_email, decrypt_phone, display_phone, normalize_email, normalize_mobile
from app.timeutil import iso, resolve_now
from app.tools import channels
from app.tools.audit import write_tool
from app.tools.errors import ToolError
from app.tools.permissions import Actor, require_role

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BATCH = 50
# After this long a message is no longer worth sending.
MAX_AGE = {
    "reminder_day": timedelta(hours=12),
    "reminder_soon": timedelta(minutes=90),
    "turn_near": timedelta(minutes=20),
    "delay": timedelta(hours=1),
    "transfer": timedelta(hours=1),
    "unavailable": timedelta(hours=12),
    "rebook": timedelta(hours=24),
    "info": timedelta(hours=3),
}
NOTES = {
    "off": "Sending was turned off before this message went out.",
    "kind_off": "The hospital does not send this kind of message.",
    "too_late": "Waited too long to be useful.",
    "app_only": "The patient asked for messages in the app only.",
    "no_address": "No phone number or e-mail address the hospital can send to.",
}
SUBJECTS = {
    "reminder": {"en": "Appointment reminder", "hi": "अपॉइंटमेंट की याद", "mr": "अपॉइंटमेंटची आठवण"},
    "change": {
        "en": "A change to your appointment",
        "hi": "आपके अपॉइंटमेंट में बदलाव",
        "mr": "तुमच्या अपॉइंटमेंटमध्ये बदल",
    },  # fmt: skip
    "queue": {"en": "Your place in the queue", "hi": "कतार में आपकी जगह", "mr": "रांगेतील तुमची जागा"},
    "other": {"en": "A message from the hospital", "hi": "अस्पताल से संदेश", "mr": "रुग्णालयाकडून संदेश"},
}
SUBJECT_OF = {"reminder_day": "reminder", "reminder_soon": "reminder", "unavailable": "change", "rebook": "change",
              "transfer": "queue", "delay": "queue", "turn_near": "queue"}  # fmt: skip
EMAIL_FOOTER = {
    "en": "To stop these e-mails, choose “In the app only” under My profile in CareFlow.",
    "hi": "ये ई-मेल बंद करने के लिए CareFlow में मेरी प्रोफ़ाइल में “सिर्फ़ ऐप में” चुनें।",
    "mr": "हे ई-मेल थांबवण्यासाठी CareFlow मध्ये माझी प्रोफाइल येथे “फक्त ॲपमध्ये” निवडा.",
}
TEST_TEXT = "Test message from {hospital}: CareFlow can send {what} to patients."


def _setting(db: Session) -> MessagingSetting | None:
    return db.get(MessagingSetting, 1)


def should_send(db: Session, kind: str) -> bool:
    """Whether a new notification of this kind is queued for sending (called by ``notify``)."""
    row = _setting(db)
    return bool(row and row.enabled and kind in (row.kinds or []))


def available(db: Session) -> dict[str, bool]:
    """The channels patients can choose from: sending on and the provider set up (shown on /config)."""
    row = _setting(db)
    on = bool(row and row.enabled)
    return {name: on and status.ready for name, status in channels.statuses().items()}


# --------------------------------------------------------------------------- delivery worker


def _hospital(db: Session, language: str) -> str:
    from app.tools.hospital import hospital_name  # hospital sends notifications itself

    return hospital_name(db, language) or hospital_name(db) or "CareFlow"


def _address(patient: Patient, channel: str) -> str | None:
    if channel == "sms":
        digits = decrypt_phone(patient.phone_encrypted)
        return f"+91{digits}" if digits else None
    return decrypt_email(patient.email_encrypted)


def _compose(db: Session, note: Notification, patient: Patient, channel: str) -> tuple[str, str]:
    lang = patient.preferred_language
    hospital = _hospital(db, lang)
    if channel == "sms":
        return "", f"{hospital}: {note.message}"
    subject = SUBJECTS[SUBJECT_OF.get(note.kind, "other")]
    footer = EMAIL_FOOTER.get(lang, EMAIL_FOOTER["en"])
    return f"{subject.get(lang, subject['en'])} – {hospital}", f"{note.message}\n\n{hospital}\n\n{footer}\n"


def _deliver_one(db: Session, note: Notification, now: datetime, status: dict, setting) -> str:
    def skip(reason: str) -> str:
        note.delivery, note.delivery_note, note.delivery_next_at = "skipped", NOTES[reason], None
        return "skipped"

    if not (setting and setting.enabled):
        return skip("off")
    if note.kind not in (setting.kinds or []):
        return skip("kind_off")
    if now - note.sent_at > MAX_AGE.get(note.kind, MAX_AGE["info"]):
        return skip("too_late")
    patient = db.get(Patient, note.patient_id)
    if patient is None or patient.erased_at is not None or patient.contact_by == "app":
        return skip("app_only")
    order = [patient.contact_by] + [c for c in ("sms", "email") if c != patient.contact_by]
    for channel in order:
        if not status[channel].ready:
            continue
        to = _address(patient, channel)
        if not to:
            continue
        subject, text = _compose(db, note, patient, channel)
        note.delivery_attempts += 1
        try:
            channels.send(channel, to, subject, text, reference=f"n{note.id}")
        except Exception as err:  # noqa: BLE001 - a provider failure must not stop the other messages
            reason = str(err) if isinstance(err, channels.DeliveryError) else "Unexpected error while sending."
            if not isinstance(err, channels.DeliveryError):
                log.exception("sending notification %s failed", note.id)
            note.delivery_note = reason[:200]
            if note.delivery_attempts >= MAX_ATTEMPTS:
                note.delivery, note.delivery_next_at = "failed", None
                return "failed"
            note.delivery_next_at = now + timedelta(minutes=2**note.delivery_attempts)
            return "retry"
        note.delivery, note.delivered_via, note.delivered_at = "sent", channel, now
        note.delivery_note, note.delivery_next_at = None, None
        note.mocked = not status[channel].real
        return "sent"
    return skip("no_address")


def deliver_due(db: Session, now: datetime | None = None, limit: int = BATCH) -> dict[str, int]:
    """Send what is waiting in the outbox. Each message is committed on its own, so a message is never sent
    twice by two workers (rows are locked, others skipped) and one failure does not undo the rest."""
    now = resolve_now(now)
    ids = db.scalars(
        select(Notification.id)
        .where(
            Notification.delivery == "pending",
            or_(Notification.delivery_next_at.is_(None), Notification.delivery_next_at <= now),
        )
        .order_by(Notification.id)
        .limit(limit)
    ).all()
    counts: Counter[str] = Counter()
    if not ids:
        return {}
    status = channels.statuses()
    for nid in ids:
        note = db.scalars(
            select(Notification)
            .where(Notification.id == nid, Notification.delivery == "pending")
            .with_for_update(skip_locked=True)
        ).first()
        if note is None:
            continue
        counts[_deliver_one(db, note, now, status, _setting(db))] += 1
        db.commit()
    return dict(counts)


# --------------------------------------------------------------------------- admin


def messaging_view(db: Session, actor: Actor, now: datetime | None = None) -> dict:
    now = resolve_now(now)
    require_role(actor, "admin")
    row = _setting(db)
    since = now - timedelta(days=7)
    counts = dict(
        db.execute(
            select(Notification.delivery, func.count())
            .where(Notification.delivery.is_not(None), Notification.sent_at >= since)
            .group_by(Notification.delivery)
        ).all()
    )
    problems = db.scalars(
        select(Notification)
        .where(Notification.delivery.in_(("failed", "skipped")), Notification.sent_at >= since)
        .order_by(Notification.sent_at.desc(), Notification.id.desc())
        .limit(20)
    ).all()
    return {
        "enabled": bool(row and row.enabled),
        "kinds": list(row.kinds) if row else [],
        "all_kinds": list(NOTIFICATION_KINDS),
        "channels": {name: status.view() for name, status in channels.statuses().items()},
        "demo_mode": get_settings().demo_mode,
        "last_7_days": {k: counts.get(k, 0) for k in ("pending", "sent", "failed", "skipped")},
        "problems": [
            {
                "notification_id": n.id,
                "kind": n.kind,
                "status": n.delivery,
                "via": n.delivered_via,
                "note": n.delivery_note or "",
                "at": iso(n.sent_at),
            }
            for n in problems
        ],
        "updated_at": iso(row.updated_at) if row else None,
        "updated_by": row.updated_by if row else None,
    }


@write_tool("update_messaging")
def update_messaging(db: Session, actor: Actor, enabled: bool, kinds: list[str], now: datetime | None = None) -> dict:
    """Turn sending on or off and choose which kinds of message go out by SMS or e-mail."""
    now = resolve_now(now)
    require_role(actor, "admin")
    unknown = sorted(set(kinds) - set(NOTIFICATION_KINDS))
    if unknown:
        raise ToolError("VALIDATION_ERROR", f"Unknown kind of message: {unknown[0]}.")
    if enabled and not kinds:
        raise ToolError("VALIDATION_ERROR", "Choose at least one kind of message to send.")
    if enabled and not any(s.ready for s in channels.statuses().values()):
        raise ToolError(
            "INVALID_STATE",
            "Neither SMS nor e-mail is set up on the server yet. See DEPLOY.md, “Messages by SMS and e-mail”.",
        )
    row = _setting(db)
    if row is None:
        row = MessagingSetting(id=1)
        db.add(row)
    row.enabled = enabled
    row.kinds = [k for k in NOTIFICATION_KINDS if k in set(kinds)]
    row.updated_at = now
    row.updated_by = db.scalar(select(AppUser.username).where(AppUser.id == actor.user_id))
    db.flush()
    return messaging_view(db, actor, now)


_recent_tests: dict[int, list[float]] = {}
TESTS_PER_10_MIN = 5


@write_tool("send_test_message")
def send_test_message(db: Session, actor: Actor, channel: str, to: str, now: datetime | None = None) -> dict:
    """Send one test message now to a number or address the admin types (audited, with it masked)."""
    resolve_now(now)
    require_role(actor, "admin")
    if channel not in ("sms", "email"):
        raise ToolError("VALIDATION_ERROR", "Choose SMS or e-mail.")
    address = f"+91{normalize_mobile(to)}" if channel == "sms" else normalize_email(to)
    if not address:
        raise ToolError("VALIDATION_ERROR", "Enter the e-mail address to send the test to.")
    status = channels.channel_status(channel)
    if not status.ready:
        raise ToolError("INVALID_STATE", "This channel is not set up on the server.")
    moment = clock.monotonic()
    recent = [t for t in _recent_tests.get(actor.user_id, []) if moment - t < 600]
    if len(recent) >= TESTS_PER_10_MIN:
        raise ToolError("RATE_LIMITED", "Please wait a few minutes before sending another test.", retry_after=600)
    _recent_tests[actor.user_id] = [*recent, moment]
    hospital = _hospital(db, "en")
    text = TEST_TEXT.format(hospital=hospital, what="text messages" if channel == "sms" else "e-mails")
    try:
        channels.send(channel, address, f"Test message – {hospital}", text, reference="test")
    except channels.DeliveryError as err:
        raise ToolError("DELIVERY_FAILED", str(err)) from None
    shown = display_phone(address[3:]) if channel == "sms" else address
    return {"sent": True, "channel": channel, "provider": status.provider, "to": shown}


@write_tool("retry_failed_messages")
def retry_failed_messages(db: Session, actor: Actor, now: datetime | None = None) -> dict:
    """Queue the messages that failed in the last day again (the provider was down, a key was wrong)."""
    now = resolve_now(now)
    require_role(actor, "admin")
    queued = 0
    for note in db.scalars(
        select(Notification).where(Notification.delivery == "failed", Notification.sent_at >= now - timedelta(days=1))
    ):
        note.delivery, note.delivery_attempts, note.delivery_next_at, note.delivery_note = "pending", 0, None, None
        queued += 1
    db.flush()
    return {"queued": queued}
