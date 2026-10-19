"""Tokenisation that works for English, Hindi and Marathi.

Python's ``\\w`` does not treat Devanagari vowel signs as word characters and
would split words apart, so text is split on whitespace and punctuation only.
"""

import re

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_SEPARATORS = re.compile(r"[\s\.,;:!?\"'“”‘’()\[\]{}<>/\\|।॥\-–—_*#`~+=%&@^$]+")

STOPWORDS = frozenset(
    """
    a an and are as at be been but by can do does for from has have how i if in is it its me my of on or hi hello
    dear thanks thank ok okay whether wanted would could kindly sir madam
    our should so that the their them then there these this to was we what when where which who why will
    with you your am any about into than too very also just get got want need please tell know
    है हैं था थे थी का की के को में से पर और या भी तो ही यह वह क्या कैसे कब कहाँ कहां मुझे मेरा मेरी मेरे
    हम आप एक कि लिए नहीं होता होती होते करना करें कर कितने कितना कितनी कौन कौनसा जी
    आहे आहेत होते होता होती आणि किंवा पण तर हे ही तो ती ते का काय कसे कधी कुठे मला माझा माझी माझे
    आम्ही तुम्ही एक की साठी नाही करायचे करू किती कोणता कोणती कोणते कोणत्या लागते लागेल
    """.split()
)


_NUKTA = "\u093c"


def normalize(text: str) -> str:
    """Lower-case, ASCII digits, and no nukta (प्रोफ़ाइल and प्रोफाइल are the same word)."""
    return text.translate(_DEVANAGARI_DIGITS).replace(_NUKTA, "").lower()


def tokenize(text: str) -> list[str]:
    return [t for t in _SEPARATORS.split(normalize(text)) if t]


def content_tokens(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in STOPWORDS]


# Light suffix stripping, used only to match inflected forms ("verified" ~ "verification",
# "मुलांचे" ~ "मुलांमध्ये"). Longest suffixes first.
_EN_SUFFIXES = ("ations", "ation", "ments", "ment", "ings", "ing", "ies", "ied", "ed", "es", "ly", "s")
_DEVANAGARI_SUFFIXES = (
    "ांच्या", "ाच्या", "च्या", "मध्ये", "ांचे", "ांची", "ांचा", "ावर", "ाने", "ाचे", "ाची", "ाचा",
    "ियों", "ाओं", "ाएं", "चे", "ची", "चा", "ला", "ना", "ने", "वर", "ात", "ों", "ें", "ी", "े", "ा",
)  # fmt: skip


def stem(token: str) -> str:
    if token.isascii():
        for suffix in _EN_SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= 4:
                return token[: -len(suffix)]
        return token
    for suffix in _DEVANAGARI_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token
