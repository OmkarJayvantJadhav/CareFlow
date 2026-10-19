"""Live queue updates over WebSocket (FR-26, docs §7).

Route handlers run in a thread pool, so publishing hands each message to the
subscriber's event loop with ``call_soon_threadsafe``. The broadcaster lives in
one process, which matches the single-process demo deployment.
"""

import asyncio
import threading
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import QueueEntry, QueueSession
from app.queue.predictions import latest_estimate
from app.timeutil import iso

QUEUE_SIZE = 100


class Broadcaster:
    def __init__(self):
        self._subscribers: dict[int, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = defaultdict(set)
        self._lock = threading.Lock()

    def subscribe(self, session_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        with self._lock:
            self._subscribers[session_id].add((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, session_id: int, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers[session_id] = {s for s in self._subscribers[session_id] if s[1] is not queue}

    def subscriber_count(self, session_id: int) -> int:
        with self._lock:
            return len(self._subscribers[session_id])

    def publish(self, session_id: int, messages: list[dict]) -> None:
        with self._lock:
            targets = list(self._subscribers[session_id])
        for loop, queue in targets:
            for message in messages:
                try:
                    loop.call_soon_threadsafe(_offer, queue, message)
                except RuntimeError:  # the subscriber's loop has closed
                    self.unsubscribe(session_id, queue)


def _offer(queue: asyncio.Queue, message: dict) -> None:
    if queue.full():  # a slow client gets the newest state rather than a backlog
        queue.get_nowait()
    queue.put_nowait(message)


broadcaster = Broadcaster()


def session_messages(db: Session, session_id: int, now: datetime) -> list[dict]:
    """The three update events for a session. Entries carry tokens only, never names."""
    session = db.get(QueueSession, session_id)
    entries = sorted(
        db.scalars(select(QueueEntry).where(QueueEntry.session_id == session_id)),
        key=lambda e: (e.position is None, e.position or 0, e.id),
    )
    queue = [
        {"entry_id": e.id, "token": e.token, "kind": e.kind, "position": e.position, "status": e.status}
        for e in entries
        if e.status in ("waiting", "called", "in_consultation", "missed")
    ]
    predictions = []
    for e in entries:
        if e.status == "waiting":
            estimate = latest_estimate(db, e.id, now)
            if estimate:
                predictions.append({"entry_id": e.id, **estimate})
    return [
        {"event": "queue.updated", "session_id": session_id, "at": iso(now), "entries": queue},
        {"event": "prediction.updated", "session_id": session_id, "at": iso(now), "predictions": predictions},
        {
            "event": "doctor.status",
            "session_id": session_id,
            "at": iso(now),
            "status": session.doctor_status,
            "delay_minutes": session.delay_minutes,
            "busy_until": iso(session.busy_until),
        },
    ]
