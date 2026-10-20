"""Browser tests of the nine screens against the real API (docs §8, TC-17, TC-20, NFR-12, NFR-13).

    cd ui && npm ci && npm run build && cd .. && pytest -m e2e tests/e2e

The server clock starts at Monday 19 October 2026, 08:00 IST (tests/e2e/server.py).
"""

import re
import time
import uuid
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import Api

pytestmark = pytest.mark.e2e
AXE = Path(__file__).resolve().parents[2] / "ui" / "node_modules" / "axe-core" / "axe.min.js"
TODAY = "2026-10-19"


def sign_in(page: Page, role_label: str) -> None:
    page.goto("/")
    page.get_by_role("button", name=re.compile(rf"^{role_label}")).click()
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()


def send(page: Page, text: str) -> None:
    page.get_by_label("Type your message…").fill(text)
    page.get_by_role("button", name="Send").click()


# --------------------------------------------------------------------------- patient (S1–S5)


def test_booking_goes_through_a_card_and_shows_in_my_appointments(page: Page):
    sign_in(page, "Patient")
    send(page, "Book a Marathi-speaking cardiologist on Saturday")
    card = page.get_by_role("region", name="Please confirm")
    expect(card).to_contain_text("Dr. Anand Kulkarni (Cardiology)")
    expect(card).to_contain_text("This card expires in")
    card.get_by_role("button", name="Confirm").click()
    expect(page.locator(".msg.assistant").last).to_contain_text("Done.")
    expect(card).to_have_count(0)
    page.get_by_role("link", name="My appointments").click()
    upcoming = page.locator("article").filter(has_text="Dr. Anand Kulkarni")
    expect(upcoming.first).to_contain_text("Sat, 24 Oct, 2026")


def test_create_an_account_then_log_in_again(page: Page):
    username = f"kiran-{uuid.uuid4().hex[:6]}"
    page.goto("/")
    page.get_by_role("button", name="Create account").click()
    form = page.get_by_role("form", name="Create account")
    form.get_by_label("Full name").fill("Kiran Jadhav")
    form.get_by_label("Username").fill(username)
    form.get_by_label("Password", exact=True).fill("monsoon-tea-7")
    form.get_by_label("Birth year").fill("1992")
    form.get_by_label("Mobile number").fill("9822012345")
    form.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()
    expect(page.get_by_text("Hello, Kiran.")).to_be_visible()
    page.get_by_role("button", name="Sign out (Kiran Jadhav)").click()

    login = page.get_by_role("form", name="Log in")
    login.get_by_label("Username").fill(username)
    login.get_by_label("Password", exact=True).fill("wrong-password")
    login.get_by_role("button", name="Log in").click()
    expect(login.get_by_role("alert")).to_contain_text("Wrong username or password.")
    login.get_by_label("Password", exact=True).fill("monsoon-tea-7")
    login.get_by_role("button", name="Log in").click()
    page.get_by_role("link", name="My appointments").click()
    expect(page.get_by_text("No upcoming appointments")).to_be_visible()


def test_emergency_takes_over_the_chat(page: Page):
    sign_in(page, "Patient")
    send(page, "My father collapsed and is not breathing")
    panel = page.get_by_role("alert")
    expect(panel).to_contain_text("Call 112 or 108 now")
    expect(page.get_by_role("button", name="Send")).to_have_count(0)
    panel.get_by_role("button", name=re.compile("not an emergency")).click()
    expect(page.get_by_role("button", name="Send")).to_be_visible()


def test_knowledge_answer_has_a_source_chip(page: Page):
    sign_in(page, "Patient")
    send(page, "Do I need to fast before a lipid profile?")
    chip = page.get_by_role("button", name=re.compile(r"^\[1\] "))
    expect(chip).to_be_visible()
    chip.click()
    expect(page.locator(".source-detail")).to_contain_text("verified")


