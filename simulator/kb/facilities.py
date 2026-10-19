"""Facilities and visitor information. The floor guide and the OPD-hours overview are
generated from the simulator's hospital definition."""

from simulator import hospital
from simulator.kb.common import KbDoc, T, bullets, clock
from simulator.kb.departments import DEPARTMENT_NAMES, FLOOR


def doc(slug: str, title: T, *sections: tuple[T, T]) -> KbDoc:
    return KbDoc("facilities", slug, title, list(sections))


def build() -> list[KbDoc]:
    floors: dict[int, list[T]] = {}
    for name, floor, _, _ in hospital.DEPARTMENTS:
        floors.setdefault(floor, []).append(DEPARTMENT_NAMES[name])
    common_areas = {
        0: [
            T("reception and help desk", "रिसेप्शन और हेल्प डेस्क", "रिसेप्शन आणि हेल्प डेस्क"),
            T("emergency department", "इमरजेंसी विभाग", "आपत्कालीन विभाग"),
            T("laboratory, pharmacy and billing", "प्रयोगशाला, फ़ार्मेसी और बिलिंग", "प्रयोगशाळा, फार्मसी आणि बिलिंग"),
            T(
                "reports counter, insurance desk and medical records",
                "रिपोर्ट काउंटर, बीमा डेस्क और मेडिकल रिकॉर्ड",
                "रिपोर्ट काउंटर, विमा डेस्क आणि मेडिकल रेकॉर्ड",
            ),
        ],
        1: [
            T(
                "radiology (X-ray, ultrasound, CT, MRI)",
                "रेडियोलॉजी (एक्स-रे, अल्ट्रासाउंड, सीटी, एमआरआई)",
                "रेडिओलॉजी (एक्स-रे, सोनोग्राफी, सीटी, एमआरआय)",
            )
        ],
        2: [T("day-care procedure suite", "डे-केयर प्रोसीजर सुइट", "डे-केअर प्रोसिजर सूट")],
        4: [T("canteen", "कैंटीन", "कॅन्टीन")],
    }
    floor_lines = []
    for floor in sorted(set(floors) | set(common_areas)):
        items = floors.get(floor, []) + common_areas.get(floor, [])
        f = FLOOR[floor]
        floor_lines.append(
            T(
                f"{f.en.capitalize()}: " + ", ".join(i.en for i in items) + ".",
                f"{f.hi}: " + ", ".join(i.hi for i in items) + "।",
                f"{f.mr}: " + ", ".join(i.mr for i in items) + ".",
            )
        )
    hours_lines = [
        T(
            f"{DEPARTMENT_NAMES[name].en}: {clock(start)}–{clock(end)}",
            f"{DEPARTMENT_NAMES[name].hi}: {clock(start)}–{clock(end)}",
            f"{DEPARTMENT_NAMES[name].mr}: {clock(start)}–{clock(end)}",
        )
        for name, _, start, end in hospital.DEPARTMENTS
    ]

    return [
        doc(
            "floor-guide",
            T("Floor guide", "मंज़िलवार जानकारी", "मजल्यानुसार माहिती"),
            (T("Where to find departments", "विभाग कहां हैं", "विभाग कुठे आहेत"), bullets(floor_lines)),
            (
                T("Lifts and stairs", "लिफ़्ट और सीढ़ियां", "लिफ्ट आणि जिने"),
                T(
                    "Four lifts are next to the reception; the lift on the left is reserved for patients on stretchers and wheelchairs.",
                    "रिसेप्शन के पास चार लिफ़्ट हैं; बाईं ओर की लिफ़्ट स्ट्रेचर और व्हीलचेयर वाले मरीज़ों के लिए आरक्षित है।",
                    "रिसेप्शनजवळ चार लिफ्ट आहेत; डावीकडील लिफ्ट स्ट्रेचर आणि व्हीलचेअरवरील रुग्णांसाठी राखीव आहे.",
                ),
            ),
        ),
        doc(
            "opd-hours",
            T("OPD hours by department", "विभागवार ओपीडी समय", "विभागानुसार ओपीडीची वेळ"),
            (
                T("Hours", "समय", "वेळ"),
                bullets(hours_lines),
            ),
            (
                T("Days", "दिन", "दिवस"),
                T(
                    "OPDs run Monday to Saturday on each doctor's OPD days. On Sundays only the emergency department, pharmacy and a short laboratory session (08:00–11:00) are open.",
                    "ओपीडी सोमवार से शनिवार हर डॉक्टर के ओपीडी दिनों में चलती है। रविवार को सिर्फ़ इमरजेंसी विभाग, फ़ार्मेसी और प्रयोगशाला का छोटा सत्र (08:00–11:00) खुला रहता है।",
                    "ओपीडी सोमवार ते शनिवार प्रत्येक डॉक्टरांच्या ओपीडी दिवशी चालते. रविवारी फक्त आपत्कालीन विभाग, फार्मसी आणि प्रयोगशाळेचे छोटे सत्र (08:00–11:00) सुरू असते.",
                ),
            ),
        ),
        doc(
            "location-and-directions",
            T("Location and directions", "पता और रास्ता", "पत्ता आणि मार्ग"),
            (
                T("Address", "पता", "पत्ता"),
                T(
                    "Indravani General Hospital, Hospital Road, Indravani Nagar. The hospital and its address are fictional.",
                    "इंद्रवाणी जनरल हॉस्पिटल, हॉस्पिटल रोड, इंद्रवाणी नगर। अस्पताल और उसका पता काल्पनिक हैं।",
                    "इंद्रवाणी जनरल हॉस्पिटल, हॉस्पिटल रोड, इंद्रवाणी नगर. रुग्णालय आणि त्याचा पत्ता काल्पनिक आहेत.",
                ),
            ),
            (
                T("Getting here", "यहां कैसे पहुंचें", "येथे कसे पोहोचावे"),
                T(
                    "City bus routes 12 and 27 stop at the main gate. An auto-rickshaw stand is outside Gate 2.",
                    "शहर की बस संख्या 12 और 27 मुख्य द्वार पर रुकती हैं। गेट 2 के बाहर ऑटो-रिक्शा स्टैंड है।",
                    "शहर बस क्रमांक 12 आणि 27 मुख्य प्रवेशद्वारावर थांबतात. गेट 2 बाहेर रिक्षा स्टँड आहे.",
                ),
            ),
        ),
        doc(
            "parking",
            T("Parking", "पार्किंग", "पार्किंग"),
            (
                T("Parking", "पार्किंग", "पार्किंग"),
                T(
                    "Car and two-wheeler parking is in the basement, entered from Gate 2. The first 30 minutes are free; after that the charge is ₹20 per hour for cars and ₹10 per hour for two-wheelers. Drop-off at the main entrance is allowed for 5 minutes.",
                    "कार और दोपहिया पार्किंग बेसमेंट में है, प्रवेश गेट 2 से। पहले 30 मिनट मुफ़्त हैं; उसके बाद कार के लिए ₹20 प्रति घंटा और दोपहिया के लिए ₹10 प्रति घंटा। मुख्य प्रवेश पर 5 मिनट के लिए उतरने-चढ़ने की अनुमति है।",
                    "कार आणि दुचाकी पार्किंग तळघरात आहे, प्रवेश गेट 2 मधून. पहिली 30 मिनिटे मोफत; त्यानंतर कारसाठी ₹20 प्रति तास आणि दुचाकीसाठी ₹10 प्रति तास. मुख्य प्रवेशद्वारावर 5 मिनिटे उतरण्या-चढण्याची परवानगी आहे.",
                ),
            ),
        ),
        doc(
            "pharmacy",
            T("Pharmacy", "फ़ार्मेसी (दवा की दुकान)", "फार्मसी (औषध दुकान)"),
            (
                T("Timings and location", "समय और स्थान", "वेळ आणि ठिकाण"),
                T(
                    "The hospital pharmacy is on the ground floor next to the billing counter and is open 24 hours a day. Medicines are given only against a valid prescription.",
                    "अस्पताल की फ़ार्मेसी भूतल पर बिलिंग काउंटर के बगल में है और 24 घंटे खुली रहती है। दवाएं सिर्फ़ मान्य पर्चे पर दी जाती हैं।",
                    "रुग्णालयाची फार्मसी तळमजल्यावर बिलिंग काउंटरशेजारी आहे आणि 24 तास सुरू असते. औषधे फक्त वैध चिठ्ठीवरच दिली जातात.",
                ),
            ),
        ),
        doc(
            "laboratory",
            T("Laboratory and sample collection", "प्रयोगशाला और सैंपल कलेक्शन", "प्रयोगशाळा आणि नमुना संकलन"),
            (
                T("Timings", "समय", "वेळ"),
                T(
                    "The laboratory on the ground floor collects samples Monday to Saturday 07:00–14:00 and Sunday 08:00–11:00. No appointment is needed; bring the test request from your doctor.",
                    "भूतल की प्रयोगशाला सोमवार से शनिवार 07:00–14:00 और रविवार 08:00–11:00 सैंपल लेती है। अपॉइंटमेंट की ज़रूरत नहीं है; डॉक्टर की जांच पर्ची साथ लाएं।",
                    "तळमजल्यावरील प्रयोगशाळा सोमवार ते शनिवार 07:00–14:00 आणि रविवार 08:00–11:00 नमुने घेते. अपॉइंटमेंटची गरज नाही; डॉक्टरांची तपासणीची चिठ्ठी सोबत आणा.",
                ),
            ),
            (
                T("Home collection", "घर से सैंपल", "घरून नमुना"),
                T(
                    "Home sample collection is available for patients aged 70 and above; book it at the laboratory desk a day in advance.",
                    "70 वर्ष और उससे ऊपर के मरीज़ों के लिए घर से सैंपल लेने की सुविधा है; एक दिन पहले प्रयोगशाला डेस्क पर बुक करें।",
                    "70 वर्षे व त्याहून अधिक वयाच्या रुग्णांसाठी घरून नमुना घेण्याची सुविधा आहे; एक दिवस आधी प्रयोगशाळा डेस्कवर बुक करा.",
                ),
            ),
        ),
        doc(
            "reports-collection",
            T("Collecting reports", "रिपोर्ट लेना", "रिपोर्ट घेणे"),
            (
                T("Where and when", "कहां और कब", "कुठे आणि केव्हा"),
                T(
                    "Printed reports are given at the Reports counter on the ground floor, 09:00–20:00 every day; bring your receipt. Reports are also shared as a secure link by SMS when they are ready.",
                    "छपी रिपोर्ट भूतल के रिपोर्ट काउंटर पर रोज़ 09:00–20:00 मिलती हैं; अपनी रसीद साथ लाएं। रिपोर्ट तैयार होने पर SMS से सुरक्षित लिंक भी भेजा जाता है।",
                    "छापील रिपोर्ट तळमजल्यावरील रिपोर्ट काउंटरवर दररोज 09:00–20:00 मिळतात; तुमची पावती सोबत आणा. रिपोर्ट तयार झाल्यावर SMS ने सुरक्षित लिंकही पाठवली जाते.",
                ),
            ),
            (
                T("Collecting for someone else", "किसी और की रिपोर्ट लेना", "दुसऱ्याचा रिपोर्ट घेणे"),
                T(
                    "A family member can collect reports with the receipt and their own photo ID.",
                    "परिवार का सदस्य रसीद और अपना फ़ोटो पहचान पत्र दिखाकर रिपोर्ट ले सकता है।",
                    "कुटुंबातील सदस्य पावती आणि स्वतःचे फोटो ओळखपत्र दाखवून रिपोर्ट घेऊ शकतो.",
                ),
            ),
        ),
        doc(
            "canteen-and-drinking-water",
            T("Canteen and drinking water", "कैंटीन और पीने का पानी", "कॅन्टीन आणि पिण्याचे पाणी"),
            (
                T("Canteen", "कैंटीन", "कॅन्टीन"),
                T(
                    "The canteen on the fourth floor serves vegetarian meals and snacks from 07:00 to 21:00.",
                    "चौथी मंज़िल की कैंटीन में 07:00 से 21:00 तक शाकाहारी भोजन और नाश्ता मिलता है।",
                    "चौथ्या मजल्यावरील कॅन्टीनमध्ये 07:00 ते 21:00 दरम्यान शाकाहारी जेवण आणि नाश्ता मिळतो.",
                ),
            ),
            (
                T("Drinking water and restrooms", "पीने का पानी और शौचालय", "पिण्याचे पाणी आणि स्वच्छतागृहे"),
                T(
                    "Free filtered drinking water and restrooms are available on every floor near the lifts.",
                    "हर मंज़िल पर लिफ़्ट के पास मुफ़्त फ़िल्टर किया पीने का पानी और शौचालय हैं।",
                    "प्रत्येक मजल्यावर लिफ्टजवळ मोफत गाळलेले पिण्याचे पाणी आणि स्वच्छतागृहे आहेत.",
                ),
            ),
        ),
        doc(
            "accessibility",
            T("Wheelchairs and accessibility", "व्हीलचेयर और सुगमता", "व्हीलचेअर आणि सुलभता"),
            (
                T("Support available", "उपलब्ध सहायता", "उपलब्ध सहाय्य"),
                bullets(
                    [
                        T(
                            "Free wheelchairs at the main entrance; ask the security staff.",
                            "मुख्य प्रवेश पर मुफ़्त व्हीलचेयर; सुरक्षा कर्मचारियों से कहें।",
                            "मुख्य प्रवेशद्वारावर मोफत व्हीलचेअर; सुरक्षा कर्मचाऱ्यांना सांगा.",
                        ),
                        T(
                            "Ramps at all entrances and accessible restrooms on every floor.",
                            "सभी प्रवेश द्वारों पर रैंप और हर मंज़िल पर सुगम शौचालय।",
                            "सर्व प्रवेशद्वारांवर रॅम्प आणि प्रत्येक मजल्यावर सुलभ स्वच्छतागृहे.",
                        ),
                        T(
                            "A staff escort for patients who need help moving between departments.",
                            "विभागों के बीच जाने में मदद चाहने वाले मरीज़ों के लिए स्टाफ़ सहायक।",
                            "विभागांदरम्यान जाण्यासाठी मदत हवी असलेल्या रुग्णांसाठी कर्मचारी सोबती.",
                        ),
                        T(
                            "CareFlow's large-text mode for easier reading on phones.",
                            "फ़ोन पर आसानी से पढ़ने के लिए CareFlow का बड़ा-अक्षर मोड।",
                            "फोनवर सहज वाचण्यासाठी CareFlow चा मोठ्या अक्षरांचा मोड.",
                        ),
                    ]
                ),
            ),
        ),
        doc(
            "emergency-department",
            T("Emergency department", "इमरजेंसी विभाग", "आपत्कालीन विभाग"),
            (
                T("Location and hours", "स्थान और समय", "ठिकाण आणि वेळ"),
                T(
                    "The emergency department is on the ground floor near the main gate, open 24 hours a day, every day, with its own ambulance entrance. For an ambulance, call 112 or 108.",
                    "इमरजेंसी विभाग मुख्य द्वार के पास भूतल पर है, हर दिन 24 घंटे खुला, और इसका अपना एम्बुलेंस प्रवेश है। एम्बुलेंस के लिए 112 या 108 पर कॉल करें।",
                    "आपत्कालीन विभाग मुख्य प्रवेशद्वाराजवळ तळमजल्यावर आहे, दररोज 24 तास सुरू, आणि त्याचे स्वतःचे रुग्णवाहिका प्रवेशद्वार आहे. रुग्णवाहिकेसाठी 112 किंवा 108 वर कॉल करा.",
                ),
            ),
        ),
        doc(
            "atm-and-payments",
            T("ATM and payment counters", "एटीएम और भुगतान काउंटर", "एटीएम आणि भरणा काउंटर"),
            (
                T("Payments", "भुगतान", "भरणा"),
                T(
                    "The billing counter on the ground floor (08:00–20:00) accepts cash, UPI and debit or credit cards. An ATM is next to the pharmacy.",
                    "भूतल का बिलिंग काउंटर (08:00–20:00) नकद, UPI और डेबिट या क्रेडिट कार्ड स्वीकार करता है। फ़ार्मेसी के बगल में एटीएम है।",
                    "तळमजल्यावरील बिलिंग काउंटर (08:00–20:00) रोख, UPI आणि डेबिट किंवा क्रेडिट कार्ड स्वीकारते. फार्मसीशेजारी एटीएम आहे.",
                ),
            ),
        ),
        doc(
            "lost-and-found-and-security",
            T("Lost and found, and security", "खोया-पाया और सुरक्षा", "हरवले-सापडले आणि सुरक्षा"),
            (
                T("Lost and found", "खोया-पाया", "हरवले-सापडले"),
                T(
                    "Lost items are kept at the security office near the main gate for 30 days.",
                    "खोई हुई चीज़ें मुख्य द्वार के पास सुरक्षा कार्यालय में 30 दिन तक रखी जाती हैं।",
                    "हरवलेल्या वस्तू मुख्य प्रवेशद्वाराजवळील सुरक्षा कार्यालयात 30 दिवस ठेवल्या जातात.",
                ),
            ),
            (
                T("Security", "सुरक्षा", "सुरक्षा"),
                T(
                    "Security staff are on duty at every entrance 24 hours a day. Please keep your valuables with you.",
                    "हर प्रवेश द्वार पर 24 घंटे सुरक्षा कर्मचारी तैनात रहते हैं। कृपया अपना कीमती सामान अपने पास रखें।",
                    "प्रत्येक प्रवेशद्वारावर 24 तास सुरक्षा कर्मचारी तैनात असतात. कृपया तुमच्या मौल्यवान वस्तू स्वतःजवळ ठेवा.",
                ),
            ),
        ),
        doc(
            "blood-bank",
            T("Blood bank", "ब्लड बैंक", "रक्तपेढी (ब्लड बँक)"),
            (
                T("Services", "सेवाएं", "सेवा"),
                T(
                    "The blood bank on the ground floor is open 24 hours for issuing blood. Voluntary donors can donate Monday to Saturday 09:00–16:00; donors must be 18–65 years old and weigh at least 50 kg.",
                    "भूतल का ब्लड बैंक खून देने (जारी करने) के लिए 24 घंटे खुला रहता है। स्वैच्छिक दाता सोमवार से शनिवार 09:00–16:00 रक्तदान कर सकते हैं; दाता की उम्र 18–65 वर्ष और वज़न कम से कम 50 किलो होना चाहिए।",
                    "तळमजल्यावरील रक्तपेढी रक्त देण्यासाठी 24 तास सुरू असते. स्वेच्छेने रक्तदान करणारे सोमवार ते शनिवार 09:00–16:00 रक्तदान करू शकतात; रक्तदात्याचे वय 18–65 वर्षे आणि वजन किमान 50 किलो असावे.",
                ),
            ),
        ),
    ]
