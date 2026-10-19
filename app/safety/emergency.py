"""Emergency check, run on every patient message before any planning (FR-02, FR-03).

Two stages, tuned for recall: hand-written patterns in English, Hindi, Marathi
and romanised Hindi/Marathi, then a small character n-gram classifier that
catches paraphrases the patterns miss. Either stage can flag an emergency.
A short list of history phrases ("last year", "follow-up after") stops a
pattern match about a past event from blocking a routine booking.
"""

import re
import threading
from dataclasses import dataclass

from app.rag.text import normalize
from app.safety.emergency_data import EMERGENCY_EXAMPLES, NON_EMERGENCY_EXAMPLES

CLASSIFIER_THRESHOLD = 0.85

_PATTERNS = {
    "en": [
        r"chest (pain|ache|tightness|pressure)", r"pain in (my |his |her |the )?chest", r"chest (is |feels )?(tight|heavy|hurting|burning badly)",
        r"heart attack", r"cardiac arrest",
        r"(can'?t|cannot|can not|unable to|not able to|struggling to|hard to|difficult to) breathe?", r"(trouble|difficulty|problem) breathing",
        r"short(ness)? of breath", r"breathless", r"gasping", r"chok(ing|ed)", r"not breathing", r"stopped breathing",
        r"unconscious", r"unresponsive", r"faint(ed|ing)", r"passed out", r"collapsed?", r"blacked out", r"not waking up", r"won'?t wake up",
        r"(severe|heavy|a lot of|lots of|uncontrolled|non-?stop|profuse) bleeding", r"bleeding (heavily|a lot|badly|won'?t stop|will not stop|non-?stop)",
        r"(vomit(ing|ed)?|cough(ing|ed)?( up)?) blood", r"blood in (vomit|cough)",
        r"stroke", r"face (is )?droop", r"slurr(ed|ing) speech", r"(sudden|suddenly)\b.{0,30}\b(weak|numb|paraly|cannot speak|can'?t speak|confus|blind)",
        r"one side of (my|his|her|the) (body|face)", r"paraly(sis|sed)",
        r"seizure", r"convuls", r"\bfits\b", r"(having|had) a fit", r"epilep",
        r"suicid", r"kill (myself|himself|herself)", r"end (my|his|her) life", r"want to die", r"self[- ]?harm", r"hurt (myself|himself|herself)",
        r"overdos", r"too many (pills|tablets|sleeping pills)", r"poison",
        r"(drank|drunk|drink|swallowed|consumed|ate|took|had|has taken) (some |a lot of |the )?(pesticide|insecticide|bleach|acid|kerosene|phenyl|rat poison|toilet cleaner|cleaning liquid|harpic)",
        r"pesticide", r"insecticide", r"kerosene", r"rat poison",
        r"(severe|serious|major|bad|road) (burn|injury|accident)", r"accident", r"hit by (a |an )?(car|bus|truck|bike|vehicle|auto)", r"head injury",
        r"fell from", r"electric shock", r"drown",
        r"anaphyla", r"(throat|tongue|lips?|face) (is |are )?(swelling|swollen|closing)", r"allergic reaction",
        r"snake ?bite", r"bitten by a snake", r"scorpion",
        r"labou?r pains?", r"water(s)? (has |have )?broke", r"bleeding (in|during) pregnancy", r"pregnant (and|with) (bleeding|severe pain)",
        r"turning blue", r"lips (are |look )?blue", r"baby (is )?(limp|not breathing|blue)",
        r"worst headache", r"sudden (severe )?headache", r"severe (abdominal|stomach|belly) pain",
        r"emergency(?! (department|ward|room|dept))", r"ambulance", r"dying",
    ],
    "hi": [
        r"सीने में (दर्द|जकड़न|भारीपन)", r"छाती में (दर्द|जकड़न|भारीपन)", r"सीना (दर्द|दुख)",
        r"दिल का दौरा", r"हार्ट अटैक",
        r"सांस (नहीं|ले नहीं|लेने में|फूल|रुक)", r"साँस (नहीं|ले नहीं|लेने में|फूल|रुक)", r"दम घुट",
        r"बेहोश", r"होश नहीं", r"गिर (पड़|पड)", r"चक्कर (खाकर|आकर) गिर",
        r"(बहुत|ज़्यादा|ज्यादा) खून", r"खून (बह|नहीं रुक|रुक नहीं)", r"खून की उल्टी", r"उल्टी में खून",
        r"लकवा", r"मुंह (टेढ़ा|टेढा)", r"मुँह (टेढ़ा|टेढा)", r"बोल नहीं (पा|सक)", r"अचानक.{0,20}(कमज़ोरी|कमजोरी|सुन्न)",
        r"दौरा (पड़|पड)", r"मिर्गी", r"झटके",
        r"आत्महत्या", r"जान (देना|दे दूं|दे दूँ)", r"मर जाना", r"मरना चाहत", r"खुद को (नुकसान|चोट)",
        r"(ज़हर|जहर)", r"(ज़्यादा|ज्यादा) (गोलियां|गोलियाँ|दवा) खा", r"कीटनाशक", r"फिनाइल (पी|पिया|पी लिया)", r"तेज़ाब (पी|पिया)",
        r"(दुर्घटना|एक्सीडेंट)", r"सिर (में|पर) चोट", r"जल (गया|गई|गए)", r"करंट लग", r"डूब",
        r"(सांप|साँप) (ने )?काट", r"बिच्छू",
        r"प्रसव (पीड़ा|पीडा|दर्द)", r"पानी की थैली", r"गर्भ.{0,20}खून",
        r"होंठ नीले", r"नीला पड़",
        r"गले में सूजन", r"जीभ (में )?सूजन",
        r"पेट में (बहुत )?तेज़ दर्द", r"पेट में (बहुत )?तेज दर्द",
        r"इमरजेंसी(?! विभाग)", r"आपातकाल", r"एम्बुलेंस", r"एंबुलेंस",
    ],
    "mr": [
        r"छातीत (दुख|कळ|वेदना|जड|दाब)", r"छाती दुख",
        r"हृदयविकाराचा झटका", r"हार्ट अटॅक", r"हार्ट अटैक",
        r"श्वास (घेता येत नाही|घेण्यास त्रास|घ्यायला त्रास|घेताना त्रास|लागत|थांब|कोंड)", r"दम (लागत|कोंड)", r"धाप लाग",
        r"बेशुद्ध", r"शुद्ध (हरप|गेली|नाही)", r"चक्कर येऊन पड", r"कोसळ",
        r"खूप रक्त", r"रक्तस्त्राव", r"रक्तस्राव", r"रक्त (थांबत नाही|वाहत)", r"रक्ताची उलटी",
        r"अर्धांगवायू", r"लकवा", r"तोंड वाकड", r"बोलता येत नाही", r"अचानक.{0,20}(अशक्त|बधिर)",
        r"फिट (आली|येत|आल)", r"झटके", r"मिरगी",
        r"आत्महत्या", r"जीव द्या", r"मरायचे आहे", r"मरायचं आहे", r"स्वतःला इजा",
        r"विष (प्या|प्याल|घेत|खाल)", r"विषबाधा", r"कीटकनाशक", r"फिनाईल (प्या|प्याय|घेत)", r"ॲसिड (प्या|प्याय)", r"जास्त गोळ्या",
        r"अपघात", r"डोक्याला (मार|लागल)", r"भाजल", r"शॉक लागला", r"बुडाल",
        r"साप चाव", r"विंचू",
        r"प्रसूती(च्या)? कळा", r"(गर्भ|डिलिव्हरी|प्रसूत).{0,30}पाणी गेल", r"गर्भ.{0,20}रक्त",
        r"ओठ निळे", r"निळा पड", r"निळी पड",
        r"घसा सुज", r"जीभ सुज",
        r"पोटात (खूप|असह्य) (दुख|वेदना)",
        r"इमर्जन्सी(?! विभाग)", r"इमरजन्सी(?! विभाग)", r"आणीबाणी", r"रुग्णवाहिका", r"ॲम्ब्युलन्स", r"अ‍ॅम्ब्युलन्स", r"एम्बुलन्स",
    ],
    "roman": [
        r"seene me(in)? dard", r"chhati me(in)? dard", r"chaati me(in)? dard", r"saans (nahi|nahin|lene me)", r"sans (nahi|nahin|lene me)",
        r"behosh", r"hosh nahi", r"bahut khoon", r"khoon (beh|nahi ruk)", r"zehar", r"jahar", r"atmahatya", r"aatmahatya",
        r"chhatit dukh", r"chhatit kal", r"shwas (gheta yet nahi|ghenyas tras)", r"beshuddh", r"apghat", r"lakwa", r"daura pad",
    ],
}  # fmt: skip

