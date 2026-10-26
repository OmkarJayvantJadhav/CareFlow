"""Queue workload balancing (feature 54). Pure functions: no database, easy to unit test.

Within one department, a walk-in patient waiting at the back of a long queue may be seen sooner by a
colleague whose queue is shorter. The suggestions are greedy and explainable: repeatedly take the last
movable patient of the doctor who will finish last and move them to the doctor who will finish first,
as long as that patient's own wait drops by at least ``min_gain`` minutes. Booked patients are never
suggested: they keep the doctor they chose. Staff confirm every move.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Waiting:
    entry_id: int
    token: str
    movable: bool  # walk-ins (including online and moved patients); booked patients keep their doctor


@dataclass
class DoctorLoad:
    doctor_id: int
    doctor_name: str
    consult_minutes: float
    free_in: float  # minutes until the doctor can start on the first waiting patient
    accepting: bool  # an open queue that can take patients
    waiting: list[Waiting] = field(default_factory=list)  # in call order

    def finish_in(self) -> float:
        return self.free_in + len(self.waiting) * self.consult_minutes


@dataclass(frozen=True)
class Move:
    entry_id: int
    token: str
    from_doctor_id: int
    from_doctor: str
    to_doctor_id: int
    to_doctor: str
    wait_now_min: int
    wait_after_min: int

    def to_dict(self) -> dict:
        return {**self.__dict__, "saves_min": self.wait_now_min - self.wait_after_min}


def suggest_moves(loads: list[DoctorLoad], min_gain: float = 10, max_moves: int = 5) -> list[Move]:
    work = [
        DoctorLoad(d.doctor_id, d.doctor_name, d.consult_minutes, d.free_in, d.accepting, list(d.waiting))
        for d in loads
        if d.accepting
    ]
    moves: list[Move] = []
    moved: set[int] = set()  # each patient is suggested at most once

    def can_move(w: Waiting) -> bool:
        return w.movable and w.entry_id not in moved

    while len(moves) < max_moves and len(work) >= 2:
        sources = [d for d in work if any(can_move(w) for w in d.waiting)]
        if not sources:
            break
        busiest = max(sources, key=lambda d: (d.finish_in(), -d.doctor_id))
        lightest = min((d for d in work if d is not busiest), key=lambda d: (d.finish_in(), d.doctor_id))
        index = max(i for i, w in enumerate(busiest.waiting) if can_move(w))
        wait_now = busiest.free_in + index * busiest.consult_minutes
        wait_after = lightest.finish_in()
        if wait_now - wait_after < min_gain:
            break
        patient = busiest.waiting.pop(index)
        lightest.waiting.append(patient)
        moved.add(patient.entry_id)
        moves.append(
            Move(
                entry_id=patient.entry_id,
                token=patient.token,
                from_doctor_id=busiest.doctor_id,
                from_doctor=busiest.doctor_name,
                to_doctor_id=lightest.doctor_id,
                to_doctor=lightest.doctor_name,
                wait_now_min=round(wait_now),
                wait_after_min=round(wait_after),
            )
        )
    return moves
