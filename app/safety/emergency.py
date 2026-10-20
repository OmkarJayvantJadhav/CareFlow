"""Emergency check, run on every patient message before any planning (FR-02, FR-03).

Two stages, tuned for recall: hand-written patterns in English, Hindi, Marathi
and romanised Hindi/Marathi, grouped by what is happening (heart, breathing,
not responding, stroke, bleeding, seizures, self-harm, poisoning, allergy,
injuries, pregnancy), then a small character n-gram classifier that catches
paraphrases the patterns miss. A specific pattern ("crushing chest pain", "not
breathing") flags on its own; a generic word ("poison", "accident", "fits") flags
only when the classifier also gives it some probability, and the classifier alone
flags above its cross-validated threshold.

Patterns are checked clause by clause: a clause that talks about the past
("had a seizure as a toddler", "fainted once in 2023") does not count unless it
also says "now", so a routine follow-up is not blocked while "fine for years,
but right now he is fitting" still is. Questions about the emergency department
or the ambulance number are information requests, not emergencies.
"""

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from app.rag.text import normalize, tokenize
from app.safety.emergency_data import EMERGENCY_EXAMPLES, NON_EMERGENCY_EXAMPLES

# python -m app.safety.emergency_tune prints recall and false alarms per threshold (5-fold CV on the
# training data). A generic-word pattern needs the classifier at its >= 99% recall level (0.2). The
# classifier alone flags at 0.6 (CV recall 90%, false alarms 4%): the highest threshold that kept every
# development emergency, after 0.45 flagged ordinary booking sentences (D-53).
CLASSIFIER_THRESHOLD = 0.6
WEAK_PATTERN_THRESHOLD = 0.2
# Very short messages ("हो", "नहीं", "ok") are out of the classifier's range: only patterns apply.
CLASSIFIER_MIN_WORDS = 4

