"""Documents that follow the hospital's setup (D-139): on a hospital's own deployment the department, doctor,
floor-guide, OPD-hours, location and emergency pages are written from what its admins entered on the setup
page, in English, Hindi and Marathi, instead of the demo hospital's.

They are ordinary shipped templates as far as the knowledge base is concerned (``origin = "template"``), so an
admin can still edit or hide one (and an edited one is then left alone). They are written again whenever the
setup changes and every hour, so a doctor whose last day has passed drops out. The demo keeps the files in
``knowledge/``, which describe the same hospital as its seed data, so its evaluation results stay comparable.
"""

import re
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Department, Doctor, HospitalProfile, KbDocument
from simulator.kb import departments as shipped
from simulator.kb.common import LANGS, LANGUAGE_NAMES, WEEKDAYS, T, bullets, list_of

# The shipped templates these replace on a hospital's deployment (paths relative to the knowledge folder).
REPLACED = re.compile(
    r"^[a-z]{2}/(departments|doctors)/[^/]+\.md$"
    r"|^[a-z]{2}/facilities/(floor-guide|opd-hours|location-and-directions|emergency-department)\.md$"
)


def follows_setup() -> bool:
    return not get_settings().demo_mode


# --------------------------------------------------------------------------- well-known departments


def _t(en: str, hi: str, mr: str) -> T:
    return T(en, hi, mr)


