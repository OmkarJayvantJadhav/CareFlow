"""Prompt-injection defence for retrieved documents.

Retrieved text is always given to the model as quoted data. In addition, any
sentence that reads like an instruction to the assistant is removed before the
text reaches the model, and the removal is reported so it can be traced.
"""

import re

from app.rag.text import normalize

_INSTRUCTION = re.compile(
    normalize(
        r"ignore (all |any |the )?(previous|prior|above|earlier|your)? ?(instructions|rules|prompts?)"
        r"|disregard (all |any |the )?(previous|prior|above|your)? ?(instructions|rules)"
        r"|forget (all |your )?(previous )?(instructions|rules)"
        r"|you are now|from now on you|act as (an? )?(admin|administrator|system|developer)"
        r"|system prompt|developer (message|mode)|new instructions|override (the )?(rules|instructions)"
        r"|(call|use|invoke) the \w+ tool|cancel (all|every) appointments?|delete (all|the) (records|data)"
        r"|<\s*/?\s*(system|assistant|tool)\s*>|\[\s*(system|inst)\s*\]"
        r"|पिछले (सभी )?निर्देश|निर्देशों को (अनदेखा|नज़रअंदाज़)|अब तुम|सूचनांकडे दुर्लक्ष|मागील सूचना|आता तू"
    )
)
_SENTENCE = re.compile(r"[^.!?।\n]+[.!?।]?")


def neutralize(text: str) -> tuple[str, bool]:
    """Return the text without instruction-like sentences, and whether anything was removed."""
    removed = False
    kept = []
    for sentence in _SENTENCE.findall(text):
        if _INSTRUCTION.search(normalize(sentence)):
            removed = True
            kept.append("[removed: instruction-like text]")
        else:
            kept.append(sentence)
    return ("".join(kept) if removed else text), removed
