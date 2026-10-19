"""Output rule for medical advice (FR-04): the assistant never names medicines or doses.

Applied to every reply the LLM writes. If the reply mentions a medicine or a
dosing instruction it is replaced by a fixed refusal that points to a doctor.
Knowledge-base text is written without medicine names, so grounded answers are
not affected.
"""

import re

from app.rag.text import normalize

MEDICINES = """
paracetamol acetaminophen crocin dolo calpol ibuprofen brufen combiflam aspirin disprin diclofenac voveran
nimesulide naproxen tramadol codeine morphine azithromycin amoxicillin augmentin amoxyclav ciprofloxacin
levofloxacin doxycycline metronidazole cefixime ceftriaxone penicillin metformin glimepiride gliclazide
sitagliptin omeprazole pantoprazole rabeprazole ranitidine famotidine digene gelusil cetirizine levocetirizine
allegra fexofenadine montelukast salbutamol asthalin budesonide prednisolone prednisone dexamethasone
betamethasone hydrocortisone amlodipine atenolol metoprolol losartan telmisartan ramipril enalapril
atorvastatin rosuvastatin clopidogrel warfarin ecosprin heparin levothyroxine thyronorm eltroxin ondansetron
domperidone loperamide norflox ofloxacin albendazole ivermectin fluconazole clotrimazole
पैरासिटामोल पेरासिटामोल क्रोसिन डोलो आइबुप्रोफेन इबुप्रोफेन एस्पिरिन एस्प्रिन डिक्लोफेनाक एज़िथ्रोमाइसिन
अज़िथ्रोमायसिन अमोक्सिसिलिन मेटफॉर्मिन मेटफॉर्मिन पैंटोप्राज़ोल सेट्रीज़ीन
""".split()

_MEDICINE_RE = re.compile(r"(?<![\w])(" + "|".join(re.escape(normalize(m)) for m in MEDICINES) + r")(?![\w])")
_DOSE_RE = re.compile(
    normalize(
        r"\b\d+(\.\d+)?\s?(mg|mcg|µg|ml|iu)\b"
        r"|\b(one|two|three|half|1|2|3)\s+(tablets?|pills?|capsules?|teaspoons?|spoons?)\b"
        r"|\b(once|twice|thrice|three times|four times)\s+(a|per)\s+day\b"
        r"|दिन में (एक|दो|तीन|चार) बार|दिवसातून (एकदा|दोनदा|तीनदा|दोन वेळा|तीन वेळा)"
        r"|\d+\s?(गोली|गोलियां|गोळी|गोळ्या)"
    )
)


def mentions_medication(text: str) -> bool:
    t = normalize(text)
    return bool(_MEDICINE_RE.search(t) or _DOSE_RE.search(t))