# Patterns are normalised like the text they are matched against (lower case, no nukta).
_COMPILED = [(lang, re.compile(normalize(p))) for lang, patterns in _PATTERNS.items() for p in patterns]

# Breathlessness that only comes on with exertion is a reason for an OPD visit, not an emergency.
_MILD = {
    normalize(p)
    for p in (
        r"short(ness)? of breath",
        r"breathless",
        r"धाप लाग",
        r"सांस (नहीं|ले नहीं|लेने में|फूल|रुक)",
        r"साँस (नहीं|ले नहीं|लेने में|फूल|रुक)",
    )
}
_EXERTION = re.compile(
    normalize(
        r"(when|while|on) (walking|climbing|running|exercis|exertion)|climbing stairs|चलने पर|चलते समय|सीढ़ियां चढ़|सीढ़ियाँ चढ़|चालताना|जिना चढताना|जिने चढताना|व्यायाम"
    )
)

_HISTORY = re.compile(
    r"(last (week|month|year)|(months|years) ago|history of|follow[- ]?up after|check[- ]?up after|"
    r"पिछले (साल|महीने)|साल पहले|महीने पहले|मागच्या (वर्षी|महिन्यात)|वर्षापूर्वी|महिन्यांपूर्वी)"
)
_NEGATION = re.compile(
    r"(\b(no|not|without|never|don'?t have|do not have|isn'?t|no sign of)\b|नहीं|नाही|बिना|शिवाय)\s*\S*\s*\S*$"
)


