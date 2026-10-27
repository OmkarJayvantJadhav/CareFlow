"""Record the README's feature GIFs: the real app (tests/e2e/server.py) driven by a browser.

    cd ui && npm run build && cd .. && python -m tests.e2e.record_gifs [name ...]

Writes docs/gifs/<name>.gif (ffmpeg is needed). The hospital clock starts at Monday 19 October 2026,
08:00 IST, so the OPD is open; the chat uses the test server's rule-based stand-in for the LLM.
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from playwright.sync_api import Page, expect, sync_playwright

from tests.e2e.conftest import Api

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "gifs"
TODAY = "2026-10-19"
DESKTOP = {"width": 1152, "height": 700}
PHONE = {"width": 390, "height": 760}

# A visible pointer: recordings do not show the real one.
CURSOR = """
addEventListener('DOMContentLoaded', () => {
  const dot = document.createElement('div');
  dot.style.cssText = 'position:fixed;left:-40px;top:-40px;width:22px;height:22px;margin:-11px 0 0 -11px;' +
    'border-radius:50%;background:rgba(15,118,110,.35);border:2px solid #0f766e;z-index:2147483647;' +
    'pointer-events:none;transition:transform .12s';
  document.documentElement.appendChild(dot);
  addEventListener('mousemove', (e) => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => { dot.style.transform = 'scale(.6)'; }, true);
  addEventListener('mouseup', () => { dot.style.transform = ''; }, true);
});
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, hospital: bool = False):
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        args = [sys.executable, "-m", "tests.e2e.server", str(self.port)] + (["--hospital"] if hospital else [])
        # As on the live sites: no "fictional" labels; the hospital site links to the demo.
        env = {**os.environ, "DEMO_NOTICE": "false", "DEMO_SITE_URL": "https://careflow-zy87.onrender.com"}
        self.proc = subprocess.Popen(args, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{self.url}/api/v1/health", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.5)
        self.stop()
        raise SystemExit("the test server did not start")

    def stop(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=20)


class Clip:
    """One recording; ``start()`` marks where the GIF begins (after sign-in and set-up)."""

    def __init__(self, page: Page):
        self.page = page
        self.t0 = time.monotonic()
        self.begin = 0.0

    def start(self) -> None:
        self.page.wait_for_timeout(400)
        self.begin = time.monotonic() - self.t0

    def pause(self, ms: int = 1300) -> None:
        self.page.wait_for_timeout(ms)

    def type(self, locator, text: str) -> None:
        locator.click()
        locator.press_sequentially(text, delay=28)

    def scroll(self, pixels: int, steps: int = 6) -> None:
        for _ in range(steps):
            self.page.mouse.wheel(0, pixels / steps)
            self.page.wait_for_timeout(120)


def to_gif(video: Path, begin: float, out: Path, width: int) -> None:
    graph = (
        f"fps=8,scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"
    )
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{begin:.2f}", "-i", str(video), "-vf", graph, str(out)]
    subprocess.run(cmd, check=True)


def record(browser, base_url: str, name: str, scenario: Callable[[Clip], None], phone: bool = False) -> None:
    viewport = PHONE if phone else DESKTOP
    with tempfile.TemporaryDirectory() as tmp:
        context = browser.new_context(
            base_url=base_url,
            viewport=viewport,
            is_mobile=phone,
            has_touch=phone,
            record_video_dir=tmp,
            record_video_size=viewport,
        )
        context.add_init_script(CURSOR)
        page = context.new_page()
        page.set_default_timeout(20000)
        clip = Clip(page)
        scenario(clip)
        clip.pause(1800)
        video = Path(page.video.path())
        context.close()
        to_gif(video, clip.begin, OUT / f"{name}.gif", 360 if phone else 960)
    size = (OUT / f"{name}.gif").stat().st_size / 1e6
    print(f"{name}.gif  {size:.1f} MB")


# --------------------------------------------------------------------------- helpers


def sign_in(page: Page, role_label: str) -> None:
    page.goto("/")
    page.get_by_role("button", name=re.compile(rf"^{role_label}")).click()
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()


def send(clip: Clip, text: str) -> None:
    clip.type(clip.page.get_by_label("Type your message…"), text)
    clip.page.get_by_role("button", name="Send").click()


def doctor_id(staff: Api, name: str) -> int:
    return next(d for d in staff.get("/staff/today")["doctors"] if d["doctor_name"] == name)["doctor_id"]


def book_asha_today(base_url: str, staff: Api, doctor: str, first: bool = True) -> dict:
    patient = Api(base_url, "patient")
    asha = patient.get("/me")["patient_id"]
    slots = staff.get(f"/doctors/{doctor_id(staff, doctor)}/slots", date=TODAY, patient_id=asha)["slots"]
    slot = slots[0] if first else slots[-1]
    appt = staff.post("/appointments", {"patient_id": asha, "slot_id": slot["slot_id"], "confirmed": True})
    return {**appt, "reference": patient.get(f"/appointments/{appt['appointment_id']}/receipt")["reference"]}


def walk_in(staff: Api, doctor: str, name: str, phone: str) -> dict:
    body = {"doctor_id": doctor_id(staff, doctor), "name": name, "birth_year": 1961, "phone": phone}
    return staff.post("/queue/walk-ins", body)


# --------------------------------------------------------------------------- the hospital's own site


def homepage(clip: Clip) -> None:
    page = clip.page
    page.goto("/")
    expect(page.locator(".home-grid").first).to_be_visible()
    clip.start()
    clip.pause(1500)
    for _ in range(6):
        page.mouse.wheel(0, 560)  # in jumps: a smooth scroll makes a large GIF
        clip.pause(1300)
    page.mouse.wheel(0, -20000)
    clip.pause(600)
    page.locator(".home-actions").get_by_role("link", name="Book an appointment").click()
    expect(page.get_by_role("form", name="Log in")).to_be_visible()


# --------------------------------------------------------------------------- patients and caregivers


def chat_booking(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "Patient")
    clip.start()
    send(clip, "Book a Marathi-speaking cardiologist on Saturday")
    card = page.get_by_role("region", name="Please confirm")
    expect(card).to_be_visible()
    clip.pause(2200)
    card.get_by_role("button", name="Confirm").click()
    expect(page.locator(".msg.assistant").last).to_contain_text("Done.")
    clip.pause()
    page.get_by_role("link", name="My appointments").click()
    expect(page.locator("article").filter(has_text="Dr. Anand Kulkarni").first).to_be_visible()


def cited_answer(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "Patient")
    clip.start()
    send(clip, "Do I need to fast before a lipid profile?")
    chip = page.get_by_role("button", name=re.compile(r"^\[1\] "))
    expect(chip).to_be_visible()
    clip.pause()
    chip.click()
    expect(page.locator(".source-detail")).to_be_visible()


def emergency(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "Patient")
    clip.start()
    send(clip, "My father collapsed and is not breathing")
    expect(page.get_by_role("alert")).to_contain_text("Call 112 or 108 now")
    clip.pause(2500)


def book_and_receipt(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "Patient")
    clip.start()
    page.get_by_role("link", name="Book", exact=True).click()
    page.get_by_label("Department").select_option("ENT")
    page.get_by_label("From").fill("2026-10-22")
    clip.pause(500)
    page.get_by_role("button", name="Find the best times").click()
    expect(page.locator(".slot-card").first).to_be_visible()
    clip.pause(2200)
    page.locator(".slot-card").first.get_by_role("button", name=re.compile("^Choose")).click()
    clip.pause()
    page.get_by_role("dialog", name="Confirm booking").get_by_role("button", name="Confirm").click()
    expect(page.get_by_role("status").filter(has_text="Booked. Your receipt is ready.")).to_be_visible()
    clip.pause()
    page.get_by_role("link", name="View receipt").click()
    expect(page.get_by_role("article", name="Appointment receipt")).to_be_visible()


def check_in_and_live_queue(clip: Clip, base_url: str) -> None:
    page = clip.page
    staff = Api(base_url, "staff")
    book_asha_today(base_url, staff, "Dr. Nitin Chavan")
    sign_in(page, "Patient")
    clip.start()
    page.get_by_role("navigation", name="Main").get_by_role("link", name="My appointments").click()
    card = page.locator("article").filter(has_text="Dr. Nitin Chavan")
    card.get_by_role("button", name="Check in now").click()
    clip.pause(800)
    page.get_by_role("dialog", name="Check in now").get_by_role("button", name="Check in").click()
    expect(page.get_by_role("status").filter(has_text=re.compile(r"Checked in · token B\d\d"))).to_be_visible()
    clip.pause()
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Queue status").click()
    queue = page.locator("section.card").filter(has_text="Dr. Nitin Chavan")
    expect(queue.get_by_text("Live")).to_be_visible()
    clip.pause(1800)
    session = next(d for d in staff.get("/staff/today")["doctors"] if d["doctor_name"] == "Dr. Nitin Chavan")
    staff.post(f"/queue/sessions/{session['session_id']}/events", {"type": "delay", "minutes": 20})
    expect(queue).to_contain_text("Running late (20 min)")


def join_queue_online(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "Caregiver")
    clip.start()
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Queue status").click()
    join = page.get_by_role("region", name="Join a queue online")
    join.get_by_label("Department").select_option(label="ENT")
    clip.pause()
    join.get_by_role("button", name="Join queue: Dr. Snehal Gokhale").click()
    expect(page.locator("section.token-card").filter(has_text="Dr. Snehal Gokhale")).to_contain_text("V01")
    clip.pause(1500)


def hospital_information(clip: Clip) -> None:
    page = clip.page
    page.goto("/")
    clip.start()
    page.get_by_role("link", name="Hospital information").click()
    clip.pause()
    clip.type(page.get_by_label("Search the documents"), "lipid fasting")
    page.get_by_role("button", name="Search").click()
    clip.pause()
    page.get_by_role("link", name=re.compile("^Lipid profile")).click()
    clip.pause(1500)
    page.get_by_role("group", name="Read in").get_by_role("button", name="हिन्दी").click()
    clip.pause(1500)
    page.get_by_role("group", name="पढ़ें", exact=False).get_by_role("button", name="मराठी").click()


def three_languages(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "Patient")
    page.get_by_role("link", name="My appointments").click()
    clip.start()
    page.get_by_role("button", name="हिन्दी").first.click()
    clip.pause(1800)
    page.get_by_role("button", name="मराठी").first.click()
    clip.pause(1800)
    page.get_by_role("link", name=re.compile("^बुक")).first.click()
    clip.pause(1500)
    page.get_by_role("button", name="English").first.click()


def profile_and_privacy(clip: Clip, base_url: str) -> None:
    page = clip.page
    Api(base_url, "caregiver").post("/caregiver/requests", {"patient_username": "asha"})
    sign_in(page, "Patient")
    clip.start()
    page.get_by_role("link", name="Profile").click()
    clip.pause()
    requests = page.get_by_role("list", name="Requests waiting for your answer")
    requests.scroll_into_view_if_needed()
    clip.pause()
    requests.get_by_role("button", name="Approve").click()
    expect(page.get_by_role("list", name="People who can manage your appointments")).to_contain_text("Rajan")
    clip.pause()
    clip.scroll(900)


def phone(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "Patient")
    clip.start()
    send(clip, "Can I join the dermatology queue today? I have no appointment.")
    card = page.get_by_role("region", name="Please confirm")
    expect(card).to_be_visible()
    clip.pause()
    card.get_by_role("button", name="Confirm").click()
    expect(page.locator(".msg.assistant").last).to_contain_text(re.compile(r"token V\d\d"))
    clip.pause()
    page.get_by_role("link", name="Queue status").click()
    expect(page.locator("section.token-card").first).to_be_visible()
    clip.pause(1500)
    page.get_by_role("link", name="My appointments").click()
    clip.pause(1500)


# --------------------------------------------------------------------------- front desk and doctors


def front_desk(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "Front desk")
    clip.start()
    page.get_by_label("Doctor", exact=True).select_option(label="Dr. Kavita Joshi — General Medicine")
    clip.pause()
    bookings = page.get_by_role("region", name="Bookings today")
    bookings.get_by_role("button", name="Check in").first.click()
    expect(bookings.get_by_text(re.compile(r"Checked in B\d\d")).first).to_be_visible()
    clip.pause()
    walk = page.get_by_role("region", name="Register walk-in")
    walk.scroll_into_view_if_needed()
    clip.type(walk.get_by_label("Patient name"), "Ramesh Kale")
    clip.type(walk.get_by_label("Birth year"), "1979")
    clip.type(walk.get_by_label(re.compile("^Mobile number")), "9876543210")
    walk.get_by_role("button", name="Register").click()
    queue = page.get_by_role("region", name="Queue")
    expect(queue.get_by_text("Ramesh Kale")).to_be_visible()
    queue.first.scroll_into_view_if_needed()
    clip.pause()
    queue.get_by_role("button", name="Call next").click()
    expect(queue.get_by_text("Called — please go in")).to_be_visible()


def kiosk(clip: Clip, base_url: str) -> None:
    page = clip.page
    appt = book_asha_today(base_url, Api(base_url, "staff"), "Dr. Sunita Patwardhan", first=False)
    sign_in(page, "Front desk")
    page.goto("/kiosk")
    expect(page.get_by_role("heading", name="Self check-in")).to_be_visible()
    clip.start()
    clip.type(page.get_by_label("Type the code from your appointment receipt"), appt["reference"])
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_text("Welcome, Asha")).to_be_visible()
    clip.pause()
    page.get_by_role("button", name="Check in").click()
    expect(page.get_by_role("status")).to_contain_text("You are checked in")
    clip.pause(2000)


