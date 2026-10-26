"""Seed data: the fictional hospital, synthetic patients, slots and upcoming bookings.

Seeding is deterministic for a given (seed, reference day), which is what makes
the demo reset (FR-34) restore exactly the same state.
"""

from datetime import date, datetime, time, timedelta

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import (
    OPERATIONAL_TABLES,
    Appointment,
    AppUser,
    CaregiverLink,
    Consent,
    Department,
    Doctor,
    HospitalProfile,
    Patient,
    PatientFieldValue,
    Slot,
)
from app.safety.pii import set_phone
from app.timeutil import at
from app.tools.booking import book_appointment
from app.tools.permissions import Actor
from app.tools.timetable import SLOT_DAYS_AHEAD, ensure_slots, top_up_slots  # noqa: F401 - re-exported
from simulator import hospital

PATIENT_COUNT = 400
SEED_DAYS_AHEAD = SLOT_DAYS_AHEAD
UPCOMING_OCCUPANCY = (0.25, 0.55)
LANGUAGE_WEIGHTS = {"mr": 0.45, "hi": 0.30, "en": 0.25}


def random_phone(rng: np.random.Generator) -> str:
    return str(rng.integers(6, 10)) + "".join(str(d) for d in rng.integers(0, 10, size=9))


def random_patient(rng: np.random.Generator) -> Patient:
    first = hospital.FIRST_NAMES[rng.integers(len(hospital.FIRST_NAMES))]
    last = hospital.LAST_NAMES[rng.integers(len(hospital.LAST_NAMES))]
    langs, weights = zip(*LANGUAGE_WEIGHTS.items(), strict=True)
    patient = Patient(name=f"{first} {last}", birth_year=int(rng.integers(1940, 2024)))
    set_phone(patient, random_phone(rng))
    patient.preferred_language = str(rng.choice(langs, p=weights))
    return patient


DEMO_ACCOUNTS_CREATED = at(date(2026, 1, 1), time(0, 0))


def seed_reference(db: Session, rng: np.random.Generator) -> None:
    db.add(HospitalProfile(id=1, **hospital.PROFILE))
    departments = {}
    for name, floor, start, end in hospital.DEPARTMENTS:
        dept = Department(name=name, floor=floor, opd_start=start, opd_end=end)
        db.add(dept)
        departments[name] = dept
    db.flush()
    for name, dept, languages, days, minutes in hospital.DOCTORS:
        db.add(
            Doctor(
                department_id=departments[dept].id, name=name, languages=languages, opd_days=days, slot_minutes=minutes
            )
        )

    demo_patients = {}
    for key, (name, birth_year, language, phone) in hospital.DEMO_PATIENTS.items():
        patient = Patient(name=name, birth_year=birth_year, preferred_language=language)
        set_phone(patient, phone)
        db.add(patient)
        demo_patients[key] = patient
    db.flush()
    for _ in range(PATIENT_COUNT):
        db.add(random_patient(rng))

    users = {}
    for username, display, role, patient_key in hospital.DEMO_USERS:
        user = AppUser(
            username=username,
            display_name=display,
            role=role,
            patient_id=demo_patients[patient_key].id if patient_key else None,
            created_at=DEMO_ACCOUNTS_CREATED,  # fixed, so a demo reset restores the accounts exactly (TC-17)
        )
        db.add(user)
        users[username] = user
    db.flush()
    ensure_doctor_accounts(db)
    for caregiver, patient_key, verified in hospital.CAREGIVER_LINKS:
        db.add(
            CaregiverLink(
                caregiver_user_id=users[caregiver].id, patient_id=demo_patients[patient_key].id, verified=verified
            )
        )
    db.flush()


def ensure_doctor_accounts(db: Session) -> int:
    """Every doctor gets an account for their own queue; databases seeded before the doctor role get theirs
    at the next start. Returns how many were added."""
    have = set(db.scalars(select(AppUser.doctor_id).where(AppUser.doctor_id.is_not(None))))
    added = 0
    for doctor in db.scalars(select(Doctor).order_by(Doctor.id)):
        if doctor.id in have:
            continue
        db.add(
            AppUser(
                username=hospital.doctor_username(doctor.name),
                display_name=doctor.name,
                role="doctor",
                doctor_id=doctor.id,
                created_at=DEMO_ACCOUNTS_CREATED,
            )
        )
        added += 1
    db.flush()
    return added


def system_actor(db: Session) -> Actor:
    user = db.scalars(select(AppUser).where(AppUser.username == "sim-desk")).one()
    return Actor.from_user(user)