@dataclass(frozen=True)
class EmergencyResult:
    is_emergency: bool
    reason: str = ""
    score: float = 0.0


def _rule_match(text: str) -> str | None:
    for _lang, pattern in _COMPILED:
        for match in pattern.finditer(text):
            before = text[max(0, match.start() - 30) : match.start()]
            if _NEGATION.search(before):
                continue
            if pattern.pattern in _MILD and _EXERTION.search(text):
                continue
            return pattern.pattern
    return None


class _Classifier:
    _lock = threading.Lock()
    _model = None

    @classmethod
    def model(cls):
        with cls._lock:
            if cls._model is None:
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.linear_model import LogisticRegression
                from sklearn.pipeline import make_pipeline

                texts = [normalize(t) for t in EMERGENCY_EXAMPLES + NON_EMERGENCY_EXAMPLES]
                labels = [1] * len(EMERGENCY_EXAMPLES) + [0] * len(NON_EMERGENCY_EXAMPLES)
                pipeline = make_pipeline(
                    TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
                    LogisticRegression(C=8.0, class_weight="balanced", max_iter=2000, random_state=0),
                )
                pipeline.fit(texts, labels)
                cls._model = pipeline
            return cls._model


def check_emergency(message: str) -> EmergencyResult:
    text = normalize(message)
    rule = _rule_match(text)
    if rule and not _HISTORY.search(text):
        return EmergencyResult(True, f"pattern:{rule}", 1.0)
    probability = float(_Classifier.model().predict_proba([text])[0][1])
    if probability >= CLASSIFIER_THRESHOLD and not _HISTORY.search(text):
        return EmergencyResult(True, "classifier", probability)
    return EmergencyResult(False, "", probability)