# Patterns grouped by what is happening, not by keyword. Each is matched per clause.
_PATTERNS = {
    "en": [
        # heart
        r"chest (pain|ache|tightness|pressure|heaviness|discomfort)", r"pain in (my |his |her |the )?chest",
        r"chest (is |feels )?(tight|heavy|hurting|burning badly|crushing)", r"(crushing|squeezing|heavy) (pain|pressure)",
        r"pain (spreading|radiating|going|moving) (to|into|down) (my |his |her |the )?(left )?(arm|jaw|neck|back)",
        r"heart attack", r"cardiac arrest",
        # breathing
        r"(can'?t|cannot|can not|unable to|not able to|struggling to|hard to|difficult to) (breathe?|catch (my|his|her) breath)",
        r"(trouble|difficulty|problem) breathing", r"struggling for (air|breath)", r"short(ness)? of breath", r"breathless",
        r"gasping", r"chok(ing|ed)", r"(not|isn'?t|is not|stopped|stop) breathing",
        r"(lips|face|skin|fingers) (are |is |look |looks |turning |turned |going )+(blue|grey|gray)", r"turning blue",
        # not responding
        r"unconscious", r"unresponsive", r"(not|isn'?t|is not|aren'?t|stopped) (responding|answering|reacting|moving)",
        r"no response", r"(won'?t|will not|can'?t|cannot|not) (wake|waking)( (him|her|them))?( up)?", r"passed out",
        r"collaps(e|ed|ing)", r"blacked out", r"faint(ed|ing)", r"(fell|fallen) (down )?and (is |isn'?t |hasn'?t |can'?t |won'?t |not )",
        # stroke
        r"stroke", r"face (is |has )?(droop|drooping|drooped|hanging|fallen)", r"(droop|drooped|drooping)\b.{0,25}\bside",
        r"slurr(ed|ing)", r"(mixing|jumbling|mixed) up (his |her |my |their )?words", r"(garbled|confused|strange) speech",
        r"(can'?t|cannot|unable to|not able to) (lift|raise|move|hold|feel) (his |her |my |their )?(left |right )?(arm|hand|leg|side|cup)",
        r"one side of (my|his|her|the|their) (body|face)", r"paraly(sis|sed)",
        r"(sudden(ly)?|all of a sudden)\b.{0,30}\b(weak|numb|paraly|cannot speak|can'?t speak|confus|blind|can'?t see|lost (his|her|my) (vision|sight))",
        r"(lost|loss of|losing) (the )?(vision|sight)( in| from| of)? one eye", r"can'?t see (out of|from|with) one eye",
        # bleeding
        r"(severe|heavy|a lot of|lots of|uncontrolled|non-?stop|profuse|serious) bleeding",
        r"bleeding (heavily|a lot|badly|profusely|won'?t stop|will not stop|non-?stop|doesn'?t stop)",
        r"(won'?t|will not|doesn'?t|does not|isn'?t|not) stop(ping)? bleeding",
        r"blood (is )?(spurting|pouring|gushing|everywhere|squirting|won'?t stop)", r"(spurting|gushing|pouring) blood",
        r"(vomit(ing|ed|s)?|cough(ing|ed|s)?( up)?) blood", r"blood in (the |his |her )?(vomit|cough)",
        r"(head|mouth|nose|ear) (is )?bleeding", r"bleeding from (the |his |her |my )?(head|mouth|ear)",
        # seizures
        r"seizure", r"convuls", r"\bfits?\b(?! (certificate|for|to|in|me|well))", r"fitting", r"epilep",
        # self-harm
        r"suicid", r"kill (myself|himself|herself)", r"end (my|his|her) life", r"end it all", r"want to die",
        r"(don'?t|do not|no longer) want to (live|be alive)", r"no (point|reason|use) (in )?(living|being alive|to live)",
        r"(saying |say )?goodbye (to everyone|forever|for the last time)", r"(my|a) last (message|note|letter)",
        r"self[- ]?harm", r"(hurt|cut|harm) (myself|himself|herself)",
        # poisoning and overdose
        r"overdos", r"too many (pills|tablets|sleeping pills|medicines)", r"poison",
        r"(swallowed|took|taken|ate|eaten|had|drank|drunk|consumed|gulped)\b.{0,30}\b(whole|entire|all|full|many|lot of|bunch of|strip|bottle|packet|handful)\b.{0,30}\b(pills?|tablets?|medicines?|medication|capsules?)",
        r"(drank|drunk|drink|swallowed|consumed|ate|took|had|has taken) (some |a lot of |the )?(pesticide|insecticide|bleach|acid|kerosene|phenyl|rat poison|toilet cleaner|cleaning liquid|harpic)",
        r"pesticide", r"insecticide", r"kerosene", r"rat (poison|killer)",
        # allergy
        r"anaphyla", r"(throat|tongue|lips?|face|mouth|eyes)\b.{0,20}\b(swelling|swollen|swelled|closing|puffing|puffed)",
        r"(swelling|swollen|swelled) (of )?(the |my |his |her )?(throat|tongue|lips?|face)", r"(can'?t|cannot|unable to) swallow",
        r"allergic reaction", r"(stung|stings|bitten|bite)\b.{0,50}\b(swell|swollen|breath)", r"hives all over",
        # injuries and burns
        r"(severe|serious|major|bad|deep) (burns?|injury|wound|cut)", r"burn(t|ed)? (badly|severely)", r"boiling (water|oil|milk)",
        r"skin (came|is coming|has come) off", r"skin (is )?peel(ing|ed) off", r"accident", r"hit by (a |an )?(car|bus|truck|bike|vehicle|auto|train)",
        r"head injury", r"(fell|fallen|falling) (from|off) (a |the )?(height|ladder|roof|stairs|building|terrace|tree|balcony|bike)",
        r"electric shock", r"electrocut", r"drown", r"bone (is )?sticking out",
        r"snake ?bite", r"(bitten|bit) by a snake", r"snake bit", r"scorpion",
        # pregnancy and children
        r"labou?r pains?", r"water(s)? (has |have )?broke", r"bleeding (in|during) (the )?pregnancy",
        r"pregnant\b.{0,40}\b(bleeding|severe pain|fits|seizure|fainted)",
        r"(baby|child|toddler|infant|newborn|son|daughter)\b.{0,30}\b(limp|blue|not breathing|isn'?t breathing|unresponsive|not moving)",
        # other red flags
        r"worst headache", r"sudden (severe )?headache", r"thunderclap", r"severe (abdominal|stomach|belly) pain",
        r"(this is|it'?s|it is) an emergency", r"emergency[,!. ]+(please|help|now)", r"(please )?help (me|us)? ?(now|quickly|fast|urgently)",
        r"(call|send|need|get|want) (an |the )?ambulance", r"ambulance (now|quickly|urgently|please)", r"\bdying\b",
    ],
    "hi": [
        r"(सीने|छाती) (में|पर) (दर्द|जकड़न|भारीपन|दबाव|भारी दबाव|जलन)", r"सीना (दर्द|दुख|भारी)", r"(दिल का दौरा|हार्ट अटैक)",
        r"(बायां|बाएं|बाया|बाये) (हाथ|बाजू).{0,20}(सुन्न|दर्द)",
        r"(सांस|साँस) (नहीं|ले नहीं|लेने में|फूल|रुक|अटक)", r"दम घुट", r"(होंठ|होठ|चेहरा) नीले", r"नीला पड़",
        r"बेहोश", r"होश (नहीं|में नहीं)", r"(कोई )?(जवाब|जबाब) नहीं (दे|दें)", r"उठ नहीं (रहे|रहीं|रहा|रही)", r"हिलाने पर भी",
        r"गिर (पड़|पड|गए|गई|गया).{0,30}(होश|जवाब|बोल नहीं|उठ नहीं|खून)", r"चक्कर (खाकर|आकर) गिर",
        r"(बहुत|ज़्यादा|ज्यादा) खून", r"खून (बह|नहीं रुक|रुक नहीं|निकल रहा|आ रहा|फव्वारे)", r"खून की उल्टी", r"उल्टी में खून", r"सिर से खून",
        r"लकवा", r"(मुंह|मुँह|चेहरा) (टेढ़ा|टेढा|एक तरफ|लटक)", r"(बोल|बोलने में) (नहीं पा|नहीं सक|लड़खड़ा|अटक)",
        r"अचानक.{0,30}(कमज़ोरी|कमजोरी|सुन्न|दिखना बंद|दिखाई नहीं|बोल नहीं)", r"(एक )?(आंख|आँख) से दिखना बंद",
        r"(हाथ|पैर) (नहीं उठ|उठा नहीं|हिला नहीं)",
        r"दौरा (पड़|पड)", r"मिर्गी", r"झटके (आ|लग)",
        r"आत्महत्या", r"जान (देना|दे दूं|दे दूँ|दे दूंगा|दे दूंगी)", r"मर जाना", r"मरना चाहत", r"खुद को (नुकसान|चोट|खत्म)",
        r"जीने का (कोई )?(मतलब|फायदा|फ़ायदा)", r"जीना नहीं चाहत", r"(सबको )?अलविदा", r"(आख़िरी|आखिरी) (मैसेज|संदेश|चिट्ठी)",
        r"(ज़हर|जहर)", r"(ज़्यादा|ज्यादा|सारी|सब|पूरी|बहुत सारी|ढेर सारी) (गोलियां|गोलियाँ|दवा|दवाइयां|टैबलेट)", r"कीटनाशक",
        r"चूहे (मारने|मार) की", r"फिनाइल (पी|पिया|पी लिया)", r"तेज़ाब (पी|पिया)",
        r"(होंठ|होठ|जीभ|गला|गले|चेहरा|चेहरे)\b.{0,15}(सूज|फूल)", r"(पूरा )?शरीर फूल", r"गला (भारी|बंद)", r"निगल नहीं",
        r"(दुर्घटना|एक्सीडेंट)", r"सिर (में|पर) (गहरी )?चोट", r"(बुरी तरह|बहुत) जल", r"उबलते (पानी|तेल)", r"खाल (उतर|निकल)",
        r"(सीढ़ी|छत|ऊंचाई|पेड़) से गिर", r"करंट लग", r"डूब", r"(सांप|साँप) (ने )?काट", r"बिच्छू",
        r"प्रसव (पीड़ा|पीडा|दर्द)", r"पानी की थैली", r"गर्भ.{0,20}खून",
        r"पेट में (बहुत |असहनीय )?(तेज़|तेज|असहनीय) दर्द",
        r"इमरजेंसी (है|हो गई)", r"एम्बुलेंस (भेज|बुला|चाहिए)", r"एंबुलेंस (भेज|बुला|चाहिए)",
    ],
    "mr": [
        r"छातीत (दुख|कळ|वेदना|जड|दाब)", r"छाती (दुख|जड)", r"छातीवर (दाब|जड)", r"(हृदयविकाराचा झटका|हार्ट अटॅक|हार्ट अटैक)",
        r"डावा हात.{0,20}(बधिर|सुन्न|दुख)",
        r"श्वास (घेता येत नाही|घेण्यास त्रास|घ्यायला त्रास|घेताना त्रास|लागत|थांब|कोंड)", r"दम (लागत|कोंड)", r"धाप लाग",
        r"(ओठ|चेहरा) निळे", r"निळा पड", r"निळी पड", r"निळे पड",
        r"बेशुद्ध", r"शुद्ध (हरप|गेली|नाही)", r"(काहीच |काही )?(उत्तर|प्रतिसाद) (देत नाही|देत नाहीत|देईना)", r"उठत (नाही|नाहीत)",
        r"चक्कर येऊन पड", r"कोसळ",
        r"खूप रक्त", r"रक्तस्त्राव", r"रक्तस्राव", r"रक्त (थांबत नाही|वाहत|येत|येतंय|येते)", r"रक्ताची उलटी", r"डोक्यातून रक्त",
        r"अर्धांगवायू", r"लकवा", r"तोंड वाकड", r"चेहरा (एका बाजूला|वाकड)", r"बोलता येत नाही", r"बोलणे.{0,15}(अडखळ|बिघड|अस्पष्ट)",
        r"अचानक.{0,30}(अशक्त|बधिर|दिसेनासे|दिसत नाही|बोलता)", r"(हात|पाय) (उचलता|हलवता|उचलताच|हलवताच) येत नाही",
        r"फिट (आली|येत|आल)", r"झटके (येत|आले|येताहेत)", r"मिरगी",
        r"आत्महत्या", r"जीव द्या", r"मरायचे आहे", r"मरायचं आहे", r"स्वतःला (इजा|संपव)", r"जगायचे नाही", r"जगायचं नाही", r"जगण्यात (काही )?अर्थ नाही",
        r"शेवटचा (मेसेज|संदेश)",
        r"विष (प्या|प्याल|घेत|खाल)", r"विषबाधा", r"कीटकनाशक", r"उंदीर मारायचे", r"फिनाईल (प्या|प्याय|घेत)", r"ॲसिड (प्या|प्याय)",
        r"(जास्त|सगळ्या|सर्व|खूप|पूर्ण) गोळ्या",
        r"(ओठ|जीभ|घसा|चेहरा|डोळे)\b.{0,15}सुज", r"अंगभर (गांधी|पित्त|पुरळ)", r"आवाज घोगरा", r"गिळता येत नाही",
        r"अपघात", r"डोक्याला (मार|लागल)", r"(खूप|गंभीर|जास्त) भाजल", r"उकळत्या (पाण्या|तेला)", r"कातडी (निघ|सोल|गेल)",
        r"(शिडी|गच्ची|छत|जिन्या|झाड)(ा)?(वरून|वर्षी)? पडल", r"शॉक लागला", r"बुडाल", r"साप चाव", r"विंचू",
        r"प्रसूती(च्या)? कळा", r"(गर्भ|डिलिव्हरी|प्रसूत).{0,30}पाणी गेल", r"गर्भ.{0,20}रक्त",
        r"पोटात (खूप|असह्य) (दुख|वेदना)",
        r"इमर्जन्सी आहे", r"इमरजन्सी आहे", r"रुग्णवाहिका (पाठव|बोलव|हवी)", r"(ॲम्ब्युलन्स|अ‍ॅम्ब्युलन्स|एम्बुलन्स) (पाठव|बोलव|हवी)",
    ],
    "roman": [
        r"seene me(in)? (dard|dabav|bhari)", r"chhati me(in)? dard", r"chaati me(in)? dard", r"saans (nahi|nahin|lene me|ruk)", r"sans (nahi|nahin|lene me)",
        r"behosh", r"hosh (nahi|me nahi)", r"jawab nahi de", r"bahut khoon", r"khoon (beh|nahi ruk)", r"zehar", r"jahar",
        r"atmahatya", r"aatmahatya", r"(saari|sab|sari) goliyan kha", r"marna chaht", r"jaan de",
        r"chhatit (dukh|kal)", r"shwas (gheta yet nahi|ghenyas tras)", r"beshuddh", r"apghat", r"lakwa", r"daura pad",
        r"jagaycha nahi", r"jagaychi ichha nahi", r"swatahala sampav", r"uttar det nahi", r"shuddh(ivar)? nahi", r"undir marayche",
    ],
}  # fmt: skip