def book_as_simulator(db: Session, patient_id: int, slot_id: int, now: datetime) -> dict:
    return book_appointment(db, system_actor(db), patient_id, slot_id, confirmed=True, now=now, source="simulator")


def simulated_patient_ids(db: Session) -> list[int]:
    """Synthetic patients the simulator may book for; demo accounts are left to the visitor."""
    demo_ids = set(db.scalars(select(AppUser.patient_id).where(AppUser.patient_id.is_not(None))))
    demo_ids |= set(db.scalars(select(CaregiverLink.patient_id)))
    live = select(Patient.id).where(Patient.erased_at.is_(None)).order_by(Patient.id)
    return [p for p in db.scalars(live) if p not in demo_ids]


def seed_upcoming_bookings(db: Session, rng: np.random.Generator, today: date, days_ahead: int) -> int:
    """Book a share of upcoming slots through the real booking rules."""
    booking_time = at(today, time.min)
    patient_ids = simulated_patient_ids(db)
    full_doctor = db.scalars(select(Doctor.id).where(Doctor.name == hospital.FULLY_BOOKED_DOCTOR)).one()
    full_days = _next_opd_days(db, full_doctor, today + timedelta(days=1), 2)

    booked = 0
    slots = db.scalars(
        select(Slot)
        .where(Slot.start_at >= at(today, time.min), Slot.start_at < at(today + timedelta(days=days_ahead), time.min))
        .order_by(Slot.doctor_id, Slot.start_at)
    ).all()
    occupancy: dict[tuple[int, date], float] = {}
    used: set[tuple[int, int, date]] = set()
    for slot in slots:
        day = slot.start_at.astimezone(booking_time.tzinfo).date()
        key = (slot.doctor_id, day)
        if key not in occupancy:
            occupancy[key] = (
                1.0 if (slot.doctor_id == full_doctor and day in full_days) else float(rng.uniform(*UPCOMING_OCCUPANCY))
            )
        if rng.random() >= occupancy[key]:
            continue
        for _ in range(10):
            patient_id = int(rng.choice(patient_ids))
            if (patient_id, slot.doctor_id, day) not in used:
                break
        else:
            continue
        used.add((patient_id, slot.doctor_id, day))
        book_as_simulator(db, patient_id, slot.id, booking_time)
        booked += 1
    return booked


def _next_opd_days(db: Session, doctor_id: int, start: date, count: int) -> list[date]:
    doctor = db.get(Doctor, doctor_id)
    days, day = [], start
    while len(days) < count:
        if day.isoweekday() in doctor.opd_days:
            days.append(day)
        day += timedelta(days=1)
    return days


def seed_demo_history(db: Session, today: date) -> None:
    """A few past visits for the demo patients so 'my appointments' has history (FR-16)."""
    sim = system_actor(db)
    asha = db.scalars(select(AppUser.patient_id).where(AppUser.username == "asha")).one()
    vinayak = db.scalars(select(CaregiverLink.patient_id).where(CaregiverLink.verified.is_(True))).first()
    plans = [(asha, "Dr. Suresh Pawar", 40), (asha, "Dr. Snehal Gokhale", 18), (vinayak, "Dr. Anand Kulkarni", 25)]
    for patient_id, doctor_name, days_ago in plans:
        doctor = db.scalars(select(Doctor).where(Doctor.name == doctor_name)).one()
        day = _next_opd_days(db, doctor.id, today - timedelta(days=days_ago), 1)[0]
        ensure_slots(db, day, day)
        slot = db.scalars(
            select(Slot)
            .where(Slot.doctor_id == doctor.id, Slot.start_at >= at(day, time.min))
            .order_by(Slot.start_at)
            .offset(2)
        ).first()
        db.add(
            Appointment(
                patient_id=patient_id,
                slot_id=slot.id,
                doctor_id=doctor.id,
                appt_date=day,
                status="completed",
                source="simulator",
                created_by=sim.user_id,
                created_at=at(day, time.min) - timedelta(days=3),
            )
        )
        slot.status = "booked"
    db.flush()


def seed_all(db: Session, today: date, seed: int = 42, days_ahead: int = SEED_DAYS_AHEAD) -> dict:
    rng = np.random.default_rng(seed)
    seed_reference(db, rng)
    slots = ensure_slots(db, today, today + timedelta(days=days_ahead - 1))
    seed_demo_history(db, today)
    booked = seed_upcoming_bookings(db, rng, today, days_ahead)
    return {
        "departments": len(hospital.DEPARTMENTS),
        "doctors": len(hospital.DOCTORS),
        "slots": slots,
        "bookings": booked,
    }


