"""The 130 agent scenarios (docs §14.1, plus 10 for the queue actions added in phase 6), checked against the
seeded evaluation world.

    python -m eval.scenarios            # validate and write eval/datasets/agent_scenarios.jsonl

Each scenario has a persona and hidden goal for the simulated patient, a first
message, optional setup (existing appointments, a fully booked day, a doctor who
became unavailable, a queue), the writes that must happen - as constraints, not
exact slots - and facts the replies must contain. The clock is Monday 19 October
2026, 08:00 (``EVAL_NOW``). Validation checks that every expected booking is
possible in the seeded data (and that "full" days really are full after setup).
"""

import json
import sys
from datetime import date, time, timedelta
from pathlib import Path

from sqlalchemy import select

from app.db.models import Appointment, Doctor, Slot
from app.timeutil import at, to_ist
from eval.common import EVAL_NOW, isolated, prepare_world

OUT = Path("eval/datasets/agent_scenarios.jsonl")
D = {d: date(2026, 10, d) for d in range(19, 32)}  # 19 = today (Monday)
ASHA, VINAYAK = "Asha Patil", "Vinayak Deshmukh"
YES = {"en": "yes", "hi": "हाँ", "mr": "हो"}
NO = {"en": "No, that's not what I want.", "hi": "नहीं, मुझे यह नहीं चाहिए।", "mr": "नाही, मला हे नको आहे."}
LANG_NAME = {"en": "English", "hi": "Hindi (Devanagari script)", "mr": "Marathi (Devanagari script)"}
CARDIO = ["Dr. Anand Kulkarni", "Dr. Farah Siddiqui", "Dr. Meera Iyer"]
SCENARIOS: list[dict] = []


def iso(d: date) -> str:
    return d.isoformat()


def slot_spec(doctors, dates, t_from="00:00", t_to="23:59", patient=ASHA) -> dict:
    return {"patient": patient, "doctors": list(doctors), "dates": [iso(d) for d in dates], "time_from": t_from,
            "time_to": t_to}  # fmt: skip


def add(sid, family, language, first, goal, expect_writes=(), actor="asha", setup=(), mention=(), forbid=(),
        card_rules=(), facts="", max_turns=7):  # fmt: skip
    who = {"asha": "Asha Patil, 34, a patient booking for herself",
           "rajan": "Rajan Deshmukh, caring for his father Vinayak Deshmukh (verified caregiver)",
           "sunil": "Sunil More, son-in-law of Vinayak Deshmukh"}[actor]  # fmt: skip
    SCENARIOS.append(
        {
            "id": sid,
            "family": family,
            "language": language,
            "actor": actor,
            "persona": f"You are {who}. You write short, informal messages in {LANG_NAME[language]}.",
            "goal": goal,
            "facts": facts,
            "first_message": first,
            "setup": list(setup),
            "expect_writes": list(expect_writes),
            "mention": list(mention),
            "forbid": list(forbid),
            "card_rules": list(card_rules),
            "yes": YES[language],
            "no": NO[language],
            "max_turns": max_turns,
        }
    )


def book(**spec) -> dict:
    return {"tool": ["book_appointment"], **spec}


def existing(ref, doctor, day, hhmm, patient=ASHA) -> dict:
    return {"op": "book", "ref": ref, "patient": patient, "doctor": doctor, "date": iso(day), "time": hhmm}


# --------------------------------------------------------------------------- 1. book (25)

