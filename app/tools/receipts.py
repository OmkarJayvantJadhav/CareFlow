"""Digital appointment receipts (feature 20) with a signed reference code.

The code is ``CF-<id>-<check>``; the check is an HMAC of the id, so a code read from a QR code can be
verified at check-in without a database lookup of the code itself.
"""

import hashlib
import hmac
import re

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Appointment
from app.timeutil import iso, to_ist
from app.tools import policy
from app.tools.errors import ToolError
from app.tools.hospital import get_profile, hospital_name
from app.tools.permissions import Actor, require_patient_access

_CODE = re.compile(r"^CF-(\d{1,9})-([0-9A-F]{6})$")


def _check(appointment_id: int) -> str:
    digest = hmac.new(get_settings().auth_secret.encode(), f"appt:{appointment_id}".encode(), hashlib.sha256)
    return digest.hexdigest()[:6].upper()


def reference_code(appointment_id: int) -> str:
    return f"CF-{appointment_id:06d}-{_check(appointment_id)}"


def appointment_from_code(code: str) -> int | None:
    """The appointment id in a valid reference code, or None."""
    match = _CODE.match(code.strip().upper())
    if not match:
        return None
    appointment_id = int(match.group(1))
    return appointment_id if hmac.compare_digest(match.group(2), _check(appointment_id)) else None


def receipt(db: Session, actor: Actor, appointment_id: int) -> dict:
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise ToolError("NOT_FOUND", f"Appointment {appointment_id} does not exist.")
    require_patient_access(db, actor, appt.patient_id)
    start = to_ist(appt.slot.start_at)
    doctor = appt.doctor
    profile = get_profile(db)
    return {
        "reference": reference_code(appt.id),
        "appointment_id": appt.id,
        "status": appt.status,
        "patient_name": appt.patient.synthetic_name,
        "patient_phone": appt.patient.phone_masked,
        "patient_birth_year": appt.patient.birth_year,
        "doctor_name": doctor.name,
        "department": doctor.department.name,
        "floor": doctor.department.floor,
        "date": start.date().isoformat(),
        "time": start.strftime("%H:%M"),
        "booked_at": iso(appt.created_at) if appt.created_at else None,
        "updated_at": iso(appt.updated_at) if appt.updated_at else None,
        "fee": None,  # the demo hospital charges nothing online; payment is at the desk
        "hospital": hospital_name(db),
        "hospital_address": profile.address if profile else "",
        "hospital_phone": profile.phone if profile else "",
        "arrive_note": "Please arrive 15 minutes early and show this receipt at the reception desk.",
        "cancellation_policy": policy.CANCEL_POLICY,
    }
