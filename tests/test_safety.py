"""Safety gate components: emergency check (FR-02), language (FR-01), medical-advice guard (FR-04),
confirmation parsing (FR-09)."""

import pytest

from app.agent.confirm import is_affirmative, is_negative
from app.safety.emergency import check_emergency
from app.safety.language import detect_language
from app.safety.output_guard import mentions_medication

# Phrasings deliberately different from the classifier's training examples.
EMERGENCIES = [
    "I have chest pain since 20 minutes",
    "my husband is unconscious on the floor",
    "she can't breathe properly",
    "he is having fits, please help",
    "my son drank pesticide",
    "there was a road accident outside",
    "it's an emergency",
    "book a cardiologist for saturday, I have chest pain right now",
    "मेरे पिताजी बेहोश हो गए हैं",
    "मां को सांस लेने में बहुत तकलीफ़ है",
    "उसने ज़हर पी लिया",
    "बच्चे को दौरा पड़ा है",
    "माझ्या छातीत कळ येत आहे",
    "आजी बेशुद्ध झाली आहे",
    "भावाचा अपघात झाला",
    "seene mein dard ho raha hai",
]
ROUTINE = [
    "book a cardiologist on saturday",
    "I want a follow-up after my heart attack last year",
    "I get short of breath when climbing stairs, I need a cardiologist",
    "what are the emergency department timings",
    "I need a medically fit certificate",
    "do I need to fast before an ECG",
    "I don't have chest pain, I just want a check-up",
    "विभागाविषयी माहिती द्या",
    "चालताना धाप लागते, डॉक्टरांना दाखवायचे आहे",
    "मुझे कल हृदय रोग विशेषज्ञ चाहिए",
    "yes please book it",
]


@pytest.mark.parametrize("message", EMERGENCIES)
def test_emergencies_are_flagged(message):
    assert check_emergency(message).is_emergency


@pytest.mark.parametrize("message", ROUTINE)
def test_routine_messages_are_not_flagged(message):
    assert not check_emergency(message).is_emergency


@pytest.mark.parametrize(
    "text, lang",
    [
        ("Book a cardiologist on Saturday", "en"),
        ("मुझे शनिवार को डॉक्टर चाहिए", "hi"),
        ("मला शनिवारी डॉक्टर पाहिजे आहे", "mr"),
        ("mujhe kal doctor chahiye", "hi"),
        ("mala udya doctor pahije aahe", "mr"),
        ("ok", "en"),
    ],
)
def test_language_detection(text, lang):
    assert detect_language(text) == lang


def test_language_hint_breaks_devanagari_ties():
    assert detect_language("डॉक्टर", hint="mr") == "mr"
    assert detect_language("डॉक्टर", hint="hi") == "hi"


@pytest.mark.parametrize(
    "text",
    ["Take paracetamol 500 mg", "You can take two tablets twice a day", "दिन में दो बार क्रोसिन लें", "dolo is fine"],
)
def test_medication_advice_is_detected(text):
    assert mentions_medication(text)


@pytest.mark.parametrize(
    "text",
    [
        "Fast for 10–12 hours before the lipid profile [1].",
        "Dr. Kulkarni has 10:30 free on Saturday.",
        "The fee is ₹600.",
    ],
)
def test_ordinary_replies_pass_the_guard(text):
    assert not mentions_medication(text)


@pytest.mark.parametrize(
    "text", ["yes", "Yes please", "ok book it", "हाँ", "हो", "होय, बुक करा", "confirm", "haan kar do"]
)
def test_affirmative(text):
    assert is_affirmative(text) and not is_negative(text)


@pytest.mark.parametrize("text", ["no", "नहीं", "नको", "no, a different time", "wait"])
def test_negative(text):
    assert is_negative(text) and not is_affirmative(text)


@pytest.mark.parametrize("text", ["yes but at 11 instead of 10:30", "book a cardiologist", "what is the fee?"])
def test_not_a_plain_confirmation(text):
    assert not is_affirmative(text)
