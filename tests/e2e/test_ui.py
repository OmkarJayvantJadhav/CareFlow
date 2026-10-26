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


def test_patient_changes_password_and_stays_signed_in(page: Page):
    username = f"leela-{uuid.uuid4().hex[:6]}"
    page.goto("/")
    page.get_by_role("button", name="Create account").click()
    form = page.get_by_role("form", name="Create account")
    form.get_by_label("Full name").fill("Leela Kulkarni")
    form.get_by_label("Username").fill(username)
    form.get_by_label("Password", exact=True).fill("monsoon-tea-7")
    form.get_by_label("Birth year").fill("1985")
    form.get_by_label("Mobile number").fill("9822012346")
    form.get_by_role("button", name="Create account").click()
    page.get_by_role("link", name="Profile").click()
    change = page.get_by_role("form", name="Change password")
    change.get_by_label("Current password", exact=True).fill("not-my-password")
    change.get_by_label("New password", exact=True).fill("winter-chai-8")
    change.get_by_label("New password, again", exact=True).fill("winter-chai-8")
    change.get_by_role("button", name="Change password").click()
    expect(change.get_by_role("alert")).to_be_visible()  # a wrong password is said, and the session stays
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()
    change.get_by_label("Current password", exact=True).fill("monsoon-tea-7")
    change.get_by_label("New password", exact=True).fill("winter-chai-8")
    change.get_by_label("New password, again", exact=True).fill("winter-chai-9")
    change.get_by_role("button", name="Change password").click()
    expect(change.get_by_role("alert")).to_contain_text("The two new passwords are different.")
    change.get_by_label("New password, again", exact=True).fill("winter-chai-8")
    change.get_by_role("button", name="Change password").click()
    expect(change.get_by_role("status")).to_contain_text("Password changed")
    page.get_by_role("link", name="My appointments").click()  # still signed in, with the new sign-in
    expect(page.get_by_text("No upcoming appointments")).to_be_visible()


def log_in(page: Page, username: str, password: str) -> None:
    login = page.get_by_role("form", name="Log in")
    login.get_by_label("Username").fill(username)
    login.get_by_label("Password", exact=True).fill(password)
    login.get_by_role("button", name="Log in").click()


def test_admin_creates_a_staff_account_that_chooses_its_own_password(page: Page):
    username = f"desk-{uuid.uuid4().hex[:6]}"
    sign_in(page, "OPD admin")
    page.get_by_role("link", name="Accounts", exact=True).click()
    page.get_by_role("button", name="New account").click()
    dialog = page.get_by_role("dialog", name="New account")
    dialog.get_by_label("Full name").fill("Kavya Shetty")
    dialog.get_by_label("Username").fill(username)
    dialog.get_by_label("Role").select_option("staff")
    dialog.get_by_role("button", name="Create account").click()
    shown = page.get_by_role("dialog", name="Temporary password")
    temporary = shown.locator("code").inner_text()
    assert len(temporary) == 12
    shown.get_by_role("button", name="Done").click()
    expect(page.get_by_role("row").filter(has_text=username)).to_contain_text("Temporary password")
    page.get_by_role("button", name=re.compile("^Sign out")).click()

    log_in(page, username, temporary)
    expect(page.get_by_role("heading", name="Choose your own password")).to_be_visible()
    expect(page.get_by_role("navigation", name="Main")).to_have_count(0)
    gate = page.get_by_role("form", name="Change password")
    gate.get_by_label("Temporary password", exact=True).fill(temporary)
    gate.get_by_label("New password", exact=True).fill("harbour-lamp-31")
    gate.get_by_label("New password, again", exact=True).fill("harbour-lamp-31")
    gate.get_by_role("button", name="Change password").click()
    expect(page.get_by_role("heading", name="Front desk", level=1)).to_be_visible()
    page.get_by_role("button", name="Sign out (Kavya Shetty)").click()

    sign_in(page, "OPD admin")
    page.get_by_role("link", name="Accounts", exact=True).click()
    page.get_by_label("Name or username").fill(username)
    page.get_by_role("button", name="Search", exact=True).click()
    page.get_by_role("button", name="Switch off: Kavya Shetty").click()
    page.get_by_role("dialog", name="Switch account off").get_by_role("button", name="Switch off").click()
    expect(page.get_by_role("status").filter(has_text="Kavya Shetty's account is switched off.")).to_be_visible()
    page.get_by_role("button", name=re.compile("^Sign out")).click()
    log_in(page, username, "harbour-lamp-31")
    expect(page.get_by_role("form", name="Log in").get_by_role("alert")).to_contain_text("switched off")


