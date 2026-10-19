"""Recognising an explicit yes / no to a confirmation card, in three languages.

Only short, unambiguous replies count. "Yes, but at 11 instead" is not a plain
confirmation: it goes back to the agent, and the pending card is dropped.
"""

import re

from app.rag.text import normalize

AFFIRMATIVE = frozenset(
    "yes yeah yep yup y ok okay sure confirm confirmed correct right fine proceed "
    "हाँ हां हा जी ठीक पक्का कन्फर्म हो होय चालेल नक्की बरोबर "
    "haan han ha ho hoy theek thik chalel nakki".split()
)
FILLER = frozenset(
    "please pls go ahead do it that this the slot appointment book booking cancel reschedule move thanks thank you "
    "is that's good sounds perfect and please. "
    "है कर दो दीजिए दें करें बुक रद्द बदल धन्यवाद जी आहे करा द्या बुक रद्द बदला धन्यवाद "
    "hai kar do kara dya karo".split()
)
NEGATIVE = frozenset(
    "no nope nah not don't dont never wait stop change different another "
    "नहीं नही ना मत रुको रुकिए बदलो दूसरा नाही नको थांबा दुसरा वेगळा "
    "nahi nahin mat nako thamba".split()
)
_WORD = re.compile(r"[^\s\.,;:!?\"'()\[\]{}।॥\-–—/🙏👍✅]+")


def _words(text: str) -> list[str]:
    return _WORD.findall(normalize(text))


def is_negative(text: str) -> bool:
    words = _words(text)
    return bool(words) and len(words) <= 8 and any(w in NEGATIVE for w in words)


def is_affirmative(text: str) -> bool:
    words = _words(text)
    if not words or len(words) > 6 or any(w in NEGATIVE for w in words):
        return False
    if not any(w in AFFIRMATIVE for w in words):
        return False
    return all(w in AFFIRMATIVE or w in FILLER for w in words)
