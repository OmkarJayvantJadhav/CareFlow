"""Phase 7E: messages by SMS and e-mail through a provider the hospital chooses, off by default."""

import hashlib
import hmac
import json
import logging
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.main import app
from app.config import get_settings
from app.db.models import AuditLog, MessagingSetting, Patient
from app.safety.pii import decrypt_email
from app.tools import messaging
from app.tools.notify import notify
from tests.conftest import NOW
from tests.test_api import headers, login
from tests.test_patient_data import bearer, register

PROVIDER_SETTINGS = (
    "sms_provider", "email_provider", "demo_mode", "sms_webhook_url", "sms_webhook_secret", "twilio_account_sid",
    "twilio_auth_token", "twilio_from", "smtp_host", "smtp_from", "smtp_port", "smtp_security", "smtp_username",
    "smtp_password",
)  # fmt: skip


@pytest.fixture
def settings():
    """The server's settings, put back after the test (they are cached for the whole process)."""
    s = get_settings()
    saved = {name: getattr(s, name) for name in PROVIDER_SETTINGS}
    yield s
    for name, value in saved.items():
        setattr(s, name, value)
    messaging._recent_tests.clear()


@pytest.fixture
def api(world, frozen_clock, settings):
    yield TestClient(app)
    world.db.rollback()
    world.db.execute(delete(MessagingSetting))  # a setting outlives a demo reset, so not wiped between tests
    world.db.commit()


def turn_on(api, kinds=("reminder_day", "delay", "turn_near", "info"), admin=None):
    admin = admin or headers(login(api, "admin"))
    answer = api.put("/api/v1/admin/messaging", json={"enabled": True, "kinds": list(kinds)}, headers=admin)
    assert answer.status_code == 200, answer.text
    return admin


def message(world, kind="delay", text="Dr. Pawar is running about 20 minutes late.", patient_id=None):
    note = notify(world.db, patient_id or world.asha.patient_id, text, NOW, kind=kind)
    world.db.commit()
    return note


def test_nothing_is_sent_until_a_provider_is_set_up_and_an_admin_turns_it_on(api, world, settings):
    assert message(world).delivery is None  # shown in the app only, as before
    admin = headers(login(api, "admin"))
    view = api.get("/api/v1/admin/messaging", headers=admin).json()
    assert view["enabled"] is False and view["channels"]["sms"] == {
        "provider": "none", "ready": False, "real": False, "problem": "not_configured", "missing": []
    }  # fmt: skip
    refused = api.put("/api/v1/admin/messaging", json={"enabled": True, "kinds": ["delay"]}, headers=admin)
    assert refused.status_code == 409 and "DEPLOY.md" in refused.json()["error"]["message"]
    assert api.get("/api/v1/config").json()["messaging"] == {"sms": False, "email": False}

    settings.sms_provider = "twilio"  # keys missing: not ready
    assert api.get("/api/v1/admin/messaging", headers=admin).json()["channels"]["sms"]["missing"] == [
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"
    ]  # fmt: skip
    settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from = "AC1", "token", "+15005550006"
    demo = api.get("/api/v1/admin/messaging", headers=admin).json()["channels"]["sms"]
    assert demo["ready"] is False and demo["problem"] == "demo_mode"  # the demo's people are invented
    staff = headers(login(api, "staff"))
    assert api.get("/api/v1/admin/messaging", headers=staff).status_code == 403
    assert api.put("/api/v1/admin/messaging", json={"enabled": False, "kinds": []}, headers=staff).status_code == 403


