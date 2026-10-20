"""Shared pieces for the synthetic knowledge base: translated strings and document structure."""

from dataclasses import dataclass, field
from datetime import date

LANGS = ("en", "hi", "mr")
LAST_VERIFIED = date(2026, 10, 1)


@dataclass(frozen=True)
class T:
    """One string in English, Hindi and Marathi."""

    en: str
    hi: str
    mr: str

    def __getitem__(self, lang: str) -> str:
        return getattr(self, lang)

    def format(self, **kwargs) -> "T":
        return T(*(getattr(self, lang).format(**kwargs) for lang in LANGS))


@dataclass
class KbDoc:
    collection: str
    slug: str
    title: T
    sections: list[tuple[T, T]] = field(default_factory=list)

    @property
    def doc_key(self) -> str:
        return f"{self.collection}/{self.slug}"


def join(*parts: T, sep: str = " ") -> T:
    return T(*(sep.join(p[lang] for p in parts if p[lang]) for lang in LANGS))


def bullets(items: list[T]) -> T:
    return T(*("\n".join(f"- {i[lang]}" for i in items) for lang in LANGS))


WEEKDAYS = {
    1: T("Monday", "सोमवार", "सोमवार"),
    2: T("Tuesday", "मंगलवार", "मंगळवार"),
    3: T("Wednesday", "बुधवार", "बुधवार"),
    4: T("Thursday", "गुरुवार", "गुरुवार"),
    5: T("Friday", "शुक्रवार", "शुक्रवार"),
    6: T("Saturday", "शनिवार", "शनिवार"),
    7: T("Sunday", "रविवार", "रविवार"),
}

LANGUAGE_NAMES = {
    "en": T("English", "अंग्रेज़ी", "इंग्रजी"),
    "hi": T("Hindi", "हिंदी", "हिंदी"),
    "mr": T("Marathi", "मराठी", "मराठी"),
}


def list_of(items: list[T]) -> T:
    """'a, b and c' in each language."""

    def one(lang: str) -> str:
        words = [i[lang] for i in items]
        if len(words) <= 1:
            return "".join(words)
        conj = {"en": " and ", "hi": " और ", "mr": " आणि "}[lang]
        return ", ".join(words[:-1]) + conj + words[-1]

    return T(*(one(lang) for lang in LANGS))


def clock(t) -> str:
    return t.strftime("%H:%M")
