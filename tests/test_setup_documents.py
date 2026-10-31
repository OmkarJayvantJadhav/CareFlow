"""D-139: on a hospital's own deployment the department, doctor and some facility pages are written from its
setup, in three languages, and follow every change; the demo keeps its shipped pages."""

from datetime import time, timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Department, KbDocument
from app.rag.retriever import get_retriever, reset_retriever
from app.rag.setup_docs import floor_name, refresh_setup_documents, setup_templates
from app.tools import documents, hospital
from tests.conftest import NOW, TODAY


@pytest.fixture
def site(world, kb, monkeypatch):
    """A hospital's deployment. The knowledge base changes stay in the test's transaction (rolled back)."""
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    reset_retriever()
    yield world
    world.db.rollback()
    reset_retriever()


def text(db, path: str) -> str | None:
    row = db.scalar(select(KbDocument).where(KbDocument.source_path == f"knowledge/{path}"))
    return None if row is None or row.hidden_at is not None else row.template


def admin(world):
    return world.user("mehta")


def add_dentistry(world):
    dept = hospital.create_department(
        world.db, admin(world), "Dentistry", 0, time(9), time(13), aliases=["teeth", "दात"], now=NOW
    )
    doctor = hospital.create_doctor(
        world.db, admin(world), "Dr. Priya Patil", dept["department_id"], ["en", "mr"], [1, 3, 5], 15, now=NOW
    )
    return dept, doctor


def test_a_new_department_and_doctor_get_their_pages_in_three_languages(site):
    db = site.db
    assert "Dr. Anand Kulkarni" in text(db, "en/departments/cardiology.md")  # seeded doctors keep their pages
    add_dentistry(site)

    en = text(db, "en/departments/dentistry.md")
    assert "# Dentistry department" in en and "toothache" in en  # a well-known department gets its description
    assert "The Dentistry OPD is on the ground floor. OPD hours are 09:00–13:00" in en
    assert "- Dr. Priya Patil: OPD on Monday, Wednesday and Friday; speaks English and Marathi." in en
    assert "## Also known as\n\nteeth, दात." in en
    assert "दंत चिकित्सा (डेंटल) विभाग" in text(db, "hi/departments/dentistry.md")
    assert "दंतचिकित्सा (डेंटल) ओपीडी तळमजल्यावर आहे" in text(db, "mr/departments/dentistry.md")

    doctor = text(db, "en/doctors/priya-patil.md")
    assert "Dr. Priya Patil is a consultant in the Dentistry department (ground floor)" in doctor
    assert "Each appointment slot is 15 minutes." in doctor
    assert "Ground floor: Dentistry." in text(db, "en/facilities/floor-guide.md")
    assert "- Dentistry: 09:00–13:00" in text(db, "en/facilities/opd-hours.md")

    # The assistant finds it straight away.
    found = " ".join(
        c.text for c in get_retriever(db).search(db, "Which doctors are in the Dentistry department?", language="en")
    )
    assert "Priya Patil" in found


def test_pages_follow_changes_and_removals(site):
    db = site.db
    dept, doctor = add_dentistry(site)
    hospital.update_doctor(
        db, admin(site), doctor["doctor_id"], languages=["en"], opd_days=[2], slot_minutes=20, now=NOW
    )
    assert "OPD on Tuesday; speaks English." in text(db, "en/departments/dentistry.md")
    assert "Each appointment slot is 20 minutes." in text(db, "en/doctors/priya-patil.md")

    hospital.delete_doctor(db, admin(site), doctor["doctor_id"], now=NOW)
    assert text(db, "en/doctors/priya-patil.md") is None
    assert "No doctor holds OPD in this department at the moment" in text(db, "en/departments/dentistry.md")

    hospital.delete_department(db, admin(site), dept["department_id"], now=NOW)
    assert text(db, "en/departments/dentistry.md") is None
    assert "Dentistry" not in text(db, "en/facilities/floor-guide.md")


