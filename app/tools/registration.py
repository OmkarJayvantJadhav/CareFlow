"""Registration rules (phase 6B): patient categories, duplicate detection, consent, custom registration
fields and caregiver access requests. As everywhere, the rules live here and the API only calls them."""

import re
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    CONSENT_PURPOSES,
    Appointment,
    AppUser,
    CaregiverLink,
    CaregiverRequest,
    Consent,
    Patient,
    PatientFieldValue,
    RegistrationField,
)
from app.safety.pii import normalize_mobile, phone_index
from app.safety.privacy import mask_phone_number
from app.timeutil import iso, resolve_now
from app.tools.audit import write_tool
from app.tools.errors import ToolError
from app.tools.notify import notify
from app.tools.permissions import Actor, require_role

SENIOR_AGE = 60
CHILD_AGE = 12
# Without a recorded choice: details may be reused at the hospital and reminders are sent; nobody else
# may act for the patient until the patient approves them.
CONSENT_DEFAULTS = {"reuse_registration": True, "reminders": True, "caregiver_access": False}
MAX_FIELDS = 12

# --------------------------------------------------------------------------- categories (feature 30)


def categories(patient: Patient, today_year: int) -> list[str]:
    age = today_year - patient.birth_year
    out = []
    if age >= SENIOR_AGE:
        out.append("senior")
    if age < CHILD_AGE:
        out.append("child")
    if patient.pregnant:
        out.append("pregnant")
    if patient.disability:
        out.append("disability")
    return out


@write_tool("set_patient_categories")
def set_patient_categories(
    db: Session, actor: Actor, patient_id: int, pregnant: bool, disability: bool, now: datetime | None = None
) -> dict:
    """Staff record the categories that are not worked out from the birth year."""
    require_role(actor, "staff", "admin")
    now = resolve_now(now)
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise ToolError("NOT_FOUND", f"Patient {patient_id} does not exist.")
    patient.pregnant = pregnant
    patient.disability = disability
    db.flush()
    return {"patient_id": patient.id, "categories": categories(patient, now.year)}


# --------------------------------------------------------------------------- consent (features 34, 35)


def consent_state(db: Session, patient_id: int) -> dict[str, bool]:
    """The consent in force per purpose: the latest recorded choice, or the default."""
    state = dict(CONSENT_DEFAULTS)
    rows = db.execute(
        select(Consent.purpose, Consent.granted)
        .where(Consent.patient_id == patient_id)
        .order_by(Consent.at, Consent.id)
    ).all()
    for purpose, granted in rows:
        state[purpose] = granted
    return state


def record_consent(db: Session, actor: Actor, patient_id: int, purpose: str, granted: bool, now: datetime) -> None:
    if purpose not in CONSENT_PURPOSES:
        raise ToolError("VALIDATION_ERROR", f"Unknown consent purpose {purpose!r}.")
    db.add(Consent(patient_id=patient_id, purpose=purpose, granted=granted, at=now, by_user_id=actor.user_id))
    db.flush()


@write_tool("set_consent")
def set_consent(db: Session, actor: Actor, purpose: str, granted: bool, now: datetime | None = None) -> dict:
    """A patient records their own choice. Caregiver access is given per caregiver, by approving a request."""
    require_role(actor, "patient")
    now = resolve_now(now)
    if purpose == "caregiver_access":
        raise ToolError("VALIDATION_ERROR", "Approve or decline caregiver requests one by one.")
    record_consent(db, actor, actor.patient_id, purpose, granted, now)
    return consent_state(db, actor.patient_id)


def consent_history(db: Session, patient_id: int) -> list[dict]:
    rows = db.scalars(
        select(Consent).where(Consent.patient_id == patient_id).order_by(Consent.at.desc(), Consent.id.desc()).limit(20)
    )
    return [{"purpose": c.purpose, "granted": c.granted, "at": iso(c.at)} for c in rows]


# --------------------------------------------------------------------------- duplicates (features 48, 34)


def normalize_name(name: str) -> str:
    return re.sub(r"[^\w]+", " ", name.casefold()).strip()