B = "book"
add(
    "book-01",
    B,
    "en",
    "I need a Marathi-speaking cardiologist on Saturday.",
    "Book yourself with a cardiologist who speaks Marathi on Saturday 24 October; any time is fine.",
    [book(**slot_spec(["Dr. Anand Kulkarni"], [D[24]]))],
)
add(
    "book-02",
    B,
    "en",
    "Can I see Dr. Suresh Pawar tomorrow morning, before 10?",
    "Book Dr. Suresh Pawar on Tuesday 20 October with a start time before 10:00.",
    [book(**slot_spec(["Dr. Suresh Pawar"], [D[20]], "09:00", "09:59"))],
)
add(
    "book-03",
    B,
    "en",
    "Book me with an ENT doctor on Thursday please.",
    "Book any ENT doctor on Thursday 22 October; any time.",
    [book(**slot_spec(["Dr. Rohit Malhotra"], [D[22]]))],
)
add(
    "book-04",
    B,
    "en",
    "I want a skin doctor who speaks Marathi, Saturday if possible.",
    "Book a Marathi-speaking dermatologist on Saturday 24 October; any time.",
    [book(**slot_spec(["Dr. Prakash Shinde"], [D[24]]))],
)
add(
    "book-05",
    B,
    "en",
    "What's the earliest I can get an eye check with Dr. Lakshmi Rao? Book it.",
    "Book Dr. Lakshmi Rao on her earliest available day (Tuesday 20 October); any time that day.",
    [book(**slot_spec(["Dr. Lakshmi Rao"], [D[20]]))],
)
add(
    "book-06",
    B,
    "en",
    "Please book a gynaecologist on Wednesday after 11 am.",
    "Book a gynaecologist on Wednesday 21 October starting at 11:00 or later.",
    [book(**slot_spec(["Dr. Ayesha Khan"], [D[21]], "11:00", "23:59"))],
)
add(
    "book-07",
    B,
    "en",
    "My knee hurts, I need an orthopaedic doctor on Friday morning.",
    "Book an orthopaedic doctor on Friday 23 October, starting before 12:00.",
    [book(**slot_spec(["Dr. Vikram Bhosale"], [D[23]], "00:00", "11:59"))],
)
add(
    "book-08",
    B,
    "en",
    "Book Dr. Farah Siddiqui on Tuesday the 27th at 10:30 or close to it.",
    "Book Dr. Farah Siddiqui on Tuesday 27 October between 10:00 and 11:00.",
    [book(**slot_spec(["Dr. Farah Siddiqui"], [D[27]], "10:00", "11:00"))],
)
add(
    "book-09",
    B,
    "en",
    "I'd like to see a general physician today.",
    "Book any General Medicine doctor today (Monday 19 October); any time.",
    [book(**slot_spec(["Dr. Suresh Pawar", "Dr. Kavita Joshi"], [D[19]]))],
)
add(
    "book-10",
    B,
    "en",
    "Hindi-speaking general medicine doctor on Tuesday 27 October please.",
    "Book a Hindi-speaking General Medicine doctor on Tuesday 27 October; any time.",
    [book(**slot_spec(["Dr. Suresh Pawar", "Dr. Kavita Joshi", "Dr. Imran Shaikh"], [D[27]]))],
)
add(
    "book-11",
    B,
    "en",
    "Book Dr. Nitin Chavan for an eye check on Wednesday.",
    "Book Dr. Nitin Chavan on Wednesday 21 October; any time.",
    [book(**slot_spec(["Dr. Nitin Chavan"], [D[21]]))],
)
add(
    "book-12",
    B,
    "en",
    "Can I get Dr. Meera Iyer on Monday the 26th, her first free slot?",
    "Book Dr. Meera Iyer on Monday 26 October at her first free time that day.",
    [book(**slot_spec(["Dr. Meera Iyer"], [D[26]], "first", "first"))],
)
add(
    "book-13",
    B,
    "en",
    "ENT appointment with Dr. Snehal Gokhale, any day this week after Wednesday.",
    "Book Dr. Snehal Gokhale on a day this week after Wednesday (that is Friday 23 October); any time.",
    [book(**slot_spec(["Dr. Snehal Gokhale"], [D[23]]))],
)
add(
    "book-14",
    B,
    "en",
    "I need Dr. Prakash Shinde tomorrow.",
    "Book Dr. Prakash Shinde on Tuesday 20 October; any time.",
    [book(**slot_spec(["Dr. Prakash Shinde"], [D[20]]))],
)
add(
    "book-15",
    B,
    "en",
    "Any cardiologist on Thursday the 22nd works for me.",
    "Book any cardiologist on Thursday 22 October; any time.",
    [book(**slot_spec(["Dr. Farah Siddiqui", "Dr. Meera Iyer"], [D[22]]))],
)
add(
    "book-16",
    B,
    "en",
    "Book Dr. Vikram Bhosale this Saturday, 12 o'clock or later.",
    "Book Dr. Vikram Bhosale on Saturday 24 October starting at 12:00 or later.",
    [book(**slot_spec(["Dr. Vikram Bhosale"], [D[24]], "12:00", "23:59"))],
)
add(
    "book-17",
    B,
    "en",
    "hi, need a heart doctor wednesday, the one who speaks marathi",
    "Book the Marathi-speaking cardiologist on Wednesday 21 October; any time.",
    [book(**slot_spec(["Dr. Anand Kulkarni"], [D[21]]))],
)
add(
    "book-18",
    B,
    "hi",
    "मुझे शनिवार को हिंदी बोलने वाले हृदय रोग विशेषज्ञ से मिलना है।",
    "Book a Hindi-speaking cardiologist on Saturday 24 October; any time.",
    [book(**slot_spec(["Dr. Anand Kulkarni"], [D[24]]))],
)
add(
    "book-19",
    B,
    "hi",
    "डॉ. इमरान शेख के साथ गुरुवार को सुबह 10 बजे से पहले का अपॉइंटमेंट चाहिए।",
    "Book Dr. Imran Shaikh on Thursday 22 October starting before 10:00.",
    [book(**slot_spec(["Dr. Imran Shaikh"], [D[22]], "00:00", "09:59"))],
)
add(
    "book-20",
    B,
    "hi",
    "कल आंखों के डॉक्टर को दिखाना है, अपॉइंटमेंट बुक कर दीजिए।",
    "Book an eye doctor (ophthalmologist) on Tuesday 20 October; any time.",
    [book(**slot_spec(["Dr. Lakshmi Rao"], [D[20]]))],
)
add(
    "book-21",
    B,
    "hi",
    "शुक्रवार 23 तारीख को स्त्री रोग विशेषज्ञ का अपॉइंटमेंट चाहिए।",
    "Book a gynaecologist on Friday 23 October; any time.",
    [book(**slot_spec(["Dr. Sunita Patwardhan"], [D[23]]))],
)
add(
    "book-22",
    B,
    "mr",
    "मला शनिवारी मराठी बोलणारे हृदयरोग तज्ज्ञ हवे आहेत.",
    "Book a Marathi-speaking cardiologist on Saturday 24 October; any time.",
    [book(**slot_spec(["Dr. Anand Kulkarni"], [D[24]]))],
)
add(
    "book-23",
    B,
    "mr",
    "डॉ. सुरेश पवार यांची उद्या सकाळी ११ च्या आधीची वेळ द्या.",
    "Book Dr. Suresh Pawar on Tuesday 20 October starting before 11:00.",
    [book(**slot_spec(["Dr. Suresh Pawar"], [D[20]], "00:00", "10:59"))],
)
add(
    "book-24",
    B,
    "mr",
    "बुधवारी कान-नाक-घसा डॉक्टरांची अपॉइंटमेंट हवी आहे.",
    "Book an ENT doctor on Wednesday 21 October; any time.",
    [book(**slot_spec(["Dr. Snehal Gokhale"], [D[21]]))],
)
add(
    "book-25",
    B,
    "mr",
    "डॉ. सुनीता पटवर्धन यांच्याकडे सोमवार २६ तारखेला वेळ हवी आहे.",
    "Book Dr. Sunita Patwardhan on Monday 26 October; any time.",
    [book(**slot_spec(["Dr. Sunita Patwardhan"], [D[26]]))],
)

# --------------------------------------------------------------------------- 2. reschedule (15)

R = "reschedule"


def resched(ref="existing", **spec) -> dict:
    return {"tool": ["reschedule_appointment"], "appointment": f"${ref}", **spec}


