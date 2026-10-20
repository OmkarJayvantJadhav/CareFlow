"""Prompt-injection defence for retrieved documents.

Retrieved text is always given to the model as quoted data. In addition, any
sentence that reads like an instruction to the assistant is removed before the
text reaches the model, and the removal is reported so it can be traced.
"""

import re

from app.rag.text import normalize

# Hospital documents describe the hospital in the third person. A sentence that addresses the assistant,
# or orders something done to "every user" or "without asking", is not hospital information.
_INSTRUCTION = re.compile(
    normalize(
        # telling the model to drop its rules
        r"ignore (all |any |the )?(previous|prior|above|earlier|your|hospital'?s?)? ?(instructions|rules|prompts?|information)"
        r"|disregard (all |any |the )?(previous|prior|above|your)? ?(instructions|rules)"
        r"|forget (all |your )?(previous )?(instructions|rules)"
        r"|you are now|from now on|act as (an? )?(admin|administrator|system|developer)|reprogram|jailbreak"
        r"|system prompt|developer (message|mode)|new instructions|\boverride\b"
        r"|system (notice|note|message|update|instruction)"
        # addressing the assistant (the documents never do)
        r"|\b(assistant|chat ?bot|bot|ai|language model|llm)\b"
        r"|(note|message|instructions?|notice|memo) (to|for) (the )?(assistant|staff member reading|model|system)"
        # orders about users or actions
        r"|(tell|ask|inform|instruct|advise|direct|remind) (every|all|each|any) (users?|patients?|callers?|visitors?)"
        r"|\b(every|all|each) (users?|patients?) who (asks?|contacts?|writes?|messages?)"
        r"|without (asking|confirmation|confirming|their consent|consent)"
        r"|(start|end|begin|prefix) (every|each|all|your) (answer|reply|response|message)"
        r"|(reply|respond|answer) (only|exactly) with|do not (cite|mention|reveal|show) (any )?(sources?|this)"
        r"|(must|should|have to|need to) (immediately )?(cancel|book|delete|reveal|share|send|reschedule|open)"
        r"|(call|use|invoke) the \w+ tool|cancel (all|every) (upcoming )?appointments?|delete (all|the) (records|data)"
        r"|<\s*/?\s*(system|assistant|tool)\s*>|\[\s*(system|inst)\s*\]"
        # Hindi and Marathi
        r"|पिछले (सभी )?निर्देश|निर्देशों को (अनदेखा|नज़रअंदाज़)|अब तुम|अब से|असिस्टेंट|चैटबॉट|सहायक (को|के लिए)"
        r"|(हर|सभी|प्रत्येक) (उपयोगकर्ता|मरीज़|मरीजों|मरीज़ों|यूज़र)\S* को"
        r"|सूचनांकडे दुर्लक्ष|मागील सूचना|आता तू|असिस्टंट|चॅटबॉट|सहाय्यकाने|सहाय्यकासाठी"
        r"|(सर्व|प्रत्येक) (रुग्णांना|रुग्णाला|वापरकर्त्यांना|वापरकर्त्याला)"
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