def find_duplicates(
    db: Session, actor: Actor, name: str, birth_year: int, phone: str | None, now: datetime | None = None
) -> dict:
    """Existing patients who are probably the same person: the same birth year and either the same name
    (ignoring case, spacing and punctuation) or the same phone number (by its keyed hash; records stored
    before numbers were encrypted only have the masked form, which is compared instead)."""
    require_role(actor, "staff", "admin")
    now = resolve_now(now)
    masked = index = None
    if phone:
        digits = normalize_mobile(phone)
        masked, index = mask_phone_number(digits), phone_index(digits)
    wanted = normalize_name(name)
    if not wanted:
        raise ToolError("VALIDATION_ERROR", "Give the patient's name.")
    candidates = db.scalars(
        select(Patient).where(Patient.birth_year == birth_year, Patient.erased_at.is_(None)).order_by(Patient.id)
    )
    matches = []
    for p in candidates:
        same_name = normalize_name(p.name) == wanted
        same_phone = index is not None and (p.phone_hash == index if p.phone_hash else p.phone_masked == masked)
        if not (same_name or same_phone):
            continue
        last = db.scalar(select(func.max(Appointment.appt_date)).where(Appointment.patient_id == p.id))
        matches.append(
            {
                "patient_id": p.id,
                "name": p.name,
                "birth_year": p.birth_year,
                "phone_masked": p.phone_masked,
                "reasons": [r for r, hit in (("same_name", same_name), ("same_phone", same_phone)) if hit],
                "has_account": db.scalar(select(AppUser.id).where(AppUser.patient_id == p.id)) is not None,
                "last_visit": last.isoformat() if last else None,
                "reuse_allowed": consent_state(db, p.id)["reuse_registration"],
                "categories": categories(p, now.year),
            }
        )
    matches.sort(key=lambda m: (-len(m["reasons"]), m["patient_id"]))
    return {"matches": matches[:5]}


def require_reuse_consent(db: Session, patient_id: int) -> None:
    if not consent_state(db, patient_id)["reuse_registration"]:
        raise ToolError(
            "FORBIDDEN",
            "This patient has withdrawn consent to reuse their registration details. "
            "Ask them to show their own account, or register them again with their agreement.",
        )


# --------------------------------------------------------------------------- custom fields (features 26, 28)


def field_dict(f: RegistrationField) -> dict:
    return {
        "field_id": f.id,
        "key": f.key,
        "labels": {"en": f.label_en, "hi": f.label_hi, "mr": f.label_mr},
        "kind": f.kind,
        "options": list(f.options or []),
        "required": f.required,
        "active": f.active,
        "position": f.position,
    }


def list_fields(db: Session, include_inactive: bool = False) -> list[dict]:
    query = select(RegistrationField).order_by(RegistrationField.position, RegistrationField.id)
    if not include_inactive:
        query = query.where(RegistrationField.active)
    return [field_dict(f) for f in db.scalars(query)]


def _clean_field(body: dict) -> dict:
    labels = body.get("labels") or {}
    out = {}
    for lang in ("en", "hi", "mr"):
        label = " ".join(str(labels.get(lang) or "").split())
        if not label or len(label) > 80:
            raise ToolError(
                "VALIDATION_ERROR", "Every field needs a label in English, Hindi and Marathi (80 characters at most)."
            )
        out[f"label_{lang}"] = label
    kind = body.get("kind")
    if kind not in ("text", "number", "choice", "yes_no"):
        raise ToolError("VALIDATION_ERROR", "The field type must be text, number, choice or yes_no.")
    options = [" ".join(str(o).split()) for o in body.get("options") or [] if str(o).strip()]
    if kind == "choice" and not 2 <= len(options) <= 10:
        raise ToolError("VALIDATION_ERROR", "A choice field needs 2 to 10 options.")
    if len(set(options)) != len(options) or any(len(o) > 60 for o in options):
        raise ToolError("VALIDATION_ERROR", "Options must be different and at most 60 characters.")
    out.update(kind=kind, options=options if kind == "choice" else [], required=bool(body.get("required")))
    return out