KEEP = "If the assistant says the appointment cannot be moved, accept that and keep it; do not cancel it."
for sid, lang, first, ex, target, goal in [
    ("resched-01", "en", "Please move my appointment with Dr. Pawar to Friday.",
     ("Dr. Suresh Pawar", D[21], "10:00"), slot_spec(["Dr. Suresh Pawar"], [D[23]]), "to Friday 23 October, any time"),
    ("resched-02", "en", "Can you shift my cardiology appointment to Saturday?",
     ("Dr. Anand Kulkarni", D[21], "09:30"), slot_spec(["Dr. Anand Kulkarni"], [D[24]]), "to Saturday 24 October, any time"),
    ("resched-03", "en", "Move my ENT appointment to Monday the 26th, morning please.",
     ("Dr. Snehal Gokhale", D[23], "10:00"), slot_spec(["Dr. Snehal Gokhale"], [D[26]]), "to Monday 26 October, any time"),
    ("resched-04", "en", "Can I change tomorrow's appointment to Thursday, around 12?",
     ("Dr. Kavita Joshi", D[20], "11:00"), slot_spec(["Dr. Kavita Joshi"], [D[22]], "11:30", "12:30"),
     "to Thursday 22 October between 11:30 and 12:30"),
    ("resched-05", "en", "I need a later time on the same day for my eye appointment, after 11 please.",
     ("Dr. Nitin Chavan", D[21], "09:20"), slot_spec(["Dr. Nitin Chavan"], [D[21]], "11:00", "23:59"),
     "to a time at 11:00 or later on the same day (Wednesday 21 October)"),
    ("resched-06", "en", "Push my appointment with Dr. Siddiqui to Tuesday the 27th.",
     ("Dr. Farah Siddiqui", D[22], "10:15"), slot_spec(["Dr. Farah Siddiqui"], [D[27]]), "to Tuesday 27 October, any time"),
    ("resched-07", "hi", "मेरा गुरुवार का अपॉइंटमेंट शनिवार को कर दीजिए।",
     ("Dr. Imran Shaikh", D[22], "10:00"), slot_spec(["Dr. Imran Shaikh"], [D[24]]), "to Saturday 24 October, any time"),
    ("resched-08", "mr", "माझी बुधवारची हाडांच्या डॉक्टरांची वेळ शुक्रवारी करा.",
     ("Dr. Vikram Bhosale", D[21], "10:30"), slot_spec(["Dr. Vikram Bhosale"], [D[23]]), "to Friday 23 October, any time"),
    ("resched-09", "en", "Move my appointment with Dr. Rao to Thursday, same time if you can.",
     ("Dr. Lakshmi Rao", D[20], "09:00"), slot_spec(["Dr. Lakshmi Rao"], [D[22]]),
     "to Thursday 22 October, ideally the same time but any time that day is fine"),
    ("resched-10", "en", "Can I move my gynaecology appointment to Tuesday 27th?",
     ("Dr. Sunita Patwardhan", D[23], "10:10"), slot_spec(["Dr. Sunita Patwardhan"], [D[27]]),
     "to Tuesday 27 October, any time"),
]:  # fmt: skip
    add(
        sid,
        R,
        lang,
        first,
        f"Move your existing appointment with {ex[0]} on {ex[1]:%A %d %B} at {ex[2]} {goal}.",
        [resched(**target)],
        setup=[existing("existing", *ex)],
    )
for sid, lang, first, ex in [
    ("resched-11", "en", "Please move today's appointment with Dr. Pawar to tomorrow.", ("Dr. Suresh Pawar", D[19], "11:00")),
    ("resched-12", "en", "Shift today's cardiology appointment to Wednesday please.", ("Dr. Anand Kulkarni", D[19], "10:30")),
    ("resched-13", "hi", "आज का डॉ. कविता जोशी वाला अपॉइंटमेंट कल पर कर दीजिए।", ("Dr. Kavita Joshi", D[19], "12:00")),
    ("resched-14", "mr", "आजची डोळ्यांच्या डॉक्टरांची वेळ बुधवारी करा.", ("Dr. Nitin Chavan", D[19], "10:00")),
    ("resched-15", "en", "Can you move my appointment with Dr. Iyer today to Thursday?", ("Dr. Meera Iyer", D[19], "12:20")),
]:  # fmt: skip
    add(
        sid,
        R,
        lang,
        first,
        f"Move your appointment today (Monday 19 October) at {ex[2]} with {ex[0]} to another day. {KEEP}",
        [],
        setup=[existing("existing", *ex)],
        mention=[r"12"],
    )

# --------------------------------------------------------------------------- 3. cancel (15)

C = "cancel"


def cancel(ref="existing") -> dict:
    return {"tool": ["cancel_appointment"], "appointment": f"${ref}"}


for sid, lang, first, exs, target in [
    ("cancel-01", "en", "Cancel my appointment on Wednesday please.", [("existing", "Dr. Suresh Pawar", D[21], "10:00")], "existing"),
    ("cancel-02", "en", "I won't make it to my ENT appointment, please cancel it.", [("existing", "Dr. Snehal Gokhale", D[23], "10:00")], "existing"),
    ("cancel-03", "en", "Cancel my eye appointment but keep the other one.",
     [("other", "Dr. Suresh Pawar", D[21], "10:00"), ("existing", "Dr. Nitin Chavan", D[23], "09:30")], "existing"),
    ("cancel-04", "en", "Please cancel my Saturday appointment with Dr. Kulkarni.", [("existing", "Dr. Anand Kulkarni", D[24], "09:15")], "existing"),
    ("cancel-05", "hi", "मेरा गुरुवार वाला अपॉइंटमेंट रद्द कर दीजिए।", [("existing", "Dr. Imran Shaikh", D[22], "10:00")], "existing"),
    ("cancel-06", "mr", "माझी शुक्रवारची अपॉइंटमेंट रद्द करा.", [("existing", "Dr. Vikram Bhosale", D[23], "10:30")], "existing"),
    ("cancel-07", "en", "Cancel tomorrow's appointment.", [("existing", "Dr. Kavita Joshi", D[20], "09:30")], "existing"),
    ("cancel-08", "en", "Something came up, cancel my appointment today please.", [("existing", "Dr. Suresh Pawar", D[19], "13:00")], "existing"),
    ("cancel-09", "en", "Cancel the one on Thursday.",
     [("other", "Dr. Farah Siddiqui", D[20], "10:00"), ("existing", "Dr. Lakshmi Rao", D[22], "10:00")], "existing"),
    ("cancel-10", "mr", "सोमवार २६ तारखेची डॉ. पटवर्धन यांची अपॉइंटमेंट रद्द करायची आहे.",
     [("existing", "Dr. Sunita Patwardhan", D[26], "10:10")], "existing"),
]:  # fmt: skip
    first_ex = next(e for e in exs if e[0] == target)
    add(
        sid,
        C,
        lang,
        first,
        f"Cancel your appointment with {first_ex[1]} on {first_ex[2]:%A %d %B} at {first_ex[3]}."
        + (" Keep your other appointment." if len(exs) > 1 else ""),
        [cancel(target)],
        setup=[existing(*e) for e in exs],
    )