def create_account(page: Page, name: str, username: str, phone: str, password: str = "monsoon-tea-7") -> None:
    page.goto("/")
    page.get_by_role("button", name="Create account").click()
    form = page.get_by_role("form", name="Create account")
    form.get_by_label("Full name").fill(name)
    form.get_by_label("Username").fill(username)
    form.get_by_label("Password", exact=True).fill(password)
    form.get_by_label("Birth year").fill("1985")
    form.get_by_label("Mobile number").fill(phone)
    form.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()


def test_staff_correct_a_record_and_an_admin_erases_it_on_request(page: Page):
    username = f"leela-{uuid.uuid4().hex[:6]}"
    create_account(page, "Leela Kulkarni", username, "98220 12399")
    page.get_by_role("button", name="Sign out (Leela Kulkarni)").click()

    sign_in(page, "Front desk")
    page.get_by_role("link", name="Patients", exact=True).click()
    page.get_by_label("Name, mobile number or record number").fill("98220 12399")
    page.get_by_role("button", name="Search", exact=True).click()
    page.get_by_role("button", name=re.compile(f"^Leela Kulkarni.*@{username}")).click()
    record = page.get_by_role("article", name="Leela Kulkarni")
    expect(record).to_contain_text("+91 98XXXXXX99")
    record.get_by_role("button", name="Show number").click()
    expect(record.get_by_role("link", name="+91 98220 12399")).to_be_visible()
    edit = page.get_by_role("form", name="Edit patient details")
    edit.get_by_label("Full name").fill("Leela A. Kulkarni")
    edit.get_by_role("button", name="Save changes").click()
    expect(edit.get_by_role("status")).to_contain_text("Saved.")
    expect(page.get_by_role("article", name="Leela A. Kulkarni")).to_be_visible()
    expect(page.get_by_role("button", name="Erase this patient's details")).to_have_count(0)  # admins only
    page.get_by_role("button", name=re.compile("^Sign out")).click()

    sign_in(page, "OPD admin")
    page.get_by_role("link", name="Patients", exact=True).click()
    page.get_by_label("Name, mobile number or record number").fill("leela a. kulkarni")
    page.get_by_role("button", name="Search", exact=True).click()
    page.get_by_role("button", name=re.compile(f"^Leela A. Kulkarni.*@{username}")).click()
    page.get_by_role("button", name="Erase this patient's details").click()
    dialog = page.get_by_role("dialog", name="Erase personal details")
    dialog.get_by_label(re.compile("^Reason")).fill("Written request at the desk")
    dialog.get_by_role("button", name="Erase for good").click()
    expect(page.get_by_role("status").filter(has_text="personal details were erased")).to_be_visible()
    page.get_by_role("button", name=re.compile("^Sign out")).click()
    log_in(page, username, "monsoon-tea-7")
    expect(page.get_by_role("form", name="Log in").get_by_role("alert")).to_contain_text("Wrong username or password.")


def test_patients_download_their_data_and_delete_their_account(page: Page):
    create_account(page, "Ravi Shinde", f"ravi-{uuid.uuid4().hex[:6]}", "98220 12398")
    page.get_by_role("link", name="Profile").click()
    with page.expect_download() as download:
        page.get_by_role("button", name="Download my data").click()
    assert download.value.suggested_filename == "careflow-my-data.json"
    page.get_by_role("button", name="Delete my account").click()
    dialog = page.get_by_role("dialog", name="Delete my account")
    dialog.get_by_label("Password", exact=True).fill("not-my-password")
    dialog.get_by_role("button", name="Delete for good").click()
    expect(dialog.get_by_role("alert")).to_contain_text("That password is not right.")
    dialog.get_by_label("Password", exact=True).fill("monsoon-tea-7")
    dialog.get_by_role("button", name="Delete for good").click()
    expect(
        page.get_by_role("status").filter(has_text="Your account and personal details have been deleted.")
    ).to_be_visible()
    expect(page.get_by_role("form", name="Log in")).to_be_visible()


