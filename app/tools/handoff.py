"""Human handoff (FR-06): a ticket the reception team picks up."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import HandoffTicket
from app.timeutil import resolve_now
from app.tools.audit import write_tool
from app.tools.errors import ToolError
from app.tools.permissions import Actor

REASONS = ("user_request", "repeated_failure", "out_of_scope", "no_source", "other")


@write_tool("handoff_to_human")
def handoff_to_human(
    db: Session,
    actor: Actor,
    conversation_id: str,
    reason: str,
    note: str = "",
    now: datetime | None = None,
) -> dict:
    """Create a handoff ticket. Asking for a person is itself the user's consent, so no card is shown."""
    now = resolve_now(now)
    if reason not in REASONS:
        raise ToolError("VALIDATION_ERROR", f"Reason must be one of {', '.join(REASONS)}.")
    text = reason if not note else f"{reason}: {note[:500]}"
    ticket = HandoffTicket(
        conversation_id=conversation_id, user_id=actor.user_id, reason=text, status="open", created_at=now
    )
    db.add(ticket)
    db.flush()
    return {"ticket_id": ticket.id, "status": ticket.status}
