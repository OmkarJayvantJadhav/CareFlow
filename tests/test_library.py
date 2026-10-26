"""The information library: every knowledge-base document is readable by anyone, without signing in."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.db.models import KbDocument


@pytest.fixture
def client():
    return TestClient(app)  # no Authorization header anywhere in this file


def test_every_document_the_assistant_can_cite_is_readable_without_signing_in(client, world, kb):
    indexed = {(d.language, d.source_path) for d in world.db.scalars(select(KbDocument))}
    readable = set()
    for lang in ("en", "hi", "mr"):
        listing = client.get("/api/v1/library", params={"language": lang})
        assert listing.status_code == 200
        body = listing.json()
        assert body["total"] == len(body["documents"]) == sum(c["count"] for c in body["collections"])
        for d in body["documents"]:
            doc = client.get(f"/api/v1/library/{d['collection']}/{d['slug']}", params={"language": lang})
            assert doc.status_code == 200 and doc.json()["sections"], d
            readable.add((lang, f"knowledge/{lang}/{d['collection']}/{d['slug']}.md"))
    assert readable == indexed and len(readable) == 363


def test_document_has_its_sections_and_translations(client):
    doc = client.get("/api/v1/library/test_preparation/lipid-profile", params={"language": "hi"}).json()
    assert doc["language"] == "hi" and doc["languages"] == ["en", "hi", "mr"]
    assert doc["doc_key"] == "test_preparation/lipid-profile" and doc["last_verified"] == "2026-10-01"
    assert all(s["heading"] and s["body"] for s in doc["sections"])
    english = client.get("/api/v1/library/test_preparation/lipid-profile").json()
    assert len(english["sections"]) == len(doc["sections"]) and english["title"] != doc["title"]


def test_search_needs_every_word_and_works_in_hindi_and_marathi(client):
    found = client.get("/api/v1/library", params={"q": "lipid fasting"}).json()
    assert found["documents"][0]["slug"] == "lipid-profile"
    assert "fast" in found["documents"][0]["summary"].lower()
    assert client.get("/api/v1/library", params={"q": "lipid zebra"}).json()["total"] == 0
    for lang, word in (("hi", "उपवास"), ("mr", "उपवास")):
        assert client.get("/api/v1/library", params={"language": lang, "q": word}).json()["total"] > 0
    queue = client.get("/api/v1/library", params={"collection": "policies", "q": "online"}).json()
    assert "join-queue-online" in {d["slug"] for d in queue["documents"]}
    assert all(d["collection"] == "policies" for d in queue["documents"])


def test_bad_requests(client):
    assert client.get("/api/v1/library/policies/no-such-page").status_code == 404
    assert client.get("/api/v1/library/../app/config").status_code == 404
    assert client.get("/api/v1/library", params={"collection": "secrets"}).status_code == 400
    assert client.get("/api/v1/library", params={"language": "fr"}).status_code == 400
    assert client.get("/api/v1/library", params={"q": "x" * 101}).status_code == 400