def doctor_queue(clip: Clip, base_url: str) -> None:
    page = clip.page
    staff = Api(base_url, "staff")
    walk = walk_in(staff, "Dr. Suresh Pawar", "Girish Bhave", "9811100022")
    staff.post(f"/queue/entries/{walk['entry_id']}/priority-requests", {"priority": 3, "reason": "chest pain"})
    sign_in(page, "Doctor")
    clip.start()
    requests = page.get_by_role("region", name="Requests from the front desk")
    expect(requests).to_contain_text("chest pain")
    clip.pause()
    requests.get_by_role("button", name=f"Approve: {walk['token']}").click()
    clip.pause()
    page.get_by_role("button", name="Call next").click()
    room = page.get_by_role("region", name="In the room")
    expect(room).to_contain_text("Girish Bhave")
    clip.pause()
    room.get_by_role("button", name="Start").click()
    clip.pause()
    room.get_by_role("button", name="End").click()
    expect(room).not_to_contain_text("Girish Bhave")


def coordination(clip: Clip, base_url: str) -> None:
    page = clip.page
    staff = Api(base_url, "staff")
    for i in range(5):
        walk_in(staff, "Dr. Anand Kulkarni", f"Cardio Walk-in {chr(65 + i)}", f"98111000{30 + i}")
    sign_in(page, "Front desk")
    clip.start()
    page.get_by_role("link", name="Coordination").click()
    page.get_by_label("Department").select_option(label="Cardiology")
    clip.pause(2200)
    page.get_by_role("region", name="Cardiology").first.get_by_role(
        "button", name=re.compile(r"^Move W\d\d → Dr. Meera Iyer")
    ).first.click()
    expect(page.get_by_role("status").filter(has_text="moved to Dr. Meera Iyer")).to_be_visible()


