"""Hospital policy documents. Every number that is also a business rule is taken
from app/tools/policy.py so the documents and the code cannot disagree."""

from app.tools import policy
from simulator.kb.common import KbDoc, T, bullets

RESCHEDULE_H = int(policy.RESCHEDULE_CUTOFF.total_seconds() // 3600)
CANCEL_H = int(policy.CANCEL_CUTOFF.total_seconds() // 3600)
HORIZON_D = policy.BOOKING_HORIZON.days
LEAD_M = int(policy.BOOKING_LEAD.total_seconds() // 60)
HOLD_H = int(policy.WAITLIST_OFFER_HOLD.total_seconds() // 3600)
GRACE_M = int(policy.LATE_GRACE.total_seconds() // 60)
CHECK_IN_OPENS_M = int(policy.SELF_CHECK_IN_OPENS.total_seconds() // 60)
CHECK_IN_CLOSES_M = int(policy.SELF_CHECK_IN_CLOSES.total_seconds() // 60)
JOIN_OPENS_M = int(policy.VIRTUAL_JOIN_OPENS.total_seconds() // 60)
JOIN_CLOSES_M = int(policy.VIRTUAL_JOIN_CLOSES.total_seconds() // 60)
ONLINE_CAP = policy.VIRTUAL_QUEUE_CAP


def doc(slug: str, title: T, *sections: tuple[T, T]) -> KbDoc:
    return KbDoc("policies", slug, title, list(sections))


def build() -> list[KbDoc]:
    return [
        doc(
            "booking-appointments",
            T("Booking an OPD appointment", "ओपीडी अपॉइंटमेंट बुक करना", "ओपीडी अपॉइंटमेंट बुक करणे"),
            (
                T("Ways to book", "बुक करने के तरीके", "बुक करण्याचे मार्ग"),
                T(
                    "You can book by chatting with CareFlow at any time of day in English, Hindi or Marathi, or at the reception desk on the ground floor between 08:00 and 20:00. A caregiver with a verified link can book for a family member.",
                    "आप दिन में किसी भी समय CareFlow से अंग्रेज़ी, हिंदी या मराठी में चैट करके, या भूतल के रिसेप्शन पर 08:00 से 20:00 के बीच बुक कर सकते हैं। सत्यापित लिंक वाला देखभालकर्ता परिवार के सदस्य के लिए बुक कर सकता है।",
                    "तुम्ही दिवसात कधीही CareFlow शी इंग्रजी, हिंदी किंवा मराठीत चॅट करून, किंवा तळमजल्यावरील रिसेप्शनवर 08:00 ते 20:00 दरम्यान बुक करू शकता. पडताळलेली लिंक असलेला काळजीवाहक कुटुंबातील सदस्यासाठी बुक करू शकतो.",
                ),
            ),
            (
                T("Booking rules", "बुकिंग के नियम", "बुकिंगचे नियम"),
                bullets(
                    [
                        T(
                            f"Appointments can be booked from {LEAD_M} minutes to {HORIZON_D} days ahead.",
                            f"अपॉइंटमेंट {LEAD_M} मिनट पहले से लेकर {HORIZON_D} दिन आगे तक बुक की जा सकती है।",
                            f"अपॉइंटमेंट {LEAD_M} मिनिटे आधीपासून {HORIZON_D} दिवस पुढेपर्यंत बुक करता येते.",
                        ),
                        T(
                            "A patient can have only one appointment with the same doctor on the same day.",
                            "एक मरीज़ की एक ही दिन एक ही डॉक्टर के साथ सिर्फ़ एक अपॉइंटमेंट हो सकती है।",
                            "एका रुग्णाची एकाच दिवशी एकाच डॉक्टरांकडे फक्त एक अपॉइंटमेंट असू शकते.",
                        ),
                        T(
                            "CareFlow always shows the doctor, date and time and asks you to confirm before booking. Nothing is booked until you confirm.",
                            "CareFlow बुक करने से पहले हमेशा डॉक्टर, तारीख और समय दिखाकर आपकी पुष्टि मांगता है। आपकी पुष्टि के बिना कुछ भी बुक नहीं होता।",
                            "CareFlow बुक करण्यापूर्वी नेहमी डॉक्टर, तारीख आणि वेळ दाखवून तुमची पुष्टी मागतो. तुमच्या पुष्टीशिवाय काहीही बुक होत नाही.",
                        ),
                        T(
                            "A confirmation card is valid for 5 minutes; after that, CareFlow checks the slot again.",
                            "पुष्टि कार्ड 5 मिनट तक मान्य रहता है; उसके बाद CareFlow स्लॉट दोबारा जांचता है।",
                            "पुष्टी कार्ड 5 मिनिटे वैध असते; त्यानंतर CareFlow स्लॉट पुन्हा तपासतो.",
                        ),
                    ]
                ),
            ),
            (
                T("If no slot is free", "अगर कोई स्लॉट खाली न हो", "एकही स्लॉट मोकळा नसल्यास"),
                T(
                    "If the doctor is fully booked on the days you want, you can join the doctor's waiting list (see the waiting-list policy).",
                    "अगर आपके चाहे दिनों में डॉक्टर पूरी तरह बुक हैं, तो आप डॉक्टर की प्रतीक्षा सूची (वेटिंग लिस्ट) में नाम जोड़ सकते हैं (प्रतीक्षा सूची नीति देखें)।",
                    "तुम्हाला हव्या असलेल्या दिवशी डॉक्टर पूर्ण बुक असल्यास, तुम्ही डॉक्टरांच्या प्रतीक्षा यादीत (वेटिंग लिस्ट) नाव नोंदवू शकता (प्रतीक्षा यादी धोरण पाहा).",
                ),
            ),
        ),
        doc(
            "rescheduling-policy",
            T("Rescheduling policy", "अपॉइंटमेंट बदलने की नीति", "अपॉइंटमेंट बदलण्याचे धोरण"),
            (
                T("When you can reschedule", "कब बदल सकते हैं", "केव्हा बदलू शकता"),
                T(
                    f"Appointments can be rescheduled up to {RESCHEDULE_H} hours before the appointment time, to any free slot in the same department. Within {RESCHEDULE_H} hours of the appointment, it can no longer be moved online; please contact the reception desk.",
                    f"अपॉइंटमेंट के समय से {RESCHEDULE_H} घंटे पहले तक उसे उसी विभाग के किसी भी खाली स्लॉट में बदला जा सकता है। अपॉइंटमेंट से {RESCHEDULE_H} घंटे के अंदर इसे ऑनलाइन नहीं बदला जा सकता; कृपया रिसेप्शन से संपर्क करें।",
                    f"अपॉइंटमेंटच्या वेळेच्या {RESCHEDULE_H} तास आधीपर्यंत ती त्याच विभागातील कोणत्याही मोकळ्या स्लॉटमध्ये बदलता येते. अपॉइंटमेंटच्या {RESCHEDULE_H} तासांच्या आत ती ऑनलाइन बदलता येत नाही; कृपया रिसेप्शनशी संपर्क साधा.",
                ),
            ),
            (
                T("What happens to the old slot", "पुराने स्लॉट का क्या होता है", "जुन्या स्लॉटचे काय होते"),
                T(
                    "When you move an appointment, your old slot is released and offered first to patients on the doctor's waiting list.",
                    "जब आप अपॉइंटमेंट बदलते हैं, तो आपका पुराना स्लॉट खाली हो जाता है और पहले डॉक्टर की प्रतीक्षा सूची के मरीज़ों को दिया जाता है।",
                    "तुम्ही अपॉइंटमेंट बदलल्यावर तुमचा जुना स्लॉट मोकळा होतो आणि आधी डॉक्टरांच्या प्रतीक्षा यादीतील रुग्णांना दिला जातो.",
                ),
            ),
            (
                T("If the doctor becomes unavailable", "अगर डॉक्टर उपलब्ध न हों", "डॉक्टर उपलब्ध नसल्यास"),
                T(
                    f"If the hospital cancels your appointment because the doctor is unavailable, you can reschedule free of charge at any time, even within {RESCHEDULE_H} hours, to any doctor in the same department.",
                    f"अगर डॉक्टर के उपलब्ध न होने से अस्पताल आपकी अपॉइंटमेंट रद्द करता है, तो आप किसी भी समय, {RESCHEDULE_H} घंटे के अंदर भी, उसी विभाग के किसी भी डॉक्टर के साथ मुफ़्त में अपॉइंटमेंट बदल सकते हैं।",
                    f"डॉक्टर उपलब्ध नसल्यामुळे रुग्णालयाने तुमची अपॉइंटमेंट रद्द केली तर तुम्ही कधीही, {RESCHEDULE_H} तासांच्या आतही, त्याच विभागातील कोणत्याही डॉक्टरांकडे विनामूल्य अपॉइंटमेंट बदलू शकता.",
                ),
            ),
        ),
        doc(
            "cancellation-policy",
            T("Cancellation policy", "अपॉइंटमेंट रद्द करने की नीति", "अपॉइंटमेंट रद्द करण्याचे धोरण"),
            (
                T("Cancelling an appointment", "अपॉइंटमेंट रद्द करना", "अपॉइंटमेंट रद्द करणे"),
                T(
                    f"Appointments can be cancelled free of charge up to {CANCEL_H} hours before the appointment time, through CareFlow or at the reception. Within {CANCEL_H} hours, the appointment can no longer be cancelled online; please contact the reception desk.",
                    f"अपॉइंटमेंट के समय से {CANCEL_H} घंटे पहले तक CareFlow या रिसेप्शन के ज़रिए उसे मुफ़्त में रद्द किया जा सकता है। {CANCEL_H} घंटे के अंदर अपॉइंटमेंट ऑनलाइन रद्द नहीं की जा सकती; कृपया रिसेप्शन से संपर्क करें।",
                    f"अपॉइंटमेंटच्या वेळेच्या {CANCEL_H} तास आधीपर्यंत CareFlow किंवा रिसेप्शनद्वारे ती विनामूल्य रद्द करता येते. {CANCEL_H} तासांच्या आत अपॉइंटमेंट ऑनलाइन रद्द करता येत नाही; कृपया रिसेप्शनशी संपर्क साधा.",
                ),
            ),
            (
                T("Fees and refunds", "फ़ीस और रिफ़ंड", "शुल्क आणि परतावा"),
                T(
                    "Consultation fees are paid at the hospital on the day of the visit, so there is nothing to refund when you cancel.",
                    "परामर्श फ़ीस मिलने के दिन अस्पताल में दी जाती है, इसलिए रद्द करने पर कोई रिफ़ंड नहीं बनता।",
                    "सल्ला शुल्क भेटीच्या दिवशी रुग्णालयात भरले जाते, त्यामुळे रद्द केल्यावर परत करण्यासारखे काही नसते.",
                ),
            ),
            (
                T("Why cancel early", "जल्दी रद्द क्यों करें", "लवकर रद्द का करावे"),
                T(
                    "Cancelling early lets another patient on the waiting list use the slot.",
                    "जल्दी रद्द करने से प्रतीक्षा सूची का कोई दूसरा मरीज़ वह स्लॉट ले सकता है।",
                    "लवकर रद्द केल्यास प्रतीक्षा यादीतील दुसरा रुग्ण तो स्लॉट वापरू शकतो.",
                ),
            ),
        ),
        doc(
            "waiting-list",
            T("Waiting list", "प्रतीक्षा सूची (वेटिंग लिस्ट)", "प्रतीक्षा यादी (वेटिंग लिस्ट)"),
            (
                T("Joining the waiting list", "प्रतीक्षा सूची में नाम जोड़ना", "प्रतीक्षा यादीत नाव नोंदवणे"),
                T(
                    "If a doctor has no free slot on the dates you want, CareFlow can add you to that doctor's waiting list for those dates, after you agree. You can be on each doctor's list only once.",
                    "अगर आपकी चाही तारीखों पर डॉक्टर के पास कोई खाली स्लॉट नहीं है, तो आपकी सहमति के बाद CareFlow आपको उन तारीखों के लिए उस डॉक्टर की प्रतीक्षा सूची में जोड़ सकता है। हर डॉक्टर की सूची में आपका नाम एक ही बार हो सकता है।",
                    "तुम्हाला हव्या असलेल्या तारखांना डॉक्टरांकडे एकही मोकळा स्लॉट नसल्यास, तुमच्या संमतीनंतर CareFlow तुम्हाला त्या तारखांसाठी त्या डॉक्टरांच्या प्रतीक्षा यादीत जोडू शकतो. प्रत्येक डॉक्टरांच्या यादीत तुमचे नाव एकदाच असू शकते.",
                ),
            ),
            (
                T("When a slot opens", "जब स्लॉट खाली हो", "स्लॉट मोकळा झाल्यावर"),
                T(
                    f"When someone cancels or moves an appointment, the slot is offered first to the patient who joined the list earliest for that date. You get a message, and the slot is held for you for up to {HOLD_H} hours. If you do not book it in time, it is offered to the next patient.",
                    f"जब कोई अपॉइंटमेंट रद्द करता है या बदलता है, तो वह स्लॉट पहले उस मरीज़ को दिया जाता है जिसने उस तारीख के लिए सबसे पहले नाम लिखवाया था। आपको संदेश मिलता है और स्लॉट {HOLD_H} घंटे तक आपके लिए रोका जाता है। समय पर बुक न करने पर यह अगले मरीज़ को दिया जाता है।",
                    f"कोणी अपॉइंटमेंट रद्द केली किंवा बदलली की तो स्लॉट आधी त्या तारखेसाठी सर्वात आधी नाव नोंदवलेल्या रुग्णाला दिला जातो. तुम्हाला संदेश येतो आणि स्लॉट {HOLD_H} तासांपर्यंत तुमच्यासाठी राखून ठेवला जातो. वेळेत बुक न केल्यास तो पुढच्या रुग्णाला दिला जातो.",
                ),
            ),
            (
                T("Leaving the list", "सूची से नाम हटना", "यादीतून नाव निघणे"),
                T(
                    "If you book any appointment with that doctor, your waiting-list entry for the doctor is closed automatically.",
                    "अगर आप उस डॉक्टर के साथ कोई भी अपॉइंटमेंट बुक कर लेते हैं, तो उस डॉक्टर की प्रतीक्षा सूची से आपका नाम अपने-आप हट जाता है।",
                    "तुम्ही त्या डॉक्टरांकडे कोणतीही अपॉइंटमेंट बुक केल्यास, त्या डॉक्टरांच्या प्रतीक्षा यादीतील तुमचे नाव आपोआप निघते.",
                ),
            ),
        ),
        doc(
            "late-arrival-and-missed-turn",
            T("Late arrival and missed turns", "देर से पहुंचना और बारी छूटना", "उशिरा येणे आणि क्रमांक चुकणे"),
            (
                T("Arriving late", "देर से पहुंचना", "उशिरा पोहोचणे"),
                T(
                    f"Please arrive 15 minutes before your appointment. If you check in more than {GRACE_M} minutes after your appointment time, you keep your appointment but are seen in order of arrival, together with walk-in patients.",
                    f"कृपया अपॉइंटमेंट से 15 मिनट पहले पहुंचें। अगर आप अपॉइंटमेंट के समय से {GRACE_M} मिनट से ज़्यादा देर से चेक-इन करते हैं, तो अपॉइंटमेंट बनी रहती है लेकिन आपको बिना अपॉइंटमेंट वाले मरीज़ों के साथ पहुंचने के क्रम में देखा जाता है।",
                    f"कृपया अपॉइंटमेंटच्या 15 मिनिटे आधी या. अपॉइंटमेंटच्या वेळेनंतर {GRACE_M} मिनिटांपेक्षा जास्त उशिरा चेक-इन केल्यास अपॉइंटमेंट कायम राहते, पण अपॉइंटमेंटशिवाय आलेल्या रुग्णांसोबत येण्याच्या क्रमाने तुम्हाला पाहिले जाते.",
                ),
            ),
            (
                T("Missing your turn", "बारी छूट जाना", "क्रमांक चुकणे"),
                T(
                    "If you are called and are not there, your turn is marked as missed. When you come back, tell the reception; you rejoin the queue in order of your return time.",
                    "अगर आपको बुलाया जाए और आप मौजूद न हों, तो आपकी बारी छूटी हुई मानी जाती है। लौटने पर रिसेप्शन को बताएं; आप लौटने के समय के क्रम में फिर से कतार में जुड़ जाते हैं।",
                    "तुम्हाला बोलावल्यावर तुम्ही हजर नसाल तर तुमचा क्रमांक चुकलेला मानला जातो. परत आल्यावर रिसेप्शनला सांगा; परत आल्याच्या वेळेनुसार तुम्ही पुन्हा रांगेत सामील होता.",
                ),
            ),
            (
                T("Not arriving at all", "बिल्कुल न आना", "अजिबात न येणे"),
                T(
                    "If you do not come on the day, the appointment is recorded as a no-show. There is no fee, but please cancel in advance so someone else can use the slot.",
                    "अगर आप उस दिन नहीं आते, तो अपॉइंटमेंट 'नो-शो' दर्ज होती है। इसकी कोई फ़ीस नहीं है, पर कृपया पहले से रद्द करें ताकि कोई और वह स्लॉट ले सके।",
                    "तुम्ही त्या दिवशी आला नाही तर अपॉइंटमेंट 'नो-शो' म्हणून नोंदवली जाते. याचे कोणतेही शुल्क नाही, पण कृपया आधीच रद्द करा म्हणजे दुसरा कोणी तो स्लॉट वापरू शकेल.",
                ),
            ),
            (
                T("Leaving before you are seen", "दिखाए बिना चले जाना", "न दाखवता निघून जाणे"),
                T(
                    "If you cannot wait any longer, leave the queue in CareFlow (Queue status, or ask the assistant) or tell the reception, so the people behind you move up. This is recorded as 'left without being seen', not as a no-show. If you missed your turn and do not come back before the OPD closes, it is recorded the same way. Either way you get a message and can book a new appointment free of charge.",
                    "अगर आप और इंतज़ार नहीं कर सकते, तो CareFlow में कतार छोड़ें (कतार स्थिति पेज पर, या सहायक से कहें) या रिसेप्शन को बताएं, ताकि आपके पीछे वाले आगे बढ़ सकें। इसे 'बिना दिखाए चले गए' दर्ज किया जाता है, 'नो-शो' नहीं। अगर आपकी बारी छूट गई और आप ओपीडी बंद होने से पहले नहीं लौटे, तो भी ऐसे ही दर्ज होता है। दोनों हालात में आपको संदेश मिलता है और आप बिना शुल्क नई अपॉइंटमेंट बुक कर सकते हैं।",
                    "तुम्हाला आणखी थांबता येत नसेल तर CareFlow मध्ये रांग सोडा (रांग स्थिती पानावर, किंवा सहाय्यकाला सांगा) किंवा रिसेप्शनला कळवा, म्हणजे तुमच्या मागचे लोक पुढे जातील. हे 'न दाखवता गेले' म्हणून नोंदवले जाते, 'नो-शो' म्हणून नाही. तुमचा क्रमांक चुकला आणि ओपीडी बंद होण्यापूर्वी तुम्ही परत आला नाही, तरीही असेच नोंदवले जाते. दोन्ही वेळी तुम्हाला संदेश येतो आणि विनाशुल्क नवीन अपॉइंटमेंट बुक करता येते.",
                ),
            ),
        ),
        doc(
            "opd-queue-and-tokens",
            T("How the OPD queue works", "ओपीडी कतार कैसे चलती है", "ओपीडी रांग कशी चालते"),
            (
                T("Tokens", "टोकन", "टोकन"),
                T(
                    "When you check in, you get a token: tokens starting with B are for booked appointments, W for walk-in patients registered at the reception, V for patients who joined the queue online, and T for patients moved from another doctor's queue.",
                    "चेक-इन करने पर आपको टोकन मिलता है: B से शुरू होने वाले टोकन बुक की गई अपॉइंटमेंट के लिए, W रिसेप्शन पर पंजीकृत बिना अपॉइंटमेंट आए मरीज़ों के लिए, V ऑनलाइन कतार में जुड़े मरीज़ों के लिए, और T किसी दूसरे डॉक्टर की कतार से भेजे गए मरीज़ों के लिए होते हैं।",
                    "चेक-इन केल्यावर तुम्हाला टोकन मिळते: B ने सुरू होणारी टोकन बुक केलेल्या अपॉइंटमेंटसाठी, W रिसेप्शनवर नोंदणी केलेल्या अपॉइंटमेंटशिवाय आलेल्या रुग्णांसाठी, V ऑनलाइन रांगेत सामील झालेल्या रुग्णांसाठी, आणि T दुसऱ्या डॉक्टरांच्या रांगेतून हलवलेल्या रुग्णांसाठी असतात.",
                ),
            ),
            (
                T("Order of patients", "मरीज़ों का क्रम", "रुग्णांचा क्रम"),
                T(
                    "Patients with a booking are seen in the order of their appointment times. Walk-in patients and patients who joined online are seen in the gaps between booked appointments, in the order they arrived or joined.",
                    "अपॉइंटमेंट वाले मरीज़ों को उनके अपॉइंटमेंट समय के क्रम में देखा जाता है। बिना अपॉइंटमेंट आए और ऑनलाइन जुड़े मरीज़ों को बुक की गई अपॉइंटमेंट के बीच के खाली समय में, पहुंचने या जुड़ने के क्रम में देखा जाता है।",
                    "अपॉइंटमेंट असलेल्या रुग्णांना त्यांच्या अपॉइंटमेंटच्या वेळेच्या क्रमाने पाहिले जाते. अपॉइंटमेंटशिवाय आलेल्या आणि ऑनलाइन सामील झालेल्या रुग्णांना बुक केलेल्या अपॉइंटमेंटमधील मोकळ्या वेळेत, आल्याच्या किंवा सामील झाल्याच्या क्रमाने पाहिले जाते.",
                ),
            ),
            (
                T("Priority", "प्राथमिकता", "प्राधान्य"),
                T(
                    "Only your doctor can move a patient forward for a medical reason; the reception can ask the doctor, but cannot decide it. The hospital may also give priority to senior citizens, children, pregnant women and people with a disability. For a patient with an appointment, this priority counts from the appointment time, so coming early does not move you ahead. Every change is recorded.",
                    "सिर्फ़ आपके डॉक्टर ही किसी चिकित्सा कारण से मरीज़ को आगे कर सकते हैं; रिसेप्शन डॉक्टर से अनुरोध कर सकता है, पर खुद निर्णय नहीं ले सकता। अस्पताल वरिष्ठ नागरिकों, बच्चों, गर्भवती महिलाओं और दिव्यांग लोगों को भी प्राथमिकता दे सकता है। अपॉइंटमेंट वाले मरीज़ के लिए यह प्राथमिकता अपॉइंटमेंट के समय से गिनी जाती है, इसलिए जल्दी आने से आप आगे नहीं होते। हर बदलाव दर्ज होता है।",
                    "फक्त तुमचे डॉक्टरच वैद्यकीय कारणासाठी रुग्णाला पुढे घेऊ शकतात; रिसेप्शन डॉक्टरांना विनंती करू शकते, पण स्वतः निर्णय घेऊ शकत नाही. रुग्णालय ज्येष्ठ नागरिक, मुले, गर्भवती महिला आणि दिव्यांग व्यक्तींनाही प्राधान्य देऊ शकते. अपॉइंटमेंट असलेल्या रुग्णासाठी हे प्राधान्य अपॉइंटमेंटच्या वेळेपासून मोजले जाते, त्यामुळे लवकर आल्याने तुम्ही पुढे जात नाही. प्रत्येक बदल नोंदवला जातो.",
                ),
            ),
            (
                T("Moving to another doctor", "दूसरे डॉक्टर के पास भेजा जाना", "दुसऱ्या डॉक्टरांकडे हलवले जाणे"),
                T(
                    "To shorten waits, the reception may move you to another doctor of the same department, and a doctor may send you to another department. You keep the time you checked in, so you do not go to the back of the line, and you get a message with your new token.",
                    "इंतज़ार कम करने के लिए रिसेप्शन आपको उसी विभाग के दूसरे डॉक्टर के पास भेज सकता है, और डॉक्टर आपको दूसरे विभाग में भेज सकते हैं। आपका चेक-इन समय बना रहता है, इसलिए आप कतार में पीछे नहीं जाते, और आपको नए टोकन के साथ संदेश मिलता है।",
                    "प्रतीक्षा कमी करण्यासाठी रिसेप्शन तुम्हाला त्याच विभागातील दुसऱ्या डॉक्टरांकडे हलवू शकते, आणि डॉक्टर तुम्हाला दुसऱ्या विभागात पाठवू शकतात. तुमची चेक-इन वेळ कायम राहते, त्यामुळे तुम्ही रांगेत मागे जात नाही, आणि तुम्हाला नवीन टोकनसह संदेश येतो.",
                ),
            ),
            (
                T("Waiting time estimates", "इंतज़ार के समय का अनुमान", "प्रतीक्षा वेळेचा अंदाज"),
                T(
                    "CareFlow shows an estimated waiting time as a range, for example 'about 35 minutes (25–50)'. The estimate changes when the doctor takes a break, is delayed or handles an emergency. If the doctor is delayed or called to an emergency, everyone waiting gets a message with the expected delay and keeps their place.",
                    "CareFlow इंतज़ार का अनुमानित समय एक दायरे में दिखाता है, जैसे 'लगभग 35 मिनट (25–50)'। डॉक्टर के ब्रेक लेने, देर होने या इमरजेंसी देखने पर अनुमान बदल जाता है। अगर डॉक्टर को देर हो या उन्हें किसी इमरजेंसी में बुलाया जाए, तो इंतज़ार कर रहे हर व्यक्ति को अनुमानित देरी के साथ संदेश मिलता है और उसकी जगह बनी रहती है।",
                    "CareFlow अंदाजे प्रतीक्षा वेळ एका मर्यादेत दाखवतो, उदाहरणार्थ 'सुमारे 35 मिनिटे (25–50)'. डॉक्टरांनी विश्रांती घेतल्यास, उशीर झाल्यास किंवा आपत्कालीन रुग्ण पाहिल्यास अंदाज बदलतो. डॉक्टरांना उशीर झाल्यास किंवा आपत्कालीन रुग्णासाठी बोलावल्यास, प्रतीक्षेतील प्रत्येकाला अपेक्षित उशिरासह संदेश येतो आणि त्यांची जागा कायम राहते.",
                ),
            ),
        ),
        doc(
            "doctor-unavailable",
            T("When a doctor is unavailable", "जब डॉक्टर उपलब्ध न हों", "डॉक्टर उपलब्ध नसतात तेव्हा"),
            (
                T("What we do", "हम क्या करते हैं", "आम्ही काय करतो"),
                T(
                    "If a doctor has to leave or cannot come, the hospital sends a message to every affected patient and closes that doctor's queue for the day. Patients who are already waiting may be moved to another doctor of the same department who is working that day; they keep their place by check-in time and get a new token.",
                    "अगर किसी डॉक्टर को जाना पड़े या वे न आ सकें, तो अस्पताल हर प्रभावित मरीज़ को संदेश भेजता है और उस दिन के लिए उस डॉक्टर की कतार बंद कर देता है। जो मरीज़ पहले से इंतज़ार कर रहे हैं, उन्हें उसी दिन काम कर रहे उसी विभाग के दूसरे डॉक्टर के पास भेजा जा सकता है; चेक-इन समय के अनुसार उनकी जगह बनी रहती है और उन्हें नया टोकन मिलता है।",
                    "एखाद्या डॉक्टरांना जावे लागले किंवा ते येऊ शकले नाहीत तर रुग्णालय प्रत्येक बाधित रुग्णाला संदेश पाठवते आणि त्या दिवसासाठी त्या डॉक्टरांची रांग बंद करते. आधीच प्रतीक्षेत असलेल्या रुग्णांना त्या दिवशी काम करणाऱ्या त्याच विभागातील दुसऱ्या डॉक्टरांकडे हलवले जाऊ शकते; चेक-इन वेळेनुसार त्यांची जागा कायम राहते आणि त्यांना नवीन टोकन मिळते.",
                ),
            ),
            (
                T("Rebooking", "दोबारा बुकिंग", "पुन्हा बुकिंग"),
                T(
                    "You can choose a new slot with CareFlow or at the reception, with the same doctor on another day or with another doctor of the same department. This rescheduling is always free and allowed at any time.",
                    "आप CareFlow से या रिसेप्शन पर नया स्लॉट चुन सकते हैं, उसी डॉक्टर के साथ किसी और दिन या उसी विभाग के किसी दूसरे डॉक्टर के साथ। यह बदलाव हमेशा मुफ़्त है और किसी भी समय किया जा सकता है।",
                    "तुम्ही CareFlow वरून किंवा रिसेप्शनवर नवीन स्लॉट निवडू शकता, त्याच डॉक्टरांकडे दुसऱ्या दिवशी किंवा त्याच विभागातील दुसऱ्या डॉक्टरांकडे. हा बदल नेहमी विनामूल्य असतो आणि कधीही करता येतो.",
                ),
            ),
        ),
        doc(
            "consultation-fees-and-payment",
            T("Consultation fees and payment", "परामर्श फ़ीस और भुगतान", "सल्ला शुल्क आणि भरणा"),
            (
                T("Fees", "फ़ीस", "शुल्क"),
                bullets(
                    [
                        T(
                            "General Medicine consultation: ₹400.",
                            "सामान्य चिकित्सा परामर्श: ₹400।",
                            "जनरल मेडिसिन सल्ला: ₹400.",
                        ),
                        T(
                            "Specialist consultation (all other departments): ₹600.",
                            "विशेषज्ञ परामर्श (बाकी सभी विभाग): ₹600।",
                            "तज्ज्ञ सल्ला (इतर सर्व विभाग): ₹600.",
                        ),
                        T(
                            "A follow-up visit with the same doctor within 7 days is free.",
                            "उसी डॉक्टर के पास 7 दिन के अंदर दोबारा दिखाना मुफ़्त है।",
                            "त्याच डॉक्टरांकडे 7 दिवसांच्या आत पुन्हा दाखवणे विनामूल्य आहे.",
                        ),
                        T(
                            "Senior citizens (60 years and above) get 20% off the consultation fee.",
                            "वरिष्ठ नागरिकों (60 वर्ष और ऊपर) को परामर्श फ़ीस पर 20% की छूट मिलती है।",
                            "ज्येष्ठ नागरिकांना (60 वर्षे व त्याहून अधिक) सल्ला शुल्कात 20% सूट मिळते.",
                        ),
                    ]
                ),
            ),
            (
                T("How to pay", "भुगतान कैसे करें", "पैसे कसे भरावे"),
                T(
                    "Pay at the billing counter on the ground floor (08:00–20:00) by cash, UPI or card before the consultation. CareFlow does not take payments.",
                    "परामर्श से पहले भूतल के बिलिंग काउंटर (08:00–20:00) पर नकद, UPI या कार्ड से भुगतान करें। CareFlow भुगतान नहीं लेता।",
                    "सल्ल्यापूर्वी तळमजल्यावरील बिलिंग काउंटरवर (08:00–20:00) रोख, UPI किंवा कार्डने पैसे भरा. CareFlow पैसे स्वीकारत नाही.",
                ),
            ),
        ),
        doc(
            "documents-to-bring",
            T("Documents to bring to your visit", "मिलने आते समय कौन से कागज़ात लाएं", "भेटीला येताना कोणती कागदपत्रे आणावी"),
            (
                T("Checklist", "सूची", "यादी"),
                bullets(
                    [
                        T(
                            "A photo ID (for example Aadhaar card, PAN card, passport or driving licence).",
                            "फ़ोटो पहचान पत्र (जैसे आधार कार्ड, पैन कार्ड, पासपोर्ट या ड्राइविंग लाइसेंस)।",
                            "फोटो ओळखपत्र (उदा. आधार कार्ड, पॅन कार्ड, पासपोर्ट किंवा वाहन परवाना).",
                        ),
                        T(
                            "Previous prescriptions, test reports and X-ray or scan films.",
                            "पुराने पर्चे, जांच रिपोर्ट और एक्स-रे या स्कैन की फ़िल्में।",
                            "जुन्या चिठ्ठ्या, तपासणी रिपोर्ट आणि एक्स-रे किंवा स्कॅनच्या फिल्म्स.",
                        ),
                        T(
                            "A list of the medicines you currently take.",
                            "आप अभी जो दवाएं ले रहे हैं उनकी सूची।",
                            "तुम्ही सध्या घेत असलेल्या औषधांची यादी.",
                        ),
                        T(
                            "Your health insurance card or the hospital's Sahayata scheme card, if you have one.",
                            "आपका स्वास्थ्य बीमा कार्ड या अस्पताल की सहायता योजना का कार्ड, अगर हो।",
                            "तुमचे आरोग्य विमा कार्ड किंवा रुग्णालयाच्या सहायता योजनेचे कार्ड, असल्यास.",
                        ),
                        T("For children: the vaccination card.", "बच्चों के लिए: टीकाकरण कार्ड।", "मुलांसाठी: लसीकरण कार्ड."),
                    ]
                ),
            ),
        ),
        doc(
            "caregiver-accounts",
            T("Caregiver accounts", "देखभालकर्ता (केयरगिवर) खाते", "काळजीवाहक (केअरगिव्हर) खाती"),
            (
                T("What a caregiver can do", "देखभालकर्ता क्या कर सकता है", "काळजीवाहक काय करू शकतो"),
                T(
                    "A family member or caregiver can book, reschedule and cancel appointments and see the appointment history of a linked patient, for example an elderly parent or a child.",
                    "परिवार का सदस्य या देखभालकर्ता जुड़े हुए मरीज़, जैसे बुज़ुर्ग माता-पिता या बच्चे, की अपॉइंटमेंट बुक कर सकता है, बदल सकता है, रद्द कर सकता है और उसका इतिहास देख सकता है।",
                    "कुटुंबातील सदस्य किंवा काळजीवाहक जोडलेल्या रुग्णाची, उदाहरणार्थ वृद्ध आई-वडील किंवा मूल, अपॉइंटमेंट बुक, बदल किंवा रद्द करू शकतो आणि त्याचा इतिहास पाहू शकतो.",
                ),
            ),
            (
                T("Getting verified", "सत्यापन कैसे कराएं", "पडताळणी कशी करावी"),
                T(
                    "The link must be verified once at the reception: bring a photo ID for yourself and for the patient. Until the link is verified, the caregiver cannot see or change the patient's appointments.",
                    "लिंक को एक बार रिसेप्शन पर सत्यापित कराना होता है: अपना और मरीज़ का फ़ोटो पहचान पत्र लाएं। लिंक सत्यापित होने तक देखभालकर्ता मरीज़ की अपॉइंटमेंट न देख सकता है, न बदल सकता है।",
                    "लिंक एकदा रिसेप्शनवर पडताळून घ्यावी लागते: स्वतःचे आणि रुग्णाचे फोटो ओळखपत्र आणा. लिंक पडताळली जाईपर्यंत काळजीवाहक रुग्णाच्या अपॉइंटमेंट पाहू किंवा बदलू शकत नाही.",
                ),
            ),
        ),
        doc(
            "privacy-and-your-data",
            T("Privacy and your data", "गोपनीयता और आपका डेटा", "गोपनीयता आणि तुमचा डेटा"),
            (
                T("What we keep", "हम क्या रखते हैं", "आम्ही काय ठेवतो"),
                T(
                    "CareFlow keeps only what it needs to manage appointments: your name, birth year, preferred language and a masked phone number. Phone numbers are never shown in full in logs or messages.",
                    "CareFlow अपॉइंटमेंट संभालने के लिए सिर्फ़ ज़रूरी जानकारी रखता है: आपका नाम, जन्म वर्ष, पसंदीदा भाषा और छिपाया हुआ (मास्क्ड) फ़ोन नंबर। लॉग या संदेशों में फ़ोन नंबर कभी पूरा नहीं दिखाया जाता।",
                    "CareFlow अपॉइंटमेंट सांभाळण्यासाठी फक्त आवश्यक माहिती ठेवतो: तुमचे नाव, जन्मवर्ष, आवडती भाषा आणि लपवलेला (मास्क्ड) फोन नंबर. लॉग किंवा संदेशांमध्ये फोन नंबर कधीही पूर्ण दाखवला जात नाही.",
                ),
            ),
            (
                T("Who can see your appointments", "आपकी अपॉइंटमेंट कौन देख सकता है", "तुमच्या अपॉइंटमेंट कोण पाहू शकतो"),
                T(
                    "Only you, a caregiver you have verified, and hospital staff. Every change to an appointment is recorded with who made it and when.",
                    "सिर्फ़ आप, आपका सत्यापित देखभालकर्ता और अस्पताल का स्टाफ़। अपॉइंटमेंट में हर बदलाव इस जानकारी के साथ दर्ज होता है कि किसने और कब किया।",
                    "फक्त तुम्ही, तुम्ही पडताळलेला काळजीवाहक आणि रुग्णालयाचे कर्मचारी. अपॉइंटमेंटमधील प्रत्येक बदल कोणी आणि केव्हा केला यासह नोंदवला जातो.",
                ),
            ),
            (
                T("About this demo", "इस डेमो के बारे में", "या डेमोबद्दल"),
                T(
                    "Indravani General Hospital is fictional and all patient data in this demo is synthetic. It is not for medical use.",
                    "इंद्रवाणी जनरल हॉस्पिटल काल्पनिक है और इस डेमो का पूरा मरीज़ डेटा कृत्रिम है। यह चिकित्सा उपयोग के लिए नहीं है।",
                    "इंद्रवाणी जनरल हॉस्पिटल काल्पनिक आहे आणि या डेमोतील सर्व रुग्ण डेटा कृत्रिम आहे. हे वैद्यकीय वापरासाठी नाही.",
                ),
            ),
        ),
        doc(
            "visiting-hours-and-companions",
            T("Visiting hours and companions", "मुलाक़ात का समय और साथ आने वाले", "भेटीची वेळ आणि सोबत येणारे"),
            (
                T("OPD visits", "ओपीडी में", "ओपीडीमध्ये"),
                T(
                    "One adult companion may come with each patient into the consultation room. Children under 18 must come with a parent or guardian.",
                    "हर मरीज़ के साथ एक वयस्क साथी परामर्श कक्ष में आ सकता है। 18 साल से कम उम्र के बच्चों को माता-पिता या अभिभावक के साथ आना ज़रूरी है।",
                    "प्रत्येक रुग्णासोबत एक प्रौढ सोबती सल्ला कक्षात येऊ शकतो. 18 वर्षांखालील मुलांनी आई-वडील किंवा पालकांसोबत येणे आवश्यक आहे.",
                ),
            ),
            (
                T("Ward visiting hours", "वार्ड में मुलाक़ात का समय", "वॉर्डमध्ये भेटीची वेळ"),
                T(
                    "Admitted patients can have visitors every day from 16:00 to 19:00, two visitors at a time. Visitor passes are issued at the reception.",
                    "भर्ती मरीज़ों से रोज़ 16:00 से 19:00 तक मिला जा सकता है, एक समय में दो लोग। मुलाक़ात पास रिसेप्शन पर मिलते हैं।",
                    "दाखल रुग्णांना रोज 16:00 ते 19:00 दरम्यान भेटता येते, एका वेळी दोन व्यक्ती. भेटीचे पास रिसेप्शनवर मिळतात.",
                ),
            ),
        ),
        doc(
            "emergencies",
            T("Emergencies", "इमरजेंसी (आपातकाल)", "आपत्कालीन परिस्थिती"),
            (
                T(
                    "CareFlow is not for emergencies",
                    "CareFlow इमरजेंसी के लिए नहीं है",
                    "CareFlow आपत्कालीन परिस्थितीसाठी नाही",
                ),
                T(
                    "If you have chest pain, difficulty breathing, severe bleeding, signs of a stroke, a seizure, a serious injury or any other emergency, do not wait for an appointment. Call 112 or 108 for an ambulance, or go straight to the nearest emergency department.",
                    "अगर आपको सीने में दर्द, सांस लेने में तकलीफ़, बहुत ज़्यादा खून बहना, लकवे के लक्षण, दौरा, गंभीर चोट या कोई और इमरजेंसी है, तो अपॉइंटमेंट का इंतज़ार न करें। एम्बुलेंस के लिए 112 या 108 पर कॉल करें, या सीधे नज़दीकी इमरजेंसी विभाग जाएं।",
                    "छातीत दुखणे, श्वास घेण्यास त्रास, खूप रक्तस्राव, पक्षाघाताची लक्षणे, झटका, गंभीर दुखापत किंवा इतर कोणतीही आपत्कालीन स्थिती असल्यास अपॉइंटमेंटची वाट पाहू नका. रुग्णवाहिकेसाठी 112 किंवा 108 वर कॉल करा, किंवा थेट जवळच्या आपत्कालीन विभागात जा.",
                ),
            ),
            (
                T("Our emergency department", "हमारा इमरजेंसी विभाग", "आमचा आपत्कालीन विभाग"),
                T(
                    "The emergency department of Indravani General Hospital is on the ground floor near the main gate and is open 24 hours a day, every day. No appointment is needed.",
                    "इंद्रवाणी जनरल हॉस्पिटल का इमरजेंसी विभाग मुख्य द्वार के पास भूतल पर है और हर दिन 24 घंटे खुला रहता है। अपॉइंटमेंट की ज़रूरत नहीं है।",
                    "इंद्रवाणी जनरल हॉस्पिटलचा आपत्कालीन विभाग मुख्य प्रवेशद्वाराजवळ तळमजल्यावर आहे आणि दररोज 24 तास सुरू असतो. अपॉइंटमेंटची गरज नाही.",
                ),
            ),
        ),
        doc(
            "language-support",
            T("Language support", "भाषा सहायता", "भाषा सहाय्य"),
            (
                T("Languages", "भाषाएं", "भाषा"),
                T(
                    "CareFlow understands and replies in English, Hindi and Marathi; it answers in the language you write in. Doctors' spoken languages are listed in their profiles, and you can ask CareFlow for a doctor who speaks your language.",
                    "CareFlow अंग्रेज़ी, हिंदी और मराठी समझता है और उन्हीं में जवाब देता है; आप जिस भाषा में लिखते हैं उसी में जवाब मिलता है। डॉक्टरों की बोली जाने वाली भाषाएं उनकी प्रोफ़ाइल में दी गई हैं, और आप CareFlow से अपनी भाषा बोलने वाला डॉक्टर मांग सकते हैं।",
                    "CareFlow इंग्रजी, हिंदी आणि मराठी समजतो आणि त्यातच उत्तर देतो; तुम्ही ज्या भाषेत लिहाल त्याच भाषेत उत्तर मिळते. डॉक्टरांच्या बोलल्या जाणाऱ्या भाषा त्यांच्या प्रोफाइलमध्ये दिल्या आहेत आणि तुम्ही CareFlow कडे तुमची भाषा बोलणारे डॉक्टर मागू शकता.",
                ),
            ),
            (
                T("Help at the hospital", "अस्पताल में मदद", "रुग्णालयात मदत"),
                T(
                    "Reception staff speak English, Hindi and Marathi and can help you fill forms.",
                    "रिसेप्शन स्टाफ़ अंग्रेज़ी, हिंदी और मराठी बोलता है और फ़ॉर्म भरने में मदद कर सकता है।",
                    "रिसेप्शनचे कर्मचारी इंग्रजी, हिंदी आणि मराठी बोलतात आणि फॉर्म भरण्यास मदत करू शकतात.",
                ),
            ),
        ),
        doc(
            "talk-to-a-person",
            T("Talking to a person", "किसी व्यक्ति से बात करना", "एखाद्या व्यक्तीशी बोलणे"),
            (
                T("How to reach a person", "किसी व्यक्ति तक कैसे पहुंचें", "व्यक्तीपर्यंत कसे पोहोचावे"),
                T(
                    "In CareFlow, press 'Talk to a person' or simply ask for a human. A help ticket is created and a member of the reception team will contact you during working hours (08:00–20:00). You can also visit the help desk at the reception on the ground floor.",
                    "CareFlow में 'किसी व्यक्ति से बात करें' दबाएं या बस किसी इंसान से बात करने को कहें। एक सहायता टिकट बनता है और रिसेप्शन टीम का कोई सदस्य कामकाज के समय (08:00–20:00) में आपसे संपर्क करेगा। आप भूतल के रिसेप्शन पर हेल्प डेस्क पर भी आ सकते हैं।",
                    "CareFlow मध्ये 'व्यक्तीशी बोला' दाबा किंवा फक्त माणसाशी बोलायचे आहे असे सांगा. एक मदत तिकीट तयार होते आणि रिसेप्शन टीमचा सदस्य कामकाजाच्या वेळेत (08:00–20:00) तुमच्याशी संपर्क साधेल. तुम्ही तळमजल्यावरील रिसेप्शनमधील हेल्प डेस्कवरही येऊ शकता.",
                ),
            ),
            (
                T("When CareFlow hands over", "CareFlow कब किसी व्यक्ति को सौंपता है", "CareFlow केव्हा व्यक्तीकडे सोपवतो"),
                T(
                    "CareFlow also hands you over to a person when it cannot help after three attempts, or when your question is outside what it can do.",
                    "जब CareFlow तीन कोशिशों के बाद भी मदद न कर सके, या आपका सवाल उसके दायरे से बाहर हो, तब भी वह आपको किसी व्यक्ति को सौंप देता है।",
                    "तीन प्रयत्नांनंतरही CareFlow मदत करू शकला नाही, किंवा तुमचा प्रश्न त्याच्या कक्षेबाहेर असेल, तेव्हाही तो तुम्हाला एखाद्या व्यक्तीकडे सोपवतो.",
                ),
            ),
        ),
        doc(
            "medical-advice-limits",
            T(
                "What CareFlow can and cannot advise",
                "CareFlow क्या सलाह दे सकता है और क्या नहीं",
                "CareFlow काय सल्ला देऊ शकतो आणि काय नाही",
            ),
            (
                T("No diagnosis or prescriptions", "न निदान, न दवा", "निदान नाही, औषध नाही"),
                T(
                    "CareFlow does not diagnose illnesses, suggest medicines or tell you doses. For these questions, please consult a doctor; CareFlow can book the appointment for you.",
                    "CareFlow बीमारी का निदान नहीं करता, दवाएं नहीं सुझाता और खुराक नहीं बताता। ऐसे सवालों के लिए कृपया डॉक्टर से मिलें; CareFlow आपके लिए अपॉइंटमेंट बुक कर सकता है।",
                    "CareFlow आजाराचे निदान करत नाही, औषधे सुचवत नाही आणि डोस सांगत नाही. अशा प्रश्नांसाठी कृपया डॉक्टरांचा सल्ला घ्या; CareFlow तुमच्यासाठी अपॉइंटमेंट बुक करू शकतो.",
                ),
            ),
            (
                T("Choosing a department", "विभाग चुनना", "विभाग निवडणे"),
                T(
                    "CareFlow can suggest which department usually handles a symptom, for example the ENT department for ear pain. If you are unsure, General Medicine is a good place to start.",
                    "CareFlow बता सकता है कि किसी लक्षण के लिए आमतौर पर कौन सा विभाग देखता है, जैसे कान दर्द के लिए ईएनटी विभाग। अगर आप तय न कर पाएं, तो सामान्य चिकित्सा से शुरुआत करना अच्छा है।",
                    "एखाद्या लक्षणासाठी साधारणपणे कोणता विभाग पाहतो हे CareFlow सुचवू शकतो, उदाहरणार्थ कानदुखीसाठी ईएनटी विभाग. खात्री नसल्यास जनरल मेडिसिनपासून सुरुवात करणे योग्य आहे.",
                ),
            ),
        ),
        doc(
            "medical-records-and-certificates",
            T("Medical records and certificates", "मेडिकल रिकॉर्ड और प्रमाणपत्र", "वैद्यकीय नोंदी आणि प्रमाणपत्रे"),
            (
                T("Copies of records", "रिकॉर्ड की प्रतियां", "नोंदींच्या प्रती"),
                T(
                    "Request copies of your consultation notes or discharge summary at the Medical Records counter on the ground floor with a photo ID. Copies are ready in 2 working days.",
                    "भूतल के मेडिकल रिकॉर्ड काउंटर पर फ़ोटो पहचान पत्र के साथ अपने परामर्श नोट्स या डिस्चार्ज सारांश की प्रतियां मांगें। प्रतियां 2 कार्य-दिवसों में तैयार हो जाती हैं।",
                    "तळमजल्यावरील मेडिकल रेकॉर्ड काउंटरवर फोटो ओळखपत्रासह तुमच्या सल्ल्याच्या नोंदी किंवा डिस्चार्ज सारांशाच्या प्रती मागा. प्रती 2 कामाच्या दिवसांत तयार होतात.",
                ),
            ),
            (
                T("Certificates", "प्रमाणपत्र", "प्रमाणपत्रे"),
                T(
                    "Fitness, sick-leave and school certificates are issued only by the treating doctor during a consultation.",
                    "फ़िटनेस, बीमारी की छुट्टी और स्कूल के प्रमाणपत्र सिर्फ़ इलाज करने वाले डॉक्टर परामर्श के दौरान देते हैं।",
                    "फिटनेस, आजारपणाची रजा आणि शाळेची प्रमाणपत्रे फक्त उपचार करणारे डॉक्टर सल्ल्यादरम्यान देतात.",
                ),
            ),
        ),
        doc(
            "feedback-and-complaints",
            T("Feedback and complaints", "सुझाव और शिकायत", "अभिप्राय आणि तक्रारी"),
            (
                T("How to give feedback", "सुझाव कैसे दें", "अभिप्राय कसा द्यावा"),
                T(
                    "Tell the help desk at the reception, write in the feedback register, or ask CareFlow to connect you to a person. We reply to every complaint within 3 working days.",
                    "रिसेप्शन के हेल्प डेस्क को बताएं, सुझाव रजिस्टर में लिखें, या CareFlow से किसी व्यक्ति से जोड़ने को कहें। हम हर शिकायत का जवाब 3 कार्य-दिवसों में देते हैं।",
                    "रिसेप्शनमधील हेल्प डेस्कला सांगा, अभिप्राय रजिस्टरमध्ये लिहा, किंवा CareFlow ला एखाद्या व्यक्तीशी जोडण्यास सांगा. आम्ही प्रत्येक तक्रारीला 3 कामाच्या दिवसांत उत्तर देतो.",
                ),
            ),
        ),
        doc(
            "walk-in-patients",
            T("Walk-in patients", "बिना अपॉइंटमेंट आने वाले मरीज़", "अपॉइंटमेंटशिवाय येणारे रुग्ण"),
            (
                T("Coming without an appointment", "बिना अपॉइंटमेंट आना", "अपॉइंटमेंटशिवाय येणे"),
                T(
                    "You can come to the OPD without an appointment on the doctor's OPD days. Register at the reception with your name, birth year and mobile number to get a W token. Walk-in patients are seen in the gaps between booked appointments, so the wait can be longer than with a booking.",
                    "आप डॉक्टर के ओपीडी दिनों में बिना अपॉइंटमेंट ओपीडी आ सकते हैं। W टोकन पाने के लिए रिसेप्शन पर अपना नाम, जन्म वर्ष और मोबाइल नंबर देकर पंजीकरण कराएं। बिना अपॉइंटमेंट वाले मरीज़ों को बुक की गई अपॉइंटमेंट के बीच के खाली समय में देखा जाता है, इसलिए इंतज़ार ज़्यादा हो सकता है।",
                    "डॉक्टरांच्या ओपीडी दिवशी तुम्ही अपॉइंटमेंटशिवाय ओपीडीत येऊ शकता. W टोकन मिळवण्यासाठी रिसेप्शनवर तुमचे नाव, जन्मवर्ष आणि मोबाइल नंबर देऊन नोंदणी करा. अपॉइंटमेंटशिवाय आलेल्या रुग्णांना बुक केलेल्या अपॉइंटमेंटमधील मोकळ्या वेळेत पाहिले जाते, त्यामुळे प्रतीक्षा जास्त असू शकते.",
                ),
            ),
            (
                T("Joining from your phone", "फ़ोन से जुड़ना", "फोनवरून सामील होणे"),
                T(
                    "If you have a CareFlow account, you can also join a doctor's queue from your phone before you leave home and come in when your turn is near. See 'Joining a queue online'.",
                    "अगर आपका CareFlow खाता है, तो आप घर से निकलने से पहले अपने फ़ोन से डॉक्टर की कतार में जुड़ सकते हैं और बारी पास आने पर आ सकते हैं। 'ऑनलाइन कतार में जुड़ना' देखें।",
                    "तुमचे CareFlow खाते असल्यास, घरातून निघण्यापूर्वी तुमच्या फोनवरून डॉक्टरांच्या रांगेत सामील होऊन क्रमांक जवळ आल्यावर येऊ शकता. 'ऑनलाइन रांगेत सामील होणे' पहा.",
                ),
            ),
        ),
        doc(
            "online-check-in",
            T("Checking in for your appointment", "अपॉइंटमेंट के लिए चेक-इन", "अपॉइंटमेंटसाठी चेक-इन"),
            (
                T("When you can check in", "आप कब चेक-इन कर सकते हैं", "तुम्ही केव्हा चेक-इन करू शकता"),
                T(
                    f"You can check in yourself from {CHECK_IN_OPENS_M} minutes before your appointment time until {CHECK_IN_CLOSES_M} minutes after it starts. After that, please check in at the reception desk; you are then seen in order of arrival. A caregiver with a verified link can check in for the patient.",
                    f"आप अपॉइंटमेंट के समय से {CHECK_IN_OPENS_M} मिनट पहले से लेकर उसके शुरू होने के {CHECK_IN_CLOSES_M} मिनट बाद तक खुद चेक-इन कर सकते हैं। उसके बाद कृपया रिसेप्शन डेस्क पर चेक-इन करें; तब आपको पहुंचने के क्रम में देखा जाता है। सत्यापित लिंक वाला देखभालकर्ता मरीज़ के लिए चेक-इन कर सकता है।",
                    f"तुम्ही अपॉइंटमेंटच्या वेळेच्या {CHECK_IN_OPENS_M} मिनिटे आधीपासून ती सुरू झाल्यानंतर {CHECK_IN_CLOSES_M} मिनिटांपर्यंत स्वतः चेक-इन करू शकता. त्यानंतर कृपया रिसेप्शन डेस्कवर चेक-इन करा; तेव्हा तुम्हाला आल्याच्या क्रमाने पाहिले जाते. पडताळलेली लिंक असलेला काळजीवाहक रुग्णासाठी चेक-इन करू शकतो.",
                ),
            ),
            (
                T("How to check in", "चेक-इन कैसे करें", "चेक-इन कसे करावे"),
                bullets(
                    [
                        T(
                            "Ask the CareFlow assistant to check you in, or use 'Check in now' under My appointments.",
                            "CareFlow सहायक से चेक-इन करने को कहें, या 'मेरी अपॉइंटमेंट' में 'अभी चेक-इन करें' का उपयोग करें।",
                            "CareFlow सहाय्यकाला चेक-इन करण्यास सांगा, किंवा 'माझ्या अपॉइंटमेंट' मध्ये 'आता चेक-इन करा' वापरा.",
                        ),
                        T(
                            "Scan the QR code on your receipt at the self check-in kiosk at the reception.",
                            "रिसेप्शन पर सेल्फ़ चेक-इन कियोस्क पर अपनी रसीद का QR कोड स्कैन करें।",
                            "रिसेप्शनवरील सेल्फ चेक-इन किओस्कवर तुमच्या पावतीवरील QR कोड स्कॅन करा.",
                        ),
                        T(
                            "Or show your receipt code at the reception desk.",
                            "या रिसेप्शन डेस्क पर अपनी रसीद का कोड दिखाएं।",
                            "किंवा रिसेप्शन डेस्कवर तुमच्या पावतीचा कोड दाखवा.",
                        ),
                    ]
                ),
            ),
            (
                T("After checking in", "चेक-इन के बाद", "चेक-इन केल्यानंतर"),
                T(
                    "You get a token straight away and can follow your place and estimated wait on the Queue status page.",
                    "आपको तुरंत टोकन मिलता है और आप कतार स्थिति पेज पर अपनी जगह और अनुमानित इंतज़ार देख सकते हैं।",
                    "तुम्हाला लगेच टोकन मिळते आणि रांग स्थिती पानावर तुमची जागा आणि अंदाजे प्रतीक्षा पाहता येते.",
                ),
            ),
        ),
        doc(
            "join-queue-online",
            T("Joining a queue online", "ऑनलाइन कतार में जुड़ना", "ऑनलाइन रांगेत सामील होणे"),
            (
                T("Who can join", "कौन जुड़ सकता है", "कोण सामील होऊ शकते"),
                T(
                    "If you have no appointment with a doctor today, you can join that doctor's queue from your phone, in CareFlow (Queue status, or ask the assistant). If you have an appointment with the doctor today, check in for it instead. You can be in one queue at a time.",
                    "अगर आज किसी डॉक्टर के साथ आपकी अपॉइंटमेंट नहीं है, तो आप CareFlow में (कतार स्थिति पेज पर, या सहायक से कहकर) अपने फ़ोन से उस डॉक्टर की कतार में जुड़ सकते हैं। अगर आज उस डॉक्टर के साथ आपकी अपॉइंटमेंट है, तो उसकी जगह उसके लिए चेक-इन करें। आप एक समय में एक ही कतार में रह सकते हैं।",
                    "आज एखाद्या डॉक्टरांकडे तुमची अपॉइंटमेंट नसेल, तर CareFlow मध्ये (रांग स्थिती पानावर, किंवा सहाय्यकाला सांगून) तुमच्या फोनवरून त्या डॉक्टरांच्या रांगेत सामील होऊ शकता. आज त्या डॉक्टरांकडे तुमची अपॉइंटमेंट असेल, तर त्याऐवजी तिच्यासाठी चेक-इन करा. तुम्ही एका वेळी एकाच रांगेत राहू शकता.",
                ),
            ),
            (
                T("When it is open", "यह कब खुला रहता है", "हे केव्हा सुरू असते"),
                T(
                    f"Online joining opens {JOIN_OPENS_M} minutes before the department's OPD starts and closes {JOIN_CLOSES_M} minutes before the OPD ends. To keep the queue fair, each doctor accepts at most {ONLINE_CAP} online patients who have not yet reached the hospital; if the online places are full, please come to the reception.",
                    f"ऑनलाइन जुड़ना विभाग की ओपीडी शुरू होने से {JOIN_OPENS_M} मिनट पहले खुलता है और ओपीडी खत्म होने से {JOIN_CLOSES_M} मिनट पहले बंद हो जाता है। कतार को निष्पक्ष रखने के लिए हर डॉक्टर अधिकतम {ONLINE_CAP} ऐसे ऑनलाइन मरीज़ लेते हैं जो अभी अस्पताल नहीं पहुंचे हैं; ऑनलाइन जगहें भर जाने पर कृपया रिसेप्शन पर आएं।",
                    f"ऑनलाइन सामील होणे विभागाची ओपीडी सुरू होण्याच्या {JOIN_OPENS_M} मिनिटे आधी सुरू होते आणि ओपीडी संपण्याच्या {JOIN_CLOSES_M} मिनिटे आधी बंद होते. रांग न्याय्य ठेवण्यासाठी प्रत्येक डॉक्टर जास्तीत जास्त {ONLINE_CAP} असे ऑनलाइन रुग्ण घेतात जे अजून रुग्णालयात पोहोचलेले नाहीत; ऑनलाइन जागा भरल्यास कृपया रिसेप्शनवर या.",
                ),
            ),
            (
                T("On the day", "उस दिन", "त्या दिवशी"),
                T(
                    "You get a token starting with V and your place in the queue by the time you joined. Please reach the OPD desk before your turn and show your token, so the staff know you have arrived. If you are called and are not there, your turn is marked as missed. If you change your mind, leave the queue in CareFlow so the people behind you move up.",
                    "आपको V से शुरू होने वाला टोकन और जुड़ने के समय के अनुसार कतार में जगह मिलती है। कृपया अपनी बारी से पहले ओपीडी डेस्क पहुंचकर अपना टोकन दिखाएं, ताकि स्टाफ़ को पता चले कि आप आ गए हैं। बुलाए जाने पर अगर आप मौजूद न हों, तो आपकी बारी छूटी हुई मानी जाती है। अगर आपका इरादा बदल जाए, तो CareFlow में कतार छोड़ दें ताकि आपके पीछे वाले आगे बढ़ सकें।",
                    "तुम्हाला V ने सुरू होणारे टोकन आणि सामील झाल्याच्या वेळेनुसार रांगेत जागा मिळते. कृपया तुमचा क्रमांक येण्यापूर्वी ओपीडी डेस्कवर पोहोचून टोकन दाखवा, म्हणजे तुम्ही आला आहात हे कर्मचाऱ्यांना कळेल. बोलावल्यावर तुम्ही हजर नसाल तर तुमचा क्रमांक चुकलेला मानला जातो. तुमचा विचार बदलल्यास CareFlow मध्ये रांग सोडा, म्हणजे तुमच्या मागचे लोक पुढे जातील.",
                ),
            ),
        ),
    ]
