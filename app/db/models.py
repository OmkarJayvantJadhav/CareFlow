"""The CareFlow tables (docs §6), in three groups: scheduling, queue, platform.

The 17 tables of the database design plus ``conversation`` (chat state, docs/DECISIONS.md D-24).

Enumerated columns are plain text guarded by CHECK constraints so that values
can be extended by a migration without type juggling.
"""

from datetime import date, datetime, time

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 384

ROLES = ("patient", "caregiver", "staff", "admin", "doctor")
LANGUAGES = ("en", "hi", "mr")
SLOT_STATUSES = ("free", "booked", "blocked")
# "left": the patient checked in but went home before being seen (feature 47); a no-show never arrived.
APPOINTMENT_STATUSES = ("booked", "rescheduled", "cancelled", "completed", "no_show", "displaced", "left")
ACTIVE_APPOINTMENT_STATUSES = ("booked", "rescheduled")
APPOINTMENT_SOURCES = ("agent", "staff", "simulator")
WAITLIST_STATUSES = ("active", "offered", "fulfilled", "cancelled")
ACTIVE_WAITLIST_STATUSES = ("active", "offered")
MERGE_RULES = ("slot_order", "alternate")
DOCTOR_STATUSES = ("available", "on_break", "delayed", "unavailable")
SESSION_STATUSES = ("open", "closed")
ENTRY_KINDS = ("booked", "walk_in")
# "transferred": moved to another doctor (a new entry carries on there); "left": left without being seen.
ENTRY_STATUSES = ("waiting", "called", "in_consultation", "done", "missed", "closed", "transferred", "left")
WAITING_ENTRY_STATUSES = ("waiting", "called")
EVENT_TYPES = (
    "check_in",
    "walk_in",
    "call",
    "consult_start",
    "consult_end",
    "missed_turn",
    "return",
    "priority",
    "break",
    "resume",
    "delay",
    "emergency",
    "unavailable",
    "session_closed",
    "remote_join",
    "arrived",
    "transfer_out",
    "transfer_in",
    "left",
    "priority_request",
)
NOTIFICATION_CHANNELS = ("sms", "whatsapp")
# What a notification is about; reminders are sent once per appointment and kind.
NOTIFICATION_KINDS = (
    "info", "reminder_day", "reminder_soon", "rebook", "unavailable", "turn_near", "transfer", "delay",
)  # fmt: skip
HANDOFF_STATUSES = ("open", "in_progress", "closed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


TZ = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- scheduling


class Department(Base):
    __tablename__ = "department"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    floor: Mapped[int] = mapped_column(SmallInteger)
    opd_start: Mapped[time] = mapped_column(Time)
    opd_end: Mapped[time] = mapped_column(Time)

    doctors: Mapped[list["Doctor"]] = relationship(back_populates="department")


class Doctor(Base):
    __tablename__ = "doctor"
    __table_args__ = (CheckConstraint("slot_minutes BETWEEN 5 AND 60", name="ck_doctor_slot_minutes"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    languages: Mapped[list[str]] = mapped_column(ARRAY(String(8)))
    # ISO weekdays, 1 = Monday … 7 = Sunday.
    opd_days: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger))
    slot_minutes: Mapped[int] = mapped_column(SmallInteger)

    department: Mapped[Department] = relationship(back_populates="doctors")


class Slot(Base):
    __tablename__ = "slot"
    __table_args__ = (
        UniqueConstraint("doctor_id", "start_at", name="uq_slot_doctor_start"),
        CheckConstraint(_in("status", SLOT_STATUSES), name="ck_slot_status"),
        CheckConstraint("end_at > start_at", name="ck_slot_times"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"))
    start_at: Mapped[datetime] = mapped_column(TZ)
    end_at: Mapped[datetime] = mapped_column(TZ)
    status: Mapped[str] = mapped_column(String(10), default="free", server_default="free")
    # FR-14: a freed slot is held for the first waiting-list patient until held_until.
    held_for_patient_id: Mapped[int | None] = mapped_column(ForeignKey("patient.id"))
    held_until: Mapped[datetime | None] = mapped_column(TZ)

    doctor: Mapped[Doctor] = relationship()


class Patient(Base):
    __tablename__ = "patient"
    __table_args__ = (
        CheckConstraint(_in("preferred_language", LANGUAGES), name="ck_patient_language"),
        # The phone number is stored masked only (docs §6, NFR-08).
        CheckConstraint("phone_masked ~ '^\\+91 [0-9]{2}X{6}[0-9]{2}$'", name="ck_patient_phone_masked"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    synthetic_name: Mapped[str] = mapped_column(String(120))
    birth_year: Mapped[int] = mapped_column(SmallInteger)
    phone_masked: Mapped[str] = mapped_column(String(20))
    preferred_language: Mapped[str] = mapped_column(String(8), default="en")
    # Patient categories set by staff (feature 30); senior and child are worked out from the birth year.
    pregnant: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    disability: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint(_in("role", ROLES), name="ck_app_user_role"),
        CheckConstraint("role <> 'patient' OR patient_id IS NOT NULL", name="ck_app_user_patient_has_record"),
        CheckConstraint("role <> 'doctor' OR doctor_id IS NOT NULL", name="ck_app_user_doctor_has_record"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(12))
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patient.id"))
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("doctor.id"))  # a doctor's own account
    # Accounts people create themselves have a password (scrypt hash); the seeded demo accounts have none.
    password_hash: Mapped[str | None] = mapped_column(String(200))
    self_registered: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    # Account management (phase 7A): a switched-off account cannot sign in; an account created or reset by an
    # admin must choose its own password first; changing the password or role invalidates earlier sign-ins.
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    credentials_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_login_at: Mapped[datetime | None] = mapped_column(TZ)


class CaregiverLink(Base):
    __tablename__ = "caregiver_link"

    caregiver_user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id"), primary_key=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class Appointment(Base):
    __tablename__ = "appointment"
    __table_args__ = (
        CheckConstraint(_in("status", APPOINTMENT_STATUSES), name="ck_appointment_status"),
        CheckConstraint(_in("source", APPOINTMENT_SOURCES), name="ck_appointment_source"),
        # One active appointment per slot: double booking is impossible in the DB.
        Index(
            "uq_appointment_active_slot",
            "slot_id",
            unique=True,
            postgresql_where=text(_in("status", ACTIVE_APPOINTMENT_STATUSES)),
        ),
        # FR-11: no duplicate active booking for the same patient, doctor and day.
        Index(
            "uq_appointment_active_patient_doctor_day",
            "patient_id",
            "doctor_id",
            "appt_date",
            unique=True,
            postgresql_where=text(_in("status", ACTIVE_APPOINTMENT_STATUSES)),
        ),
        Index("ix_appointment_patient", "patient_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id"))
    slot_id: Mapped[int] = mapped_column(ForeignKey("slot.id"))
    # Denormalised from the slot so the duplicate rule can be a partial unique index.
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"))
    appt_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default="booked")
    source: Mapped[str] = mapped_column(String(10))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(TZ)

    slot: Mapped[Slot] = relationship()
    patient: Mapped[Patient] = relationship()
    doctor: Mapped[Doctor] = relationship()


class WaitingList(Base):
    __tablename__ = "waiting_list"
    __table_args__ = (
        CheckConstraint(_in("status", WAITLIST_STATUSES), name="ck_waiting_list_status"),
        Index(
            "uq_waiting_list_active",
            "patient_id",
            "doctor_id",
            unique=True,
            postgresql_where=text(_in("status", ACTIVE_WAITLIST_STATUSES)),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"))
    preferred_dates: Mapped[list[date]] = mapped_column(ARRAY(Date))
    status: Mapped[str] = mapped_column(String(10), default="active")
    offered_slot_id: Mapped[int | None] = mapped_column(ForeignKey("slot.id"))
    offer_expires_at: Mapped[datetime | None] = mapped_column(TZ)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


# --------------------------------------------------------------------------- queue


class QueueSession(Base):
    __tablename__ = "queue_session"
    __table_args__ = (
        UniqueConstraint("doctor_id", "date", name="uq_queue_session_doctor_date"),
        CheckConstraint(_in("merge_rule", MERGE_RULES), name="ck_queue_session_merge_rule"),
        CheckConstraint(_in("doctor_status", DOCTOR_STATUSES), name="ck_queue_session_doctor_status"),
        CheckConstraint(_in("status", SESSION_STATUSES), name="ck_queue_session_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"))
    date: Mapped[date] = mapped_column(Date)
    merge_rule: Mapped[str] = mapped_column(String(12))
    started_at: Mapped[datetime | None] = mapped_column(TZ)
    status: Mapped[str] = mapped_column(String(8), default="open")
    doctor_status: Mapped[str] = mapped_column(String(12), default="available")
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    # While on a break or handling an emergency, the doctor is busy until this time.
    busy_until: Mapped[datetime | None] = mapped_column(TZ)
    closed_at: Mapped[datetime | None] = mapped_column(TZ)

    doctor: Mapped[Doctor] = relationship()
    entries: Mapped[list["QueueEntry"]] = relationship(back_populates="session", order_by="QueueEntry.id")


class QueueEntry(Base):
    __tablename__ = "queue_entry"
    __table_args__ = (
        UniqueConstraint("session_id", "token", name="uq_queue_entry_token"),
        # One live entry per appointment; a transferred entry hands the appointment on to its successor.
        Index(
            "uq_queue_entry_appointment",
            "appointment_id",
            unique=True,
            postgresql_where=text("status <> 'transferred'"),
        ),
        CheckConstraint(_in("kind", ENTRY_KINDS), name="ck_queue_entry_kind"),
        CheckConstraint(_in("status", ENTRY_STATUSES), name="ck_queue_entry_status"),
        CheckConstraint("kind = 'walk_in' OR appointment_id IS NOT NULL", name="ck_queue_entry_booked_has_appt"),
        Index("ix_queue_entry_session", "session_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("queue_session.id"))
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointment.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id"))
    token: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(8))
    # Slot start for booked entries; used by the merge rule.
    scheduled_at: Mapped[datetime | None] = mapped_column(TZ)
    checked_in_at: Mapped[datetime] = mapped_column(TZ)
    # Set when a patient who missed their turn comes back.
    requeued_at: Mapped[datetime | None] = mapped_column(TZ)
    position: Mapped[int | None] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(SmallInteger, default=0)
    called_at: Mapped[datetime | None] = mapped_column(TZ)
    consult_start: Mapped[datetime | None] = mapped_column(TZ)
    consult_end: Mapped[datetime | None] = mapped_column(TZ)
    late_minutes: Mapped[int | None] = mapped_column(Integer)  # booked arrivals after their slot (feature 33)
    status: Mapped[str] = mapped_column(String(16), default="waiting")
    # Virtual queue (feature 38): joined from a phone; arrived_at is set when they reach the desk.
    joined_remotely: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    arrived_at: Mapped[datetime | None] = mapped_column(TZ)
    # Set on the new entry when a patient is moved from another doctor's queue (features 42, 43, 53).
    transferred_from_id: Mapped[int | None] = mapped_column(ForeignKey("queue_entry.id"))

    session: Mapped[QueueSession] = relationship(back_populates="entries")
    appointment: Mapped[Appointment | None] = relationship()
    patient: Mapped[Patient] = relationship()


class QueueEvent(Base):
    """Append-only (enforced by a trigger in the migration)."""

    __tablename__ = "queue_event"
    __table_args__ = (
        CheckConstraint(_in("type", EVENT_TYPES), name="ck_queue_event_type"),
        Index("ix_queue_event_session", "session_id", "at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("queue_session.id"))
    type: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    at: Mapped[datetime] = mapped_column(TZ)


class WaitPrediction(Base):
    """Append-only (enforced by a trigger in the migration)."""

    __tablename__ = "wait_prediction"
    __table_args__ = (Index("ix_wait_prediction_entry", "entry_id", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("queue_entry.id"))
    predicted_min: Mapped[float]
    low_min: Mapped[float]
    high_min: Mapped[float]
    model_version: Mapped[str] = mapped_column(String(40))
    at: Mapped[datetime] = mapped_column(TZ)


# --------------------------------------------------------------------------- platform


class KbDocument(Base):
    __tablename__ = "kb_document"
    __table_args__ = (CheckConstraint(_in("language", LANGUAGES), name="ck_kb_document_language"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(8))
    last_verified: Mapped[date] = mapped_column(Date)
    source_path: Mapped[str] = mapped_column(String(300), unique=True)
    # Translations of one document share a doc_key, e.g. "test_preparation/lipid-profile".
    doc_key: Mapped[str] = mapped_column(String(200), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))

    chunks: Mapped[list["KbChunk"]] = relationship(back_populates="document", order_by="KbChunk.chunk_index")


class KbChunk(Base):
    __tablename__ = "kb_chunk"
    __table_args__ = (
        Index(
            "ix_kb_chunk_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_kb_chunk_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("kb_document.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(SmallInteger)
    section: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    # Which embedder produced the vector; queries only compare vectors from the same one.
    embedding_model: Mapped[str] = mapped_column(String(120), index=True)
    # 'simple' configuration: no stemming, works for English, Hindi and Marathi.
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', coalesce(section, '') || ' ' || text)", persisted=True)
    )

    document: Mapped[KbDocument] = relationship(back_populates="chunks")


class Notification(Base):
    __tablename__ = "notification"
    __table_args__ = (
        CheckConstraint(_in("channel", NOTIFICATION_CHANNELS), name="ck_notification_channel"),
        CheckConstraint(_in("kind", NOTIFICATION_KINDS), name="ck_notification_kind"),
        Index(
            "uq_notification_reminder",
            "appointment_id",
            "kind",
            unique=True,
            postgresql_where=text("kind IN ('reminder_day', 'reminder_soon')"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id"), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(TZ)
    mocked: Mapped[bool] = mapped_column(Boolean, default=True)
    kind: Mapped[str] = mapped_column(String(16), default="info", server_default="info")
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointment.id"))
    read_at: Mapped[datetime | None] = mapped_column(TZ)


CONSENT_PURPOSES = ("reuse_registration", "reminders", "caregiver_access")
PATIENT_CATEGORIES = ("senior", "child", "pregnant", "disability")
FIELD_KINDS = ("text", "number", "choice", "yes_no")


class RegistrationField(Base):
    """An extra question on the registration forms, configured by an admin (feature 28)."""

    __tablename__ = "registration_field"
    __table_args__ = (CheckConstraint(_in("kind", FIELD_KINDS), name="ck_registration_field_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    label_en: Mapped[str] = mapped_column(String(80))
    label_hi: Mapped[str] = mapped_column(String(80))
    label_mr: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10))
    options: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    position: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


class PatientFieldValue(Base):
    __tablename__ = "patient_field_value"

    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id"), primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("registration_field.id"), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


class Consent(Base):
    """Append-only consent history; the latest row per patient and purpose is in force (feature 35)."""

    __tablename__ = "consent"
    __table_args__ = (
        CheckConstraint(_in("purpose", CONSENT_PURPOSES), name="ck_consent_purpose"),
        Index("ix_consent_patient_purpose", "patient_id", "purpose", "at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id"))
    purpose: Mapped[str] = mapped_column(String(24))
    granted: Mapped[bool] = mapped_column(Boolean)
    at: Mapped[datetime] = mapped_column(TZ)
    by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))


class CaregiverRequest(Base):
    """A caregiver asks to act for a patient; the patient approves or declines (feature 35)."""

    __tablename__ = "caregiver_request"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'declined')", name="ck_caregiver_request_status"),
        Index(
            "uq_caregiver_request_pending",
            "caregiver_user_id",
            "patient_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    caregiver_user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id"))
    status: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending")
    requested_at: Mapped[datetime] = mapped_column(TZ)
    decided_at: Mapped[datetime | None] = mapped_column(TZ)


class DoctorLeave(Base):
    """Days a doctor is away; their slots are blocked and booked patients asked to rebook."""

    __tablename__ = "doctor_leave"
    __table_args__ = (CheckConstraint("end_date >= start_date", name="ck_doctor_leave_dates"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(120), default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())

    doctor: Mapped[Doctor] = relationship()


class PriorityRule(Base):
    """Automatic queue priority per patient category (feature 51); 0 means the category gets no priority."""

    __tablename__ = "priority_rule"
    __table_args__ = (
        CheckConstraint(_in("category", PATIENT_CATEGORIES), name="ck_priority_rule_category"),
        CheckConstraint("weight BETWEEN 0 AND 3", name="ck_priority_rule_weight"),
    )

    category: Mapped[str] = mapped_column(String(12), primary_key=True)
    weight: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    # Who changed a weight is in the audit log; no foreign key, so a demo reset keeps the configuration.
    updated_at: Mapped[datetime | None] = mapped_column(TZ)


class PriorityRequest(Base):
    """The front desk asks for a priority change; the patient's doctor authorizes or declines it (feature 52)."""

    __tablename__ = "priority_request"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'declined')", name="ck_priority_request_status"),
        CheckConstraint("priority BETWEEN 0 AND 3", name="ck_priority_request_priority"),
        Index("uq_priority_request_pending", "entry_id", unique=True, postgresql_where=text("status = 'pending'")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("queue_entry.id"))
    priority: Mapped[int] = mapped_column(SmallInteger)
    reason: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending")
    requested_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    requested_at: Mapped[datetime] = mapped_column(TZ)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    decided_at: Mapped[datetime | None] = mapped_column(TZ)

    entry: Mapped[QueueEntry] = relationship()


class AuditLog(Base):
    """Append-only (enforced by a trigger in the migration). Arguments are masked."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), index=True)
    role: Mapped[str] = mapped_column(String(12))
    tool: Mapped[str] = mapped_column(String(60))
    arguments: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(TZ)


class Conversation(Base):
    """Chat state: compact history, the pending confirmation card and counters."""

    __tablename__ = "conversation"
    __table_args__ = (
        CheckConstraint(_in("language", LANGUAGES), name="ck_conversation_language"),
        Index("ix_conversation_user", "user_id"),
        Index("ix_conversation_session", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    session_id: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8), default="en")
    history: Mapped[list] = mapped_column(JSONB, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    pending_action: Mapped[dict | None] = mapped_column(JSONB)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    handoff_ticket_id: Mapped[int | None] = mapped_column(ForeignKey("handoff_ticket.id"))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


class HandoffTicket(Base):
    __tablename__ = "handoff_ticket"
    __table_args__ = (CheckConstraint(_in("status", HANDOFF_STATUSES), name="ck_handoff_ticket_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="open")
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


# Everything that demo reset wipes and reloads (FR-34). The knowledge base is
# reference content, loaded by its own ingestion step, and is left alone.
OPERATIONAL_TABLES = (
    "priority_request",
    "caregiver_request",
    "consent",
    "patient_field_value",
    "doctor_leave",
    "conversation",
    "handoff_ticket",
    "audit_log",
    "notification",
    "wait_prediction",
    "queue_event",
    "queue_entry",
    "queue_session",
    "waiting_list",
    "appointment",
    "caregiver_link",
    "app_user",
    "slot",
    "patient",
    "doctor",
    "department",
)