# Patterns are normalised like the text they are matched against (lower case, no nukta).
_COMPILED = [(lang, re.compile(normalize(p))) for lang, patterns in _PATTERNS.items() for p in patterns]

# Single words that also appear in questions, idioms and plans ("poison control", "this queue is
# killing me", "the accident ward"). They flag only if the classifier agrees a little.
_WEAK = {
    normalize(p)
    for p in (
        r"poison",
        r"pesticide",
        r"insecticide",
        r"kerosene",
        r"rat (poison|killer)",
        r"overdos",
        r"accident",
        r"\bdying\b",
        r"\bfits?\b(?! (certificate|for|to|in|me|well))",
        r"seizure",
        r"epilep",
        r"stroke",
        r"drown",
        r"electric shock",
        r"electrocut",
        r"scorpion",
        r"faint(ed|ing)",
        r"collaps(e|ed|ing)",
        r"head injury",
        r"(ज़हर|जहर)",
        r"(दुर्घटना|एक्सीडेंट)",
        r"डूब",
        r"करंट लग",
        r"बिच्छू",
        r"मिर्गी",
        r"अपघात",
        r"विषबाधा",
        r"बुडाल",
        r"शॉक लागला",
        r"विंचू",
        r"मिरगी",
        r"कोसळ",
        r"zehar",
        r"jahar",
        r"apghat",
    )
}