def test_the_log_provider_sends_the_chosen_kinds_with_the_number_masked(api, world, settings, caplog):
    settings.sms_provider = "log"
    turn_on(api)
    assert api.get("/api/v1/config").json()["messaging"] == {"sms": True, "email": False}
    delay = message(world)
    other = message(world, kind="transfer", text="You have been moved to Dr. Rao.")
    assert delay.delivery == "pending" and other.delivery is None  # transfers are not among the kinds sent
    with caplog.at_level(logging.INFO, logger="app.tools.channels"):
        assert messaging.deliver_due(world.db, NOW + timedelta(seconds=20)) == {"sent": 1}
    world.db.refresh(delay)
    assert (delay.delivery, delay.delivered_via, delay.mocked) == ("sent", "sms", True)  # logged, not really sent
    patient = world.db.get(Patient, world.asha.patient_id)
    assert patient.phone_masked in caplog.text and "running about 20 minutes late" in caplog.text
    from app.safety.pii import decrypt_phone

    assert decrypt_phone(patient.phone_encrypted) not in caplog.text
    assert messaging.deliver_due(world.db, NOW + timedelta(minutes=1)) == {}  # sent once

    shown = api.get("/api/v1/me/notifications", headers=headers(login(api, "patient"))).json()["notifications"]
    assert {(n["kind"], n["delivery"], n["delivered_via"]) for n in shown} >= {("delay", "sent", "sms"),
                                                                                ("transfer", None, None)}  # fmt: skip


def test_messages_too_old_or_no_longer_wanted_are_skipped(api, world, settings):
    settings.sms_provider = "log"
    admin = turn_on(api)
    late = message(world, kind="turn_near", text="Your turn is near (token A-12).")
    assert messaging.deliver_due(world.db, NOW + timedelta(minutes=45)) == {"skipped": 1}
    world.db.refresh(late)
    assert late.delivery == "skipped" and late.delivery_note == messaging.NOTES["too_late"]

    waiting = message(world)
    api.put("/api/v1/admin/messaging", json={"enabled": False, "kinds": ["delay"]}, headers=admin)
    assert message(world).delivery is None  # nothing new is queued while sending is off
    messaging.deliver_due(world.db, NOW + timedelta(minutes=1))
    world.db.refresh(waiting)
    assert waiting.delivery == "skipped" and waiting.delivery_note == messaging.NOTES["off"]

    turn_on(api)
    patient = world.db.get(Patient, world.asha.patient_id)
    patient.contact_by = "app"
    world.db.commit()
    quiet = message(world)
    messaging.deliver_due(world.db, NOW + timedelta(minutes=1))
    world.db.refresh(quiet)
    assert quiet.delivery == "skipped" and quiet.delivery_note == messaging.NOTES["app_only"]
    view = api.get("/api/v1/admin/messaging", headers=admin).json()
    assert view["last_7_days"]["skipped"] == 3 and len(view["problems"]) == 3


