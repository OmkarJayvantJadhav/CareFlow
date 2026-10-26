"""Phase 7D: admins keep the information documents and the booking rules; the index follows every change."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.main import app
from app.db.models import KbDocument, PolicySetting
from app.rag.ingest import ingest
from app.rag.kb import DEFAULT_ROOT, reindex
from app.rag.retriever import get_retriever
from app.tools import policy
from app.tools.booking import book_appointment, cancel_appointment
from app.tools.errors import ToolError
from tests.conftest import NOW, TODAY
from tests.test_api import headers, login


@pytest.fixture
def api(world, frozen_clock, kb):
    yield TestClient(app)
    # The knowledge base and the rules outlive a test: put both back as shipped.
    db = world.db
    db.rollback()
    db.execute(delete(PolicySetting))
    policy.apply()
    db.execute(delete(KbDocument).where(KbDocument.origin == "added"))
    for row in db.scalars(
        select(KbDocument).where((KbDocument.origin != "template") | KbDocument.hidden_at.is_not(None))
    ):
        row.template = (DEFAULT_ROOT.parent / row.source_path).read_text(encoding="utf-8")
        row.origin, row.hidden_at = "template", None
    db.flush()
    reindex(db)  # refits only if a test changed the embedder (a simulated deployment)
    db.commit()


def doc_id(db, source: str) -> int:
    return db.scalar(select(KbDocument.id).where(KbDocument.source_path == source))


def search(db, query: str, language: str = "en") -> str:
    return " ".join(c.text for c in get_retriever(db).search(db, query, language=language))


CANCELLATION = "knowledge/en/policies/cancellation-policy.md"


def test_admins_change_a_rule_and_the_code_and_documents_follow(api, world):
    admin = headers(login(api, "admin"))
    current = api.get("/api/v1/admin/policy", headers=admin).json()
    assert current["values"]["cancel_hours"] == 4 and current["limits"]["cancel_hours"]["min"] == 2
    changed = api.put("/api/v1/admin/policy", json={"values": {"cancel_hours": 6}}, headers=admin)
    assert changed.status_code == 200, changed.text
    assert changed.json()["values"]["cancel_hours"] == 6 and changed.json()["documents_updated"] >= 3

    doc = api.get("/api/v1/library/policies/cancellation-policy").json()
    assert "up to 6 hours before" in doc["sections"][0]["body"] or "6 hours" in str(doc["sections"])
    assert "6 hours" in search(world.db, "cancel free of charge before the appointment")
    assert "6 hours" in policy.CANCEL_POLICY and api.get("/api/v1/config").json()["policy"]["cancel_hours"] == 6

    # The rule itself: five hours before is now too late to cancel online.
    pawar = world.doctor("Dr. Suresh Pawar")
    tomorrow = world.slots(pawar, TODAY + timedelta(days=1))
    appt = book_appointment(world.db, world.asha, world.asha.patient_id, tomorrow[0].id, confirmed=True, now=NOW)
    five_before = tomorrow[0].start_at - timedelta(hours=5)
    with pytest.raises(ToolError) as err:
        cancel_appointment(world.db, world.asha, appt["appointment_id"], confirmed=True, now=five_before)
    assert err.value.code == "POLICY_WINDOW" and "6 hours" in err.value.message

    for bad in ({"cancel_hours": 1}, {"cancel_hours": 500}, {"bogus": 3}):
        assert api.put("/api/v1/admin/policy", json={"values": bad}, headers=admin).status_code == 400
    staff = headers(login(api, "staff"))
    assert api.put("/api/v1/admin/policy", json={"values": {"cancel_hours": 8}}, headers=staff).status_code == 403
    assert world.db.get(PolicySetting, "cancel_hours").value == 6


def test_admins_edit_a_shipped_document_and_can_revert_it(api, world):
    admin = headers(login(api, "admin"))
    did = doc_id(world.db, CANCELLATION)
    original = api.get(f"/api/v1/admin/documents/{did}", headers=admin).json()
    assert original["origin"] == "template" and "{{cancel_hours}}" in original["body"]
    body = original["body"] + "\n## Bicycle parking\n\nBicycles can be parked free of charge next to Gate 3.\n"
    # The library was read before the change (and the clock is behind the database's): it must not stay stale.
    assert api.get("/api/v1/library/policies/cancellation-policy").status_code == 200
    saved = api.put(f"/api/v1/admin/documents/{did}", json={"title": original["title"], "body": body}, headers=admin)
    assert saved.status_code == 200, saved.text
    assert saved.json()["origin"] == "edited" and saved.json()["last_verified"] == TODAY.isoformat()
    assert saved.json()["index"]["reindexed"] >= 1
    assert "Gate 3" in search(world.db, "where can I park my bicycle")
    library = api.get("/api/v1/library/policies/cancellation-policy").json()
    assert library["sections"][-1]["heading"] == "Bicycle parking"

    # Loading the shipped templates again (a new deployment) leaves the edited document alone.
    ingest(world.db, if_needed=True)
    world.db.commit()
    assert "Gate 3" in world.db.get(KbDocument, did).template
    reverted = api.post(f"/api/v1/admin/documents/{did}/revert", headers=admin)
    assert reverted.status_code == 200 and reverted.json()["origin"] == "template"
    assert "Gate 3" not in search(world.db, "where can I park my bicycle")
    assert api.post(f"/api/v1/admin/documents/{did}/revert", headers=admin).status_code == 409


def test_admins_add_documents_and_translations(api, world):
    admin = headers(login(api, "admin"))
    body = "## When\n\nThe pharmacy is open 24 hours. Cancel online up to {{cancel_hours}} hours before a visit.\n"
    made = api.post("/api/v1/admin/documents", json={"title": "Night pharmacy", "body": body,
                                                      "collection": "facilities", "language": "en"}, headers=admin)  # fmt: skip
    assert made.status_code == 201, made.text
    doc = made.json()
    assert doc["origin"] == "added" and doc["slug"] == "night-pharmacy" and doc["missing_languages"] == ["hi", "mr"]
    shown = api.get("/api/v1/library/facilities/night-pharmacy").json()
    assert "up to 4 hours" in shown["sections"][0]["body"]
    assert "Night pharmacy" in search(world.db, "is the pharmacy open at night")

    hindi = api.post("/api/v1/admin/documents", json={"title": "रात की फार्मेसी", "body": "## कब\n\nफार्मेसी 24 घंटे खुली रहती है।\n",
                                                       "language": "hi", "translation_of": doc["document_id"]}, headers=admin)  # fmt: skip
    assert hindi.status_code == 201 and hindi.json()["doc_key"] == doc["doc_key"]
    assert api.get("/api/v1/library/facilities/night-pharmacy?language=hi").json()["languages"] == ["en", "hi"]
    again = api.post("/api/v1/admin/documents", json={"title": "फिर से", "body": "## कब\n\nफिर।\n", "language": "hi",
                                                       "translation_of": doc["document_id"]}, headers=admin)  # fmt: skip
    assert again.status_code == 409

    bad = {"title": "Odd", "collection": "facilities", "language": "en"}
    assert (
        api.post("/api/v1/admin/documents", json={**bad, "body": "No heading here."}, headers=admin).status_code == 400
    )
    unknown = {**bad, "body": "## A\n\nWithin {{refund_days}} days.\n"}
    assert api.post("/api/v1/admin/documents", json=unknown, headers=admin).status_code == 400
    assert api.post("/api/v1/admin/documents", json={**bad, "collection": "gossip", "body": "## A\n\nB\n"},
                    headers=admin).status_code == 400  # fmt: skip
    assert api.get("/api/v1/admin/documents", headers=headers(login(api, "staff"))).status_code == 403


def test_hidden_documents_leave_the_library_and_the_search(api, world):
    admin = headers(login(api, "admin"))
    did = doc_id(world.db, CANCELLATION)
    assert api.post(f"/api/v1/admin/documents/{did}/hide", headers=admin).json()["hidden"] is True
    assert api.get("/api/v1/library/policies/cancellation-policy").status_code == 404
    assert "Cancellation policy" not in search(world.db, "cancellation policy cancel free of charge")
    ingest(world.db, if_needed=True)  # a new deployment does not bring it back
    world.db.commit()
    assert world.db.get(KbDocument, did).hidden_at is not None
    listed = api.get("/api/v1/admin/documents", params={"q": "cancellation"}, headers=admin).json()
    assert any(d["document_id"] == did and d["hidden"] for d in listed["documents"]) and listed["counts"]["hidden"] == 1
    assert api.post(f"/api/v1/admin/documents/{did}/restore", headers=admin).status_code == 200
    assert api.get("/api/v1/library/policies/cancellation-policy").status_code == 200

    made = api.post("/api/v1/admin/documents", json={"title": "Temporary notice", "body": "## Notice\n\nLift 2 is closed.\n",
                                                      "collection": "facilities", "language": "en"}, headers=admin).json()  # fmt: skip
    gone = api.post(f"/api/v1/admin/documents/{made['document_id']}/hide", headers=admin).json()
    assert gone["deleted"] is True and world.db.get(KbDocument, made["document_id"]) is None