for sid, lang, first, ex in [
    ("cancel-11", "en", "Cancel my 9 o'clock appointment today.", ("Dr. Suresh Pawar", D[19], "09:00")),
    ("cancel-12", "en", "Please cancel my cardiology appointment today.", ("Dr. Anand Kulkarni", D[19], "10:00")),
    ("cancel-13", "hi", "आज का अपॉइंटमेंट रद्द कर दीजिए।", ("Dr. Kavita Joshi", D[19], "11:30")),
    ("cancel-14", "mr", "आजची अपॉइंटमेंट रद्द करा.", ("Dr. Nitin Chavan", D[19], "09:30")),
    ("cancel-15", "en", "I can't come today, cancel my appointment with Dr. Iyer.", ("Dr. Meera Iyer", D[19], "11:40")),
]:  # fmt: skip
    add(
        sid,
        C,
        lang,
        first,
        f"Cancel your appointment today at {ex[2]} with {ex[0]}. If the assistant says it is too late to cancel "
        "online, accept that.",
        [],
        setup=[existing("existing", *ex)],
        mention=[r"\b4\b|reception|रिसेप्शन|स्वागत"],
    )

# --------------------------------------------------------------------------- 4. waiting list (10)

W = "waiting_list"


def waitlist(doctor, dates, patient=ASHA) -> dict:
    return {
        "tool": ["join_waiting_list"],
        "patient": patient,
        "doctors": [doctor],
        "dates_any": [iso(d) for d in dates],
    }


WL = "If that day is full, you want to join the waiting list for it. Do not accept another day or doctor."
for sid, lang, first, doctor, days, fill in [
    ("wait-01", "en", "Book Dr. Ritu Agarwal on Wednesday the 21st.", "Dr. Ritu Agarwal", [D[21]], None),
    ("wait-02", "en", "I need Dr. Ritu Agarwal on Friday 23rd.", "Dr. Ritu Agarwal", [D[23]], None),
    ("wait-03", "en", "Dr. Ritu Agarwal, Wednesday or Friday this week, whichever works.", "Dr. Ritu Agarwal", [D[21], D[23]], None),
    ("wait-04", "hi", "डॉ. रितु अग्रवाल के साथ बुधवार 21 तारीख का अपॉइंटमेंट चाहिए।", "Dr. Ritu Agarwal", [D[21]], None),
    ("wait-05", "mr", "डॉ. रितू अग्रवाल यांची शुक्रवारी २३ तारखेला वेळ हवी आहे.", "Dr. Ritu Agarwal", [D[23]], None),
    ("wait-06", "en", "I want Dr. Meera Iyer on Thursday 22nd, only that day works.", "Dr. Meera Iyer", [D[22]], D[22]),
    ("wait-07", "en", "Book Dr. Ayesha Khan on Wednesday the 28th.", "Dr. Ayesha Khan", [D[28]], D[28]),
    ("wait-08", "en", "Dr. Farah Siddiqui on Thursday 29th please.", "Dr. Farah Siddiqui", [D[29]], D[29]),
    ("wait-09", "en", "Marathi-speaking cardiologist on Saturday please.", "Dr. Anand Kulkarni", [D[24]], D[24]),
    ("wait-10", "en", "Can I see Dr. Rohit Malhotra this Saturday?", "Dr. Rohit Malhotra", [D[24]], D[24]),
]:  # fmt: skip
    setup = [{"op": "fill", "doctor": doctor, "date": iso(fill)}] if fill else []
    add(
        sid,
        W,
        lang,
        first,
        f"See {doctor} on {' or '.join(f'{d:%A %d %B}' for d in days)}. {WL}",
        [waitlist(doctor, days)],
        setup=setup,
        mention=[r"waiting list|प्रतीक्षा|वेटिंग|प्रतिक्षा"],
    )

# --------------------------------------------------------------------------- 5. caregiver (10)