def test_interface_switches_to_hindi_and_marathi(page: Page):
    sign_in(page, "Patient")
    page.get_by_role("button", name="हिन्दी").first.click()
    expect(page.get_by_role("link", name="मेरे अपॉइंटमेंट")).to_be_visible()
    expect(page.locator(".banner")).to_contain_text("चिकित्सा उपयोग के लिए नहीं")
    page.get_by_role("button", name="मराठी").first.click()
    expect(page.get_by_role("link", name="माझ्या अपॉइंटमेंट")).to_be_visible()
    assert page.evaluate("document.documentElement.lang") == "mr"


def _book_and_check_in_asha(base_url: str, staff_api: Api, doctor_name: str) -> dict:
    asha = Api(base_url, "patient").get("/me")["patient_id"]
    doctor = next(d for d in staff_api.get("/staff/today")["doctors"] if d["doctor_name"] == doctor_name)
    slots = staff_api.get(f"/doctors/{doctor['doctor_id']}/slots", date=TODAY, patient_id=asha)["slots"]
    appt = staff_api.post("/appointments", {"patient_id": asha, "slot_id": slots[-1]["slot_id"], "confirmed": True})
    entry = staff_api.post(f"/queue/entries/{appt['appointment_id']}/check-in")
    return entry


def test_tc20_queue_page_updates_within_two_seconds(page: Page, base_url: str, staff_api: Api):
    entry = _book_and_check_in_asha(base_url, staff_api, "Dr. Suresh Pawar")
    sign_in(page, "Patient")
    page.get_by_role("link", name="Queue status").click()
    card = page.locator("section.card").filter(has_text="Dr. Suresh Pawar")
    expect(card).to_contain_text(entry["token"])
    expect(card.get_by_text("Live")).to_be_visible()
    started = time.monotonic()
    staff_api.post(f"/queue/sessions/{entry['session_id']}/events", {"type": "delay", "minutes": 20})
    expect(card).to_contain_text("Running late (20 min)", timeout=5000)
    elapsed = time.monotonic() - started
    assert elapsed < 2.0, f"queue page updated after {elapsed:.2f} s"


# --------------------------------------------------------------------------- staff (S6, S7)


def test_front_desk_checks_in_and_registers_a_walk_in(page: Page):
    sign_in(page, "Front desk")
    page.get_by_label("Doctor").select_option(label="Dr. Kavita Joshi — General Medicine")
    bookings = page.get_by_role("region", name="Bookings today")
    bookings.get_by_role("button", name="Check in").first.click()
    expect(bookings.get_by_text(re.compile(r"Checked in B\d\d")).first).to_be_visible()
    queue = page.get_by_role("region", name="Queue")
    expect(queue.get_by_role("cell", name=re.compile(r"^B\d\d"))).to_have_count(1)
    walk_in = page.get_by_role("region", name="Register walk-in")
    walk_in.get_by_label("Patient name").fill("Ramesh Kale")
    walk_in.get_by_role("button", name="Register").click()
    expect(queue.get_by_text("Ramesh Kale")).to_have_count(0)  # birth year and phone are required first
    walk_in.get_by_label("Birth year").fill("1979")
    walk_in.get_by_label("Phone (stored masked)").fill("9876543210")
    walk_in.get_by_role("button", name="Register").click()
    expect(queue.get_by_text("Ramesh Kale")).to_be_visible()
    queue.get_by_role("button", name="Call next").click()
    expect(queue.get_by_text("Called — please go in")).to_be_visible()


def test_doctor_marked_unavailable_informs_patients(page: Page):
    sign_in(page, "Front desk")
    page.get_by_role("link", name="Doctor status").click()
    card = page.get_by_role("region", name="Dr. Meera Iyer")
    page.once("dialog", lambda dialog: dialog.accept())
    card.get_by_role("button", name="Unavailable today").click()
    expect(page.get_by_role("status").filter(has_text="Patients informed")).to_be_visible()
    expect(card).to_contain_text("Not available today")