def test_book_from_recommendations_then_receipt_reschedule_and_cancel(page: Page):
    sign_in(page, "Patient")
    page.get_by_role("link", name="Book", exact=True).click()
    page.get_by_label("Department").select_option("ENT")
    page.get_by_label("From").fill("2026-10-22")  # far enough ahead to reschedule and cancel online
    page.get_by_role("button", name="Find the best times").click()
    first = page.locator(".slot-card").first
    # Asha has seen an ENT doctor before: continuity ranks above the soonest time, which is still listed.
    expect(first.locator(".reasons")).to_contain_text("Doctor you have seen")
    expect(page.locator(".slot-card .reasons").filter(has_text="Soonest")).to_have_count(1)
    doctor = first.locator("strong").first.inner_text()
    first.get_by_role("button", name=re.compile("^Choose")).click()
    dialog = page.get_by_role("dialog", name="Confirm booking")
    expect(dialog).to_contain_text(f"{doctor} (ENT)")
    dialog.get_by_role("button", name="Confirm").click()
    expect(page.get_by_role("status").filter(has_text="Booked. Your receipt is ready.")).to_be_visible()
    page.get_by_role("link", name="View receipt").click()
    receipt = page.get_by_role("article", name="Appointment receipt")
    expect(receipt).to_contain_text(re.compile(r"CF-\d{6}-[0-9A-F]{6}"))
    expect(receipt.get_by_role("img", name=re.compile("^Reference CF-"))).to_be_visible()

    page.get_by_role("link", name="My appointments").first.click()
    card = page.locator("article").filter(has_text=doctor).first
    card.get_by_role("button", name="Reschedule").click()
    expect(page.get_by_role("heading", name="Choose a new time")).to_be_visible()
    page.get_by_label("From").fill("2026-10-26")
    page.get_by_role("button", name="Find the best times").click()
    expect(page.locator(".slot-card").first).to_contain_text("26 Oct")
    page.locator(".slot-card").first.get_by_role("button", name=re.compile("^Move here")).click()
    page.get_by_role("dialog", name="Confirm new time").get_by_role("button", name="Confirm").click()
    expect(page.get_by_role("status").filter(has_text="Your appointment has been moved.")).to_be_visible()

    page.get_by_role("navigation", name="Main").get_by_role("link", name="My appointments").click()
    page.locator("article").filter(has_text=doctor).first.get_by_role("button", name="Cancel").click()
    page.get_by_role("dialog", name="Cancel this appointment?").get_by_role("button", name="Yes, cancel it").click()
    expect(page.get_by_role("status").filter(has_text="Your appointment has been cancelled.")).to_be_visible()


def test_profile_changes_are_saved(page: Page):
    sign_in(page, "Patient")
    page.get_by_role("link", name="Profile").click()
    page.get_by_label("Full name").fill("Asha R. Patil")
    page.get_by_label("Mobile number").fill("9123456780")
    page.get_by_role("button", name="Save changes").click()
    expect(page.get_by_role("status").filter(has_text="Saved.")).to_be_visible()
    expect(page.get_by_text("On file: +91 91XXXXXX80.")).to_be_visible()
    page.get_by_label("Full name").fill("Asha Patil")
    page.get_by_role("button", name="Save changes").click()
    expect(page.get_by_role("status").filter(has_text="Saved.")).to_be_visible()


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


def test_assistant_joins_a_queue_online_and_leaves_it(page: Page):
    sign_in(page, "Patient")
    send(page, "Can I join the dermatology queue today? I have no appointment.")
    card = page.get_by_role("region", name="Please confirm")
    expect(card).to_contain_text("Dr. Ritu Agarwal (Dermatology)")
    expect(card).to_contain_text("Floor")
    card.get_by_role("button", name="Confirm").click()
    expect(page.locator(".msg.assistant").last).to_contain_text(re.compile(r"token V\d\d"))
    send(page, "Something came up, please take me out of the queue.")
    card = page.get_by_role("region", name="Please confirm")
    expect(card).to_contain_text("Dr. Ritu Agarwal")
    card.get_by_role("button", name="Confirm").click()
    expect(page.locator(".msg.assistant").last).to_contain_text("has left Dr. Ritu Agarwal's queue")


