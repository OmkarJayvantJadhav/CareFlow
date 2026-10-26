"""The hospital's booking and queue rules (phase 7D): stored per key, applied to app.tools.policy."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppUser, PolicySetting
from app.timeutil import iso, resolve_now
from app.tools import policy
from app.tools.audit import write_tool
from app.tools.errors import ToolError
from app.tools.permissions import Actor, require_role


def load_policy(db: Session) -> dict[str, int]:
    """Apply the stored numbers (defaults for any not set) in this process."""
    return policy.apply(dict(db.execute(select(PolicySetting.key, PolicySetting.value)).all()))


def policy_view(db: Session) -> dict:
    rows = {r.key: r for r in db.scalars(select(PolicySetting))}
    last = max((r.updated_at for r in rows.values()), default=None)
    return {
        "values": policy.current(),
        "defaults": dict(policy.DEFAULTS),
        "limits": {k: {"min": low, "max": high, "unit": unit} for k, (_, low, high, unit) in policy.SETTINGS.items()},
        "updated_at": iso(last) if last else None,
    }


@write_tool("update_policy")
def update_policy(db: Session, actor: Actor, values: dict[str, int], now: datetime | None = None) -> dict:
    """Change the rules; every document that states one of them is shown and indexed with the new number."""
    from app.rag.kb import reindex

    now = resolve_now(now)
    require_role(actor, "admin")
    try:
        merged = policy.check(values)
    except ValueError as err:
        raise ToolError("VALIDATION_ERROR", str(err)) from None
    username = db.scalar(select(AppUser.username).where(AppUser.id == actor.user_id))
    for key, value in merged.items():
        row = db.get(PolicySetting, key)
        if row is None:
            db.add(PolicySetting(key=key, value=value, updated_at=now, updated_by=username))
        elif row.value != value:
            row.value, row.updated_at, row.updated_by = value, now, username
    db.flush()
    previous = policy.current()
    policy.apply(merged)
    try:
        index = reindex(db, refit=False)
    except Exception:
        policy.apply(previous)  # the transaction rolls back; keep this process on the stored rules
        raise
    return {**policy_view(db), "documents_updated": index["reindexed"]}