# Breathlessness that only comes on with exertion is a reason for an OPD visit, not an emergency.
_MILD = {
    normalize(p)
    for p in (
        r"short(ness)? of breath",
        r"breathless",
        r"धाप लाग",
        r"(सांस|साँस) (नहीं|ले नहीं|लेने में|फूल|रुक|अटक)",
        r"दम (लागत|कोंड)",
    )
}
_EXERTION = re.compile(
    normalize(
        r"(when|while|on|after) (walking|climbing|running|exercis|exertion)|climbing stairs|चलने पर|चलते समय|सीढ़ियां चढ़|सीढ़ियाँ चढ़|चालताना|जिना चढताना|जिने चढताना|व्यायाम"
    )
)

# Something that happened in the past, said in the same clause as the symptom ("had a seizure as a
# toddler", "fainted once in 2023", "भाजले होते, जखम भरली आहे"). "two hours ago" is not history.
_HISTORY = re.compile(
    normalize(
        r"last (week|month|year)|(days|weeks|months|years) ago|\b(19|20)\d\d\b|history of|follow[- ]?up|check[- ]?up|"
        r"as a (child|kid|baby|toddler|teenager)|when (i|he|she) was (a |an )?(child|kid|baby|toddler|young|\d+)|childhood|"
        r"\bonce\b|in the past|(has|have) been (fine|well|normal|ok)|healed|recovered|investigated|routine|annual|review|"
        r"पिछले (साल|महीने|हफ्ते)|(साल|महीने|हफ्ते|हफ़्ते|दिन) पहले|बचपन में|ठीक हो गया|ठीक है|"
        r"मागच्या (वर्षी|महिन्यात|आठवड्यात)|(वर्षा|वर्षां|महिन्या|महिन्यां|आठवड्या|आठवड्यां|दिवसां)पूर्वी|लहानपणी|बरे झाले|भरली आहे|"
        r"काही त्रास नाही|तपासणी|follow"
    )
)
# Said with a history phrase, these still mean "now": "fine for years, but right now he is fitting".
_NOW = re.compile(
    normalize(
        r"\b(now|right now|currently|at the moment|just now|since (this )?(morning|an hour|\d+)|for the (last|past) \d+ (min|minutes|hour)|"
        r"started|suddenly|won'?t stop|isn'?t stopping)\b|अभी|आत्ता|आता|अचानक|अब (भी)?|सुबह से"
    )
)
_CLAUSES = re.compile(normalize(r"[.;!?\n]+|,|\bbut\b|\band\b|\bthough\b|लेकिन|पर |और |पण |परंतु|आणि "))
_NEGATION = re.compile(
    r"(\b(no|not|without|never|don'?t have|do not have|isn'?t|no sign of)\b|नहीं|नाही|बिना|शिवाय)\s*\S*\s*\S*$"
)
# Questions about the emergency department or ambulance service are information requests.
_INFO = re.compile(
    normalize(
        r"emergency (department|ward|room|dept|admission|number|services?|entrance|unit)|ambulance (number|service|charges?|fees?|cost)|"
        r"(इमरजेंसी|आपातकालीन) (विभाग|वार्ड)|आपातकालीन|इमर्जन्सी (विभाग|वॉर्ड)|आपत्कालीन विभाग"
    )
)