def truncate_operational(db: Session) -> None:
    db.execute(text(f"TRUNCATE {', '.join(OPERATIONAL_TABLES)} RESTART IDENTITY CASCADE"))


def _own_accounts(db: Session) -> list[dict]:
    """Accounts people created themselves, with their patient records, consent history and answers to
    the registration questions (a withdrawn consent must survive a demo reset), and caregivers' own accounts."""
    caregivers = [
        {
            "username": user.username,
            "display_name": user.display_name,
            "password_hash": user.password_hash,
            "created_at": user.created_at,
            "caregiver": True,
        }
        for user in db.scalars(
            select(AppUser).where(AppUser.self_registered, AppUser.role == "caregiver", AppUser.active)
        )
    ]
    rows = db.execute(
        select(AppUser, Patient)
        .join(Patient, Patient.id == AppUser.patient_id)
        .where(AppUser.self_registered, Patient.erased_at.is_(None))
    ).all()
    return [
        {
            "username": user.username,
            "display_name": user.display_name,
            "password_hash": user.password_hash,
            "created_at": user.created_at,
            "name": patient.name,
            "birth_year": patient.birth_year,
            "phone_masked": patient.phone_masked,
            "phone_encrypted": patient.phone_encrypted,
            "phone_hash": patient.phone_hash,
            "email_masked": patient.email_masked,
            "email_encrypted": patient.email_encrypted,
            "contact_by": patient.contact_by,
            "language": patient.preferred_language,
            "pregnant": patient.pregnant,
            "disability": patient.disability,
            "consents": [
                (c.purpose, c.granted, c.at)
                for c in db.scalars(
                    select(Consent)
                    .where(Consent.patient_id == patient.id, Consent.purpose != "caregiver_access")
                    .order_by(Consent.at, Consent.id)
                )
            ],
            "answers": [
                (v.field_id, v.value)
                for v in db.scalars(select(PatientFieldValue).where(PatientFieldValue.patient_id == patient.id))
            ],
        }
        for user, patient in rows
    ] + caregivers


def _restore_accounts(db: Session, accounts: list[dict]) -> None:
    for a in accounts:
        if a.get("caregiver"):
            db.add(
                AppUser(
                    username=a["username"],
                    display_name=a["display_name"],
                    role="caregiver",
                    password_hash=a["password_hash"],
                    self_registered=True,
                    created_at=a["created_at"],
                )
            )
            continue
        patient = Patient(
            name=a["name"],
            birth_year=a["birth_year"],
            phone_masked=a["phone_masked"],
            phone_encrypted=a["phone_encrypted"],
            phone_hash=a["phone_hash"],
            email_masked=a["email_masked"],
            email_encrypted=a["email_encrypted"],
            contact_by=a["contact_by"],
            preferred_language=a["language"],
            pregnant=a["pregnant"],
            disability=a["disability"],
        )
        db.add(patient)
        db.flush()
        user = AppUser(
            username=a["username"],
            display_name=a["display_name"],
            role="patient",
            patient_id=patient.id,
            password_hash=a["password_hash"],
            self_registered=True,
            created_at=a["created_at"],
        )
        db.add(user)
        db.flush()
        for purpose, granted, at_time in a["consents"]:
            db.add(Consent(patient_id=patient.id, purpose=purpose, granted=granted, at=at_time, by_user_id=user.id))
        for field_id, value in a["answers"]:
            db.add(PatientFieldValue(patient_id=patient.id, field_id=field_id, value=value))
    db.flush()


def reset_demo(db: Session, today: date, seed: int = 42, days_ahead: int = SEED_DAYS_AHEAD) -> dict:
    """FR-34: wipe operational tables and reload the seed data.

    Accounts people created themselves are kept (with new ids, so they sign in again); their
    appointments, queues and conversations are reset like everyone else's.
    """
    accounts = _own_accounts(db)
    truncate_operational(db)
    summary = seed_all(db, today, seed, days_ahead)
    _restore_accounts(db, accounts)
    return {**summary, "own_accounts_kept": len(accounts)}


def ensure_demo_profile(db: Session) -> bool:
    """The demo hospital's details on a database seeded before they were stored (phase 7B)."""
    if db.get(HospitalProfile, 1) is not None or not is_seeded(db):
        return False
    db.add(HospitalProfile(id=1, **hospital.PROFILE))
    db.flush()
    return True


def is_seeded(db: Session) -> bool:
    return db.scalar(select(Department.id).limit(1)) is not None