def test_anyone_can_read_the_hospital_information_without_signing_in(page: Page):
    page.goto("/")
    page.get_by_role("link", name="Hospital information").click()
    expect(page.get_by_role("heading", level=1, name="Hospital information")).to_be_visible()
    page.get_by_label("Search the documents").fill("lipid fasting")
    page.get_by_role("button", name="Search").click()
    expect(page.get_by_text("Found 1 for “lipid fasting”")).to_be_visible()
    page.get_by_role("link", name=re.compile("^Lipid profile")).click()
    expect(page.get_by_role("heading", level=1, name=re.compile("^Lipid profile"))).to_be_visible()
    page.get_by_role("group", name="Read in").get_by_role("button", name="हिन्दी").click()
    expect(page.get_by_role("heading", level=1, name=re.compile("लिपिड"))).to_be_visible()
    assert page.evaluate("document.querySelector('article').lang") == "hi"
    page.get_by_role("group", name="पढ़ें", exact=False).get_by_role("button", name="English").click()
    page.get_by_role("link", name="All hospital information").click()
    page.get_by_role("button", name=re.compile(r"^Test preparation \(")).click()
    expect(page.locator(".library-item")).to_have_count(51)


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


def _book_asha_today(base_url: str, staff_api: Api, doctor_name: str, first: bool = True) -> dict:
    """Book Asha today with a doctor no other test uses; returns the appointment with its receipt code."""
    patient = Api(base_url, "patient")
    asha = patient.get("/me")["patient_id"]
    doctor = next(d for d in staff_api.get("/staff/today")["doctors"] if d["doctor_name"] == doctor_name)
    slots = staff_api.get(f"/doctors/{doctor['doctor_id']}/slots", date=TODAY, patient_id=asha)["slots"]
    slot = slots[0] if first else slots[-1]
    appt = staff_api.post("/appointments", {"patient_id": asha, "slot_id": slot["slot_id"], "confirmed": True})
    return {**appt, "reference": patient.get(f"/appointments/{appt['appointment_id']}/receipt")["reference"]}


def test_patient_checks_in_online_inside_the_window(page: Page, base_url: str, staff_api: Api):
    _book_asha_today(base_url, staff_api, "Dr. Nitin Chavan")  # 09:00; the clock is just after 08:00
    sign_in(page, "Patient")
    page.get_by_role("navigation", name="Main").get_by_role("link", name="My appointments").click()
    card = page.locator("article").filter(has_text="Dr. Nitin Chavan")
    card.get_by_role("button", name="Check in now").click()
    page.get_by_role("dialog", name="Check in now").get_by_role("button", name="Check in").click()
    expect(page.get_by_role("status").filter(has_text=re.compile(r"Checked in · token B\d\d"))).to_be_visible()
    expect(card.get_by_role("link", name=re.compile(r"^Checked in · token B\d\d"))).to_be_visible()


def test_consent_and_caregiver_approval(page: Page, base_url: str):
    rajan = Api(base_url, "caregiver")
    rajan.post("/caregiver/requests", {"patient_username": "asha"})
    sign_in(page, "Patient")
    page.get_by_role("link", name="Profile").click()
    reminders = page.get_by_label("Appointment reminders")
    reminders.uncheck()
    expect(page.locator(".consent-row").filter(has_text="Appointment reminders")).to_contain_text("Not allowed")
    reminders.check()
    requests = page.get_by_role("list", name="Requests waiting for your answer")
    expect(requests).to_contain_text("Rajan Deshmukh")
    requests.get_by_role("button", name="Approve").click()
    people = page.get_by_role("list", name="People who can manage your appointments")
    expect(people).to_contain_text("Rajan Deshmukh")
    people.get_by_role("button", name="Remove access").click()
    expect(page.get_by_text("Nobody else can manage your appointments.")).to_be_visible()


# --------------------------------------------------------------------------- staff (S6, S7)


def test_front_desk_checks_in_and_registers_a_walk_in(page: Page):
    sign_in(page, "Front desk")
    page.get_by_label("Doctor", exact=True).select_option(label="Dr. Kavita Joshi — General Medicine")
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


def test_staff_record_and_remove_leave_in_the_calendar(page: Page):
    sign_in(page, "Front desk")
    page.get_by_role("link", name="Calendar").click()
    page.get_by_label("Doctor", exact=True).select_option(label="Dr. Imran Shaikh — General Medicine")
    expect(page.get_by_text(re.compile(r"^Typical visit: \d+ min"))).to_be_visible()
    leave = page.get_by_role("region", name="Leave", exact=True)
    leave.get_by_label("From").fill("2026-10-27")
    leave.get_by_label("To").fill("2026-10-27")
    leave.get_by_label("Reason (optional)").fill("Conference")
    leave.get_by_role("button", name="Add leave").click()
    page.get_by_role("dialog", name="Add leave").get_by_role("button", name="Add leave").click()
    expect(page.get_by_role("status").filter(has_text="Leave recorded.")).to_be_visible()
    page.get_by_role("button", name="Next week").click()
    expect(page.get_by_text("On leave · Conference")).to_be_visible()
    leave.get_by_role("button", name="Remove leave").click()
    expect(page.get_by_role("status").filter(has_text="Leave removed")).to_be_visible()


