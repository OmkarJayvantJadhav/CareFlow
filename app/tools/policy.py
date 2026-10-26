"""Hospital booking policy. These values are business rules enforced in code;
the knowledge-base policy documents must state the same numbers."""

from datetime import timedelta

RESCHEDULE_CUTOFF = timedelta(hours=12)
CANCEL_CUTOFF = timedelta(hours=4)
BOOKING_HORIZON = timedelta(days=30)
# A slot must start at least this far in the future to be offered or booked.
BOOKING_LEAD = timedelta(minutes=15)
WAITLIST_OFFER_HOLD = timedelta(hours=2)
WAITLIST_MIN_LEAD = timedelta(hours=1)
# Booked patients arriving later than this after their slot start lose slot order.
LATE_GRACE = timedelta(minutes=15)
# Patients may check themselves in from an hour before their slot until the late grace runs out;
# outside that window the reception desk checks them in.
SELF_CHECK_IN_OPENS = timedelta(hours=1)
SELF_CHECK_IN_CLOSES = LATE_GRACE
# Virtual queue (feature 38): patients without a booking may join a doctor's queue from their phone from an
# hour before OPD opens until 30 minutes before it closes, while fewer than VIRTUAL_QUEUE_CAP remote patients
# who have not yet arrived are waiting for that doctor.
VIRTUAL_JOIN_OPENS = timedelta(hours=1)
VIRTUAL_JOIN_CLOSES = timedelta(minutes=30)
VIRTUAL_QUEUE_CAP = 10

RESCHEDULE_POLICY = (
    "Appointments can be rescheduled up to 12 hours before the appointment time. "
    "Within 12 hours, please contact the reception desk."
)
CANCEL_POLICY = (
    "Appointments can be cancelled free of charge up to 4 hours before the appointment time. "
    "Within 4 hours, the appointment can no longer be cancelled online; please contact the reception desk."
)