# Departments a hospital is likely to add beyond the demo's eight: their names, what they do and why people
# come. A department matching none of these gets the parts that come from the setup only.
EXTRA = {
    "General Surgery": (
        _t("General Surgery", "सामान्य शल्य चिकित्सा (जनरल सर्जरी)", "जनरल सर्जरी (सामान्य शस्त्रक्रिया)"),
        _t(
            "The General Surgery department assesses and treats conditions that may need an operation, such as hernias, piles, gallstones, appendicitis, lumps and wounds, and follows patients up after surgery.",
            "सामान्य शल्य चिकित्सा विभाग उन बीमारियों की जांच और इलाज करता है जिनमें ऑपरेशन की ज़रूरत पड़ सकती है, जैसे हर्निया, बवासीर, पित्ताशय की पथरी, अपेंडिसाइटिस, गांठें और घाव, और ऑपरेशन के बाद मरीज़ों की जांच करता है।",
            "जनरल सर्जरी विभाग ज्या आजारांसाठी शस्त्रक्रियेची गरज पडू शकते, जसे हर्निया, मूळव्याध, पित्ताशयातील खडे, अपेंडिसायटिस, गाठी आणि जखमा, त्यांची तपासणी व उपचार करतो आणि शस्त्रक्रियेनंतर रुग्णांची तपासणी करतो.",
        ),
        [
            _t("hernia or a swelling in the groin", "हर्निया या जांघ के पास सूजन", "हर्निया किंवा जांघेजवळ सूज"),
            _t("piles, fissures and fistula", "बवासीर, फ़िशर और भगंदर", "मूळव्याध, फिशर आणि भगंदर"),
            _t(
                "gallstones and pain in the upper abdomen",
                "पित्ताशय की पथरी और पेट के ऊपरी हिस्से में दर्द",
                "पित्ताशयातील खडे आणि पोटाच्या वरच्या भागात दुखणे",
            ),
            _t("lumps, cysts and abscesses", "गांठें, सिस्ट और फोड़े", "गाठी, सिस्ट आणि गळू"),
            _t(
                "dressings and follow-up after an operation",
                "ऑपरेशन के बाद पट्टी और जांच",
                "शस्त्रक्रियेनंतर ड्रेसिंग आणि तपासणी",
            ),
        ],
        ["general surgery", "surgery", "surgeon", "general surgeon"],
    ),
    "Obstetrics and Gynaecology": (
        _t(
            "Obstetrics and Gynaecology",
            "प्रसूति एवं स्त्री रोग (ऑब्स्टेट्रिक्स और गायनेकोलॉजी)",
            "प्रसूती व स्त्रीरोग (ऑब्स्टेट्रिक्स आणि गायनॅकॉलॉजी)",
        ),
        _t(
            "The Obstetrics and Gynaecology department cares for women's health and for pregnancy, from check-ups before delivery to care after it, as well as menstrual problems and menopause.",
            "प्रसूति एवं स्त्री रोग विभाग महिलाओं के स्वास्थ्य और गर्भावस्था की देखभाल करता है, प्रसव से पहले की जांच से लेकर प्रसव के बाद की देखभाल तक, साथ ही मासिक धर्म की समस्याओं और रजोनिवृत्ति की भी।",
            "प्रसूती व स्त्रीरोग विभाग महिलांच्या आरोग्याची आणि गर्भावस्थेची काळजी घेतो, प्रसूतीपूर्व तपासणीपासून प्रसूतीनंतरच्या काळजीपर्यंत, तसेच मासिक पाळीच्या समस्या आणि रजोनिवृत्तीचीही.",
        ),
        [
            *shipped.REASONS["Gynaecology"],
            _t("check-ups after delivery", "प्रसव के बाद की जांच", "प्रसूतीनंतरची तपासणी"),
        ],
        [
            "obstetrics and gynaecology",
            "obstetrics and gynecology",
            "obstetrics",
            "ob gyn",
            "obgyn",
            "obg",
            "maternity",
        ],
    ),
    "Dentistry": (
        _t("Dentistry (dental care)", "दंत चिकित्सा (डेंटल)", "दंतचिकित्सा (डेंटल)"),
        _t(
            "The Dental department checks and treats teeth and gums, including fillings, root canal treatment, extractions, cleaning and dentures.",
            "दंत चिकित्सा विभाग दांतों और मसूड़ों की जांच और इलाज करता है, जिसमें फ़िलिंग, रूट कैनाल, दांत निकालना, सफ़ाई और नकली दांत शामिल हैं।",
            "दंतचिकित्सा विभाग दात आणि हिरड्यांची तपासणी व उपचार करतो, ज्यात फिलिंग, रूट कॅनाल, दात काढणे, स्वच्छता आणि कवळी यांचा समावेश आहे.",
        ),
        [
            _t("toothache and sensitive teeth", "दांत दर्द और दांतों में झनझनाहट", "दातदुखी आणि दात शिवशिवणे"),
            _t("bleeding or swollen gums", "मसूड़ों से खून आना या सूजन", "हिरड्यांतून रक्त येणे किंवा सूज"),
            _t(
                "cavities, fillings and root canal treatment",
                "कीड़ा लगे दांत, फ़िलिंग और रूट कैनाल",
                "कीड लागलेले दात, फिलिंग आणि रूट कॅनाल",
            ),
            _t("cleaning and check-ups", "दांतों की सफ़ाई और जांच", "दातांची स्वच्छता आणि तपासणी"),
            _t("dentures and missing teeth", "नकली दांत और टूटे दांत", "कवळी आणि पडलेले दात"),
        ],
        ["dentistry", "dental", "dentist", "dental care", "dental surgery"],
    ),
    "Psychiatry": (
        _t("Psychiatry", "मनोरोग (साइकेट्री)", "मानसोपचार (सायकिॲट्री)"),
        _t(
            "The Psychiatry department helps with mental health: stress, low mood, anxiety, sleep problems and addiction, with counselling and treatment.",
            "मनोरोग विभाग मानसिक स्वास्थ्य में मदद करता है: तनाव, उदासी, घबराहट, नींद की समस्याएं और नशे की लत, परामर्श और इलाज के साथ।",
            "मानसोपचार विभाग मानसिक आरोग्यासाठी मदत करतो: ताण, उदासी, चिंता, झोपेच्या समस्या आणि व्यसन, समुपदेशन आणि उपचारांसह.",
        ),
        [
            _t("stress, worry or panic attacks", "तनाव, चिंता या घबराहट के दौरे", "ताण, काळजी किंवा घाबरण्याचे झटके"),
            _t(
                "feeling low or losing interest for weeks",
                "हफ़्तों तक उदास रहना या किसी चीज़ में मन न लगना",
                "आठवडे उदास वाटणे किंवा कशातही मन न लागणे",
            ),
            _t("sleep problems", "नींद की समस्याएं", "झोपेच्या समस्या"),
            _t(
                "alcohol, tobacco or other addiction",
                "शराब, तंबाकू या दूसरी लत",
                "दारू, तंबाखू किंवा इतर व्यसन",
            ),
            _t(
                "memory problems in older adults",
                "बुज़ुर्गों में याददाश्त की समस्या",
                "वृद्धांमधील स्मरणशक्तीच्या समस्या",
            ),
        ],
        ["psychiatry", "psychiatrist", "mental health", "psychology", "counselling", "counseling"],
    ),
    "Physiotherapy": (
        _t("Physiotherapy", "फ़िज़ियोथेरेपी", "फिजिओथेरपी"),
        _t(
            "The Physiotherapy department helps people recover movement and strength through exercise and therapy, after injuries, operations or strokes and for long-term pain.",
            "फ़िज़ियोथेरेपी विभाग व्यायाम और थेरेपी से चोट, ऑपरेशन या लकवे के बाद और लंबे समय के दर्द में चलने-फिरने की क्षमता और ताक़त वापस पाने में मदद करता है।",
            "फिजिओथेरपी विभाग व्यायाम आणि थेरपीद्वारे दुखापत, शस्त्रक्रिया किंवा अर्धांगवायूनंतर आणि दीर्घकालीन दुखण्यात हालचाल आणि ताकद परत मिळवण्यास मदत करतो.",
        ),
        [
            _t("back, neck and knee pain", "कमर, गर्दन और घुटने का दर्द", "पाठ, मान आणि गुडघेदुखी"),
            _t(
                "stiffness after a fracture or operation",
                "फ़्रैक्चर या ऑपरेशन के बाद जकड़न",
                "फ्रॅक्चर किंवा शस्त्रक्रियेनंतर ताठरपणा",
            ),
            _t("recovery after a stroke", "लकवे के बाद सुधार", "अर्धांगवायूनंतर सुधारणा"),
            _t("sports injuries", "खेल की चोटें", "खेळातील दुखापती"),
        ],
        ["physiotherapy", "physio", "physiotherapist", "physical therapy", "rehabilitation", "rehab"],
    ),
    "Pulmonology": (
        _t("Pulmonology (chest and lungs)", "फेफड़ा रोग (पल्मोनोलॉजी)", "फुफ्फुसरोग (पल्मोनोलॉजी)"),
        _t(
            "The Pulmonology department treats conditions of the lungs and breathing, such as asthma, COPD, long-lasting cough and tuberculosis, and runs lung function tests.",
            "फेफड़ा रोग विभाग फेफड़ों और सांस की बीमारियों का इलाज करता है, जैसे अस्थमा, सीओपीडी, लंबी खांसी और टीबी, और फेफड़ों की कार्यक्षमता की जांच करता है।",
            "फुफ्फुसरोग विभाग फुफ्फुसे आणि श्वसनाच्या आजारांवर उपचार करतो, जसे दमा, सीओपीडी, दीर्घकाळ खोकला आणि क्षयरोग, आणि फुफ्फुसांच्या कार्यक्षमतेची तपासणी करतो.",
        ),
        [
            _t("asthma and wheezing", "अस्थमा और सांस में घरघराहट", "दमा आणि श्वास घेताना घरघर"),
            _t(
                "a cough lasting more than two weeks",
                "दो हफ़्ते से ज़्यादा चलने वाली खांसी",
                "दोन आठवड्यांपेक्षा जास्त काळ खोकला",
            ),
            _t("breathlessness", "सांस फूलना", "धाप लागणे"),
            _t("tuberculosis follow-up", "टीबी के इलाज की जांच", "क्षयरोगाच्या उपचारांची तपासणी"),
        ],
        ["pulmonology", "pulmonologist", "respiratory medicine", "chest medicine", "chest", "chest and tb"],
    ),
    "Neurology": (
        _t("Neurology", "तंत्रिका रोग (न्यूरोलॉजी)", "मेंदूविकार (न्यूरोलॉजी)"),
        _t(
            "The Neurology department treats conditions of the brain, spinal cord and nerves, such as headaches, fits, strokes, numbness and Parkinson's disease.",
            "तंत्रिका रोग विभाग दिमाग़, रीढ़ की हड्डी और नसों की बीमारियों का इलाज करता है, जैसे सिरदर्द, दौरे, लकवा, सुन्नपन और पार्किंसन रोग।",
            "मेंदूविकार विभाग मेंदू, मज्जारज्जू आणि नसांच्या आजारांवर उपचार करतो, जसे डोकेदुखी, फिट येणे, अर्धांगवायू, बधिरपणा आणि पार्किन्सन्स आजार.",
        ),
        [
            _t(
                "frequent or severe headaches and migraine",
                "बार-बार या तेज़ सिरदर्द और माइग्रेन",
                "वारंवार किंवा तीव्र डोकेदुखी आणि मायग्रेन",
            ),
            _t("fits (seizures)", "दौरे (मिर्गी)", "फिट येणे (अपस्मार)"),
            _t("follow-up after a stroke", "लकवे के बाद की जांच", "अर्धांगवायूनंतरची तपासणी"),
            _t(
                "numbness, tingling or weakness",
                "सुन्नपन, झुनझुनी या कमज़ोरी",
                "बधिरपणा, मुंग्या येणे किंवा अशक्तपणा",
            ),
            _t("tremor and Parkinson's disease", "कंपन और पार्किंसन रोग", "कंप आणि पार्किन्सन्स आजार"),
        ],
        ["neurology", "neurologist", "neuro"],
    ),
    "Urology": (
        _t("Urology", "मूत्र रोग (यूरोलॉजी)", "मूत्ररोग (युरोलॉजी)"),
        _t(
            "The Urology department treats problems of the kidneys, bladder, urinary tract and the male reproductive organs, including kidney stones and prostate problems.",
            "मूत्र रोग विभाग गुर्दे, मूत्राशय, मूत्र मार्ग और पुरुष प्रजनन अंगों की समस्याओं का इलाज करता है, जिसमें गुर्दे की पथरी और प्रोस्टेट की समस्याएं शामिल हैं।",
            "मूत्ररोग विभाग मूत्रपिंड, मूत्राशय, मूत्रमार्ग आणि पुरुष प्रजनन अवयवांच्या समस्यांवर उपचार करतो, ज्यात मुतखडा आणि प्रोस्टेटच्या समस्यांचा समावेश आहे.",
        ),
        [
            _t("kidney stones", "गुर्दे की पथरी", "मुतखडा"),
            _t(
                "burning or pain while passing urine",
                "पेशाब में जलन या दर्द",
                "लघवी करताना जळजळ किंवा वेदना",
            ),
            _t(
                "frequent urination or a weak stream",
                "बार-बार पेशाब आना या धार कमज़ोर होना",
                "वारंवार लघवी होणे किंवा धार कमकुवत होणे",
            ),
            _t("prostate problems", "प्रोस्टेट की समस्याएं", "प्रोस्टेटच्या समस्या"),
        ],
        ["urology", "urologist"],
    ),
    "Gastroenterology": (
        _t("Gastroenterology", "पेट रोग (गैस्ट्रोएंटेरोलॉजी)", "पोटाचे विकार (गॅस्ट्रोएंटेरॉलॉजी)"),
        _t(
            "The Gastroenterology department treats conditions of the stomach, intestines, liver and pancreas, and runs endoscopy.",
            "पेट रोग विभाग पेट, आंतों, लिवर और अग्न्याशय की बीमारियों का इलाज करता है और एंडोस्कोपी करता है।",
            "पोटाचे विकार विभाग पोट, आतडी, यकृत आणि स्वादुपिंडाच्या आजारांवर उपचार करतो आणि एंडोस्कोपी करतो.",
        ),
        [
            _t(
                "acidity, heartburn and indigestion",
                "एसिडिटी, सीने में जलन और अपच",
                "ॲसिडिटी, छातीत जळजळ आणि अपचन",
            ),
            _t("long-lasting stomach pain", "लंबे समय तक पेट दर्द", "दीर्घकाळ पोटदुखी"),
            _t(
                "constipation or loose motions that do not settle",
                "कब्ज़ या दस्त जो ठीक न हों",
                "बरी न होणारी बद्धकोष्ठता किंवा जुलाब",
            ),
            _t("jaundice and liver problems", "पीलिया और लिवर की समस्याएं", "कावीळ आणि यकृताच्या समस्या"),
        ],
        ["gastroenterology", "gastroenterologist", "gastro", "gastroenterology and hepatology"],
    ),
}