# --------------------------------------------------------------------------- admin (S8, S9)


def test_dashboard_shows_departments_and_evaluation(page: Page):
    sign_in(page, "OPD admin")
    table = page.get_by_role("table")
    expect(table.get_by_role("row")).to_have_count(9)  # header + 8 departments
    expect(page.get_by_text("Latest evaluation results")).to_be_visible()
    expect(page.get_by_text(re.compile(r"Medical-advice bait: \d+/\d+"))).to_be_visible()


def test_analytics_answers_with_sql_and_refuses_writes(page: Page):
    sign_in(page, "OPD admin")
    page.get_by_role("link", name="Analytics").click()
    page.get_by_label("Analytics").fill("How many appointments per department?")
    page.get_by_role("button", name="Ask").click()
    expect(page.get_by_text("Generated SQL")).to_be_visible()
    expect(page.get_by_role("columnheader", name="department")).to_be_visible()
    with page.expect_download() as download:
        page.get_by_role("button", name="Export CSV").click()
    assert download.value.suggested_filename == "careflow-analytics.csv"
    page.get_by_label("Analytics").fill("Delete all of last week's no-shows")
    page.get_by_role("button", name="Ask").click()
    expect(page.get_by_role("alert")).to_contain_text("Only read-only questions are allowed here.")


# --------------------------------------------------------------------------- accessibility and phone layout


def _axe_violations(page: Page) -> list[dict]:
    page.add_script_tag(path=str(AXE))
    result = page.evaluate("axe.run(document, {runOnly: ['wcag2a', 'wcag2aa']})")
    return [
        {"id": v["id"], "impact": v["impact"], "nodes": [n["target"] for n in v["nodes"][:3]]}
        for v in result["violations"]
        if v["impact"] in ("serious", "critical")
    ]


@pytest.mark.parametrize(
    "role, links",
    [
        (None, []),
        ("Patient", ["Assistant", "My appointments", "Queue status"]),
        ("Front desk", ["Front desk", "Doctor status"]),
        ("OPD admin", ["Dashboard", "Analytics"]),
    ],
)
def test_no_serious_accessibility_violations(page: Page, role, links):
    if role is None:
        page.goto("/")
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        assert _axe_violations(page) == []
        return
    sign_in(page, role)
    for link in links:
        page.get_by_role("link", name=link, exact=True).click()
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        page.wait_for_load_state("networkidle")
        assert _axe_violations(page) == [], link


def test_patient_screens_fit_a_360_px_phone_in_large_text(phone: Page):
    phone.goto("/")
    phone.get_by_label("Large text").check()
    phone.get_by_role("button", name=re.compile("^Patient")).click()
    for link in ("Assistant", "My appointments", "Queue status"):
        phone.get_by_role("link", name=link, exact=True).click()
        expect(phone.get_by_role("heading", level=1)).to_be_visible()
        overflow = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 0, f"{link}: {overflow}px of horizontal scroll"
    # A checkbox counts with its label (the whole label is the tap target).
    targets = phone.evaluate(
        "[...document.querySelectorAll('button, a, input, select')].filter(e => e.offsetParent)"
        ".map(e => (e.closest('label') || e).getBoundingClientRect().height).filter(h => h < 44).length"
    )
    assert targets == 0, f"{targets} tap targets are smaller than 44 px"


# --------------------------------------------------------------------------- demo reset (TC-17), last


def test_zz_demo_reset_from_the_dashboard(page: Page, admin_api: Api):
    sign_in(page, "OPD admin")
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Reset demo data").click()
    expect(page.get_by_role("status").filter(has_text="Demo data reset.")).to_be_visible(timeout=60000)
    waiting = sum(d["waiting"] for d in admin_api.get("/admin/dashboard")["departments"])
    assert waiting == 0  # the queues created by the earlier tests are gone
