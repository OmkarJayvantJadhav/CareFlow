"""Fixed, localised replies. These are used where the system answers without the
LLM (emergencies, confirmations, refusals), so their wording is deterministic."""

from typing import Any

M: dict[str, dict[str, str]] = {
    "emergency": {
        "en": (
            "This may be a medical emergency. Please call 112 or 108 for an ambulance now, or go to the nearest "
            "emergency department immediately. At Indravani General Hospital the emergency department is on the "
            "ground floor near the main gate and is open 24 hours. Do not wait for an OPD appointment.\n"
            "If this is not an emergency, tell me and I will help you with an appointment."
        ),
        "hi": (
            "यह मेडिकल इमरजेंसी हो सकती है। कृपया अभी एम्बुलेंस के लिए 112 या 108 पर कॉल करें, या तुरंत नज़दीकी "
            "इमरजेंसी विभाग जाएं। इंद्रवाणी जनरल हॉस्पिटल का इमरजेंसी विभाग मुख्य द्वार के पास भूतल पर है और "
            "24 घंटे खुला रहता है। ओपीडी अपॉइंटमेंट का इंतज़ार न करें।\n"
            "अगर यह इमरजेंसी नहीं है, तो मुझे बताएं, मैं अपॉइंटमेंट में आपकी मदद करूंगा।"
        ),
        "mr": (
            "ही वैद्यकीय आपत्कालीन स्थिती असू शकते. कृपया आत्ताच रुग्णवाहिकेसाठी 112 किंवा 108 वर कॉल करा, किंवा "
            "लगेच जवळच्या आपत्कालीन विभागात जा. इंद्रवाणी जनरल हॉस्पिटलचा आपत्कालीन विभाग मुख्य प्रवेशद्वाराजवळ "
            "तळमजल्यावर आहे आणि 24 तास सुरू असतो. ओपीडी अपॉइंटमेंटची वाट पाहू नका.\n"
            "ही आपत्कालीन स्थिती नसल्यास मला सांगा, मी अपॉइंटमेंटसाठी मदत करेन."
        ),
    },
    "handoff": {
        "en": "I have asked a member of our reception team to help you (ticket #{ticket_id}). They will contact you during working hours, 08:00–20:00. You can also visit the help desk at the reception on the ground floor.",
        "hi": "मैंने हमारी रिसेप्शन टीम के सदस्य से आपकी मदद करने को कहा है (टिकट #{ticket_id})। वे कामकाज के समय 08:00–20:00 में आपसे संपर्क करेंगे। आप भूतल के रिसेप्शन पर हेल्प डेस्क पर भी आ सकते हैं।",
        "mr": "मी आमच्या रिसेप्शन टीममधील सदस्याला तुमची मदत करण्यास सांगितले आहे (तिकीट #{ticket_id}). ते कामकाजाच्या वेळेत 08:00–20:00 तुमच्याशी संपर्क साधतील. तुम्ही तळमजल्यावरील रिसेप्शनमधील हेल्प डेस्कवरही येऊ शकता.",
    },
    "handoff_after_failures": {
        "en": "I'm sorry, I couldn't sort this out. I have passed your request to our reception team (ticket #{ticket_id}); they will contact you during working hours, 08:00–20:00.",
        "hi": "माफ़ कीजिए, मैं यह काम पूरा नहीं कर सका। मैंने आपका अनुरोध हमारी रिसेप्शन टीम को भेज दिया है (टिकट #{ticket_id}); वे कामकाज के समय 08:00–20:00 में आपसे संपर्क करेंगे।",
        "mr": "माफ करा, मला हे पूर्ण करता आले नाही. मी तुमची विनंती आमच्या रिसेप्शन टीमकडे पाठवली आहे (तिकीट #{ticket_id}); ते कामकाजाच्या वेळेत 08:00–20:00 तुमच्याशी संपर्क साधतील.",
    },
    "no_source": {
        "en": "I couldn't find this in the hospital's documents, so I don't want to guess. Would you like me to connect you to a person?",
        "hi": "मुझे यह जानकारी अस्पताल के दस्तावेज़ों में नहीं मिली, इसलिए मैं अंदाज़ा नहीं लगाना चाहता। क्या मैं आपको किसी व्यक्ति से जोड़ दूं?",
        "mr": "ही माहिती मला रुग्णालयाच्या कागदपत्रांमध्ये सापडली नाही, त्यामुळे मी अंदाज लावू इच्छित नाही. मी तुम्हाला एखाद्या व्यक्तीशी जोडू का?",
    },
    "no_medicine_advice": {
        "en": "I can't advise on medicines or doses. Please ask a doctor; I can book an appointment for you if you like.",
        "hi": "मैं दवाओं या उनकी खुराक के बारे में सलाह नहीं दे सकता। कृपया डॉक्टर से पूछें; आप चाहें तो मैं आपके लिए अपॉइंटमेंट बुक कर सकता हूं।",
        "mr": "मी औषधे किंवा त्यांच्या डोसबद्दल सल्ला देऊ शकत नाही. कृपया डॉक्टरांना विचारा; हवे असल्यास मी तुमच्यासाठी अपॉइंटमेंट बुक करू शकतो.",
    },
    "confirm_book": {
        "en": "Please confirm: book {patient} with {doctor} ({department}) on {date} at {time}?",
        "hi": "कृपया पुष्टि करें: {patient} के लिए {doctor} ({department}) के साथ {date} को {time} बजे अपॉइंटमेंट बुक करूं?",
        "mr": "कृपया पुष्टी करा: {patient} यांच्यासाठी {doctor} ({department}) यांच्याकडे {date} रोजी {time} वाजता अपॉइंटमेंट बुक करू का?",
    },
    "confirm_reschedule": {
        "en": "Please confirm: move {patient}'s appointment with {old_doctor} on {old_date} at {old_time} to {doctor} on {date} at {time}?",
        "hi": "कृपया पुष्टि करें: {patient} की {old_doctor} के साथ {old_date} {old_time} की अपॉइंटमेंट को {doctor} के साथ {date} {time} पर बदल दूं?",
        "mr": "कृपया पुष्टी करा: {patient} यांची {old_doctor} यांच्याकडील {old_date} {old_time} ची अपॉइंटमेंट {doctor} यांच्याकडे {date} {time} वर हलवू का?",
    },
    "confirm_cancel": {
        "en": "Please confirm: cancel {patient}'s appointment with {doctor} on {date} at {time}?",
        "hi": "कृपया पुष्टि करें: {patient} की {doctor} के साथ {date} {time} की अपॉइंटमेंट रद्द करूं?",
        "mr": "कृपया पुष्टी करा: {patient} यांची {doctor} यांच्याकडील {date} {time} ची अपॉइंटमेंट रद्द करू का?",
    },
    "confirm_waiting_list": {
        "en": "Please confirm: add {patient} to {doctor}'s waiting list for {dates}?",
        "hi": "कृपया पुष्टि करें: {patient} को {dates} के लिए {doctor} की प्रतीक्षा सूची में जोड़ दूं?",
        "mr": "कृपया पुष्टी करा: {patient} यांना {dates} साठी {doctor} यांच्या प्रतीक्षा यादीत जोडू का?",
    },
    "confirm_check_in": {
        "en": "Please confirm: check {patient} in for the appointment with {doctor} ({department}) today at {time}?",
        "hi": "कृपया पुष्टि करें: {patient} को आज {time} बजे {doctor} ({department}) की अपॉइंटमेंट के लिए चेक-इन करूं?",
        "mr": "कृपया पुष्टी करा: {patient} यांना आज {time} वाजताच्या {doctor} ({department}) यांच्याकडील अपॉइंटमेंटसाठी चेक-इन करू का?",
    },
    "confirm_join_queue": {
        "en": "Please confirm: add {patient} to {doctor}'s queue ({department}, floor {floor}) today? {people_ahead} people are ahead now.",
        "hi": "कृपया पुष्टि करें: {patient} को आज {doctor} ({department}, मंज़िल {floor}) की कतार में जोड़ दूं? अभी आगे {people_ahead} लोग हैं।",
        "mr": "कृपया पुष्टी करा: {patient} यांना आज {doctor} ({department}, मजला {floor}) यांच्या रांगेत जोडू का? सध्या पुढे {people_ahead} जण आहेत.",
    },
    "confirm_leave_queue": {
        "en": "Please confirm: take {patient} (token {token}) out of {doctor}'s queue? The place cannot be kept.",
        "hi": "कृपया पुष्टि करें: {patient} (टोकन {token}) को {doctor} की कतार से हटा दूं? यह जगह रोकी नहीं जा सकती।",
        "mr": "कृपया पुष्टी करा: {patient} (टोकन {token}) यांना {doctor} यांच्या रांगेतून काढू का? ही जागा राखून ठेवता येणार नाही.",
    },
    "done_check_in": {
        "en": "Done. {patient} is checked in with {doctor}. Your token is {token}; you can follow your place on the Queue status page.",
        "hi": "हो गया। {patient} का {doctor} के लिए चेक-इन हो गया है। आपका टोकन {token} है; आप कतार स्थिति पेज पर अपनी जगह देख सकते हैं।",
        "mr": "झाले. {patient} यांचे {doctor} यांच्यासाठी चेक-इन झाले आहे. तुमचा टोकन {token} आहे; रांग स्थिती पानावर तुमची जागा पाहता येईल.",
    },
    "done_join_queue": {
        "en": "Done. {patient} is in {doctor}'s queue with token {token}. Please reach the OPD desk on floor {floor} before your turn; you can follow your place on the Queue status page.",
        "hi": "हो गया। {patient} टोकन {token} के साथ {doctor} की कतार में हैं। कृपया अपनी बारी से पहले मंज़िल {floor} पर ओपीडी डेस्क पहुंचें; आप कतार स्थिति पेज पर अपनी जगह देख सकते हैं।",
        "mr": "झाले. {patient} टोकन {token} सह {doctor} यांच्या रांगेत आहेत. कृपया तुमचा क्रमांक येण्यापूर्वी मजला {floor} वरील ओपीडी डेस्कवर पोहोचा; रांग स्थिती पानावर तुमची जागा पाहता येईल.",
    },
    "done_leave_queue": {
        "en": "Done. {patient} has left {doctor}'s queue. You can book an appointment or join a queue again whenever you like.",
        "hi": "हो गया। {patient} {doctor} की कतार से हट गए हैं। आप जब चाहें अपॉइंटमेंट बुक कर सकते हैं या फिर से कतार में जुड़ सकते हैं।",
        "mr": "झाले. {patient} {doctor} यांच्या रांगेतून बाहेर पडले आहेत. तुम्हाला हवे तेव्हा अपॉइंटमेंट बुक करता येईल किंवा पुन्हा रांगेत सामील होता येईल.",
    },
    "done_book": {
        "en": "Done. {patient} is booked with {doctor} ({department}) on {date} at {time}. Please arrive 15 minutes early. The appointment can be cancelled free of charge up to {cancel_hours} hours before.",
        "hi": "हो गया। {patient} की अपॉइंटमेंट {doctor} ({department}) के साथ {date} को {time} बजे बुक हो गई है। कृपया 15 मिनट पहले पहुंचें। अपॉइंटमेंट समय से {cancel_hours} घंटे पहले तक मुफ़्त में रद्द की जा सकती है।",
        "mr": "झाले. {patient} यांची अपॉइंटमेंट {doctor} ({department}) यांच्याकडे {date} रोजी {time} वाजता बुक झाली आहे. कृपया 15 मिनिटे आधी या. अपॉइंटमेंटच्या वेळेच्या {cancel_hours} तास आधीपर्यंत ती विनामूल्य रद्द करता येते.",
    },
    "done_reschedule": {
        "en": "Done. The appointment is now with {doctor} on {date} at {time}. The old slot has been released.",
        "hi": "हो गया। अपॉइंटमेंट अब {doctor} के साथ {date} को {time} बजे है। पुराना स्लॉट खाली कर दिया गया है।",
        "mr": "झाले. अपॉइंटमेंट आता {doctor} यांच्याकडे {date} रोजी {time} वाजता आहे. जुना स्लॉट मोकळा केला आहे.",
    },
    "done_cancel": {
        "en": "Done. The appointment with {doctor} on {date} at {time} is cancelled.",
        "hi": "हो गया। {doctor} के साथ {date} {time} की अपॉइंटमेंट रद्द कर दी गई है।",
        "mr": "झाले. {doctor} यांच्याकडील {date} {time} ची अपॉइंटमेंट रद्द केली आहे.",
    },
    "done_waiting_list": {
        "en": "Done. {patient} is on {doctor}'s waiting list for {dates}. If a slot opens, you will get a message and it will be held for you for up to 2 hours.",
        "hi": "हो गया। {patient} {dates} के लिए {doctor} की प्रतीक्षा सूची में हैं। स्लॉट खाली होने पर आपको संदेश मिलेगा और वह 2 घंटे तक आपके लिए रोका जाएगा।",
        "mr": "झाले. {patient} {dates} साठी {doctor} यांच्या प्रतीक्षा यादीत आहेत. स्लॉट मोकळा झाल्यावर तुम्हाला संदेश येईल आणि तो 2 तासांपर्यंत तुमच्यासाठी राखून ठेवला जाईल.",
    },
    "nothing_changed": {
        "en": "Okay, I haven't changed anything. What would you like to do instead?",
        "hi": "ठीक है, मैंने कुछ नहीं बदला। आप इसकी जगह क्या करना चाहेंगे?",
        "mr": "ठीक आहे, मी काहीही बदलले नाही. त्याऐवजी तुम्हाला काय करायचे आहे?",
    },
    "card_expired": {
        "en": "That confirmation has expired (cards are valid for 5 minutes), so nothing was changed. Shall I check the details again?",
        "hi": "वह पुष्टि समाप्त हो गई है (कार्ड 5 मिनट तक मान्य रहते हैं), इसलिए कुछ नहीं बदला गया। क्या मैं विवरण फिर से जांचूं?",
        "mr": "ती पुष्टी कालबाह्य झाली आहे (कार्ड 5 मिनिटे वैध असतात), त्यामुळे काहीही बदलले नाही. मी तपशील पुन्हा तपासू का?",
    },
    "card_unknown": {
        "en": "That confirmation is no longer valid, so nothing was changed. Shall I check the details again?",
        "hi": "वह पुष्टि अब मान्य नहीं है, इसलिए कुछ नहीं बदला गया। क्या मैं विवरण फिर से जांचूं?",
        "mr": "ती पुष्टी आता वैध नाही, त्यामुळे काहीही बदलले नाही. मी तपशील पुन्हा तपासू का?",
    },
    "slot_taken": {
        "en": "Sorry, that slot was taken a moment ago, so nothing was booked.{alternatives}",
        "hi": "माफ़ कीजिए, वह स्लॉट अभी-अभी किसी और ने ले लिया, इसलिए कुछ बुक नहीं हुआ।{alternatives}",
        "mr": "माफ करा, तो स्लॉट नुकताच दुसऱ्या कोणी घेतला, त्यामुळे काहीही बुक झाले नाही.{alternatives}",
    },
    "alternatives": {
        "en": " Free times that day: {times}. Which one would you like?",
        "hi": " उस दिन खाली समय: {times}। आप कौन सा चाहेंगे?",
        "mr": " त्या दिवशी मोकळ्या वेळा: {times}. तुम्हाला कोणती हवी?",
    },
    "action_failed": {
        "en": "I couldn't complete that: {reason} Nothing was changed.",
        "hi": "मैं यह पूरा नहीं कर सका: {reason} कुछ भी नहीं बदला गया।",
        "mr": "मला हे पूर्ण करता आले नाही: {reason} काहीही बदलले नाही.",
    },
    "agent_failed": {
        "en": "Sorry, I couldn't work that out. Could you say it another way, for example the doctor or specialty and the day you want?",
        "hi": "माफ़ कीजिए, मैं यह समझ नहीं पाया। क्या आप दूसरे तरीके से बता सकते हैं, जैसे डॉक्टर या विभाग और आपको कौन सा दिन चाहिए?",
        "mr": "माफ करा, मला हे समजले नाही. तुम्ही वेगळ्या प्रकारे सांगू शकाल का, उदाहरणार्थ डॉक्टर किंवा विभाग आणि तुम्हाला कोणता दिवस हवा?",
    },
}


def message(key: str, lang: str, **values: Any) -> str:
    template = M[key].get(lang) or M[key]["en"]
    return template.format(**values)


WEEKDAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "hi": ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
    "mr": ["सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
}
MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    "mr": ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"],
}
LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}


def display_date(day, lang: str) -> str:
    """'Saturday 24 Oct 2026' / 'शनिवार, 24 अक्टूबर 2026'."""
    lang = lang if lang in WEEKDAYS else "en"
    weekday = WEEKDAYS[lang][day.weekday()]
    month = MONTHS[lang][day.month - 1]
    if lang == "en":
        return f"{weekday} {day.day} {month} {day.year}"
    return f"{weekday}, {day.day} {month} {day.year}"