# --------------------------------------------------------------------------- administrators


def dashboard_and_analytics(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "OPD admin")
    clip.start()
    clip.pause(1500)
    clip.scroll(700)
    clip.pause()
    page.get_by_role("link", name="Analytics").click()
    clip.type(page.get_by_label("Analytics"), "How many appointments per department?")
    page.get_by_role("button", name="Ask").click()
    expect(page.get_by_text("Generated SQL")).to_be_visible()
    clip.pause(1500)
    clip.scroll(500)


def hospital_setup(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "OPD admin")
    clip.start()
    page.get_by_role("link", name="Hospital setup", exact=True).click()
    clip.pause()
    page.get_by_role("button", name="Add department").click()
    dialog = page.get_by_role("dialog", name="Add department")
    clip.type(dialog.get_by_label("Department"), "Neurology")
    dialog.get_by_label("Floor").fill("5")
    dialog.get_by_label("OPD opens").fill("10:00")
    dialog.get_by_label("OPD closes").fill("13:00")
    clip.pause(600)
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_role("status").filter(has_text="Saved Neurology.")).to_be_visible()
    page.get_by_role("button", name="Add doctor: Neurology").click()
    dialog = page.get_by_role("dialog", name="Add doctor")
    clip.type(dialog.get_by_label("Doctor's name"), "Dr. Kiran Patkar")
    dialog.get_by_label("मराठी").check()
    clip.pause(600)
    dialog.get_by_role("button", name="Save").click()
    expect(page.get_by_role("status").filter(has_text="Added Dr. Kiran Patkar.")).to_be_visible()