def test_desk_checks_in_by_receipt_code_and_the_kiosk_too(page: Page, base_url: str, staff_api: Api):
    at_desk = _book_asha_today(base_url, staff_api, "Dr. Snehal Gokhale", first=False)
    at_kiosk = _book_asha_today(base_url, staff_api, "Dr. Sunita Patwardhan", first=False)
    sign_in(page, "Front desk")
    card = page.get_by_role("region", name="Check in by receipt code")
    card.get_by_label("Receipt code").fill(at_desk["reference"].lower())
    card.get_by_role("button", name="Look up").click()
    expect(card).to_contain_text("Asha Patil")
    card.get_by_role("button", name="Check in").click()
    page.get_by_role("dialog", name="Check in").get_by_role("button", name="Check in").click()
    expect(card.get_by_role("status")).to_contain_text(re.compile(r"Checked in · token B\d\d"))

    card.get_by_role("link", name="Open kiosk").click()
    expect(page.get_by_role("heading", name="Self check-in")).to_be_visible()
    page.get_by_label("Type the code from your appointment receipt").fill(at_kiosk["reference"])
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_text("Welcome, Asha")).to_be_visible()
    expect(page.get_by_text("Patil")).to_have_count(0)  # only the first name is shown at the kiosk
    page.get_by_role("button", name="Check in").click()
    expect(page.get_by_role("status")).to_contain_text("You are checked in")
    page.get_by_role("button", name="Next patient").click()
    page.get_by_label("Type the code from your appointment receipt").fill("CF-000001-ZZZZZZ")
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_role("alert")).to_contain_text("This code is not valid")


def test_walk_in_finds_the_existing_record(page: Page):
    sign_in(page, "Front desk")
    page.get_by_label("Doctor", exact=True).select_option(label="Dr. Vikram Bhosale — Orthopaedics")
    walk_in = page.get_by_role("region", name="Register walk-in")
    walk_in.get_by_label("Patient name").fill("asha  patil")
    walk_in.get_by_label("Birth year").fill("1992")
    walk_in.get_by_label("Phone (stored masked)").fill("9000000000")
    walk_in.get_by_role("button", name="Register").click()
    matches = page.get_by_role("region", name="This patient may already be registered")
    expect(matches).to_contain_text("Asha Patil")
    expect(matches).to_contain_text("Same name")
    matches.get_by_role("button", name="Use this record").first.click()
    expect(page.get_by_role("region", name="Queue").get_by_text("Asha Patil")).to_be_visible()


def test_admin_adds_a_registration_question_asked_at_sign_up(page: Page):
    question = f"Blood group {uuid.uuid4().hex[:4]}"  # the form keeps its questions between runs
    sign_in(page, "OPD admin")
    page.get_by_role("link", name="Registration form").click()
    page.get_by_label("Question in English").fill(question)
    page.get_by_label("Question in Hindi").fill("रक्त समूह")
    page.get_by_label("Question in Marathi").fill("रक्तगट")
    page.get_by_label("Answer type").select_option("choice")
    page.get_by_label("Options").fill("A+, B+, O+, AB+")
    page.get_by_role("button", name="Add question").click()
    expect(page.get_by_role("status").filter(has_text="Question added.")).to_be_visible()
    expect(page.get_by_role("region", name="Current questions")).to_contain_text(question)
    page.get_by_role("button", name=re.compile("^Sign out")).first.click()
    page.get_by_role("button", name="Create account").click()
    form = page.get_by_role("form", name="Create account")
    expect(form.get_by_label(re.compile(f"^{question}"))).to_be_visible()


# --------------------------------------------------------------------------- queue management (phase 6C)


def _walk_in(staff_api: Api, doctor_name: str, name: str, phone: str) -> dict:
    doctor = next(d for d in staff_api.get("/staff/today")["doctors"] if d["doctor_name"] == doctor_name)
    body = {"doctor_id": doctor["doctor_id"], "name": name, "birth_year": 1961, "phone": phone}
    return staff_api.post("/queue/walk-ins", body)


