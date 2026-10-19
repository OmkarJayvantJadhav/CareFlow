"""Language detection for English, Hindi and Marathi (FR-01).

Devanagari text is Hindi or Marathi; the two share a script, so they are told
apart by frequent function words. Romanised Hindi/Marathi ("mujhe doctor
chahiye", "mala doctor pahije") is recognised by the same idea.
"""

import re

from app.rag.text import normalize

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")
_WORDS = re.compile(r"[^\s\.,;:!?\"'()\[\]{}।॥\-–—/]+")

HI_MARKERS = frozenset(
    "है हैं था थी थे मुझे मेरा मेरी मेरे मैं आप आपका चाहिए करना करनी करें कीजिए कीजिये के की में से नहीं क्या "
    "कहाँ कहां कब कैसे और कल हाँ हां ठीक बताइए बताइये दीजिए सकते सकता सकती हूं हूँ रहा रही वाला वाली लिए भी "
    "डॉक्टर्स दिखाना मिलेगा मिलेगी".split()
)
MR_MARKERS = frozenset(
    "आहे आहेत आहोत मला माझा माझी माझे माझ्या तुम्ही तुमचा तुमची करायची करायचे करायचा पाहिजे हवी हवे हवा "
    "नाही नको कुठे कधी कसे काय आणि उद्या होय द्या करा सांगा मिळेल लागते लागेल आज साठी असेल होईल शकतो शकते "
    "माझ्यासाठी वडिलांसाठी आईसाठी".split()
)
HI_ROMAN = frozenset(
    "mujhe mera meri mere hai hain chahiye kya nahi nahin karna karni kijiye kab kahan aap haan theek thik batao "
    "bataiye dijiye milega sakte liye wala wali".split()
)
MR_ROMAN = frozenset(
    "mala majha majhi majhe aahe ahe aahet pahije havi hava have nako kuthe kadhi kasa kay udya hoy sanga kara "
    "karaycha karaychi karayche milel lagel aaj sathi zala zali".split()
)


def detect_language(text: str, hint: str | None = None) -> str:
    """Return 'en', 'hi' or 'mr'. ``hint`` (the user's preferred language) breaks ties."""
    devanagari = len(_DEVANAGARI.findall(text))
    latin = len(_LATIN.findall(text))
    words = [w for w in _WORDS.findall(normalize(text)) if w]
    if devanagari and devanagari >= latin * 0.5:
        hi = sum(w in HI_MARKERS for w in words)
        mr = sum(w in MR_MARKERS for w in words)
        if mr > hi:
            return "mr"
        if hi > mr:
            return "hi"
        return hint if hint in ("hi", "mr") else "hi"
    hi = sum(w in HI_ROMAN for w in words)
    mr = sum(w in MR_ROMAN for w in words)
    if max(hi, mr) >= 2:
        if mr > hi:
            return "mr"
        if hi > mr:
            return "hi"
        return hint if hint in ("hi", "mr") else "hi"
    return "en"
