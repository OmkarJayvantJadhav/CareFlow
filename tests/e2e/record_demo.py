"""Record the demo video: the real app with the real LLM (Groq, then Gemini), driven by a browser.

    GROQ_API_KEY=... GEMINI_API_KEY=... python -m tests.e2e.record_demo

Writes docs/demo/careflow-demo.webm. The hospital clock starts at Monday 19 October 2026, 08:00 IST
(see tests/e2e/server.py) so the OPD is open; every reply in the video is the model's own.
"""

import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import Page, expect, sync_playwright

from tests.e2e.conftest import Api

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "demo" / "careflow-demo.webm"
PAUSE = 1600  # ms the viewer gets to read each step


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_reply(page: Page) -> None:
    page.wait_for_timeout(300)
    expect(page.locator(".typing")).to_have_count(0, timeout=60000)  # "Working on it…" in any language
    page.wait_for_timeout(PAUSE)


def say(page: Page, text: str) -> None:
    # Selectors that do not depend on the interface language.
    box = page.locator("#chat-input")
    box.click()
    box.press_sequentially(text, delay=25)
    page.locator("form.composer button[type=submit]").click()
    wait_for_reply(page)


def sign_in(page: Page, role: str) -> None:
    if page.get_by_role("button", name=re.compile("^Sign out")).count():
        page.get_by_role("button", name=re.compile("^Sign out")).click()
    page.get_by_role("button", name=re.compile(rf"^{role}")).click()
    page.wait_for_timeout(PAUSE)


def main() -> int:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    server = subprocess.Popen([sys.executable, "-m", "tests.e2e.server", str(port), "--real-llm"], cwd=ROOT)
    try:
        for _ in range(240):
            try:
                if httpx.get(f"{base}/api/v1/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        # Asha has an appointment today and is checked in, so the queue page has something to show.
        staff = Api(base, "staff")
        asha = Api(base, "patient").get("/me")["patient_id"]
        pawar = next(d for d in staff.get("/staff/today")["doctors"] if d["doctor_name"] == "Dr. Suresh Pawar")
        slot = staff.get(f"/doctors/{pawar['doctor_id']}/slots", date="2026-10-19", patient_id=asha)["slots"][-1]
        appt = staff.post("/appointments", {"patient_id": asha, "slot_id": slot["slot_id"], "confirmed": True})
        entry = staff.post(f"/queue/entries/{appt['appointment_id']}/check-in")

        video_dir = ROOT / "docs" / "demo" / "raw"
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(
                base_url=base, viewport={"width": 1280, "height": 720},
                record_video_dir=str(video_dir), record_video_size={"width": 1280, "height": 720},
            )  # fmt: skip
            page = context.new_page()
            page.set_default_timeout(60000)
            page.goto("/")
            page.wait_for_timeout(PAUSE)

            # Patient: book through a confirmation card.
            sign_in(page, "Patient")
            say(page, "Book a Marathi-speaking cardiologist on Saturday")
            for follow_up in ("The first available time, please.", "Yes, book that one."):
                if page.get_by_role("region", name="Please confirm").count():
                    break
                say(page, follow_up)
            card = page.get_by_role("region", name="Please confirm")
            if card.count():
                page.wait_for_timeout(PAUSE)
                card.get_by_role("button", name="Confirm").click()
                wait_for_reply(page)

            # A cited answer from the hospital's documents.
            say(page, "Do I need to fast before a lipid profile?")
            chips = page.get_by_role("button", name=re.compile(r"^\[1\] "))
            if chips.count():
                chips.first.click()
                page.wait_for_timeout(PAUSE)

            # Marathi.
            page.get_by_role("button", name="मराठी").first.click()
            say(page, "माझ्या पुढच्या अपॉइंटमेंट कोणत्या आहेत?")
            page.get_by_role("button", name="English").first.click()

            # Emergency: guidance takes over, nothing is booked.
            say(page, "My father just collapsed and is not breathing")
            page.wait_for_timeout(PAUSE * 2)
            page.get_by_role("button", name=re.compile("not an emergency")).click()

            page.get_by_role("link", name="My appointments").click()
            page.wait_for_timeout(PAUSE * 2)

            # Live queue: staff record a delay, the patient's page updates by itself.
            page.get_by_role("link", name="Queue status").click()
            page.wait_for_timeout(PAUSE * 2)
            staff.post(f"/queue/sessions/{entry['session_id']}/events", {"type": "delay", "minutes": 20})
            page.wait_for_timeout(PAUSE * 2)

            # Front desk.
            sign_in(page, "Front desk")
            page.get_by_label("Doctor").select_option(label="Dr. Kavita Joshi — General Medicine")
            page.wait_for_timeout(PAUSE)
            page.get_by_role("region", name="Bookings today").get_by_role("button", name="Check in").first.click()
            page.wait_for_timeout(PAUSE)
            page.get_by_role("region", name="Queue").get_by_role("button", name="Call next").click()
            page.wait_for_timeout(PAUSE * 2)

            # Admin: dashboard and analytics with the generated SQL.
            sign_in(page, "OPD admin")
            page.wait_for_timeout(PAUSE * 2)
            page.get_by_role("link", name="Analytics").click()
            page.get_by_label("Analytics").fill("Which department has the most appointments today?")
            page.get_by_role("button", name="Ask").click()
            expect(page.get_by_role("button", name="Ask")).to_be_enabled(timeout=90000)
            page.wait_for_timeout(PAUSE * 2)
            page.get_by_label("Analytics").fill("Delete all no-shows from last week")
            page.get_by_role("button", name="Ask").click()
            page.wait_for_timeout(PAUSE * 2)

            video = page.video.path()
            context.close()
            browser.close()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(video, OUT)
        shutil.rmtree(video_dir, ignore_errors=True)
        print(f"{OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
        return 0
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