def test_caregiver_joins_a_queue_online_and_leaves_it(page: Page):
    sign_in(page, "Caregiver")
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Queue status").click()
    join = page.get_by_role("region", name="Join a queue online")
    join.get_by_label("Department").select_option(label="ENT")
    join.get_by_role("button", name="Join queue: Dr. Snehal Gokhale").click()
    card = page.locator("section.token-card").filter(has_text="Dr. Snehal Gokhale")
    expect(card).to_contain_text("V01")
    expect(card).to_contain_text("Please reach the OPD desk on floor 2")
    card.get_by_role("button", name="Leave the queue").click()
    page.get_by_role("dialog", name="Leave the queue (V01)?").get_by_role("button", name="Leave the queue").click()
    expect(card).to_have_count(0)


def test_front_desk_asks_the_doctor_and_moves_a_patient(page: Page, staff_api: Api):
    walk = _walk_in(staff_api, "Dr. Kavita Joshi", "Sunanda Pathak", "9811100011")
    token = walk["token"]
    sign_in(page, "Front desk")
    page.get_by_label("Doctor", exact=True).select_option(label="Dr. Kavita Joshi — General Medicine")
    queue = page.get_by_role("region", name="Queue")
    queue.get_by_role("button", name=f"Ask doctor for priority: {token}").click()
    dialog = page.get_by_role("dialog", name=f"Ask the doctor to change {token}'s priority")
    dialog.get_by_label("Reason for the doctor").fill("pregnant, feeling faint")
    dialog.get_by_role("button", name="Send to doctor").click()
    expect(queue.get_by_text("Asked doctor: priority 1")).to_be_visible()
    queue.get_by_role("button", name=f"Move: {token}").click()
    dialog = page.get_by_role("dialog", name=f"Move {token} to another doctor")
    dialog.get_by_label("Move to").select_option(label="Dr. Suresh Pawar")
    dialog.get_by_role("button", name="Move").click()
    expect(queue.get_by_text("Sunanda Pathak")).to_have_count(0)
    page.get_by_label("Doctor", exact=True).select_option(label="Dr. Suresh Pawar — General Medicine")
    expect(queue.get_by_text("Sunanda Pathak")).to_be_visible()
    expect(queue.get_by_text("Moved here")).to_be_visible()


def test_doctor_authorizes_priority_and_sees_their_patient(page: Page, staff_api: Api):
    walk = _walk_in(staff_api, "Dr. Suresh Pawar", "Girish Bhave", "9811100022")
    staff_api.post(f"/queue/sessions/{walk['session_id']}/events", {"type": "resume"})  # end any earlier delay
    staff_api.post(f"/queue/entries/{walk['entry_id']}/priority-requests", {"priority": 3, "reason": "chest pain"})
    sign_in(page, "Doctor")
    expect(page.get_by_role("heading", level=1, name="My queue")).to_be_visible()
    requests = page.get_by_role("region", name="Requests from the front desk")
    expect(requests).to_contain_text("chest pain")
    requests.get_by_role("button", name=f"Approve: {walk['token']}").click()
    expect(requests).to_contain_text("No requests waiting for you.")
    expect(page.get_by_label(f"Priority for {walk['token']}")).to_have_value("3")
    page.get_by_role("button", name="Call next").click()
    room = page.get_by_role("region", name="In the room")
    expect(room).to_contain_text("Girish Bhave")
    room.get_by_role("button", name="Start").click()
    room.get_by_role("button", name="End").click()
    expect(room).not_to_contain_text("Girish Bhave")


def test_coordination_suggests_and_makes_a_balancing_move(page: Page, staff_api: Api):
    for i in range(5):
        _walk_in(staff_api, "Dr. Anand Kulkarni", f"Cardio Walkin {chr(65 + i)}", f"98111000{30 + i}")
    sign_in(page, "Front desk")
    page.get_by_role("link", name="Coordination").click()
    page.get_by_label("Department").select_option(label="Cardiology")
    cardiology = page.get_by_role("region", name="Cardiology").first
    expect(cardiology.get_by_role("row").filter(has_text="Dr. Anand Kulkarni")).to_be_visible()
    move = cardiology.get_by_role("button", name=re.compile(r"^Move W\d\d → Dr. Meera Iyer")).first
    move.click()
    expect(
        page.get_by_role("status").filter(has_text=re.compile(r"moved to Dr. Meera Iyer. New token: T\d\d"))
    ).to_be_visible()