def test_a_doctor_leaves_the_pages_after_their_last_day(site):
    db = site.db
    _, doctor = add_dentistry(site)
    last = TODAY + timedelta(days=2)
    hospital.set_last_day(db, admin(site), doctor["doctor_id"], last, now=NOW)
    assert f"Their last OPD day here is {last.day} {last:%B %Y}." in text(db, "en/doctors/priya-patil.md")
    assert not any(refresh_setup_documents(db, last).values())  # still here on the last day
    refresh_setup_documents(db, last + timedelta(days=1))  # the hourly check
    assert text(db, "en/doctors/priya-patil.md") is None


def test_unchanged_pages_keep_their_date(site):
    db = site.db
    add_dentistry(site)
    later = refresh_setup_documents(db, TODAY + timedelta(days=1))
    assert later == {"added": 0, "updated": 0, "removed": 0}
    assert f"last_verified: {TODAY.isoformat()}" in text(db, "en/departments/dentistry.md")


def test_the_hospitals_details_fill_the_location_and_emergency_pages(site):
    db = site.db
    hospital.update_profile(
        db,
        admin(site),
        {"en": "Omkar General Hospital", "mr": "ओंकार जनरल हॉस्पिटल"},
        "Station Road, Kolhapur",
        "0231 2650000",
        time(8),
        time(20),
        {"en": "The emergency department is at Gate 1, open 24 hours."},
        now=NOW,
    )
    location = text(db, "en/facilities/location-and-directions.md")
    assert "Omkar General Hospital, Station Road, Kolhapur." in location
    assert "The reception is open 08:00–20:00; phone 0231 2650000." in location
    assert "ओंकार जनरल हॉस्पिटल, Station Road, Kolhapur." in text(db, "mr/facilities/location-and-directions.md")
    emergency = text(db, "en/facilities/emergency-department.md")
    assert "The emergency department is at Gate 1, open 24 hours. For an ambulance, call 112 or 108." in emergency
    assert "City bus routes" not in location  # the demo hospital's directions are gone


def test_an_edited_page_is_kept_and_undo_brings_back_the_setup_version(site):
    db = site.db
    add_dentistry(site)
    row = db.scalar(select(KbDocument).where(KbDocument.source_path == "knowledge/en/departments/dentistry.md"))
    documents.save_document(db, admin(site), row.id, "Dentistry department", "## About\n\nOur own words.\n", now=NOW)
    dept_id = next(d.id for d in db.scalars(select(Department)) if d.name == "Dentistry")
    hospital.create_doctor(db, admin(site), "Dr. Rahul More", dept_id, ["en"], [6], 15, now=NOW)
    assert "Our own words." in text(db, "en/departments/dentistry.md")  # an admin's edit is left alone

    documents.revert_document(db, admin(site), row.id, now=NOW)
    reverted = text(db, "en/departments/dentistry.md")
    assert "Dr. Rahul More" in reverted and "Our own words." not in reverted


def row_department(site) -> int:
    return next(
        d["id"]
        for d in hospital.hospital_setup(site.db, admin(site), now=NOW)["departments"]
        if d["name"] == "Dentistry"
    )


def test_the_demo_keeps_its_shipped_pages(world, kb):
    assert get_settings().demo_mode is True
    hospital.create_department(world.db, world.user("mehta"), "Dentistry", 0, time(9), time(13), now=NOW)
    assert text(world.db, "en/departments/dentistry.md") is None
    world.db.rollback()


def test_unknown_departments_and_floors():
    assert floor_name(-1).en == "basement" and floor_name(-2).mr == "तळघर 2"
    assert floor_name(3).hi == "तीसरी मंज़िल" and floor_name(14).en == "floor 14"


def test_pages_are_written_for_any_department_name(site):
    db = site.db
    hospital.create_department(db, admin(site), "Sleep Clinic", 12, time(14), time(17), now=NOW)
    pages = setup_templates(db, TODAY)
    page = pages["en/departments/sleep-clinic.md"]
    assert "## About the department" not in page  # nothing is invented for a department we do not know
    assert "The Sleep Clinic OPD is on the floor 12." in page