@write_tool("create_registration_field")
def create_registration_field(db: Session, actor: Actor, body: dict, now: datetime | None = None) -> dict:
    require_role(actor, "admin")
    if db.scalar(select(func.count()).select_from(RegistrationField).where(RegistrationField.active)) >= MAX_FIELDS:
        raise ToolError("VALIDATION_ERROR", f"At most {MAX_FIELDS} extra fields can be active.")
    values = _clean_field(body)
    for existing in db.scalars(select(RegistrationField.label_en).where(RegistrationField.active)):
        if normalize_name(existing) == normalize_name(values["label_en"]):
            raise ToolError("DUPLICATE", "A question with this name is already on the form.")
    key = re.sub(r"[^a-z0-9]+", "_", values["label_en"].casefold()).strip("_")[:32] or "field"
    base, n = key, 2
    while db.scalar(select(RegistrationField.id).where(RegistrationField.key == key)) is not None:
        key, n = f"{base}_{n}", n + 1
    position = (db.scalar(select(func.max(RegistrationField.position))) or 0) + 1
    field = RegistrationField(key=key, position=position, **values)
    db.add(field)
    db.flush()
    return field_dict(field)


@write_tool("update_registration_field")
def update_registration_field(
    db: Session, actor: Actor, field_id: int, body: dict, now: datetime | None = None
) -> dict:
    """Change a field's labels, type, options or whether it is required or shown. Answers already given
    are kept; a field that is switched off is simply no longer asked."""
    require_role(actor, "admin")
    field = db.get(RegistrationField, field_id)
    if field is None:
        raise ToolError("NOT_FOUND", f"Field {field_id} does not exist.")
    for key, value in _clean_field(body).items():
        setattr(field, key, value)
    field.active = bool(body.get("active", field.active))
    db.flush()
    return field_dict(field)


def clean_answers(db: Session, answers: dict | None) -> dict[int, str]:
    """Check the answers against the active fields; returns {field_id: value}. Raises on any problem."""
    answers = answers or {}
    fields = {f.key: f for f in db.scalars(select(RegistrationField).where(RegistrationField.active))}
    unknown = set(answers) - set(fields)
    if unknown:
        raise ToolError("VALIDATION_ERROR", f"Unknown registration field: {sorted(unknown)[0]}.")
    out = {}
    for key, field in fields.items():
        raw = answers.get(key)
        value = "" if raw is None else " ".join(str(raw).split())
        if not value:
            if field.required:
                raise ToolError("VALIDATION_ERROR", f"Please answer: {field.label_en}.")
            continue
        if len(value) > 200:
            raise ToolError("VALIDATION_ERROR", f"The answer to {field.label_en} is too long.")
        if field.kind == "number" and not re.fullmatch(r"-?\d+(\.\d+)?", value):
            raise ToolError("VALIDATION_ERROR", f"{field.label_en} must be a number.")
        if field.kind == "choice" and value not in field.options:
            raise ToolError("VALIDATION_ERROR", f"Choose one of the options for {field.label_en}.")
        if field.kind == "yes_no":
            if value not in ("yes", "no"):
                raise ToolError("VALIDATION_ERROR", f"{field.label_en} must be yes or no.")
        out[field.id] = value
    return out


def save_answers(db: Session, patient_id: int, answers: dict[int, str]) -> None:
    for field_id, value in answers.items():
        row = db.get(PatientFieldValue, (patient_id, field_id))
        if row is None:
            db.add(PatientFieldValue(patient_id=patient_id, field_id=field_id, value=value))
        else:
            row.value = value
    db.flush()


def patient_answers(db: Session, patient_id: int) -> dict[str, str]:
    rows = db.execute(
        select(RegistrationField.key, PatientFieldValue.value)
        .join(PatientFieldValue, PatientFieldValue.field_id == RegistrationField.id)
        .where(PatientFieldValue.patient_id == patient_id)
    ).all()
    return dict(rows)


# --------------------------------------------------------------------------- caregiver access (feature 35)


def _request_dict(db: Session, r: CaregiverRequest) -> dict:
    caregiver = db.get(AppUser, r.caregiver_user_id)
    patient = db.get(Patient, r.patient_id)
    return {
        "request_id": r.id,
        "caregiver_name": caregiver.display_name,
        "patient_name": patient.name,
        "status": r.status,
        "requested_at": iso(r.requested_at),
        "decided_at": iso(r.decided_at) if r.decided_at else None,
    }


