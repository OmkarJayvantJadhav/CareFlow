"""Hospital booking and queue policy: business rules enforced in code.

The numbers are the hospital's to set (phase 7D): an admin changes them on the setup page, they are stored
in ``policy_setting`` and applied here, in this process, at start-up and on every change. The rest of the
code reads them as ``policy.CANCEL_CUTOFF`` and so on at the moment it needs them. The knowledge-base
documents state the same numbers through placeholders such as ``{{cancel_hours}}`` (``placeholders()``), so
the documents and the code cannot disagree.
"""

from datetime import timedelta

# key: (default, lowest, highest, unit). The unit is part of the key's name, so a document says
# "{{cancel_hours}} hours". The lowest values avoid "1 hours" in the documents.
SETTINGS: dict[str, tuple[int, int, int, str]] = {
    "booking_lead_minutes": (15, 5, 240, "minutes"),
    "booking_horizon_days": (30, 7, 180, "days"),
    "reschedule_hours": (12, 2, 168, "hours"),
    "cancel_hours": (4, 2, 168, "hours"),
    "waitlist_hold_hours": (2, 2, 48, "hours"),
    "late_grace_minutes": (15, 5, 120, "minutes"),
    "check_in_opens_minutes": (60, 10, 240, "minutes"),
    "virtual_join_opens_minutes": (60, 10, 240, "minutes"),
    "virtual_join_closes_minutes": (30, 5, 240, "minutes"),
    "virtual_queue_cap": (10, 1, 100, "patients"),
}
DEFAULTS = {key: spec[0] for key, spec in SETTINGS.items()}

# Fixed rule (not set by the hospital): a freed slot is offered from the waiting list only if it starts at
# least this far ahead.
WAITLIST_MIN_LEAD = timedelta(hours=1)

_current: dict[str, int] = {}


def apply(values: dict[str, int] | None = None) -> dict[str, int]:
    """Make these numbers (defaults for any missing) the rules in force in this process."""
    global BOOKING_LEAD, BOOKING_HORIZON, RESCHEDULE_CUTOFF, CANCEL_CUTOFF, WAITLIST_OFFER_HOLD, LATE_GRACE
    global SELF_CHECK_IN_OPENS, SELF_CHECK_IN_CLOSES, VIRTUAL_JOIN_OPENS, VIRTUAL_JOIN_CLOSES, VIRTUAL_QUEUE_CAP
    global RESCHEDULE_POLICY, CANCEL_POLICY
    v = {**DEFAULTS, **{k: int(x) for k, x in (values or {}).items() if k in SETTINGS}}
    _current.clear()
    _current.update(v)
    # A slot must start at least this far in the future to be offered or booked.
    BOOKING_LEAD = timedelta(minutes=v["booking_lead_minutes"])
    BOOKING_HORIZON = timedelta(days=v["booking_horizon_days"])
    RESCHEDULE_CUTOFF = timedelta(hours=v["reschedule_hours"])
    CANCEL_CUTOFF = timedelta(hours=v["cancel_hours"])
    WAITLIST_OFFER_HOLD = timedelta(hours=v["waitlist_hold_hours"])
    # Booked patients arriving later than this after their slot start lose slot order.
    LATE_GRACE = timedelta(minutes=v["late_grace_minutes"])
    # Patients may check themselves in from before their slot until the late grace runs out; outside that
    # window the reception desk checks them in.
    SELF_CHECK_IN_OPENS = timedelta(minutes=v["check_in_opens_minutes"])
    SELF_CHECK_IN_CLOSES = LATE_GRACE
    # Virtual queue (feature 38): patients without a booking may join a doctor's queue from their phone from
    # before OPD opens until shortly before it closes, while fewer than VIRTUAL_QUEUE_CAP remote patients who
    # have not yet arrived are waiting for that doctor.
    VIRTUAL_JOIN_OPENS = timedelta(minutes=v["virtual_join_opens_minutes"])
    VIRTUAL_JOIN_CLOSES = timedelta(minutes=v["virtual_join_closes_minutes"])
    VIRTUAL_QUEUE_CAP = v["virtual_queue_cap"]
    RESCHEDULE_POLICY = (
        f"Appointments can be rescheduled up to {v['reschedule_hours']} hours before the appointment time. "
        f"Within {v['reschedule_hours']} hours, please contact the reception desk."
    )
    CANCEL_POLICY = (
        f"Appointments can be cancelled free of charge up to {v['cancel_hours']} hours before the appointment "
        f"time. Within {v['cancel_hours']} hours, the appointment can no longer be cancelled online; please "
        "contact the reception desk."
    )
    return dict(v)


def current() -> dict[str, int]:
    return dict(_current)


def placeholders() -> dict[str, str]:
    """``{{key}}`` -> the number in force, for the knowledge-base documents."""
    return {f"{{{{{key}}}}}": str(value) for key, value in _current.items()}


def check(values: dict[str, int]) -> dict[str, int]:
    """Validate a change; returns the complete set. Raises ValueError with a readable reason."""
    out = {**_current}
    for key, value in values.items():
        if key not in SETTINGS:
            raise ValueError(f"Unknown setting {key!r}.")
        _, low, high, unit = SETTINGS[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{key}: a whole number of {unit} from {low} to {high}.")
        out[key] = value
    if out["late_grace_minutes"] >= out["booking_horizon_days"] * 24 * 60:
        raise ValueError("The late-arrival grace must be shorter than the booking window.")
    return out


apply()
