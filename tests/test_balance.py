"""Queue workload balancing suggestions (feature 54). Pure unit tests, no database."""

from app.queue.balance import DoctorLoad, Waiting, suggest_moves


def load(doctor_id: int, waiting: list[tuple[int, bool]], consult: float = 10, free_in: float = 0, accepting=True):
    return DoctorLoad(
        doctor_id, f"Dr {doctor_id}", consult, free_in, accepting, [Waiting(e, f"W{e:02d}", m) for e, m in waiting]
    )


def test_moves_the_last_walk_in_from_the_longest_queue_to_the_shortest():
    busy = load(1, [(1, True), (2, True), (3, True), (4, True), (5, True), (6, True)])
    idle = load(2, [])
    moves = suggest_moves([busy, idle])
    # Six patients at 10 minutes vs none: moving the 6th (wait 50 -> 0), 5th (40 -> 10) and 4th (30 -> 20).
    assert [(m.entry_id, m.wait_now_min, m.wait_after_min) for m in moves] == [(6, 50, 0), (5, 40, 10), (4, 30, 20)]
    assert all(m.to_dict()["saves_min"] >= 10 for m in moves)


def test_booked_patients_keep_the_doctor_they_chose():
    busy = load(1, [(1, False), (2, False), (3, False), (4, True)])
    moves = suggest_moves([busy, load(2, [])])
    assert [m.entry_id for m in moves] == [4]


def test_no_suggestion_when_the_gain_is_small_or_nobody_can_take_patients():
    assert suggest_moves([load(1, [(1, True), (2, True)]), load(2, [(3, True)])]) == []
    closed = load(2, [], accepting=False)
    assert suggest_moves([load(1, [(e, True) for e in range(1, 8)]), closed]) == []


def test_a_doctor_on_a_break_counts_as_busy_until_it_ends():
    """The colleague is free in 45 minutes, so moving a patient who would wait 30 minutes does not help."""
    busy = load(1, [(1, True), (2, True), (3, True), (4, True)])
    on_break = load(2, [], free_in=45)
    assert suggest_moves([busy, on_break]) == []


def test_each_patient_is_suggested_once_and_moves_are_capped():
    busy = load(1, [(e, True) for e in range(1, 21)], consult=15)
    moves = suggest_moves([busy, load(2, []), load(3, [])], max_moves=5)
    assert len(moves) == 5 and len({m.entry_id for m in moves}) == 5
    assert {m.to_doctor_id for m in moves} == {2, 3}