def test_admin_sets_priority_rules(page: Page):
    sign_in(page, "OPD admin")
    page.get_by_role("link", name="Priority rules").click()
    page.get_by_label("Priority for Pregnant").select_option(label="2 — High")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("status").filter(has_text="Saved. Today's queues have been reordered.")).to_be_visible()
    page.reload()
    expect(page.get_by_label("Priority for Pregnant")).to_have_value("2")


def test_doctor_marked_unavailable_informs_patients(page: Page):
    sign_in(page, "Front desk")
    page.get_by_role("link", name="Doctor status").click()
    card = page.get_by_role("region", name="Dr. Meera Iyer")
    card.get_by_role("button", name="Unavailable today").click()
    dialog = page.get_by_role("dialog", name="Unavailable today — Dr. Meera Iyer")
    expect(dialog.get_by_label("Move the patients already waiting to other doctors in the department")).to_be_checked()
    dialog.get_by_role("button", name="Unavailable today").click()
    expect(page.get_by_role("status").filter(has_text="Patients informed")).to_be_visible()
    expect(card).to_contain_text("Not available today")


# --------------------------------------------------------------------------- admin (S8, S9)


def test_dashboard_shows_departments_and_evaluation(page: Page):
    sign_in(page, "OPD admin")
    table = page.get_by_role("table", name="Departments right now")
    expect(table.get_by_role("row")).to_have_count(9)  # header + 8 departments
    expect(page.get_by_role("table", name="Utilization by department")).to_be_visible()
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
        (
            "Patient",
            [
                "Assistant",
                "Book",
                "My appointments",
                "Queue status",
                "Hospital information",
                "Notifications",
                "Profile",
            ],
        ),
        ("Front desk", ["Front desk", "Calendar", "Doctor status", "Coordination", "Patients", "My account"]),
        (
            "OPD admin",
            [
                "Dashboard",
                "Analytics",
                "Hospital setup",
                "Patients",
                "Accounts",
                "Registration form",
                "Priority rules",
                "Coordination",
                "My account",
            ],
        ),
        ("Doctor", ["My queue", "My account"]),
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
        # The bell's name carries the unread count: "Notifications (2 unread)".
        name = re.compile(r"^Notifications") if link == "Notifications" else link
        page.get_by_role("link", name=name, exact=link != "Notifications").click()
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        page.wait_for_load_state("networkidle")
        assert _axe_violations(page) == [], link


def test_library_pages_have_no_serious_accessibility_violations(page: Page):
    page.goto("/library")
    expect(page.locator(".library-item").first).to_be_visible()
    assert _axe_violations(page) == []
    page.goto("/library/policies/join-queue-online")
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    assert _axe_violations(page) == []


def test_kiosk_has_no_serious_accessibility_violations(page: Page):
    sign_in(page, "Front desk")
    page.goto("/kiosk")
    expect(page.get_by_role("heading", name="Self check-in")).to_be_visible()
    assert _axe_violations(page) == []


PHONE_WIDTH = 360


def _overflow(page: Page) -> int:
    # Against the phone's own width: on a mobile viewport window.innerWidth grows with the page.
    return page.evaluate("document.documentElement.scrollWidth") - PHONE_WIDTH


@pytest.mark.parametrize(
    "role, paths",
    [
        ("Front desk", ["/desk", "/calendar", "/doctors", "/coordination", "/patients", "/account"]),
        ("Doctor", ["/my-queue", "/account"]),
        (
            "OPD admin",
            [
                "/admin",
                "/analytics",
                "/hospital-setup",
                "/accounts",
                "/registration-form",
                "/priority-rules",
                "/coordination",
            ],
        ),
    ],
)
def test_staff_screens_fit_a_360_px_phone_in_large_text(phone: Page, role, paths):
    phone.goto("/")
    phone.get_by_label("Large text").check()
    phone.get_by_role("button", name=re.compile(f"^{role}")).click()
    expect(phone.get_by_role("navigation", name="Main")).to_be_visible()
    for path in paths:
        phone.goto(path)
        expect(phone.get_by_role("heading", level=1)).to_be_visible()
        phone.wait_for_load_state("networkidle")
        assert _overflow(phone) <= 0, f"{role} {path}: {_overflow(phone)}px of horizontal scroll"