@dataclass(frozen=True)
class EmergencyResult:
    is_emergency: bool
    reason: str = ""
    score: float = 0.0


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSES.split(text) if c and c.strip()]


def _rule_match(text: str) -> tuple[str, bool] | None:
    """The first pattern that matches outside a past/negated context, and whether it is a weak one."""
    for clause in _clauses(text):
        past = _HISTORY.search(clause) and not _NOW.search(clause)
        if past:
            continue
        for _lang, pattern in _COMPILED:
            for match in pattern.finditer(clause):
                before = clause[max(0, match.start() - 30) : match.start()]
                if _NEGATION.search(before):
                    continue
                if pattern.pattern in _MILD and _EXERTION.search(text):
                    continue
                return pattern.pattern, pattern.pattern in _WEAK
    return None


TRAINING_FILE = Path(__file__).with_name("emergency_training.jsonl")


def training_data() -> tuple[list[str], list[int]]:
    """Hand-written examples plus the larger training file (never the evaluation sets)."""
    texts = list(EMERGENCY_EXAMPLES) + list(NON_EMERGENCY_EXAMPLES)
    labels = [1] * len(EMERGENCY_EXAMPLES) + [0] * len(NON_EMERGENCY_EXAMPLES)
    for line in TRAINING_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            texts.append(row["text"])
            labels.append(int(row["label"]))
    return [normalize(t) for t in texts], labels