def test_a_webhook_gateway_gets_a_signed_request_and_failures_are_retried(api, world, settings, monkeypatch):
    admin = headers(login(api, "admin"))  # demo sign-in is only open in demo mode
    settings.demo_mode = False
    settings.sms_provider = "webhook"
    settings.sms_webhook_url, settings.sms_webhook_secret = "https://sms.example.org/send", "shared-secret"
    calls, answers = [], [500, 502, 200]

    def fake_post(url, content, headers, timeout):
        calls.append((url, content, headers))
        return httpx.Response(answers[len(calls) - 1], json={"id": "gw-42"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    turn_on(api, admin=admin)
    note = message(world)
    assert messaging.deliver_due(world.db, NOW) == {"retry": 1}
    world.db.refresh(note)
    assert note.delivery == "pending" and note.delivery_next_at == NOW + timedelta(minutes=2)
    assert "answered 500" in note.delivery_note
    assert messaging.deliver_due(world.db, NOW + timedelta(minutes=1)) == {}  # not yet due again
    assert messaging.deliver_due(world.db, NOW + timedelta(minutes=2)) == {"retry": 1}
    assert messaging.deliver_due(world.db, NOW + timedelta(minutes=7)) == {"sent": 1}
    world.db.refresh(note)
    assert (note.delivery, note.mocked, note.delivery_attempts) == ("sent", False, 3)

    url, content, sent_headers = calls[-1]
    body = json.loads(content)
    patient = world.db.get(Patient, world.asha.patient_id)
    from app.safety.pii import decrypt_phone

    assert body["to"] == "+91" + decrypt_phone(patient.phone_encrypted) and body["reference"] == f"n{note.id}"
    assert body["text"].endswith("Dr. Pawar is running about 20 minutes late.")
    expected = hmac.new(b"shared-secret", f"{sent_headers['X-CareFlow-Timestamp']}.".encode() + content,
                        hashlib.sha256).hexdigest()  # fmt: skip
    assert sent_headers["X-CareFlow-Signature"] == f"sha256={expected}"

    # Three failures: given up, until an admin queues it again.
    answers[:] = [503, 503, 503, 200]
    calls.clear()
    stuck = message(world)
    for minutes in (0, 2, 6):
        messaging.deliver_due(world.db, NOW + timedelta(minutes=minutes))
    world.db.refresh(stuck)
    assert stuck.delivery == "failed" and "answered 503" in stuck.delivery_note
    assert api.get("/api/v1/admin/messaging", headers=admin).json()["last_7_days"]["failed"] == 1
    assert api.post("/api/v1/admin/messaging/retry", headers=admin).json() == {"queued": 1}
    assert messaging.deliver_due(world.db, NOW + timedelta(minutes=8)) == {"sent": 1}


def test_patients_choose_email_or_the_app_only(api, world, settings, monkeypatch):
    settings.sms_provider, settings.email_provider = "log", "log"
    turn_on(api)
    me = bearer(register(api)["token"])
    refused = api.patch("/api/v1/me/profile", json={"contact_by": "email"}, headers=me)
    assert refused.status_code == 400  # no address yet
    assert api.patch("/api/v1/me/profile", json={"email": "not-an-address"}, headers=me).status_code == 400
    changed = api.patch("/api/v1/me/profile", json={"email": "Meena.Rao@Example.ORG", "contact_by": "email"},
                        headers=me).json()  # fmt: skip
    assert changed["email_masked"] == "M***@example.org" and changed["contact_by"] == "email"
    meena = world.db.scalars(select(Patient).where(Patient.name == "Meena Rao")).one()
    assert decrypt_email(meena.email_encrypted) == "Meena.Rao@example.org"
    assert "Meena.Rao" not in (meena.email_encrypted or "")

    sent = []
    monkeypatch.setattr(messaging.channels, "_send_log",
                        lambda channel, to, subject, text: sent.append((channel, to, subject, text)) or "log")  # fmt: skip
    note = message(world, kind="reminder_day", text="आठवण: उद्या 10:00 वाजता", patient_id=meena.id)
    messaging.deliver_due(world.db, NOW)
    world.db.refresh(note)
    assert note.delivered_via == "email"
    channel, to, subject, text = sent[-1]
    assert (channel, to) == ("email", "Meena.Rao@example.org") and subject.startswith("अपॉइंटमेंटची आठवण")
    assert "फक्त ॲपमध्ये" in text  # how to stop, in the patient's language

    # E-mail no longer set up on the server: the message goes by SMS instead.
    settings.email_provider = "none"
    note = message(world, kind="info", text="A slot has opened.", patient_id=meena.id)
    messaging.deliver_due(world.db, NOW)
    world.db.refresh(note)
    assert note.delivered_via == "sms" and sent[-1][1].startswith("+91")

    # Removing the address moves the choice back to SMS; the export holds the address while it is set.
    api.patch("/api/v1/me/profile", json={"email": "meena@example.org"}, headers=me)
    assert api.get("/api/v1/me/export", headers=me).json()["patient"]["email"] == "meena@example.org"
    cleared = api.patch("/api/v1/me/profile", json={"email": ""}, headers=me).json()
    assert cleared["email_masked"] == "" and cleared["contact_by"] == "sms"


def test_staff_record_the_address_and_admins_send_a_test(api, world, settings):
    settings.email_provider = "log"
    staff = headers(login(api, "staff"))
    pid = world.asha.patient_id
    record = api.patch(f"/api/v1/staff/patients/{pid}", json={"email": "asha.k@example.in", "contact_by": "email"},
                       headers=staff)  # fmt: skip
    assert record.status_code == 200, record.text
    assert record.json()["email_masked"] == "a***@example.in" and record.json()["contact_by"] == "email"
    audit = world.db.scalars(select(AuditLog).where(AuditLog.tool == "update_patient")).all()
    assert "asha.k@" not in json.dumps([a.arguments for a in audit] + [a.result for a in audit])

    admin = headers(login(api, "admin"))
    sent = api.post("/api/v1/admin/messaging/test", json={"channel": "email", "to": "it@example.in"}, headers=admin)
    assert sent.status_code == 200 and sent.json()["provider"] == "log"
    logged = world.db.scalars(select(AuditLog).where(AuditLog.tool == "send_test_message")).one()
    assert "it@" not in json.dumps(logged.arguments) and "i***@example.in" in json.dumps(logged.arguments)
    not_ready = api.post("/api/v1/admin/messaging/test", json={"channel": "sms", "to": "9876543210"}, headers=admin)
    assert not_ready.status_code == 409
    bad = api.post("/api/v1/admin/messaging/test", json={"channel": "email", "to": "nobody"}, headers=admin)
    assert bad.status_code == 400
    assert api.post("/api/v1/admin/messaging/test", json={"channel": "email", "to": "it@example.in"},
                    headers=staff).status_code == 403  # fmt: skip
    for _ in range(4):
        api.post("/api/v1/admin/messaging/test", json={"channel": "email", "to": "it@example.in"}, headers=admin)
    limited = api.post("/api/v1/admin/messaging/test", json={"channel": "email", "to": "it@example.in"}, headers=admin)
    assert limited.status_code == 429

    erased = api.post(f"/api/v1/admin/patients/{pid}/erase", json={"reason": "asked"}, headers=admin)
    assert erased.status_code == 200, erased.text
    patient = world.db.get(Patient, pid)
    world.db.refresh(patient)
    assert (patient.email_masked, patient.email_encrypted, patient.contact_by) == ("", None, "app")


def test_smtp_and_twilio_senders(settings, monkeypatch):
    from app.tools import channels

    settings.demo_mode = False
    settings.email_provider, settings.smtp_host, settings.smtp_from = "smtp", "smtp.example.org", "opd@example.org"
    settings.smtp_username, settings.smtp_password, settings.smtp_security = "opd", "pw", "starttls"
    seen = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            seen["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context):
            seen["tls"] = True

        def login(self, user, password):
            seen["login"] = user

        def send_message(self, msg):
            seen["msg"] = msg

    monkeypatch.setattr(channels.smtplib, "SMTP", FakeSMTP)
    ref = channels.send("email", "patient@example.org", "Appointment reminder – City Hospital", "See you tomorrow.")
    assert seen["server"] == ("smtp.example.org", 587) and seen["tls"] and seen["login"] == "opd"
    assert seen["msg"]["To"] == "patient@example.org" and ref.endswith("@example.org>")

    settings.sms_provider = "twilio"
    settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from = "AC1", "tok", "+15005550006"
    posted = {}

    def fake_post(url, data, auth, timeout):
        posted.update(url=url, data=data, auth=auth)
        if data["To"] == "+919000000000":
            return httpx.Response(400, json={"code": 21211, "message": "Invalid 'To' Phone Number"},
                                  request=httpx.Request("POST", url))  # fmt: skip
        return httpx.Response(201, json={"sid": "SM123"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(channels.httpx, "post", fake_post)
    assert channels.send("sms", "+919876543210", "", "Hello") == "SM123"
    assert posted["url"].endswith("/Accounts/AC1/Messages.json") and posted["auth"] == ("AC1", "tok")
    with pytest.raises(channels.DeliveryError, match="21211"):
        channels.send("sms", "+919000000000", "", "Hello")