def test_patient_screens_fit_a_360_px_phone_in_large_text(phone: Page):
    phone.goto("/")
    phone.get_by_label("Large text").check()
    phone.get_by_role("button", name=re.compile("^Patient")).click()
    for link in ("Assistant", "Book", "My appointments", "Queue status", "Profile"):
        phone.get_by_role("link", name=link, exact=True).click()
        expect(phone.get_by_role("heading", level=1)).to_be_visible()
        assert _overflow(phone) <= 0, f"{link}: {_overflow(phone)}px of horizontal scroll"
    # A checkbox counts with its label (the whole label is the tap target).
    targets = phone.evaluate(
        "[...document.querySelectorAll('button, a, input, select')].filter(e => e.offsetParent)"
        ".map(e => (e.closest('label') || e).getBoundingClientRect().height).filter(h => h < 44).length"
    )
    assert targets == 0, f"{targets} tap targets are smaller than 44 px"


# --------------------------------------------------------------------------- hospital setup (adds a department), then reset


def test_admin_sets_up_a_department_and_doctor_that_patients_can_book(page: Page):
    sign_in(page, "OPD admin")
    page.get_by_role("link", name="Hospital setup", exact=True).click()
    details = page.get_by_role("form", name="Hospital details")
    details.get_by_label("Hospital name (English)").fill("Indravani General Hospital and Research Centre")
    details.get_by_role("button", name="Save changes").click()
    expect(details.get_by_role("status")).to_contain_text("Saved.")
    expect(page.locator(".brand-sub").first).to_have_text("Indravani General Hospital and Research Centre")
    details.get_by_label("Hospital name (English)").fill("Indravani General Hospital")
    details.get_by_role("button", name="Save changes").click()
    expect(page.locator(".brand-sub").first).to_have_text("Indravani General Hospital")

    page.get_by_role("button", name="Add department").click()
    dialog = page.get_by_role("dialog", name="Add department")
    dialog.get_by_label("Department").fill("Neurology")
    dialog.get_by_label("Floor").fill("5")
    dialog.get_by_label("OPD opens").fill("10:00")
    dialog.get_by_label("OPD closes").fill("13:00")
    dialog.get_by_label("Other words patients use").fill("brain, nerves")
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_role("status").filter(has_text="Saved Neurology.")).to_be_visible()

    page.get_by_role("button", name="Add doctor: Neurology").click()
    dialog = page.get_by_role("dialog", name="Add doctor")
    dialog.get_by_label("Doctor's name").fill("Dr. Kiran Patkar")
    dialog.get_by_label("Minutes per appointment").fill("20")
    dialog.get_by_label("मराठी").check()
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_role("status").filter(has_text="Added Dr. Kiran Patkar.")).to_contain_text("applies from Tue")
    page.get_by_role("button", name=re.compile("^Sign out")).click()

    sign_in(page, "Patient")
    page.get_by_role("link", name="Book", exact=True).click()
    page.get_by_label("Department").select_option("Neurology")
    page.get_by_role("button", name="Find the best times").click()
    first = page.locator(".slot-card").first
    expect(first).to_contain_text("Dr. Kiran Patkar")
    first.get_by_role("button", name=re.compile("^Choose")).click()
    page.get_by_role("dialog", name="Confirm booking").get_by_role("button", name="Confirm").click()
    expect(page.get_by_role("status").filter(has_text="Booked. Your receipt is ready.")).to_be_visible()
    page.get_by_role("button", name=re.compile("^Sign out")).click()

    # The doctor leaves after today: the patient's visit is moved off and they are told.
    sign_in(page, "OPD admin")
    page.get_by_role("link", name="Hospital setup", exact=True).click()
    page.get_by_role("button", name="Last day: Dr. Kiran Patkar").click()
    dialog = page.get_by_role("dialog", name="Last day")
    dialog.get_by_label("Last OPD day").fill(TODAY)
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_role("status").filter(has_text="Later visits moved off (patients told): 1.")).to_be_visible()
    page.get_by_role("button", name=re.compile("^Sign out")).click()
    sign_in(page, "Patient")
    page.get_by_role("link", name=re.compile("^Notifications")).click()
    expect(page.get_by_text("Dr. Kiran Patkar no longer holds OPD here").first).to_be_visible()


# --------------------------------------------------------------------------- demo reset (TC-17), last


def test_zz_demo_reset_from_the_dashboard(page: Page, admin_api: Api):
    sign_in(page, "OPD admin")
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Reset demo data").click()
    expect(page.get_by_role("status").filter(has_text="Demo data reset.")).to_be_visible(timeout=60000)
    waiting = sum(d["waiting"] for d in admin_api.get("/admin/dashboard")["departments"])
    assert waiting == 0  # the queues created by the earlier tests are gone