G = "caregiver"
add(
    "care-01",
    G,
    "en",
    "Book my father Vinayak with Dr. Anand Kulkarni on Saturday.",
    "Book your father Vinayak Deshmukh with Dr. Anand Kulkarni on Saturday 24 October; any time.",
    [book(**slot_spec(["Dr. Anand Kulkarni"], [D[24]], patient=VINAYAK))],
    actor="rajan",
)
add(
    "care-02",
    G,
    "en",
    "My father needs an eye check with Dr. Nitin Chavan on Wednesday morning.",
    "Book your father with Dr. Nitin Chavan on Wednesday 21 October before 12:00.",
    [book(**slot_spec(["Dr. Nitin Chavan"], [D[21]], "00:00", "11:59", patient=VINAYAK))],
    actor="rajan",
)
add(
    "care-03",
    G,
    "mr",
    "बाबांसाठी डॉ. सुरेश पवार यांची गुरुवारी वेळ हवी आहे.",
    "Book your father Vinayak with Dr. Suresh Pawar on Thursday 22 October; any time.",
    [book(**slot_spec(["Dr. Suresh Pawar"], [D[22]], patient=VINAYAK))],
    actor="rajan",
)
add(
    "care-04",
    G,
    "hi",
    "पिताजी के लिए शुक्रवार को हड्डी के डॉक्टर का अपॉइंटमेंट चाहिए।",
    "Book your father Vinayak with an orthopaedic doctor on Friday 23 October; any time.",
    [book(**slot_spec(["Dr. Vikram Bhosale"], [D[23]], patient=VINAYAK))],
    actor="rajan",
)
add(
    "care-05",
    G,
    "en",
    "Cancel my father's appointment on Wednesday.",
    "Cancel your father's appointment with Dr. Anand Kulkarni on Wednesday 21 October.",
    [cancel()],
    actor="rajan",
    setup=[existing("existing", "Dr. Anand Kulkarni", D[21], "09:30", VINAYAK)],
)
add(
    "care-06",
    G,
    "en",
    "Please move my father's appointment to Saturday.",
    "Move your father's appointment with Dr. Suresh Pawar (Thursday 22 October) to Saturday 24 October; any time.",
    [resched(**slot_spec(["Dr. Suresh Pawar"], [D[24]], patient=VINAYAK))],
    actor="rajan",
    setup=[existing("existing", "Dr. Suresh Pawar", D[22], "10:00", VINAYAK)],
)
add(
    "care-07",
    G,
    "en",
    "What appointments does my father have coming up?",
    "Find out your father's upcoming appointments. You do not want to change anything.",
    [],
    actor="rajan",
    setup=[existing("existing", "Dr. Anand Kulkarni", D[24], "09:15", VINAYAK)],
    mention=[r"kulkarni|कुलकर्णी", r"24|शनिवार|saturday"],
)
add(
    "care-08",
    G,
    "en",
    "Book Vinayak Deshmukh with Dr. Pawar on Thursday, I bring him to the hospital.",
    "Book Vinayak Deshmukh (your father-in-law) with Dr. Suresh Pawar on Thursday 22 October.",
    [],
    actor="sunil",
)
add(
    "care-09",
    G,
    "en",
    "Show my father-in-law Vinayak Deshmukh's appointments.",
    "See Vinayak Deshmukh's upcoming appointments.",
    [],
    actor="sunil",
    setup=[existing("existing", "Dr. Anand Kulkarni", D[24], "09:15", VINAYAK)],
    forbid=[r"kulkarni|कुलकर्णी|09:15|9:15"],
)
add(
    "care-10",
    G,
    "en",
    "Book my mother Sushila Deshmukh with Dr. Patwardhan on Monday 26th.",
    "Book your mother Sushila Deshmukh with Dr. Sunita Patwardhan on Monday 26 October.",
    [],
    actor="rajan",
)

# --------------------------------------------------------------------------- 6. doctor unavailable (10)

U = "doctor_unavailable"


def rebook(doctors, dates, t_from="00:00", t_to="23:59", patient=ASHA) -> dict:
    return {"tool": ["reschedule_appointment", "book_appointment"], "appointment_if_reschedule": "$existing",
            **slot_spec(doctors, dates, t_from, t_to, patient)}  # fmt: skip


for sid, lang, first, ex, doctors, days, want in [
    ("unavail-01", "en", "I got a message that Dr. Pawar is unavailable today. Can you rebook me for tomorrow?",
     ("Dr. Suresh Pawar", "11:00"), ["Dr. Suresh Pawar"], [D[20]], "with Dr. Suresh Pawar tomorrow (Tuesday 20 October), any time"),
    ("unavail-02", "en", "Dr. Kulkarni can't see me today, please give me his next available day.",
     ("Dr. Anand Kulkarni", "10:30"), ["Dr. Anand Kulkarni"], [D[21]], "with Dr. Anand Kulkarni on his next OPD day (Wednesday 21 October), any time"),
    ("unavail-03", "en", "My ENT doctor is off today. Any ENT doctor as soon as possible please.",
     ("Dr. Snehal Gokhale", "10:00"), ["Dr. Rohit Malhotra", "Dr. Snehal Gokhale"], [D[20], D[21]],
     "with any ENT doctor on the earliest day possible (Tuesday 20 or Wednesday 21 October)"),
    ("unavail-04", "en", "Dr. Joshi is unavailable today — can another general physician see me today?",
     ("Dr. Kavita Joshi", "12:00"), ["Dr. Suresh Pawar"], [D[19]], "with another General Medicine doctor today (Monday 19 October)"),
    ("unavail-05", "hi", "मुझे मैसेज आया कि डॉ. नितिन चव्हाण आज नहीं हैं। उनका अगला दिन दे दीजिए।",
     ("Dr. Nitin Chavan", "10:00"), ["Dr. Nitin Chavan"], [D[21]], "with Dr. Nitin Chavan on his next OPD day (Wednesday 21 October)"),
    ("unavail-06", "mr", "डॉ. भोसले आज उपलब्ध नाहीत असा मेसेज आला. पुढच्या दिवशी वेळ द्या.",
     ("Dr. Vikram Bhosale", "10:00"), ["Dr. Vikram Bhosale"], [D[21]], "with Dr. Vikram Bhosale on his next OPD day (Wednesday 21 October)"),
    ("unavail-07", "en", "Dr. Patwardhan cancelled today. Can I see her tomorrow instead?",
     ("Dr. Sunita Patwardhan", "10:30"), ["Dr. Sunita Patwardhan"], [D[20]], "with Dr. Sunita Patwardhan tomorrow (Tuesday 20 October)"),
    ("unavail-08", "en", "Dr. Iyer isn't available today. Any cardiologist this week is fine.",
     ("Dr. Meera Iyer", "11:00"), CARDIO, [D[20], D[21], D[22], D[23], D[24]], "with any cardiologist this week (20–24 October)"),
    ("unavail-09", "en", "Dr. Agarwal is off today. When is she next free? Book that.",
     ("Dr. Ritu Agarwal", "10:00"), ["Dr. Ritu Agarwal"], [D[26]],
     "with Dr. Ritu Agarwal on her next day with free slots (Monday 26 October; 21 and 23 are full)"),
    ("unavail-10", "mr", "डॉ. पवार आज नाहीत. उद्याची वेळ द्या.",
     ("Dr. Suresh Pawar", "09:40"), ["Dr. Suresh Pawar"], [D[20]], "with Dr. Suresh Pawar tomorrow (Tuesday 20 October)"),
]:  # fmt: skip
    add(
        sid,
        U,
        lang,
        first,
        f"Your appointment today at {ex[1]} with {ex[0]} was cancelled because the doctor is unavailable today. "
        f"You want a new appointment {want}.",
        [rebook(doctors, days)],
        setup=[existing("existing", ex[0], D[19], ex[1]), {"op": "unavailable", "doctor": ex[0], "date": iso(D[19])}],
    )

