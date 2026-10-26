"""Queue merge rules (FR-22). Pure functions: no database, easy to unit test.

Entries fall into three lanes:

* priority lane - the patient's doctor raised the priority (feature 52), or the
  patient belongs to a category the admin gives priority to (feature 51);
  highest priority first, then by arrival.
* booked lane - booked patients who arrived on time keep their slot order.
* walk-in lane - walk-ins, plus booked patients who arrived more than the late
  grace period after their slot, who missed their turn and came back, or who
  were moved here from another doctor; these are ordered by (re)arrival time
  (a moved patient keeps the time they first checked in).

Rules for merging the booked and walk-in lanes:

* ``slot_order`` (default) - booked patients keep slot order; walk-ins fill
  gaps. The doctor's day is projected forward one average consultation at a
  time; a booked patient is taken once their slot time has arrived, and a
  walk-in is taken whenever the next booked patient is not yet due.
* ``alternate`` - one booked patient, then one walk-in, and so on.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.db.models import MERGE_RULES
from app.tools import policy


@dataclass(frozen=True)
class QueueItem:
    entry_id: int
    kind: str  # "booked" | "walk_in"
    checked_in_at: datetime
    scheduled_at: datetime | None = None
    requeued_at: datetime | None = None
    priority: int = 0
    transferred: bool = False

    @property
    def arrival(self) -> datetime:
        return self.requeued_at or self.checked_in_at

    @property
    def keeps_slot_order(self) -> bool:
        return (
            self.kind == "booked"
            and not self.transferred
            and self.scheduled_at is not None
            and self.requeued_at is None
            and self.checked_in_at <= self.scheduled_at + policy.LATE_GRACE
        )


def effective_priority(manual: int, categories: Iterable[str], weights: Mapping[str, int], due: bool) -> int:
    """The doctor's manual priority, or the highest weight among the patient's categories if that is higher.

    A booked patient's category counts only once their slot time has come (``due``), so arriving early
    with a later booking does not jump the queue.
    """
    automatic = max((weights.get(c, 0) for c in categories), default=0) if due else 0
    return max(manual, automatic)


def merge_order(items: list[QueueItem], rule: str, start: datetime, consult_minutes: float) -> list[int]:
    """Return entry ids in the order they will be called."""
    if rule not in MERGE_RULES:
        raise ValueError(f"unknown merge rule {rule!r}")
    priority = sorted((i for i in items if i.priority > 0), key=lambda i: (-i.priority, i.arrival, i.entry_id))
    rest = [i for i in items if i.priority <= 0]
    booked = sorted((i for i in rest if i.keeps_slot_order), key=lambda i: (i.scheduled_at, i.entry_id))
    walk_ins = sorted((i for i in rest if not i.keeps_slot_order), key=lambda i: (i.arrival, i.entry_id))

    ordered: list[QueueItem] = list(priority)
    if rule == "alternate":
        while booked or walk_ins:
            if booked:
                ordered.append(booked.pop(0))
            if walk_ins:
                ordered.append(walk_ins.pop(0))
    else:
        step = timedelta(minutes=consult_minutes)
        clock = start + step * len(priority)
        while booked or walk_ins:
            next_booked_due = booked and booked[0].scheduled_at <= clock
            if booked and (next_booked_due or not walk_ins):
                ordered.append(booked.pop(0))
            else:
                ordered.append(walk_ins.pop(0))
            clock += step
    return [i.entry_id for i in ordered]