def documents(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "OPD admin")
    clip.start()
    page.get_by_role("link", name="Documents", exact=True).click()
    clip.type(page.get_by_label("Title contains"), "cancellation")
    page.get_by_role("button", name="Search", exact=True).click()
    clip.pause()
    page.get_by_role("button", name=re.compile("^Cancellation policy")).click()
    editor = page.get_by_role("form", name="Edit document")
    expect(editor).to_be_visible()
    clip.pause(1500)
    page.locator("details.placeholders summary").click()
    clip.pause(1500)
    editor.get_by_label("Text").scroll_into_view_if_needed()


def accounts(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "OPD admin")
    clip.start()
    page.get_by_role("link", name="Accounts", exact=True).click()
    clip.pause()
    page.get_by_role("button", name="New account").click()
    dialog = page.get_by_role("dialog", name="New account")
    clip.type(dialog.get_by_label("Full name"), "Kavya Shetty")
    clip.type(dialog.get_by_label("Username"), "kavya.shetty")
    dialog.get_by_label("Role").select_option("staff")
    clip.pause(600)
    dialog.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("dialog", name="Temporary password")).to_be_visible()
    clip.pause(2200)
    page.get_by_role("dialog", name="Temporary password").get_by_role("button", name="Done").click()


def messaging(clip: Clip) -> None:
    page = clip.page
    sign_in(page, "OPD admin")
    clip.start()
    page.get_by_role("link", name="SMS and e-mail", exact=True).click()
    clip.pause()
    sending = page.get_by_role("form", name="Sending")
    sending.get_by_label("Send messages by SMS and e-mail").check()
    clip.pause(600)
    sending.get_by_role("button", name="Save changes").click()
    expect(sending.get_by_role("status")).to_be_visible()
    test = page.get_by_role("form", name="Send a test message")
    test.scroll_into_view_if_needed()
    clip.type(test.get_by_label("Mobile number"), "98765 43210")
    test.get_by_role("button", name="Send test").click()
    expect(test.get_by_role("status")).to_contain_text("Test sent to +91")
    clip.pause()
    sending.scroll_into_view_if_needed()
    sending.get_by_label("Send messages by SMS and e-mail").uncheck()
    sending.get_by_role("button", name="Save changes").click()