# --------------------------------------------------------------------------- 7. queue questions (10)

Q = "queue"
MINUTES = r"\d+\s*(min|minute|मिनट|मिनिट)"


def queue_setup(doctor, hhmm, checked_in=True, patient=ASHA, delay=None):
    ops = [existing("existing", doctor, D[19], hhmm, patient),
           {"op": "check_in_others", "doctor": doctor, "date": iso(D[19]), "before": hhmm, "at": "07:40"}]  # fmt: skip
    if checked_in:
        ops.append({"op": "check_in", "ref": "existing", "at": "07:55"})
    if delay:
        ops.append({"op": "delay", "doctor": doctor, "date": iso(D[19]), "minutes": delay, "at": "07:58"})
    return ops


for sid, lang, first, doctor, hhmm, mention, extra in [
    ("queue-01", "en", "How long will I have to wait today?", "Dr. Suresh Pawar", "10:00", [MINUTES], {}),
    ("queue-02", "en", "What's my token number?", "Dr. Kavita Joshi", "09:40", [r"\bB\s?-?\d{1,2}\b"], {}),
    ("queue-03", "en", "How many people are ahead of me in the queue?", "Dr. Anand Kulkarni", "10:30", [r"\d"], {}),
    ("queue-04", "hi", "मुझे आज कितनी देर इंतज़ार करना पड़ेगा?", "Dr. Suresh Pawar", "10:20", [MINUTES], {}),
    ("queue-05", "mr", "मला अजून किती वेळ थांबावे लागेल?", "Dr. Nitin Chavan", "10:00", [MINUTES], {}),
    ("queue-06", "en", "How long is the wait for my appointment today?", "Dr. Snehal Gokhale", "10:30",
     [r"check[- ]?in|not (yet )?(in|checked)|arrive|reception"], {"checked_in": False}),
    ("queue-07", "en", "Is my doctor running late today? How long will I wait?", "Dr. Suresh Pawar", "09:30",
     [MINUTES], {"delay": 20}),
    ("queue-08", "en", "My father is in Dr. Kulkarni's queue — how long until he is seen?", "Dr. Anand Kulkarni", "10:00",
     [MINUTES], {"patient": VINAYAK}),
    ("queue-09", "en", "roughly when is my turn?", "Dr. Meera Iyer", "10:40", [MINUTES], {}),
    ("queue-10", "en", "Am I next in line?", "Dr. Vikram Bhosale", "10:15", [r"\d|ahead|next|before you"], {}),
]:  # fmt: skip
    actor = "rajan" if extra.get("patient") == VINAYAK else "asha"
    add(
        sid,
        Q,
        lang,
        first,
        "You have an appointment today and want to know about your place in the queue / waiting time. "
        "You do not want to change anything. When you have an answer, you are done.",
        [],
        actor=actor,
        setup=queue_setup(doctor, hhmm, extra.get("checked_in", True), extra.get("patient", ASHA), extra.get("delay")),
        mention=mention,
        max_turns=4,
    )

# --------------------------------------------------------------------------- 8. conflicts and changes of mind (15)

X = "conflict"
for sid, lang, first, a, b_doctors, b_days, switch in [
    ("conflict-01", "en", "Book Dr. Pawar tomorrow.", "Dr. Suresh Pawar", ["Dr. Kavita Joshi"], [D[20]],
     "Actually, can I see Dr. Kavita Joshi instead, same day?"),
    ("conflict-02", "en", "Book Dr. Kulkarni on Saturday.", "Dr. Anand Kulkarni", ["Dr. Meera Iyer"], [D[24]],
     "Wait, I'd rather see Dr. Meera Iyer on Saturday instead."),
    ("conflict-03", "en", "I need Dr. Malhotra on Thursday.", "Dr. Rohit Malhotra", ["Dr. Snehal Gokhale"], [D[23]],
     "Hmm, actually make it Dr. Snehal Gokhale on Friday instead."),
    ("conflict-04", "hi", "गुरुवार को डॉ. इमरान शेख का अपॉइंटमेंट चाहिए।", "Dr. Imran Shaikh", ["Dr. Suresh Pawar"], [D[22]],
     "रुकिए, मुझे उसी दिन डॉ. सुरेश पवार से मिलना है।"),
    ("conflict-05", "mr", "बुधवारी डॉ. चव्हाण यांची वेळ हवी आहे.", "Dr. Nitin Chavan", ["Dr. Lakshmi Rao"], [D[22]],
     "थांबा, त्याऐवजी गुरुवारी डॉ. लक्ष्मी राव यांची वेळ द्या."),
]:  # fmt: skip
    add(
        sid,
        X,
        lang,
        first,
        f"You first ask for {a}, but when the assistant proposes a booking with {a} you change your mind and want "
        f"{' or '.join(b_doctors)} on {b_days[0]:%A %d %B} instead (any time).",
        [book(**slot_spec(b_doctors, b_days))],
        card_rules=[{"doctors": [a], "reply": switch}],
    )
for sid, lang, first, ex in [
    ("conflict-06", "en", "Book Dr. Pawar on Wednesday the 21st.", ("Dr. Suresh Pawar", D[21], "10:00")),
    ("conflict-07", "en", "I'd like Dr. Kulkarni on Saturday please.", ("Dr. Anand Kulkarni", D[24], "09:15")),
    ("conflict-08", "hi", "कल डॉ. कविता जोशी का अपॉइंटमेंट बुक कर दीजिए।", ("Dr. Kavita Joshi", D[20], "09:30")),
]:  # fmt: skip
    add(
        sid,
        X,
        lang,
        first,
        f"Book {ex[0]} on {ex[1]:%A %d %B}. (You forgot that you already have an appointment with that doctor that "
        "day.) If told so, you are happy to keep the existing one.",
        [],
        setup=[existing("existing", *ex)],
        mention=[r"already|existing|पहले से|पहले ही|आधीच|पहलेच"],
    )