@write_tool("request_caregiver_access")
def request_caregiver_access(db: Session, actor: Actor, patient_username: str, now: datetime | None = None) -> dict:
    """A caregiver asks to act for a patient who has an account; nothing is shared until they approve."""
    require_role(actor, "caregiver")
    now = resolve_now(now)
    user = db.scalars(
        select(AppUser).where(AppUser.username == patient_username.strip().lower(), AppUser.active)
    ).first()
    # The same answer whether or not the account exists, so usernames cannot be probed.
    if user is None or user.role != "patient":
        raise ToolError("NOT_FOUND", "No patient account with that username accepts requests.")
    link = db.get(CaregiverLink, (actor.user_id, user.patient_id))
    if link is not None and link.verified:
        raise ToolError("DUPLICATE", "You can already act for this patient.")
    pending = db.scalars(
        select(CaregiverRequest).where(
            CaregiverRequest.caregiver_user_id == actor.user_id,
            CaregiverRequest.patient_id == user.patient_id,
            CaregiverRequest.status == "pending",
        )
    ).first()
    if pending is not None:
        raise ToolError("DUPLICATE", "Your request is already waiting for the patient's answer.")
    request = CaregiverRequest(caregiver_user_id=actor.user_id, patient_id=user.patient_id, requested_at=now)
    db.add(request)
    db.flush()
    caregiver = db.get(AppUser, actor.user_id)
    result = {**_request_dict(db, request), "patient_name": None}
    notify(
        db,
        user.patient_id,
        f"{caregiver.display_name} asks to manage your CareFlow appointments. Approve or decline in your profile.",
        now,
    )
    return result


@write_tool("decide_caregiver_request")
def decide_caregiver_request(
    db: Session, actor: Actor, request_id: int, approve: bool, now: datetime | None = None
) -> dict:
    require_role(actor, "patient")
    now = resolve_now(now)
    request = db.get(CaregiverRequest, request_id)
    if request is None or request.patient_id != actor.patient_id:
        raise ToolError("NOT_FOUND", "There is no such request for you.")
    if request.status != "pending":
        raise ToolError("INVALID_STATE", "This request has already been answered.")
    request.status = "approved" if approve else "declined"
    request.decided_at = now
    link = db.get(CaregiverLink, (request.caregiver_user_id, request.patient_id))
    if approve:
        if link is None:
            db.add(
                CaregiverLink(caregiver_user_id=request.caregiver_user_id, patient_id=request.patient_id, verified=True)
            )
        else:
            link.verified = True
    record_consent(db, actor, actor.patient_id, "caregiver_access", approve, now)
    db.flush()
    return _request_dict(db, request)


@write_tool("revoke_caregiver")
def revoke_caregiver(db: Session, actor: Actor, caregiver_user_id: int, now: datetime | None = None) -> dict:
    require_role(actor, "patient")
    now = resolve_now(now)
    link = db.get(CaregiverLink, (caregiver_user_id, actor.patient_id))
    if link is None or not link.verified:
        raise ToolError("NOT_FOUND", "That person cannot act for you.")
    link.verified = False
    record_consent(db, actor, actor.patient_id, "caregiver_access", False, now)
    db.flush()
    return {"caregiver_user_id": caregiver_user_id, "verified": False}


def patient_requests(db: Session, patient_id: int) -> dict:
    requests = db.scalars(
        select(CaregiverRequest)
        .where(CaregiverRequest.patient_id == patient_id)
        .order_by(CaregiverRequest.requested_at.desc())
        .limit(20)
    )
    caregivers = db.execute(
        select(AppUser.id, AppUser.display_name)
        .join(CaregiverLink, CaregiverLink.caregiver_user_id == AppUser.id)
        .where(CaregiverLink.patient_id == patient_id, CaregiverLink.verified)
    ).all()
    return {
        "requests": [_request_dict(db, r) for r in requests],
        "caregivers": [{"caregiver_user_id": uid, "name": name} for uid, name in caregivers],
    }


def caregiver_requests(db: Session, actor: Actor) -> list[dict]:
    require_role(actor, "caregiver")
    rows = db.scalars(
        select(CaregiverRequest)
        .where(CaregiverRequest.caregiver_user_id == actor.user_id)
        .order_by(CaregiverRequest.requested_at.desc())
        .limit(20)
    )
    # The patient's name is shown only once they approve: a username alone must not reveal who it is.
    return [
        {**_request_dict(db, r), "patient_name": None} if r.status != "approved" else _request_dict(db, r) for r in rows
    ]
