"""TC-09 and the merge-rule details (FR-22). Pure unit tests, no database."""

from datetime import datetime, timedelta

import pytest

from app.config import HOSPITAL_TZ
from app.queue.merge import QueueItem, effective_priority, merge_order

T0 = datetime(2026, 10, 19, 9, 0, tzinfo=HOSPITAL_TZ)


def m(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def booked(entry_id: int, slot_min: float, arrived_min: float, **kw) -> QueueItem:
    return QueueItem(entry_id=entry_id, kind="booked", scheduled_at=m(slot_min), checked_in_at=m(arrived_min), **kw)


def walk_in(entry_id: int, arrived_min: float, **kw) -> QueueItem:
    return QueueItem(entry_id=entry_id, kind="walk_in", checked_in_at=m(arrived_min), **kw)


# Three booked patients at 09:00, 09:30, 10:00 and two walk-ins who arrived at 08:50 and 08:55.
THREE_BOOKED_TWO_WALK_INS = [
    booked(1, 0, -10),
    booked(2, 30, 20),
    booked(3, 60, 50),
    walk_in(4, -10),
    walk_in(5, -5),
]


def test_tc09_slot_order_walk_ins_fill_gaps():
    # 15-minute consultations from 09:00: B1 is due at 09:00; at 09:15 B2 is not due
    # yet, so a walk-in fills the gap; at 09:30 B2 is due; at 09:45 the second
    # walk-in fills the gap before B3 at 10:00.
    assert merge_order(THREE_BOOKED_TWO_WALK_INS, "slot_order", T0, 15) == [1, 4, 2, 5, 3]


def test_tc09_alternate_rule():
    assert merge_order(THREE_BOOKED_TWO_WALK_INS, "alternate", T0, 15) == [1, 4, 2, 5, 3]


def test_slot_order_differs_from_alternate_when_bookings_are_dense():
    items = [booked(1, 0, -5), booked(2, 10, -5), booked(3, 20, -5), walk_in(4, -20), walk_in(5, -15)]
    # Back-to-back 10-minute bookings leave no gap: booked keep slot order, walk-ins wait.
    assert merge_order(items, "slot_order", T0, 10) == [1, 2, 3, 4, 5]
    assert merge_order(items, "alternate", T0, 10) == [1, 4, 2, 5, 3]


def test_late_booked_patient_loses_slot_order():
    # B1's slot was 09:00 but they arrived at 09:20 (beyond the 15-minute grace):
    # they queue by arrival time like a walk-in, behind W3 who arrived at 09:05.
    items = [booked(1, 0, 20), booked(2, 30, 25), walk_in(3, 5)]
    assert merge_order(items, "slot_order", m(30), 15) == [2, 3, 1]


def test_booked_patient_within_grace_keeps_slot_order():
    items = [booked(1, 0, 14), walk_in(2, -30)]
    assert merge_order(items, "slot_order", m(14), 10) == [1, 2]


def test_returning_patient_queues_by_return_time():
    items = [booked(1, 0, -10, requeued_at=m(40)), walk_in(2, 30), walk_in(3, 45)]
    assert merge_order(items, "slot_order", m(40), 10) == [2, 1, 3]


def test_priority_lane_goes_first():
    items = [booked(1, 0, -10), walk_in(2, -5, priority=1), walk_in(3, 0, priority=2)]
    assert merge_order(items, "slot_order", T0, 10) == [3, 2, 1]


def test_no_walk_ins_booked_go_in_slot_order_even_if_early():
    items = [booked(2, 60, -5), booked(1, 30, -5)]
    assert merge_order(items, "slot_order", T0, 10) == [1, 2]


def test_unknown_rule_is_rejected():
    with pytest.raises(ValueError):
        merge_order([], "random", T0, 10)


# --------------------------------------------------------------------------- features 51 - 53


def test_moved_booked_patient_joins_the_walk_in_lane_by_their_check_in_time():
    """A patient moved from another doctor has no slot here; they keep the time they first checked in."""
    items = [booked(1, 0, -10), booked(2, 15, 10), booked(9, 0, -20, transferred=True), walk_in(4, -5)]
    assert merge_order(items, "alternate", T0, 15) == [1, 9, 2, 4]


@pytest.mark.parametrize(
    ("manual", "categories", "due", "expected"),
    [
        (0, [], True, 0),
        (0, ["senior"], True, 1),
        (0, ["senior", "pregnant"], True, 2),
        (3, ["pregnant"], True, 3),  # the doctor's choice wins when it is higher
        (0, ["pregnant"], False, 0),  # a booked patient's category counts only once their slot is due
        (1, ["pregnant"], False, 1),
        (0, ["child"], True, 0),  # weight 0: the category has no priority
    ],
)
def test_effective_priority(manual, categories, due, expected):
    weights = {"senior": 1, "pregnant": 2, "child": 0}
    assert effective_priority(manual, categories, weights, due) == expected