# Other names for the demo's eight (the names a hospital is likely to type, not symptoms).
SHIPPED_SYNONYMS = {
    "General Medicine": ["general medicine", "medicine", "internal medicine", "general physician", "physician"],
    "Cardiology": ["cardiology", "cardiologist", "cardiac", "heart"],
    "ENT": ["ent", "ear nose and throat", "ent ear nose and throat", "otorhinolaryngology", "otolaryngology"],
    "Orthopaedics": ["orthopaedics", "orthopedics", "orthopaedic", "orthopedic", "ortho", "bone and joint"],
    "Paediatrics": ["paediatrics", "pediatrics", "paediatric", "pediatric", "child health"],
    "Dermatology": ["dermatology", "dermatologist", "skin", "skin and vd"],
    "Gynaecology": ["gynaecology", "gynecology", "gynaecologist", "gynecologist"],
    "Ophthalmology": ["ophthalmology", "ophthalmologist", "eye", "eyes", "eye care"],
}


def _key(name: str) -> str:
    text = name.casefold().replace("&", " and ")
    text = re.sub(r"\b(department|dept|opd|clinic)\b", " ", text)
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def _known(name: str) -> tuple[T | None, T | None, list[T]]:
    """The translated name, a description and common reasons to visit, for a department we recognise."""
    key = _key(name)
    for known, (names, about, reasons, synonyms) in EXTRA.items():
        if key in {_key(known), *synonyms}:
            return names, about, reasons
    for known, synonyms in SHIPPED_SYNONYMS.items():
        if key in {_key(known), *synonyms}:
            return shipped.DEPARTMENT_NAMES[known], shipped.ABOUT[known], shipped.REASONS[known]
    return None, None, []


