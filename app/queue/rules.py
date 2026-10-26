"""Configurable queue-priority rules (feature 51): how much priority each patient category gets."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import PATIENT_CATEGORIES, PriorityRule, QueueSession
from app.queue import engine
from app.timeutil import iso, resolve_now
from app.tools.audit import write_tool
from app.tools.errors import ToolError
from app.tools.permissions import Actor, require_role


def list_rules(db: Session) -> list[dict]:
    rows = {r.category: r for r in db.scalars(select(PriorityRule).execution_options(populate_existing=True))}
    return [
        {
            "category": c,
            "weight": rows[c].weight if c in rows else 0,
            "updated_at": iso(rows[c].updated_at) if c in rows else None,
        }
        for c in PATIENT_CATEGORIES
    ]


@write_tool("set_priority_rules")
def set_priority_rules(db: Session, actor: Actor, weights: dict[str, int], now: datetime | None = None) -> dict:
    """Admins set the weights; every open queue today is reordered at once (feature 55)."""
    now = resolve_now(now)
    require_role(actor, "admin")
    unknown = set(weights) - set(PATIENT_CATEGORIES)
    if unknown:
        raise ToolError("VALIDATION_ERROR", f"Unknown patient category: {', '.join(sorted(unknown))}.")
    for category, weight in weights.items():
        if not isinstance(weight, int) or not 0 <= weight <= engine.MAX_PRIORITY:
            raise ToolError("VALIDATION_ERROR", f"Priority must be between 0 and {engine.MAX_PRIORITY}.")
        db.execute(
            insert(PriorityRule)
            .values(category=category, weight=weight, updated_at=now)
            .on_conflict_do_update(index_elements=["category"], set_={"weight": weight, "updated_at": now})
        )
    db.flush()
    reordered = []
    for session_id in db.scalars(
        select(QueueSession.id)
        .where(QueueSession.date == now.date(), QueueSession.status == "open")
        .order_by(QueueSession.id)
    ).all():
        engine.reorder_session(db, session_id, now)
        reordered.append(session_id)
    return {"rules": list_rules(db), "reordered_sessions": reordered}