def build_classifier():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline, make_union

    features = make_union(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
        TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"[^\s,.!?;:()]+"),
    )
    return make_pipeline(features, LogisticRegression(C=8.0, class_weight="balanced", max_iter=3000, random_state=0))


class _Classifier:
    _lock = threading.Lock()
    _model = None

    @classmethod
    def model(cls):
        with cls._lock:
            if cls._model is None:
                texts, labels = training_data()
                cls._model = build_classifier().fit(texts, labels)
            return cls._model


def check_emergency(message: str) -> EmergencyResult:
    text = normalize(message)
    rule = _rule_match(text)
    if rule and not rule[1]:
        return EmergencyResult(True, f"pattern:{rule[0]}", 1.0)
    probability = float(_Classifier.model().predict_proba([text])[0][1])
    if rule and probability >= WEAK_PATTERN_THRESHOLD and not _INFO.search(text):
        return EmergencyResult(True, f"pattern:{rule[0]}+classifier", probability)
    if len(tokenize(text)) < CLASSIFIER_MIN_WORDS:
        return EmergencyResult(False, "", probability)
    if probability >= CLASSIFIER_THRESHOLD and not _HISTORY.search(text) and not _INFO.search(text):
        return EmergencyResult(True, "classifier", probability)
    return EmergencyResult(False, "", probability)