# --------------------------------------------------------------------------- words and phrases

ORDINAL_EN = ["ground", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"]
ORDINAL_HI = ["भूतल", "पहली", "दूसरी", "तीसरी", "चौथी", "पाँचवीं", "छठी", "सातवीं", "आठवीं", "नौवीं", "दसवीं"]
ORDINAL_MR = ["तळ", "पहिला", "दुसरा", "तिसरा", "चौथा", "पाचवा", "सहावा", "सातवा", "आठवा", "नववा", "दहावा"]
ORDINAL_MR_AT = ["तळ", "पहिल्या", "दुसऱ्या", "तिसऱ्या", "चौथ्या", "पाचव्या", "सहाव्या", "सातव्या", "आठव्या", "नवव्या", "दहाव्या"]


def floor_name(floor: int) -> T:
    """'second floor' in each language; floors are -3 (basement) to 60."""
    if floor < 0:
        level = "" if floor == -1 else f" {-floor}"
        return T(f"basement{level}", f"बेसमेंट{level}", f"तळघर{level}")
    if floor == 0:
        return T("ground floor", ORDINAL_HI[0], "तळमजला")
    if floor < len(ORDINAL_EN):
        return T(f"{ORDINAL_EN[floor]} floor", f"{ORDINAL_HI[floor]} मंज़िल", f"{ORDINAL_MR[floor]} मजला")
    return T(f"floor {floor}", f"मंज़िल {floor}", f"मजला {floor}")


def _floor_at_mr(floor: int) -> str:
    """Marathi needs the locative ('on the second floor')."""
    if floor < 0:
        return f"{floor_name(floor).mr}मध्ये" if floor == -1 else f"{floor_name(floor).mr} मध्ये"
    if floor == 0:
        return "तळमजल्यावर"
    if floor < len(ORDINAL_MR_AT):
        return f"{ORDINAL_MR_AT[floor]} मजल्यावर"
    return f"मजला {floor} वर"


def _clock(value) -> str:
    return value.strftime("%H:%M")


def _days(days: list[int]) -> T:
    return list_of([WEEKDAYS[d] for d in sorted(days)])


def _languages(codes: list[str]) -> T:
    return list_of([LANGUAGE_NAMES[c] for c in codes if c in LANGUAGE_NAMES])


def _day(value: date) -> T:
    return T(f"{value.day} {value:%B %Y}", f"{value:%d-%m-%Y}", f"{value:%d-%m-%Y}")


def _slug(name: str, taken: set[str], fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold().removeprefix("dr. ").removeprefix("dr ")).strip("-")
    slug = slug if slug.isascii() and slug else fallback
    if slug in taken:
        slug = f"{slug}-{fallback.rsplit('-', 1)[-1]}"
    taken.add(slug)
    return slug


def _document(collection: str, slug: str, title: T, sections: list[tuple[T, T]], verified: date) -> dict[str, str]:
    """The Markdown for each language, keyed by the path the shipped template would have."""
    out = {}
    for lang in LANGS:
        lines = ["---", f"title: {title[lang]}", f"collection: {collection}", f"language: {lang}"]
        lines += [f"last_verified: {verified.isoformat()}", f"doc_key: {collection}/{slug}", "---"]
        lines += [f"# {title[lang]}", ""]
        for heading, body in sections:
            lines += [f"## {heading[lang]}", "", body[lang].strip(), ""]
        out[f"{lang}/{collection}/{slug}.md"] = "\n".join(lines)
    return out


H_ALSO = T("Also known as", "दूसरे नाम", "इतर नावे")
NO_DOCTOR = T(
    "No doctor holds OPD in this department at the moment. Please ask at the reception.",
    "इस समय इस विभाग में कोई डॉक्टर ओपीडी नहीं लेते। कृपया रिसेप्शन पर पूछें।",
    "सध्या या विभागात कोणतेही डॉक्टर ओपीडी घेत नाहीत. कृपया रिसेप्शनवर विचारा.",
)
BOOKING = T(
    "Book, reschedule or cancel an appointment by chatting with CareFlow in English, Hindi or Marathi, on the Book page, or at the reception desk. Walk-in patients get a token at the reception and are seen between booked appointments.",
    "CareFlow से अंग्रेज़ी, हिंदी या मराठी में चैट करके, 'बुक करें' पेज पर, या रिसेप्शन पर अपॉइंटमेंट बुक करें, बदलें या रद्द करें। बिना अपॉइंटमेंट आने वाले मरीज़ों को रिसेप्शन पर टोकन मिलता है और उन्हें बुक किए गए मरीज़ों के बीच देखा जाता है।",
    "CareFlow शी इंग्रजी, हिंदी किंवा मराठीत चॅट करून, 'बुक करा' पानावर, किंवा रिसेप्शनवर अपॉइंटमेंट बुक करा, बदला किंवा रद्द करा. अपॉइंटमेंटशिवाय येणाऱ्या रुग्णांना रिसेप्शनवर टोकन मिळते आणि त्यांना बुक केलेल्या रुग्णांच्या दरम्यान पाहिले जाते.",
)
SUNDAY_CLOSED = T(
    "Sunday is closed except for emergencies.",
    "रविवार को सिर्फ़ इमरजेंसी सेवा खुली रहती है।",
    "रविवारी फक्त आपत्कालीन सेवा सुरू असते.",
)
AMBULANCE = T(
    "For an ambulance, call 112 or 108.",
    "एम्बुलेंस के लिए 112 या 108 पर कॉल करें।",
    "रुग्णवाहिकेसाठी 112 किंवा 108 वर कॉल करा.",
)


def _period(lang: str) -> str:
    return "।" if lang == "hi" else "."


# --------------------------------------------------------------------------- the documents


def setup_templates(db: Session, today: date, verified: date | None = None) -> dict[str, str]:
    """Every document written from the setup, as ``{path under knowledge/: Markdown}``."""
    verified = verified or today
    profile = db.get(HospitalProfile, 1)
    departments = list(db.scalars(select(Department).order_by(Department.name)))
    doctors: dict[int, list[Doctor]] = {dept.id: [] for dept in departments}
    for doctor in db.scalars(select(Doctor).order_by(Doctor.name)):
        if doctor.is_current(today) and doctor.department_id in doctors:
            doctors[doctor.department_id].append(doctor)
    names: dict[int, T] = {}
    out: dict[str, str] = {}
    dept_slugs: set[str] = set()
    sunday = any(7 in d.opd_days for ds in doctors.values() for d in ds)

    for dept in departments:
        known_name, about, reasons = _known(dept.name)
        name = T(dept.name, known_name.hi, known_name.mr) if known_name else T(dept.name, dept.name, dept.name)
        names[dept.id] = name
        sections: list[tuple[T, T]] = []
        if about:
            sections.append((shipped.H_ABOUT, about))
        if reasons:
            sections.append((shipped.H_REASONS, bullets(reasons)))
        floor = floor_name(dept.floor)
        hours = f"{_clock(dept.opd_start)}–{_clock(dept.opd_end)}"
        timings = T(
            f"The {name.en} OPD is on the {floor.en}. OPD hours are {hours} on each doctor's OPD days (see below).",
            f"{name.hi} ओपीडी {floor.hi} पर है। ओपीडी का समय हर डॉक्टर के ओपीडी दिनों में {hours} है (नीचे देखें)।",
            f"{name.mr} ओपीडी {_floor_at_mr(dept.floor)} आहे. प्रत्येक डॉक्टरांच्या ओपीडी दिवशी ओपीडीची वेळ {hours} आहे (खाली पाहा).",
        )
        if not sunday:
            timings = T(*(f"{timings[lang]} {SUNDAY_CLOSED[lang]}" for lang in LANGS))
        sections.append((shipped.H_TIMINGS, timings))
        lines = []
        for doctor in doctors[dept.id]:
            days, langs = _days(doctor.opd_days), _languages(doctor.languages)
            until = _day(doctor.last_day) if doctor.last_day else None
            lines.append(
                T(
                    f"{doctor.name}: OPD on {days.en}; speaks {langs.en}"
                    + (f"; last OPD day here {until.en}" if until else "")
                    + ".",
                    f"{doctor.name}: ओपीडी {days.hi} को; भाषाएं: {langs.hi}"
                    + (f"; यहां आख़िरी ओपीडी दिन {until.hi}" if until else "")
                    + "।",
                    f"{doctor.name}: ओपीडी {days.mr}; भाषा: {langs.mr}"
                    + (f"; येथे शेवटचा ओपीडी दिवस {until.mr}" if until else "")
                    + ".",
                )
            )
        sections.append((shipped.H_DOCTORS, bullets(lines) if lines else NO_DOCTOR))
        if dept.aliases:
            words = ", ".join(dept.aliases)
            sections.append((H_ALSO, T(*(f"{words}{_period(lang)}" for lang in LANGS))))
        sections.append((shipped.H_BEFORE, shipped.BEFORE_VISIT))
        slug = _slug(dept.name, dept_slugs, f"department-{dept.id}")
        english = dept.name if dept.name.casefold().endswith("department") else f"{name.en} department"
        title = T(english, f"{name.hi} विभाग", f"{name.mr} विभाग")
        out |= _document("departments", slug, title, sections, verified)

    doctor_slugs: set[str] = set()
    for dept in departments:
        name, floor = names[dept.id], floor_name(dept.floor)
        hours = f"{_clock(dept.opd_start)}–{_clock(dept.opd_end)}"
        for doctor in doctors[dept.id]:
            days, langs = _days(doctor.opd_days), _languages(doctor.languages)
            minutes = doctor.slot_minutes
            profile_text = T(
                f"{doctor.name} is a consultant in the {name.en} department ({floor.en}). OPD days: {days.en}, {hours}. Languages: {langs.en}. Each appointment slot is {minutes} minutes.",
                f"{doctor.name} {name.hi} विभाग ({floor.hi}) में कंसल्टेंट हैं। ओपीडी के दिन: {days.hi}, {hours}। भाषाएं: {langs.hi}। हर अपॉइंटमेंट स्लॉट {minutes} मिनट का है।",
                f"{doctor.name} हे {name.mr} विभागात ({floor.mr}) कन्सल्टंट आहेत. ओपीडीचे दिवस: {days.mr}, {hours}. भाषा: {langs.mr}. प्रत्येक अपॉइंटमेंट स्लॉट {minutes} मिनिटांचा आहे.",
            )
            if doctor.last_day:
                until = _day(doctor.last_day)
                profile_text = T(
                    f"{profile_text.en} Their last OPD day here is {until.en}.",
                    f"{profile_text.hi} यहां उनका आख़िरी ओपीडी दिन {until.hi} है।",
                    f"{profile_text.mr} येथे त्यांचा शेवटचा ओपीडी दिवस {until.mr} आहे.",
                )
            slug = _slug(doctor.name, doctor_slugs, f"doctor-{doctor.id}")
            title = T(f"{doctor.name}, {name.en}", f"{doctor.name}, {name.hi}", f"{doctor.name}, {name.mr}")
            out |= _document(
                "doctors", slug, title, [(shipped.H_PROFILE, profile_text), (shipped.H_BOOKING, BOOKING)], verified
            )

    out |= _facilities(departments, names, profile, sunday, verified)
    return out


def _facilities(
    departments: list[Department], names: dict[int, T], profile: HospitalProfile | None, sunday: bool, verified: date
) -> dict[str, str]:
    out: dict[str, str] = {}
    by_floor: dict[int, list[T]] = {}
    for dept in departments:
        by_floor.setdefault(dept.floor, []).append(names[dept.id])
    floor_lines = []
    for floor in sorted(by_floor):
        f = floor_name(floor)
        items = by_floor[floor]
        floor_lines.append(
            T(
                f"{f.en[0].upper()}{f.en[1:]}: " + ", ".join(i.en for i in items) + ".",
                f"{f.hi}: " + ", ".join(i.hi for i in items) + "।",
                f"{f.mr}: " + ", ".join(i.mr for i in items) + ".",
            )
        )
    ask = T(
        "Ask at the reception for directions to anything else.",
        "किसी और जगह का रास्ता रिसेप्शन पर पूछें।",
        "इतर कोणत्याही ठिकाणाचा मार्ग रिसेप्शनवर विचारा.",
    )
    where = T(*("\n".join([bullets(floor_lines)[lang], "", ask[lang]]) if floor_lines else ask[lang] for lang in LANGS))
    out |= _document(
        "facilities",
        "floor-guide",
        T("Floor guide", "मंज़िलवार जानकारी", "मजल्यानुसार माहिती"),
        [(T("Where to find departments", "विभाग कहां हैं", "विभाग कुठे आहेत"), where)],
        verified,
    )

    hours_lines = [
        T(*(f"{names[d.id][lang]}: {_clock(d.opd_start)}–{_clock(d.opd_end)}" for lang in LANGS)) for d in departments
    ]
    days = T(
        "Each department's OPD runs on its doctors' OPD days; the department pages list them.",
        "हर विभाग की ओपीडी उसके डॉक्टरों के ओपीडी दिनों में चलती है; विभाग के पेज पर ये दिन दिए गए हैं।",
        "प्रत्येक विभागाची ओपीडी त्याच्या डॉक्टरांच्या ओपीडी दिवशी चालते; विभागाच्या पानावर हे दिवस दिले आहेत.",
    )
    if not sunday:
        days = T(*(f"{days[lang]} {SUNDAY_CLOSED[lang]}" for lang in LANGS))
    out |= _document(
        "facilities",
        "opd-hours",
        T("OPD hours by department", "विभागवार ओपीडी समय", "विभागानुसार ओपीडीची वेळ"),
        [
            (T("Hours", "समय", "वेळ"), bullets(hours_lines) if hours_lines else ask),
            (T("Days", "दिन", "दिवस"), days),
        ],
        verified,
    )

    name = {
        lang: ((profile.name or {}).get(lang) or (profile.name or {}).get("en", "")) if profile else ""
        for lang in LANGS
    }
    address = profile.address if profile else ""
    place = T(*(", ".join(p for p in (name[lang], address) if p) for lang in LANGS))
    location: list[tuple[T, T]] = []
    if place.en:
        location.append((T("Address", "पता", "पत्ता"), T(*(f"{place[lang]}{_period(lang)}" for lang in LANGS))))
    if profile:
        hours = f"{_clock(profile.reception_opens)}–{_clock(profile.reception_closes)}"
        phone = profile.phone
        location.append(
            (
                T("Reception", "रिसेप्शन", "रिसेप्शन"),
                T(
                    f"The reception is open {hours}" + (f"; phone {phone}" if phone else "") + ".",
                    f"रिसेप्शन {hours} खुला रहता है" + (f"; फ़ोन {phone}" if phone else "") + "।",
                    f"रिसेप्शन {hours} सुरू असते" + (f"; फोन {phone}" if phone else "") + ".",
                ),
            )
        )
    if location:
        out |= _document(
            "facilities",
            "location-and-directions",
            T("Location and directions", "पता और रास्ता", "पत्ता आणि मार्ग"),
            location,
            verified,
        )

    notes = (profile.emergency_note or {}) if profile else {}
    where_er = T(
        *(
            (notes.get(lang) or notes.get("en") or default).strip()
            for lang, default in zip(
                LANGS,
                (
                    "Ask at the reception or the gate where the emergency department is.",
                    "इमरजेंसी विभाग कहां है, यह रिसेप्शन या गेट पर पूछें।",
                    "आपत्कालीन विभाग कुठे आहे ते रिसेप्शनवर किंवा गेटवर विचारा.",
                ),
                strict=True,
            )
        )
    )
    out |= _document(
        "facilities",
        "emergency-department",
        T("Emergency department", "इमरजेंसी विभाग", "आपत्कालीन विभाग"),
        [
            (
                T("Location and hours", "स्थान और समय", "ठिकाण आणि वेळ"),
                T(*(f"{where_er[lang]} {AMBULANCE[lang]}" for lang in LANGS)),
            )
        ],
        verified,
    )
    return out


def templates_for(db: Session, root: Path, today: date) -> tuple[dict[str, str], set[str]]:
    """The templates to load, keyed like ``read_templates`` (``knowledge/en/...``), and the ones written from
    the setup. In the demo, just the shipped files."""
    from app.rag.chunking import read_templates

    shipped_templates = dict(read_templates(root))
    if not follows_setup():
        return shipped_templates, set()
    prefix = f"{root.name}/"
    kept = {
        path: raw
        for path, raw in shipped_templates.items()
        if not (path.startswith(prefix) and REPLACED.match(path[len(prefix) :]))
    }
    generated = {f"{prefix}{path}": raw for path, raw in setup_templates(db, today).items()}
    return kept | generated, set(generated)


VERIFIED_LINE = re.compile(r"^last_verified: .*$", re.M)


def same_apart_from_date(a: str | None, b: str) -> bool:
    """A setup document re-written with the same content keeps its date, so readers see when it changed."""
    return a is not None and VERIFIED_LINE.sub("", a) == VERIFIED_LINE.sub("", b)


def knowledge_base_loaded(db: Session) -> bool:
    return db.scalar(select(KbDocument.id).limit(1)) is not None


def refresh_setup_documents(db: Session, today: date) -> dict | None:
    """Bring the setup's documents and the index in line with the setup (a hospital's deployment only, and only
    once the knowledge base was loaded: the server must not build the search model itself, D-67)."""
    if not follows_setup() or not knowledge_base_loaded(db):
        return None
    from app.rag.kb import reindex, sync_templates
    from app.rag.retriever import reset_retriever

    changes = sync_templates(db, today=today)
    if not any(changes.values()):
        return changes
    result = reindex(db, refit=False)
    reset_retriever()  # also when documents were only removed
    return {**changes, **result}