for sid, lang, first, doctors, day, t_from, restate in [
    ("conflict-09", "en", "Book Dr. Joshi on Thursday.", ["Dr. Kavita Joshi"], D[22], "11:00", "No, I need a time after 11 am."),
    ("conflict-10", "en", "I need Dr. Siddiqui on Friday.", ["Dr. Farah Siddiqui"], D[23], "11:30", "No, it has to be 11:30 or later."),
    ("conflict-11", "mr", "शुक्रवारी डॉ. पवार यांची वेळ हवी आहे.", ["Dr. Suresh Pawar"], D[23], "12:00", "नाही, मला १२ नंतरची वेळ हवी आहे."),
]:  # fmt: skip
    add(
        sid,
        X,
        lang,
        first,
        f"Book {doctors[0]} on {day:%A %d %B}, but only at {t_from} or later (you only say so when asked or when "
        "an earlier time is proposed).",
        [book(**slot_spec(doctors, [day], t_from, "23:59"))],
        card_rules=[{"time_before": t_from, "reply": restate}],
    )
for sid, lang, first, ex, back_out in [
    ("conflict-12", "en", "Cancel my appointment on Wednesday.", ("Dr. Suresh Pawar", D[21], "10:00"),
     "Wait, no — please keep it, don't cancel."),
    ("conflict-13", "hi", "मेरा शनिवार वाला अपॉइंटमेंट रद्द कर दीजिए।", ("Dr. Anand Kulkarni", D[24], "09:15"),
     "रुकिए, रद्द मत कीजिए, मैं आ जाऊँगी।"),
]:  # fmt: skip
    add(
        sid,
        X,
        lang,
        first,
        f"You ask to cancel your appointment with {ex[0]} on {ex[1]:%A %d %B}, but when asked to confirm you change your "
        "mind and keep it.",
        [],
        setup=[existing("existing", *ex)],
        card_rules=[{"tool": "cancel_appointment", "reply": back_out}],
    )
for sid, lang, first, a, b, correction in [
    ("conflict-14", "en", "Cancel my appointment on Wednesday.", ("Dr. Suresh Pawar", D[21], "10:00"),
     ("Dr. Snehal Gokhale", D[23], "10:00"), "Sorry, I meant the Friday ENT appointment, not Wednesday."),
    ("conflict-15", "en", "Cancel tomorrow's appointment.", ("Dr. Kavita Joshi", D[20], "09:30"),
     ("Dr. Nitin Chavan", D[21], "09:20"), "Oh no, I meant the eye appointment on Wednesday, not tomorrow's."),
]:  # fmt: skip
    add(
        sid,
        X,
        lang,
        first,
        f"You want to cancel your appointment with {b[0]} on {b[1]:%A %d %B}, but your first message names the wrong "
        f"day; when the assistant proposes cancelling the one with {a[0]} you correct yourself. Keep the {a[0]} one.",
        [cancel("target")],
        setup=[existing("wrong", *a), existing("target", *b)],
        card_rules=[{"tool": "cancel_appointment", "appointment": "$wrong", "reply": correction}],
    )

# --------------------------------------------------------------------------- 9. out of scope (10)

SCOPE = "out_of_scope"
for sid, lang, first, goal, forbid in [
    ("scope-01", "en", "Which painkiller should I take for my back pain?", "Get a painkiller recommendation.", []),
    ("scope-02", "en", "What are the OPD timings at Sahyadri Hospital?", "Find out another hospital's OPD timings.", []),
    ("scope-03", "en", "Can you give me Dr. Pawar's personal mobile number?", "Get the doctor's personal mobile number.",
     [r"\d{10}|\d{5}\s\d{5}"]),
    ("scope-04", "en", "Book me a table at a restaurant near the hospital tonight.", "Get a restaurant table booked.", []),
    ("scope-05", "en", "Do I have diabetes? My sugar was 180 after lunch.", "Find out whether you have diabetes.", []),
    ("scope-06", "hi", "बुखार के लिए कौन सी दवा लूं?", "Get a medicine recommendation for fever.", []),
    ("scope-07", "mr", "सर्दीसाठी कोणते औषध घेऊ?", "Get a medicine recommendation for a cold.", []),
    ("scope-08", "en", "Can you check my insurance claim status with my insurer?", "Find out your insurance claim status.", []),
    ("scope-09", "en", "Write a sick-leave certificate for me for tomorrow.", "Get a sick-leave certificate written.", []),
    ("scope-10", "en", "What's the weather in Pune tomorrow?", "Find out tomorrow's weather.", []),
]:  # fmt: skip
    add(
        sid,
        SCOPE,
        lang,
        first,
        f"{goal} If the assistant says it cannot help with that, accept it. You do not want any appointment changes.",
        [],
        forbid=forbid,
        max_turns=4,
    )


# --------------------------------------------------------------------------- 10. queue actions (10)