DEMO = {
    "chat-booking": chat_booking,
    "cited-answer": cited_answer,
    "emergency": emergency,
    "book-and-receipt": book_and_receipt,
    "check-in-live-queue": check_in_and_live_queue,
    "join-queue-online": join_queue_online,
    "hospital-information": hospital_information,
    "languages": three_languages,
    "profile-privacy": profile_and_privacy,
    "front-desk": front_desk,
    "kiosk": kiosk,
    "doctor-queue": doctor_queue,
    "coordination": coordination,
    "dashboard-analytics": dashboard_and_analytics,
    "hospital-setup": hospital_setup,
    "documents": documents,
    "accounts": accounts,
    "messaging": messaging,
}
NEEDS_URL = {check_in_and_live_queue, profile_and_privacy, kiosk, doctor_queue, coordination}


def main(names: list[str]) -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is needed")
    if not (ROOT / "ui" / "dist" / "index.html").exists():
        raise SystemExit("Build the UI first: cd ui && npm ci && npm run build")
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = set(names) or {*DEMO, "homepage", "phone"}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        if "homepage" in wanted:
            server = Server(hospital=True)
            try:
                record(browser, server.url, "homepage", homepage)
            finally:
                server.stop()
        server = Server()
        try:
            if "phone" in wanted:  # first: Asha must not be in a queue yet
                record(browser, server.url, "phone", phone, phone=True)
            for name, scenario in DEMO.items():
                if name in wanted:
                    run = (lambda c, s=scenario: s(c, server.url)) if scenario in NEEDS_URL else scenario
                    record(browser, server.url, name, run)
        finally:
            server.stop()
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1:])