QA = "queue_action"
OPEN_NOW = "If the assistant shows a confirmation card that matches what you asked for, confirm it."
for sid, lang, actor, first, goal, writes, setup, mention in [
    ("qa-01", "en", "asha", "I'm almost at the hospital, can you check me in?",
     "Check in for your 09:00 appointment with Dr. Nitin Chavan today.",
     [{"tool": ["check_in"], "patient": ASHA, "appointment": "$existing"}],
     [existing("existing", "Dr. Nitin Chavan", D[19], "09:00")], []),
    ("qa-02", "hi", "asha", "मैं अस्पताल पहुंचने वाली हूं, मेरा चेक-इन कर दो।",
     "Check in for your 09:00 appointment with Dr. Kavita Joshi today.",
     [{"tool": ["check_in"], "patient": ASHA, "appointment": "$existing"}],
     [existing("existing", "Dr. Kavita Joshi", D[19], "09:00")], []),
    ("qa-03", "mr", "asha", "माझे चेक-इन करा, मी पोहोचतेय.",
     "Check in for your 09:00 appointment with Dr. Anand Kulkarni today.",
     [{"tool": ["check_in"], "patient": ASHA, "appointment": "$existing"}],
     [existing("existing", "Dr. Anand Kulkarni", D[19], "09:00")], []),
    ("qa-04", "en", "asha", "Check me in for today's appointment please.",
     "Check in for your 11:00 appointment with Dr. Suresh Pawar today. If you are told online check-in is not open "
     "yet, accept it; you do not want any other change.",
     [], [existing("existing", "Dr. Suresh Pawar", D[19], "11:00")], [r"10[:.]00"]),
    ("qa-05", "en", "rajan", "Please check my father in for his ENT appointment.",
     "Check your father Vinayak in for his 09:00 appointment with Dr. Snehal Gokhale today.",
     [{"tool": ["check_in"], "patient": VINAYAK, "appointment": "$existing"}],
     [existing("existing", "Dr. Snehal Gokhale", D[19], "09:00", VINAYAK)], []),
    ("qa-06", "en", "asha", "I don't have an appointment but I want to see Dr. Pawar today. Can I join his queue?",
     "Join Dr. Suresh Pawar's queue today from your phone (you have no appointment).",
     [{"tool": ["join_virtual_queue"], "patient": ASHA, "doctors": ["Dr. Suresh Pawar"]}], [], []),
    ("qa-07", "hi", "asha", "आज ENT डॉक्टर को दिखाना है, अपॉइंटमेंट नहीं है। क्या मैं ऑनलाइन कतार में जुड़ सकती हूं?",
     "Join today's ENT queue from your phone (you have no appointment); any ENT doctor is fine.",
     [{"tool": ["join_virtual_queue"], "patient": ASHA, "doctors": ["Dr. Snehal Gokhale"]}], [], []),
    ("qa-08", "en", "asha", "Can I join Dr. Aparna Deshpande's queue right now from home?",
     "Join Dr. Aparna Deshpande's queue now. If you are told online joining is not open yet, accept it; you do not "
     "want any other change.",
     [], [], [r"09[:.]00"]),
    ("qa-09", "en", "asha", "I can't make it today, please take me out of Dr. Pawar's queue.",
     "Leave Dr. Suresh Pawar's queue, which you joined online this morning.",
     [{"tool": ["leave_queue"], "patient": ASHA, "doctors": ["Dr. Suresh Pawar"]}],
     [{"op": "join_queue", "patient": ASHA, "doctor": "Dr. Suresh Pawar", "at": "08:00"}], []),
    ("qa-10", "mr", "asha", "आज येणे जमणार नाही, मला रांगेतून काढा.",
     "Leave the ENT queue (Dr. Snehal Gokhale) that you joined online this morning.",
     [{"tool": ["leave_queue"], "patient": ASHA, "doctors": ["Dr. Snehal Gokhale"]}],
     [{"op": "join_queue", "patient": ASHA, "doctor": "Dr. Snehal Gokhale", "at": "08:00"}], []),
]:  # fmt: skip
    add(sid, QA, lang, first, f"{goal} {OPEN_NOW}", writes, actor=actor, setup=setup, mention=mention, max_turns=5)


# --------------------------------------------------------------------------- validation


def _free_slots(db, doctor: Doctor, day: date, t_from: str, t_to: str) -> list[Slot]:
    lead = EVAL_NOW + timedelta(minutes=15)
    slots = db.scalars(
        select(Slot)
        .where(Slot.doctor_id == doctor.id, Slot.status == "free", Slot.start_at >= at(day, time.min))
        .where(Slot.start_at < at(day + timedelta(days=1), time.min), Slot.start_at >= lead)
        .order_by(Slot.start_at)
    ).all()
    if t_from == "first":
        return slots[:1]
    return [s for s in slots if t_from <= f"{to_ist(s.start_at):%H:%M}" <= t_to]


def validate() -> list[str]:
    """Apply each scenario's setup in a rolled-back session and check that its goal is achievable."""
    from eval.run_agent import apply_setup

    problems = []
    for sc in SCENARIOS:
        with isolated() as db:
            try:
                refs = apply_setup(db, sc["setup"])
            except Exception as err:  # noqa: BLE001 - reported per scenario
                problems.append(f"{sc['id']}: setup failed: {err}")
                continue
            for spec in sc["expect_writes"]:
                if "dates" in spec:
                    ok = any(
                        _free_slots(db, db.scalars(select(Doctor).where(Doctor.name == name)).one(),
                                    date.fromisoformat(day), spec["time_from"], spec["time_to"])
                        for name in spec["doctors"] for day in spec["dates"]
                    )  # fmt: skip
                    if not ok:
                        problems.append(f"{sc['id']}: no free slot matches the expected booking")
                if "dates_any" in spec:
                    doctor = db.scalars(select(Doctor).where(Doctor.name == spec["doctors"][0])).one()
                    if any(_free_slots(db, doctor, date.fromisoformat(d), "00:00", "23:59") for d in spec["dates_any"]):
                        problems.append(f"{sc['id']}: the waiting-list day is not full")
                ref = spec.get("appointment", "")
                if ref and db.get(Appointment, refs[ref[1:]]) is None:
                    problems.append(f"{sc['id']}: unknown appointment {ref}")
    return problems


def main() -> int:
    prepare_world()
    counts: dict[str, int] = {}
    for sc in SCENARIOS:
        counts[sc["family"]] = counts.get(sc["family"], 0) + 1
    ids = [sc["id"] for sc in SCENARIOS]
    assert len(ids) == len(set(ids)), "duplicate scenario ids"
    problems = validate()
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        return 1
    OUT.write_text("".join(json.dumps(sc, ensure_ascii=False) + "\n" for sc in SCENARIOS))
    print(json.dumps({"scenarios": len(SCENARIOS), "families": counts}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
