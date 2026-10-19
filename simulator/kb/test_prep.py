"""Test-preparation documents, composed from a translated phrase library.

Only preparation logistics are described; no medicine names or doses (FR-04).
"""

from dataclasses import dataclass, field

from simulator.kb.common import KbDoc, T, bullets

H_OVERVIEW = T("Overview", "जानकारी", "माहिती")
H_BEFORE = T("Before the test", "जांच से पहले", "तपासणीपूर्वी")
H_DAY = T("On the day of the test", "जांच के दिन", "तपासणीच्या दिवशी")
H_REPORTS = T("Reports", "रिपोर्ट", "रिपोर्ट")

FAST_NONE = T(
    "No fasting is needed (you do not need an empty stomach); you can eat and drink normally.",
    "उपवास (खाली पेट आने) की ज़रूरत नहीं है; आप सामान्य रूप से खा-पी सकते हैं।",
    "उपाशी राहण्याची (उपाशीपोटी येण्याची) गरज नाही; तुम्ही नेहमीप्रमाणे खाऊ-पिऊ शकता.",
)
FAST_HOURS = T(
    "Fasting is required (come on an empty stomach): do not eat or drink anything except plain water for {hours} hours before the test.",
    "उपवास (खाली पेट आना) ज़रूरी है: जांच से पहले {hours} घंटे तक सादे पानी के अलावा कुछ भी न खाएं-पिएं।",
    "उपाशी राहणे (उपाशीपोटी येणे) आवश्यक आहे: तपासणीपूर्वी {hours} तास साध्या पाण्याशिवाय काहीही खाऊ-पिऊ नका.",
)

P = {
    "water_ok": T(
        "Plain water is allowed during the fast; tea, coffee, milk and juice are not.",
        "उपवास के दौरान सादा पानी पी सकते हैं; चाय, कॉफ़ी, दूध और जूस नहीं।",
        "उपवासादरम्यान साधे पाणी पिऊ शकता; चहा, कॉफी, दूध आणि ज्यूस नाही.",
    ),
    "regular_meds": T(
        "Continue your regular medicines unless your doctor has told you otherwise. If you have diabetes, ask your doctor how to manage your medicines while fasting.",
        "जब तक डॉक्टर ने अलग से न कहा हो, अपनी नियमित दवाएं जारी रखें। अगर आपको डायबिटीज़ है, तो उपवास के दौरान दवाओं के बारे में अपने डॉक्टर से पूछें।",
        "डॉक्टरांनी वेगळे सांगितले नसेल तर तुमची नेहमीची औषधे सुरू ठेवा. तुम्हाला मधुमेह असल्यास, उपवासाच्या काळात औषधांबद्दल तुमच्या डॉक्टरांना विचारा.",
    ),
    "no_alcohol": T(
        "Avoid alcohol for 24 hours before the test.",
        "जांच से 24 घंटे पहले तक शराब न पिएं।",
        "तपासणीपूर्वी 24 तास मद्यपान टाळा.",
    ),
    "light_dinner": T(
        "Have a light dinner the night before and avoid fried or very fatty food.",
        "जांच से पहले की रात हल्का खाना खाएं और तला हुआ या बहुत चिकना खाना न खाएं।",
        "आदल्या रात्री हलके जेवण घ्या आणि तळलेले किंवा जास्त तेलकट पदार्थ टाळा.",
    ),
    "morning": T(
        "Come in the morning, ideally between 07:00 and 10:00, so the fasting period is easy to manage.",
        "सुबह आएं, बेहतर होगा 07:00 से 10:00 के बीच, ताकि उपवास आसानी से हो सके।",
        "सकाळी या, शक्यतो 07:00 ते 10:00 दरम्यान, म्हणजे उपवास सांभाळणे सोपे जाईल.",
    ),
    "first_urine": T(
        "Collect the first urine of the morning, mid-stream, in the sterile container from the laboratory.",
        "सुबह का पहला पेशाब, बीच की धार से, प्रयोगशाला के स्टेराइल डिब्बे में लें।",
        "सकाळची पहिली लघवी, मधल्या धारेतून, प्रयोगशाळेच्या निर्जंतुक डबीत घ्या.",
    ),
    "deliver_urine": T(
        "Bring the sample to the laboratory within one hour of collection.",
        "सैंपल लेने के एक घंटे के अंदर प्रयोगशाला में पहुंचाएं।",
        "नमुना घेतल्यापासून एका तासाच्या आत प्रयोगशाळेत आणा.",
    ),
    "before_new_medicine": T(
        "If possible, give the sample before starting any new medicine prescribed for an infection.",
        "हो सके तो संक्रमण के लिए लिखी गई कोई नई दवा शुरू करने से पहले सैंपल दें।",
        "शक्य असल्यास, संसर्गासाठी दिलेले कोणतेही नवीन औषध सुरू करण्यापूर्वी नमुना द्या.",
    ),
    "period": T(
        "Women should avoid giving a urine sample during the menstrual period; tell the staff if this applies.",
        "महिलाएं मासिक धर्म के दौरान पेशाब का सैंपल न दें; ऐसा हो तो स्टाफ़ को बताएं।",
        "महिलांनी मासिक पाळीच्या काळात लघवीचा नमुना देणे टाळावे; तसे असल्यास कर्मचाऱ्यांना सांगा.",
    ),
    "stool": T(
        "Collect a small amount of stool in the clean container from the laboratory and bring it within two hours. Do not mix it with urine or water.",
        "प्रयोगशाला के साफ़ डिब्बे में थोड़ा मल लें और दो घंटे के अंदर लाएं। इसमें पेशाब या पानी न मिलने दें।",
        "प्रयोगशाळेच्या स्वच्छ डबीत थोडी विष्ठा घ्या आणि दोन तासांच्या आत आणा. त्यात लघवी किंवा पाणी मिसळू देऊ नका.",
    ),
    "full_bladder": T(
        "A full bladder is needed: drink 4–5 glasses of water one hour before the scan and do not pass urine until the scan is over.",
        "मूत्राशय भरा होना चाहिए: स्कैन से एक घंटा पहले 4–5 गिलास पानी पिएं और स्कैन पूरा होने तक पेशाब न करें।",
        "मूत्राशय भरलेले असणे आवश्यक आहे: स्कॅनच्या एक तास आधी 4–5 ग्लास पाणी प्या आणि स्कॅन संपेपर्यंत लघवीला जाऊ नका.",
    ),
    "metal": T(
        "Remove metal objects such as jewellery, hair clips, belts and watches. Tell the staff if you have a pacemaker, an implant or any metal in your body.",
        "गहने, हेयर क्लिप, बेल्ट और घड़ी जैसी धातु की चीज़ें उतार दें। अगर आपके शरीर में पेसमेकर, इम्प्लांट या कोई धातु है तो स्टाफ़ को बताएं।",
        "दागिने, केसांच्या क्लिप, बेल्ट आणि घड्याळ अशा धातूच्या वस्तू काढून ठेवा. तुमच्या शरीरात पेसमेकर, इम्प्लांट किंवा कोणताही धातू असल्यास कर्मचाऱ्यांना सांगा.",
    ),
    "pregnancy": T(
        "Tell the staff if you are pregnant or might be pregnant.",
        "अगर आप गर्भवती हैं या हो सकती हैं तो स्टाफ़ को बताएं।",
        "तुम्ही गर्भवती असाल किंवा असण्याची शक्यता असेल तर कर्मचाऱ्यांना सांगा.",
    ),
    "contrast": T(
        "If contrast dye is planned, bring a recent kidney function (creatinine) report and tell the staff about any allergy you have had before.",
        "अगर कॉन्ट्रास्ट डाई दी जानी है तो हाल की किडनी जांच (क्रिएटिनिन) रिपोर्ट लाएं और पहले हुई किसी एलर्जी के बारे में स्टाफ़ को बताएं।",
        "कॉन्ट्रास्ट डाय द्यायची असल्यास अलीकडील किडनी तपासणीचा (क्रिएटिनिन) रिपोर्ट आणा आणि आधी झालेल्या कोणत्याही ॲलर्जीबद्दल कर्मचाऱ्यांना सांगा.",
    ),
    "loose_clothes": T(
        "Wear loose, comfortable clothes without metal buttons or zips.",
        "धातु के बटन या ज़िप के बिना ढीले, आरामदायक कपड़े पहनें।",
        "धातूची बटणे किंवा झिप नसलेले सैल, आरामदायक कपडे घाला.",
    ),
    "no_lotion": T(
        "Do not apply oil, lotion or powder on your chest or limbs on the day of the test.",
        "जांच के दिन छाती या हाथ-पैरों पर तेल, लोशन या पाउडर न लगाएं।",
        "तपासणीच्या दिवशी छातीवर किंवा हातापायांवर तेल, लोशन किंवा पावडर लावू नका.",
    ),
    "shoes": T(
        "Wear comfortable walking shoes and loose clothes.",
        "चलने के लिए आरामदायक जूते और ढीले कपड़े पहनें।",
        "चालण्यासाठी आरामदायक बूट आणि सैल कपडे घाला.",
    ),
    "light_meal_2h": T(
        "Have only a light meal, at least two hours before the test.",
        "जांच से कम से कम दो घंटे पहले सिर्फ़ हल्का भोजन करें।",
        "तपासणीच्या किमान दोन तास आधी फक्त हलका आहार घ्या.",
    ),
    "no_caffeine": T(
        "Avoid tea, coffee, cola and energy drinks for 12 hours before the test.",
        "जांच से 12 घंटे पहले तक चाय, कॉफ़ी, कोला और एनर्जी ड्रिंक न लें।",
        "तपासणीपूर्वी 12 तास चहा, कॉफी, कोला आणि एनर्जी ड्रिंक टाळा.",
    ),
    "heart_meds": T(
        "Ask your cardiologist in advance whether any of your regular heart medicines should be paused; do not stop them on your own.",
        "अपने हृदय रोग विशेषज्ञ से पहले ही पूछ लें कि क्या कोई नियमित दवा रोकनी है; खुद से दवा बंद न करें।",
        "तुमची नेहमीची हृदयाची औषधे थांबवायची का हे तुमच्या हृदयरोगतज्ज्ञांना आधीच विचारा; स्वतःहून औषध बंद करू नका.",
    ),
    "no_deodorant": T(
        "Do not use deodorant, talcum powder or cream under the arms or on the chest on the day of the test.",
        "जांच के दिन बगल या छाती पर डियोड्रेंट, टैल्कम पाउडर या क्रीम न लगाएं।",
        "तपासणीच्या दिवशी काखेत किंवा छातीवर डिओडरंट, टाल्कम पावडर किंवा क्रीम लावू नका.",
    ),
    "after_period": T(
        "The best time is one week after your menstrual period, when the breasts are least tender.",
        "सबसे अच्छा समय मासिक धर्म के एक हफ़्ते बाद है, जब स्तनों में दर्द सबसे कम होता है।",
        "मासिक पाळीनंतर एक आठवड्याने सर्वात योग्य वेळ असते, तेव्हा स्तनांमध्ये वेदना सर्वात कमी असतात.",
    ),
    "escort": T(
        "Come with an adult companion: you should not drive or ride a two-wheeler for the rest of the day.",
        "किसी वयस्क साथी के साथ आएं: उस दिन आपको गाड़ी या दोपहिया नहीं चलाना चाहिए।",
        "एखाद्या प्रौढ सोबत्यासोबत या: त्या दिवशी तुम्ही गाडी किंवा दुचाकी चालवू नये.",
    ),
    "sunglasses": T(
        "Bring sunglasses; your vision may be blurred and sensitive to light for 4–6 hours.",
        "धूप का चश्मा साथ लाएं; 4–6 घंटे तक नज़र धुंधली और रोशनी से चुभने वाली हो सकती है।",
        "गॉगल सोबत आणा; 4–6 तास दृष्टी धूसर आणि प्रकाशाला संवेदनशील राहू शकते.",
    ),
    "no_contacts": T(
        "Do not wear contact lenses on the day of the test; bring your glasses instead.",
        "जांच के दिन कॉन्टैक्ट लेंस न पहनें; इसके बजाय अपना चश्मा लाएं।",
        "तपासणीच्या दिवशी कॉन्टॅक्ट लेन्स घालू नका; त्याऐवजी तुमचा चष्मा आणा.",
    ),
    "sedation": T(
        "You may be given medicine to make you drowsy, so plan to rest for the rest of the day.",
        "आपको नींद लाने वाली दवा दी जा सकती है, इसलिए उस दिन बाकी समय आराम करने की योजना बनाएं।",
        "तुम्हाला गुंगी आणणारे औषध दिले जाऊ शकते, त्यामुळे त्या दिवशी उरलेला वेळ आराम करण्याचे नियोजन करा.",
    ),
    "bowel_prep": T(
        "The Procedure Suite desk gives you a written bowel-preparation plan; follow it exactly. Take only clear liquids on the day before the test.",
        "प्रोसीजर सुइट डेस्क आपको आंत की सफ़ाई की लिखित योजना देगा; उसका ठीक से पालन करें। जांच से एक दिन पहले सिर्फ़ साफ़ तरल पदार्थ लें।",
        "प्रोसिजर सूट डेस्क तुम्हाला आतड्यांच्या स्वच्छतेची लेखी योजना देईल; ती तंतोतंत पाळा. तपासणीच्या आदल्या दिवशी फक्त पातळ, स्वच्छ द्रव घ्या.",
    ),
    "no_smoking": T(
        "Do not smoke for at least 4 hours before the test and avoid a heavy meal in the 2 hours before it.",
        "जांच से कम से कम 4 घंटे पहले धूम्रपान न करें और 2 घंटे पहले भारी भोजन न करें।",
        "तपासणीच्या किमान 4 तास आधी धूम्रपान करू नका आणि 2 तास आधी जड जेवण टाळा.",
    ),
    "no_noise": T(
        "Avoid loud noise such as concerts, firecrackers or loud music for 12 hours before the test.",
        "जांच से 12 घंटे पहले तक तेज़ आवाज़, जैसे कॉन्सर्ट, पटाखे या तेज़ संगीत से बचें।",
        "तपासणीपूर्वी 12 तास मोठा आवाज, जसे की कॉन्सर्ट, फटाके किंवा मोठे संगीत, टाळा.",
    ),
    "clean_hair": T(
        "Wash your hair the night before with shampoo only; do not apply oil, gel or spray.",
        "जांच से पहले की रात सिर्फ़ शैम्पू से बाल धोएं; तेल, जेल या स्प्रे न लगाएं।",
        "आदल्या रात्री फक्त शाम्पूने केस धुवा; तेल, जेल किंवा स्प्रे लावू नका.",
    ),
    "timed_meal": T(
        "Eat your normal meal, note the time you started eating, and give the blood sample exactly 2 hours after that.",
        "अपना सामान्य भोजन करें, खाना शुरू करने का समय नोट करें, और उसके ठीक 2 घंटे बाद खून का सैंपल दें।",
        "तुमचे नेहमीचे जेवण घ्या, जेवायला सुरुवात केल्याची वेळ लिहून ठेवा आणि त्यानंतर बरोबर 2 तासांनी रक्ताचा नमुना द्या.",
    ),
    "gtt_stay": T(
        "The test takes about 2–3 hours: after the first sample you drink a glucose solution and stay at the laboratory for further samples. Do not eat, smoke or walk around much during this time.",
        "जांच में लगभग 2–3 घंटे लगते हैं: पहले सैंपल के बाद आपको ग्लूकोज़ का घोल पिलाया जाता है और आगे के सैंपल के लिए प्रयोगशाला में रुकना होता है। इस दौरान न खाएं, न धूम्रपान करें और ज़्यादा न घूमें।",
        "तपासणीला सुमारे 2–3 तास लागतात: पहिल्या नमुन्यानंतर तुम्हाला ग्लुकोजचे द्रावण दिले जाते आणि पुढील नमुन्यांसाठी प्रयोगशाळेत थांबावे लागते. या काळात खाऊ नका, धूम्रपान करू नका आणि फार फिरू नका.",
    ),
    "thyroid_timing": T(
        "If you take a thyroid tablet, give the blood sample before your morning dose unless your doctor advises otherwise.",
        "अगर आप थायरॉइड की गोली लेते हैं, तो डॉक्टर की अलग सलाह न हो तो सुबह की खुराक से पहले खून का सैंपल दें।",
        "तुम्ही थायरॉईडची गोळी घेत असाल तर, डॉक्टरांनी वेगळे सांगितले नसल्यास सकाळचा डोस घेण्यापूर्वी रक्ताचा नमुना द्या.",
    ),
    "morning_8": T(
        "The sample must be taken between 07:00 and 09:00 because the level changes through the day.",
        "सैंपल 07:00 से 09:00 के बीच ही लिया जाना चाहिए क्योंकि दिन भर में इसका स्तर बदलता है।",
        "नमुना 07:00 ते 09:00 दरम्यानच घेतला पाहिजे कारण दिवसभरात याची पातळी बदलते.",
    ),
    "urine_24h": T(
        "Collect all urine for 24 hours in the large container from the laboratory: discard the first urine of day one, then collect every sample including the first urine of day two. Keep the container cool.",
        "प्रयोगशाला के बड़े डिब्बे में 24 घंटे का पूरा पेशाब इकट्ठा करें: पहले दिन का पहला पेशाब फेंक दें, फिर दूसरे दिन के पहले पेशाब समेत हर बार का पेशाब इकट्ठा करें। डिब्बे को ठंडी जगह रखें।",
        "प्रयोगशाळेच्या मोठ्या डब्यात 24 तासांची सर्व लघवी गोळा करा: पहिल्या दिवशीची पहिली लघवी टाकून द्या, नंतर दुसऱ्या दिवसाच्या पहिल्या लघवीसह प्रत्येक वेळची लघवी गोळा करा. डबा थंड जागी ठेवा.",
    ),
    "holter": T(
        "Have a bath before you come, because the recorder must stay dry for 24 hours. Wear a loose, front-opening top and keep a note of your activities and any symptoms.",
        "आने से पहले नहा लें, क्योंकि रिकॉर्डर को 24 घंटे सूखा रखना होता है। आगे से खुलने वाला ढीला टॉप पहनें और अपनी गतिविधियों व लक्षणों को नोट करते रहें।",
        "येण्यापूर्वी आंघोळ करा, कारण रेकॉर्डर 24 तास कोरडा ठेवावा लागतो. पुढून उघडणारा सैल टॉप घाला आणि तुमच्या हालचाली व लक्षणे लिहून ठेवा.",
    ),
    "bring_prescription": T(
        "Bring the doctor's prescription or test request, a photo ID and any previous reports.",
        "डॉक्टर का पर्चा या जांच की पर्ची, फ़ोटो पहचान पत्र और पुरानी रिपोर्ट साथ लाएं।",
        "डॉक्टरांची चिठ्ठी किंवा तपासणीची चिठ्ठी, फोटो ओळखपत्र आणि जुने रिपोर्ट सोबत आणा.",
    ),
}

WHERE = {
    "lab": T(
        "Samples are collected at the Laboratory on the ground floor, Monday to Saturday 07:00–14:00 and Sunday 08:00–11:00. No appointment is needed.",
        "सैंपल भूतल (ग्राउंड फ़्लोर) की प्रयोगशाला में लिए जाते हैं: सोमवार से शनिवार 07:00–14:00 और रविवार 08:00–11:00। अपॉइंटमेंट की ज़रूरत नहीं है।",
        "नमुने तळमजल्यावरील प्रयोगशाळेत घेतले जातात: सोमवार ते शनिवार 07:00–14:00 आणि रविवार 08:00–11:00. अपॉइंटमेंटची गरज नाही.",
    ),
    "radiology": T(
        "The test is done in the Radiology department on the first floor, Monday to Saturday 08:00–20:00. Book a time at the Radiology desk or the reception, and arrive 15 minutes early.",
        "यह जांच पहली मंज़िल के रेडियोलॉजी विभाग में होती है: सोमवार से शनिवार 08:00–20:00। रेडियोलॉजी डेस्क या रिसेप्शन पर समय बुक करें और 15 मिनट पहले पहुंचें।",
        "ही तपासणी पहिल्या मजल्यावरील रेडिओलॉजी विभागात होते: सोमवार ते शनिवार 08:00–20:00. रेडिओलॉजी डेस्क किंवा रिसेप्शनवर वेळ बुक करा आणि 15 मिनिटे आधी या.",
    ),
    "cardiac": T(
        "The test is done in the Cardiology department on the third floor, Monday to Saturday 09:00–17:00. Book a time at the Cardiology desk or the reception.",
        "यह जांच तीसरी मंज़िल के हृदय रोग विभाग में होती है: सोमवार से शनिवार 09:00–17:00। हृदय रोग डेस्क या रिसेप्शन पर समय बुक करें।",
        "ही तपासणी तिसऱ्या मजल्यावरील हृदयरोग विभागात होते: सोमवार ते शनिवार 09:00–17:00. हृदयरोग डेस्क किंवा रिसेप्शनवर वेळ बुक करा.",
    ),
    "procedure": T(
        "The procedure is done in the Day-Care Procedure Suite on the second floor by appointment only. The department confirms the time by phone a day before.",
        "यह प्रक्रिया दूसरी मंज़िल के डे-केयर प्रोसीजर सुइट में सिर्फ़ अपॉइंटमेंट से होती है। विभाग एक दिन पहले फ़ोन पर समय की पुष्टि करता है।",
        "ही प्रक्रिया दुसऱ्या मजल्यावरील डे-केअर प्रोसिजर सूटमध्ये फक्त अपॉइंटमेंटने होते. विभाग एक दिवस आधी फोनवर वेळ निश्चित करतो.",
    ),
    "clinic": T(
        "The test is done in the department's clinic room during OPD hours; ask the reception for the room number.",
        "यह जांच ओपीडी समय में विभाग के क्लिनिक कक्ष में होती है; कमरा नंबर रिसेप्शन से पूछें।",
        "ही तपासणी ओपीडीच्या वेळेत विभागाच्या क्लिनिक खोलीत होते; खोली क्रमांक रिसेप्शनवर विचारा.",
    ),
}

REPORT = {
    "same_day": T(
        "Reports are usually ready the same day after 18:00.",
        "रिपोर्ट आमतौर पर उसी दिन 18:00 के बाद मिल जाती है।",
        "रिपोर्ट साधारणपणे त्याच दिवशी 18:00 नंतर मिळतो.",
    ),
    "next_day": T(
        "Reports are usually ready the next working day.",
        "रिपोर्ट आमतौर पर अगले कार्य-दिवस मिल जाती है।",
        "रिपोर्ट साधारणपणे पुढच्या कामाच्या दिवशी मिळतो.",
    ),
    "two_three_days": T(
        "Reports are usually ready in 2–3 working days.",
        "रिपोर्ट आमतौर पर 2–3 कार्य-दिवसों में मिलती है।",
        "रिपोर्ट साधारणपणे 2–3 कामाच्या दिवसांत मिळतो.",
    ),
    "immediate": T(
        "The result is usually explained to you the same day by the doctor.",
        "नतीजा आमतौर पर उसी दिन डॉक्टर आपको समझा देते हैं।",
        "निकाल साधारणपणे त्याच दिवशी डॉक्टर तुम्हाला समजावून सांगतात.",
    ),
}
COLLECT = T(
    "Collect printed reports at the Reports counter on the ground floor (bring the receipt), or open the secure link sent by SMS.",
    "छपी हुई रिपोर्ट भूतल के रिपोर्ट काउंटर से लें (रसीद साथ लाएं), या SMS से भेजा गया सुरक्षित लिंक खोलें।",
    "छापील रिपोर्ट तळमजल्यावरील रिपोर्ट काउंटरवरून घ्या (पावती सोबत आणा), किंवा SMS ने पाठवलेली सुरक्षित लिंक उघडा.",
)
DURATION = T(
    "The test itself takes about {minutes} minutes.",
    "जांच में खुद लगभग {minutes} मिनट लगते हैं।",
    "तपासणीला स्वतः सुमारे {minutes} मिनिटे लागतात.",
)


@dataclass
class LabTest:
    slug: str
    name: T
    about: T
    fasting: str | int = 0  # hours, "10–12" style text, or 0
    steps: list[str] = field(default_factory=list)
    where: str = "lab"
    minutes: int = 5
    report: str = "same_day"


TESTS = [
    LabTest(
        "complete-blood-count",
        T("Complete blood count (CBC)", "कम्प्लीट ब्लड काउंट (CBC)", "कम्प्लीट ब्लड काउंट (CBC)"),
        T(
            "A CBC measures red cells, white cells, haemoglobin and platelets from a small blood sample.",
            "CBC खून के छोटे सैंपल से लाल कोशिकाएं, सफ़ेद कोशिकाएं, हीमोग्लोबिन और प्लेटलेट्स मापता है।",
            "CBC रक्ताच्या छोट्या नमुन्यातून लाल पेशी, पांढऱ्या पेशी, हिमोग्लोबिन आणि प्लेटलेट्स मोजते.",
        ),
        steps=["bring_prescription"],
    ),
    LabTest(
        "lipid-profile",
        T("Lipid profile (cholesterol test)", "लिपिड प्रोफ़ाइल (कोलेस्ट्रॉल जांच)", "लिपिड प्रोफाइल (कोलेस्टेरॉल तपासणी)"),
        T(
            "A lipid profile measures total cholesterol, HDL, LDL and triglycerides in the blood.",
            "लिपिड प्रोफ़ाइल खून में कुल कोलेस्ट्रॉल, HDL, LDL और ट्राइग्लिसराइड मापता है।",
            "लिपिड प्रोफाइल रक्तातील एकूण कोलेस्टेरॉल, HDL, LDL आणि ट्रायग्लिसराइड मोजते.",
        ),
        fasting="10–12",
        steps=["water_ok", "light_dinner", "no_alcohol", "regular_meds", "morning", "bring_prescription"],
    ),
    LabTest(
        "fasting-blood-sugar",
        T("Fasting blood sugar (FBS)", "फ़ास्टिंग ब्लड शुगर (FBS)", "उपाशीपोटी रक्तशर्करा (FBS)"),
        T(
            "This test measures the blood glucose level after an overnight fast.",
            "यह जांच रात भर के उपवास के बाद खून में ग्लूकोज़ का स्तर मापती है।",
            "ही तपासणी रात्रभराच्या उपवासानंतर रक्तातील ग्लुकोजची पातळी मोजते.",
        ),
        fasting="8–10",
        steps=["water_ok", "regular_meds", "morning", "bring_prescription"],
    ),
    LabTest(
        "post-prandial-blood-sugar",
        T("Post-meal blood sugar (PPBS)", "खाने के बाद की ब्लड शुगर (PPBS)", "जेवणानंतरची रक्तशर्करा (PPBS)"),
        T(
            "This test measures blood glucose two hours after a meal.",
            "यह जांच भोजन के दो घंटे बाद खून में ग्लूकोज़ मापती है।",
            "ही तपासणी जेवणानंतर दोन तासांनी रक्तातील ग्लुकोज मोजते.",
        ),
        steps=["timed_meal", "regular_meds", "bring_prescription"],
    ),
    LabTest(
        "hba1c",
        T("HbA1c (average blood sugar)", "HbA1c (औसत ब्लड शुगर)", "HbA1c (सरासरी रक्तशर्करा)"),
        T(
            "HbA1c shows your average blood sugar over the last two to three months.",
            "HbA1c पिछले दो-तीन महीनों की औसत ब्लड शुगर दिखाता है।",
            "HbA1c मागील दोन ते तीन महिन्यांची सरासरी रक्तशर्करा दाखवते.",
        ),
        steps=["bring_prescription"],
    ),
    LabTest(
        "thyroid-profile",
        T("Thyroid profile (T3, T4, TSH)", "थायरॉइड प्रोफ़ाइल (T3, T4, TSH)", "थायरॉईड प्रोफाइल (T3, T4, TSH)"),
        T(
            "This blood test checks how well your thyroid gland is working.",
            "यह खून की जांच बताती है कि आपकी थायरॉइड ग्रंथि कितनी ठीक से काम कर रही है।",
            "ही रक्त तपासणी तुमची थायरॉईड ग्रंथी किती चांगले काम करते हे तपासते.",
        ),
        steps=["thyroid_timing", "morning", "bring_prescription"],
    ),
    LabTest(
        "liver-function-test",
        T("Liver function test (LFT)", "लिवर फ़ंक्शन टेस्ट (LFT)", "यकृत कार्य तपासणी (LFT)"),
        T(
            "An LFT measures liver enzymes, bilirubin and proteins to check the health of the liver.",
            "LFT लिवर के एंज़ाइम, बिलीरुबिन और प्रोटीन मापकर लिवर की सेहत जांचता है।",
            "LFT यकृताचे एन्झाइम, बिलिरुबिन आणि प्रथिने मोजून यकृताचे आरोग्य तपासते.",
        ),
        fasting=8,
        steps=["water_ok", "no_alcohol", "regular_meds", "bring_prescription"],
    ),
    LabTest(
        "kidney-function-test",
        T("Kidney function test (KFT)", "किडनी फ़ंक्शन टेस्ट (KFT)", "मूत्रपिंड कार्य तपासणी (KFT)"),
        T(
            "A KFT measures creatinine, urea and related values to check how well the kidneys filter blood.",
            "KFT क्रिएटिनिन, यूरिया और संबंधित मान मापकर बताता है कि किडनी खून को कितनी अच्छी तरह साफ़ करती है।",
            "KFT क्रिएटिनिन, युरिया आणि संबंधित मूल्ये मोजून मूत्रपिंड रक्त किती चांगले गाळतात हे तपासते.",
        ),
        steps=["regular_meds", "bring_prescription"],
    ),
    LabTest(
        "serum-electrolytes",
        T(
            "Serum electrolytes (sodium, potassium)",
            "सीरम इलेक्ट्रोलाइट (सोडियम, पोटैशियम)",
            "सीरम इलेक्ट्रोलाइट (सोडियम, पोटॅशियम)",
        ),
        T(
            "This test measures sodium, potassium and chloride levels in the blood.",
            "यह जांच खून में सोडियम, पोटैशियम और क्लोराइड का स्तर मापती है।",
            "ही तपासणी रक्तातील सोडियम, पोटॅशियम आणि क्लोराइडची पातळी मोजते.",
        ),
        steps=["regular_meds", "bring_prescription"],
    ),
    LabTest(
        "vitamin-d",
        T("Vitamin D (25-OH)", "विटामिन D (25-OH)", "व्हिटॅमिन D (25-OH)"),
        T(
            "This blood test measures the level of vitamin D in your body.",
            "यह खून की जांच शरीर में विटामिन D का स्तर मापती है।",
            "ही रक्त तपासणी शरीरातील व्हिटॅमिन D ची पातळी मोजते.",
        ),
        steps=["bring_prescription"],
        report="two_three_days",
    ),
    LabTest(
        "vitamin-b12",
        T("Vitamin B12", "विटामिन B12", "व्हिटॅमिन B12"),
        T(
            "This blood test measures the level of vitamin B12.",
            "यह खून की जांच विटामिन B12 का स्तर मापती है।",
            "ही रक्त तपासणी व्हिटॅमिन B12 ची पातळी मोजते.",
        ),
        fasting=8,
        steps=["water_ok", "morning", "bring_prescription"],
        report="next_day",
    ),
    LabTest(
        "iron-studies",
        T("Iron studies (serum iron, ferritin)", "आयरन जांच (सीरम आयरन, फ़ेरिटिन)", "लोह तपासणी (सीरम आयर्न, फेरिटिन)"),
        T(
            "Iron studies check the amount of iron in the blood and the body's iron stores.",
            "आयरन जांच खून में आयरन की मात्रा और शरीर में जमा आयरन की जांच करती है।",
            "लोह तपासणी रक्तातील लोहाचे प्रमाण आणि शरीरातील लोहाचा साठा तपासते.",
        ),
        fasting=8,
        steps=["water_ok", "morning", "bring_prescription"],
        report="next_day",
    ),
    LabTest(
        "uric-acid",
        T("Uric acid", "यूरिक एसिड", "युरिक ॲसिड"),
        T(
            "This test measures uric acid in the blood, which is raised in gout.",
            "यह जांच खून में यूरिक एसिड मापती है, जो गठिया (गाउट) में बढ़ जाता है।",
            "ही तपासणी रक्तातील युरिक ॲसिड मोजते, जे गाऊटमध्ये वाढलेले असते.",
        ),
        fasting=4,
        steps=["water_ok", "no_alcohol", "bring_prescription"],
    ),
    LabTest(
        "esr",
        T("ESR (erythrocyte sedimentation rate)", "ESR (इरिथ्रोसाइट सेडिमेंटेशन रेट)", "ESR (एरिथ्रोसाइट सेडिमेंटेशन रेट)"),
        T(
            "ESR is a simple blood test that shows whether there is inflammation in the body.",
            "ESR एक साधारण खून की जांच है जो बताती है कि शरीर में सूजन है या नहीं।",
            "ESR ही एक साधी रक्त तपासणी आहे जी शरीरात सूज आहे का ते दाखवते.",
        ),
        steps=["bring_prescription"],
    ),
    LabTest(
        "crp",
        T("C-reactive protein (CRP)", "सी-रिएक्टिव प्रोटीन (CRP)", "सी-रिॲक्टिव्ह प्रोटीन (CRP)"),
        T(
            "CRP is a blood marker of infection or inflammation.",
            "CRP संक्रमण या सूजन का खून में मिलने वाला संकेतक है।",
            "CRP हा संसर्ग किंवा सुजेचा रक्तातील निदर्शक आहे.",
        ),
        steps=["bring_prescription"],
    ),
    LabTest(
        "blood-group",
        T("Blood group and Rh typing", "ब्लड ग्रुप और Rh जांच", "रक्तगट आणि Rh तपासणी"),
        T(
            "This test identifies your blood group (A, B, AB or O) and Rh type.",
            "यह जांच आपका ब्लड ग्रुप (A, B, AB या O) और Rh प्रकार बताती है।",
            "ही तपासणी तुमचा रक्तगट (A, B, AB किंवा O) आणि Rh प्रकार ओळखते.",
        ),
        steps=["bring_prescription"],
    ),
    LabTest(
        "pt-inr",
        T("Prothrombin time (PT/INR)", "प्रोथ्रोम्बिन टाइम (PT/INR)", "प्रोथ्रोम्बिन टाइम (PT/INR)"),
        T(
            "PT/INR shows how quickly your blood clots. It is often checked before procedures.",
            "PT/INR बताता है कि आपका खून कितनी जल्दी जमता है। यह अक्सर किसी प्रक्रिया से पहले जांचा जाता है।",
            "PT/INR तुमचे रक्त किती लवकर गोठते हे दाखवते. हे बहुधा प्रक्रियेपूर्वी तपासले जाते.",
        ),
        steps=["regular_meds", "bring_prescription"],
    ),
    LabTest(
        "dengue-test",
        T(
            "Dengue test (NS1 antigen and antibodies)",
            "डेंगू जांच (NS1 एंटीजन और एंटीबॉडी)",
            "डेंग्यू तपासणी (NS1 अँटिजेन आणि अँटीबॉडी)",
        ),
        T(
            "This blood test helps find out whether a fever is caused by dengue.",
            "यह खून की जांच यह पता लगाने में मदद करती है कि बुखार डेंगू से है या नहीं।",
            "ही रक्त तपासणी ताप डेंग्यूमुळे आहे का हे शोधण्यास मदत करते.",
        ),
        steps=["bring_prescription"],
    ),
    LabTest(
        "malaria-test",
        T(
            "Malaria test (smear and rapid test)",
            "मलेरिया जांच (स्मीयर और रैपिड टेस्ट)",
            "मलेरिया तपासणी (स्मिअर आणि रॅपिड टेस्ट)",
        ),
        T(
            "This blood test looks for malaria parasites.",
            "यह खून की जांच मलेरिया के परजीवी खोजती है।",
            "ही रक्त तपासणी मलेरियाचे परजीवी शोधते.",
        ),
        steps=["bring_prescription"],
    ),
    LabTest(
        "typhoid-test",
        T("Typhoid test (Widal / rapid test)", "टाइफ़ाइड जांच (विडाल / रैपिड टेस्ट)", "टायफॉइड तपासणी (विडाल / रॅपिड टेस्ट)"),
        T(
            "This blood test helps diagnose typhoid fever.",
            "यह खून की जांच टाइफ़ाइड बुखार की पहचान में मदद करती है।",
            "ही रक्त तपासणी टायफॉइड तापाचे निदान करण्यास मदत करते.",
        ),
        steps=["bring_prescription"],
        report="next_day",
    ),
    LabTest(
        "infection-screening",
        T("Infection screening (HIV, HBsAg, HCV)", "संक्रमण जांच (HIV, HBsAg, HCV)", "संसर्ग तपासणी (HIV, HBsAg, HCV)"),
        T(
            "This blood test screens for HIV, hepatitis B and hepatitis C, often before surgery. Results are confidential.",
            "यह खून की जांच HIV, हेपेटाइटिस B और हेपेटाइटिस C की जांच करती है, अक्सर सर्जरी से पहले। नतीजे गोपनीय रहते हैं।",
            "ही रक्त तपासणी HIV, हेपेटायटिस B आणि हेपेटायटिस C साठी केली जाते, बहुधा शस्त्रक्रियेपूर्वी. निकाल गोपनीय ठेवले जातात.",
        ),
        steps=["bring_prescription"],
        report="next_day",
    ),
    LabTest(
        "glucose-tolerance-test",
        T("Glucose tolerance test (GTT)", "ग्लूकोज़ टॉलरेंस टेस्ट (GTT)", "ग्लुकोज टॉलरन्स टेस्ट (GTT)"),
        T(
            "A GTT checks how your body handles sugar, for example in pregnancy.",
            "GTT जांचता है कि आपका शरीर शुगर को कैसे संभालता है, जैसे गर्भावस्था में।",
            "GTT तुमचे शरीर साखर कशी हाताळते हे तपासते, उदाहरणार्थ गर्भावस्थेत.",
        ),
        fasting="8–10",
        steps=["water_ok", "gtt_stay", "morning", "bring_prescription"],
        minutes=150,
    ),
    LabTest(
        "fasting-insulin",
        T("Fasting insulin", "फ़ास्टिंग इंसुलिन", "उपाशीपोटी इन्सुलिन"),
        T(
            "This test measures the insulin level in the blood after a fast.",
            "यह जांच उपवास के बाद खून में इंसुलिन का स्तर मापती है।",
            "ही तपासणी उपवासानंतर रक्तातील इन्सुलिनची पातळी मोजते.",
        ),
        fasting="10–12",
        steps=["water_ok", "morning", "regular_meds", "bring_prescription"],
        report="next_day",
    ),
    LabTest(
        "morning-cortisol",
        T("Morning cortisol", "सुबह का कॉर्टिसोल", "सकाळचे कॉर्टिसॉल"),
        T(
            "Cortisol is a stress hormone; its level is highest in the morning.",
            "कॉर्टिसोल एक तनाव हार्मोन है; इसका स्तर सुबह सबसे ज़्यादा होता है।",
            "कॉर्टिसॉल हा ताणतणावाचा हार्मोन आहे; त्याची पातळी सकाळी सर्वाधिक असते.",
        ),
        steps=["morning_8", "bring_prescription"],
        report="next_day",
    ),
    LabTest(
        "serum-calcium",
        T("Serum calcium", "सीरम कैल्शियम", "सीरम कॅल्शियम"),
        T(
            "This test measures the calcium level in the blood.",
            "यह जांच खून में कैल्शियम का स्तर मापती है।",
            "ही तपासणी रक्तातील कॅल्शियमची पातळी मोजते.",
        ),
        steps=["bring_prescription"],
    ),
    LabTest(
        "urine-routine",
        T("Urine routine and microscopy", "पेशाब की सामान्य जांच (यूरिन रूटीन)", "लघवीची नियमित तपासणी (युरिन रुटीन)"),
        T(
            "This test checks urine for infection, sugar, protein and blood.",
            "यह जांच पेशाब में संक्रमण, शुगर, प्रोटीन और खून की जांच करती है।",
            "ही तपासणी लघवीत संसर्ग, साखर, प्रथिने आणि रक्त आहे का ते तपासते.",
        ),
        steps=["first_urine", "deliver_urine", "period", "bring_prescription"],
    ),
    LabTest(
        "urine-culture",
        T("Urine culture", "यूरिन कल्चर", "युरिन कल्चर"),
        T(
            "A urine culture finds which germ is causing a urinary infection.",
            "यूरिन कल्चर से पता चलता है कि पेशाब के संक्रमण का कारण कौन सा कीटाणु है।",
            "युरिन कल्चरमुळे लघवीच्या संसर्गाला कोणता जंतू कारणीभूत आहे हे कळते.",
        ),
        steps=["first_urine", "before_new_medicine", "deliver_urine", "bring_prescription"],
        report="two_three_days",
    ),
    LabTest(
        "urine-24-hour-protein",
        T("24-hour urine protein", "24 घंटे का यूरिन प्रोटीन", "24 तासांचे युरिन प्रोटीन"),
        T(
            "This test measures how much protein the kidneys pass in urine over a full day.",
            "यह जांच मापती है कि पूरे दिन में किडनी पेशाब में कितना प्रोटीन निकालती है।",
            "ही तपासणी पूर्ण दिवसात मूत्रपिंड लघवीतून किती प्रथिने बाहेर टाकतात हे मोजते.",
        ),
        steps=["urine_24h", "bring_prescription"],
        report="next_day",
    ),
    LabTest(
        "urine-pregnancy-test",
        T("Urine pregnancy test", "पेशाब से प्रेग्नेंसी जांच", "लघवीद्वारे गर्भधारणा तपासणी"),
        T(
            "This test detects the pregnancy hormone in urine.",
            "यह जांच पेशाब में प्रेग्नेंसी हार्मोन का पता लगाती है।",
            "ही तपासणी लघवीतील गर्भधारणेचा हार्मोन ओळखते.",
        ),
        steps=["first_urine", "deliver_urine"],
    ),
    LabTest(
        "stool-routine",
        T("Stool routine examination", "मल की सामान्य जांच (स्टूल रूटीन)", "विष्ठेची नियमित तपासणी (स्टूल रुटीन)"),
        T(
            "This test checks stool for infection, worms and digestion problems.",
            "यह जांच मल में संक्रमण, कीड़े और पाचन की समस्याओं की जांच करती है।",
            "ही तपासणी विष्ठेत संसर्ग, जंत आणि पचनाच्या समस्या तपासते.",
        ),
        steps=["stool", "bring_prescription"],
    ),
    LabTest(
        "stool-occult-blood",
        T("Stool occult blood test", "मल में छिपे खून की जांच (ऑकल्ट ब्लड)", "विष्ठेतील लपलेल्या रक्ताची तपासणी (ऑकल्ट ब्लड)"),
        T(
            "This test looks for traces of blood in stool that cannot be seen by eye.",
            "यह जांच मल में ऐसे खून के निशान खोजती है जो आंख से नहीं दिखते।",
            "ही तपासणी विष्ठेतील डोळ्यांना न दिसणाऱ्या रक्ताच्या खुणा शोधते.",
        ),
        steps=["stool", "bring_prescription"],
        report="next_day",
    ),
    LabTest(
        "chest-x-ray",
        T("Chest X-ray", "छाती का एक्स-रे", "छातीचा एक्स-रे"),
        T(
            "A chest X-ray takes a picture of the lungs, heart and chest bones.",
            "छाती का एक्स-रे फेफड़ों, दिल और छाती की हड्डियों की तस्वीर लेता है।",
            "छातीचा एक्स-रे फुफ्फुसे, हृदय आणि छातीच्या हाडांचे चित्र घेतो.",
        ),
        steps=["metal", "pregnancy", "bring_prescription"],
        where="radiology",
        report="same_day",
    ),
    LabTest(
        "ultrasound-abdomen",
        T("Ultrasound of the upper abdomen", "पेट के ऊपरी भाग का अल्ट्रासाउंड", "पोटाच्या वरच्या भागाची सोनोग्राफी"),
        T(
            "This scan uses sound waves to look at the liver, gall bladder, pancreas and kidneys.",
            "यह स्कैन ध्वनि तरंगों से लिवर, पित्ताशय, अग्न्याशय और किडनी को देखता है।",
            "हा स्कॅन ध्वनिलहरींनी यकृत, पित्ताशय, स्वादुपिंड आणि मूत्रपिंड पाहतो.",
        ),
        fasting=6,
        steps=["water_ok", "loose_clothes", "bring_prescription"],
        where="radiology",
        minutes=20,
        report="same_day",
    ),
    LabTest(
        "ultrasound-pelvis",
        T("Ultrasound of the pelvis", "पेड़ू (पेल्विस) का अल्ट्रासाउंड", "ओटीपोटाची (पेल्विस) सोनोग्राफी"),
        T(
            "This scan looks at the bladder and, in women, the uterus and ovaries.",
            "यह स्कैन मूत्राशय और महिलाओं में गर्भाशय व अंडाशय को देखता है।",
            "हा स्कॅन मूत्राशय आणि स्त्रियांमध्ये गर्भाशय व अंडाशय पाहतो.",
        ),
        steps=["full_bladder", "loose_clothes", "bring_prescription"],
        where="radiology",
        minutes=20,
        report="same_day",
    ),
    LabTest(
        "ultrasound-whole-abdomen",
        T("Ultrasound of the whole abdomen", "पूरे पेट का अल्ट्रासाउंड", "संपूर्ण पोटाची सोनोग्राफी"),
        T(
            "This scan looks at all the organs of the abdomen and pelvis in one visit.",
            "यह स्कैन एक ही बार में पेट और पेड़ू के सभी अंगों को देखता है।",
            "हा स्कॅन एकाच वेळी पोट आणि ओटीपोटातील सर्व अवयव पाहतो.",
        ),
        fasting=6,
        steps=["water_ok", "full_bladder", "loose_clothes", "bring_prescription"],
        where="radiology",
        minutes=30,
        report="same_day",
    ),
    LabTest(
        "ct-scan",
        T("CT scan (without contrast)", "सीटी स्कैन (बिना कॉन्ट्रास्ट)", "सीटी स्कॅन (कॉन्ट्रास्टशिवाय)"),
        T(
            "A CT scan uses X-rays and a computer to make detailed cross-section images.",
            "सीटी स्कैन एक्स-रे और कंप्यूटर से शरीर की बारीक परतदार तस्वीरें बनाता है।",
            "सीटी स्कॅन एक्स-रे आणि संगणकाने शरीराच्या तपशीलवार छेद-प्रतिमा तयार करतो.",
        ),
        steps=["metal", "pregnancy", "loose_clothes", "bring_prescription"],
        where="radiology",
        minutes=15,
        report="next_day",
    ),
    LabTest(
        "ct-scan-contrast",
        T("CT scan with contrast", "कॉन्ट्रास्ट के साथ सीटी स्कैन", "कॉन्ट्रास्टसह सीटी स्कॅन"),
        T(
            "In a contrast CT, a dye is injected into a vein so blood vessels and organs show up clearly.",
            "कॉन्ट्रास्ट सीटी में नस में डाई डाली जाती है ताकि खून की नलियां और अंग साफ़ दिखें।",
            "कॉन्ट्रास्ट सीटीमध्ये शिरेत डाय दिली जाते, ज्यामुळे रक्तवाहिन्या आणि अवयव स्पष्ट दिसतात.",
        ),
        fasting=4,
        steps=["water_ok", "contrast", "metal", "pregnancy", "bring_prescription"],
        where="radiology",
        minutes=30,
        report="next_day",
    ),
    LabTest(
        "mri-scan",
        T("MRI scan", "एमआरआई स्कैन", "एमआरआय स्कॅन"),
        T(
            "An MRI uses a strong magnet to make detailed images of the brain, spine, joints and organs. It does not use X-rays.",
            "एमआरआई तेज़ चुंबक से दिमाग, रीढ़, जोड़ों और अंगों की बारीक तस्वीरें बनाता है। इसमें एक्स-रे का उपयोग नहीं होता।",
            "एमआरआय मजबूत चुंबकाने मेंदू, मणका, सांधे आणि अवयवांच्या तपशीलवार प्रतिमा तयार करतो. यात एक्स-रे वापरले जात नाहीत.",
        ),
        steps=["metal", "loose_clothes", "bring_prescription"],
        where="radiology",
        minutes=40,
        report="next_day",
    ),
    LabTest(
        "mammography",
        T("Mammography", "मैमोग्राफ़ी", "मॅमोग्राफी"),
        T(
            "Mammography is a low-dose X-ray of the breasts used for screening and diagnosis.",
            "मैमोग्राफ़ी स्तनों का कम मात्रा वाला एक्स-रे है, जो स्क्रीनिंग और जांच में काम आता है।",
            "मॅमोग्राफी हा स्तनांचा कमी मात्रेचा एक्स-रे आहे, जो तपासणी आणि निदानासाठी वापरला जातो.",
        ),
        steps=["no_deodorant", "after_period", "pregnancy", "bring_prescription"],
        where="radiology",
        minutes=20,
        report="next_day",
    ),
    LabTest(
        "bone-density-dexa",
        T("Bone density scan (DEXA)", "हड्डियों की घनता जांच (DEXA)", "हाडांची घनता तपासणी (DEXA)"),
        T(
            "A DEXA scan measures bone strength and helps detect osteoporosis.",
            "DEXA स्कैन हड्डियों की मज़बूती मापता है और ऑस्टियोपोरोसिस का पता लगाने में मदद करता है।",
            "DEXA स्कॅन हाडांची मजबुती मोजतो आणि ऑस्टिओपोरोसिस ओळखण्यास मदत करतो.",
        ),
        steps=["loose_clothes", "metal", "pregnancy", "bring_prescription"],
        where="radiology",
        minutes=15,
        report="next_day",
    ),
    LabTest(
        "ecg",
        T("ECG (electrocardiogram)", "ईसीजी (इलेक्ट्रोकार्डियोग्राम)", "ईसीजी (इलेक्ट्रोकार्डिओग्राम)"),
        T(
            "An ECG records the electrical activity of the heart using small stickers on the chest, arms and legs.",
            "ईसीजी छाती, हाथ और पैरों पर छोटे स्टिकर लगाकर दिल की विद्युत गतिविधि रिकॉर्ड करता है।",
            "ईसीजी छाती, हात आणि पायांवर छोटे स्टिकर लावून हृदयाची विद्युत क्रिया नोंदवतो.",
        ),
        steps=["no_lotion", "loose_clothes", "bring_prescription"],
        where="cardiac",
        minutes=10,
        report="immediate",
    ),
    LabTest(
        "echocardiogram",
        T("2D echocardiogram (echo)", "2D इकोकार्डियोग्राम (इको)", "2D इकोकार्डिओग्राम (इको)"),
        T(
            "An echo is an ultrasound of the heart that shows its chambers, valves and pumping.",
            "इको दिल का अल्ट्रासाउंड है जो उसके कक्ष, वाल्व और पंपिंग दिखाता है।",
            "इको ही हृदयाची सोनोग्राफी आहे जी त्याचे कप्पे, झडपा आणि पंपिंग दाखवते.",
        ),
        steps=["loose_clothes", "bring_prescription"],
        where="cardiac",
        minutes=30,
        report="immediate",
    ),
    LabTest(
        "treadmill-stress-test",
        T("Treadmill stress test (TMT)", "ट्रेडमिल स्ट्रेस टेस्ट (TMT)", "ट्रेडमिल स्ट्रेस टेस्ट (TMT)"),
        T(
            "In a TMT, your ECG is recorded while you walk on a treadmill that gradually speeds up.",
            "TMT में धीरे-धीरे तेज़ होती ट्रेडमिल पर चलते समय आपका ईसीजी रिकॉर्ड किया जाता है।",
            "TMT मध्ये हळूहळू वेग वाढणाऱ्या ट्रेडमिलवर चालताना तुमचा ईसीजी नोंदवला जातो.",
        ),
        steps=["light_meal_2h", "no_caffeine", "shoes", "heart_meds", "bring_prescription"],
        where="cardiac",
        minutes=45,
        report="immediate",
    ),
    LabTest(
        "holter-monitoring",
        T("Holter monitoring (24-hour ECG)", "होल्टर मॉनिटरिंग (24 घंटे का ईसीजी)", "होल्टर मॉनिटरिंग (24 तासांचा ईसीजी)"),
        T(
            "A small recorder worn for 24 hours records every heartbeat during normal daily life.",
            "24 घंटे पहना जाने वाला छोटा रिकॉर्डर रोज़मर्रा की ज़िंदगी में दिल की हर धड़कन रिकॉर्ड करता है।",
            "24 तास घातलेला छोटा रेकॉर्डर रोजच्या दिनक्रमात हृदयाचा प्रत्येक ठोका नोंदवतो.",
        ),
        steps=["holter", "no_lotion", "bring_prescription"],
        where="cardiac",
        minutes=20,
        report="two_three_days",
    ),
    LabTest(
        "pulmonary-function-test",
        T(
            "Pulmonary function test (PFT / spirometry)",
            "फेफड़ों की कार्य जांच (PFT / स्पाइरोमेट्री)",
            "फुफ्फुस कार्य तपासणी (PFT / स्पायरोमेट्री)",
        ),
        T(
            "A PFT measures how much air you can breathe in and out and how fast.",
            "PFT मापता है कि आप कितनी हवा अंदर-बाहर ले सकते हैं और कितनी तेज़ी से।",
            "PFT तुम्ही किती हवा आत-बाहेर घेऊ शकता आणि किती वेगाने हे मोजते.",
        ),
        steps=["no_smoking", "loose_clothes", "bring_prescription"],
        where="clinic",
        minutes=30,
        report="immediate",
    ),
    LabTest(
        "audiometry",
        T("Hearing test (audiometry)", "सुनने की जांच (ऑडियोमेट्री)", "ऐकण्याची तपासणी (ऑडिओमेट्री)"),
        T(
            "Audiometry measures how well you hear sounds of different pitch and loudness. It is done in the ENT department.",
            "ऑडियोमेट्री मापती है कि आप अलग-अलग पिच और तेज़ी की आवाज़ें कितनी अच्छी तरह सुनते हैं। यह ईएनटी विभाग में होती है।",
            "ऑडिओमेट्री वेगवेगळ्या पट्टीचे आणि तीव्रतेचे आवाज तुम्ही किती चांगले ऐकता हे मोजते. ही ईएनटी विभागात होते.",
        ),
        steps=["no_noise", "bring_prescription"],
        where="clinic",
        minutes=30,
        report="immediate",
    ),
    LabTest(
        "dilated-eye-examination",
        T("Dilated eye examination", "आंख की पुतली फैलाकर जांच", "बाहुली विस्फारून डोळ्यांची तपासणी"),
        T(
            "Eye drops are used to widen the pupils so the doctor can examine the retina. It is done in the Ophthalmology department.",
            "आंखों में ड्रॉप डालकर पुतली फैलाई जाती है ताकि डॉक्टर रेटिना देख सकें। यह नेत्र रोग विभाग में होती है।",
            "डोळ्यांत थेंब घालून बाहुली विस्फारली जाते, ज्यामुळे डॉक्टर रेटिना तपासू शकतात. ही नेत्ररोग विभागात होते.",
        ),
        steps=["escort", "sunglasses", "no_contacts", "bring_prescription"],
        where="clinic",
        minutes=45,
        report="immediate",
    ),
    LabTest(
        "upper-gi-endoscopy",
        T("Upper GI endoscopy", "अपर जीआई एंडोस्कोपी", "अप्पर जीआय एंडोस्कोपी"),
        T(
            "A thin flexible camera is passed through the mouth to look at the food pipe, stomach and duodenum.",
            "एक पतला लचीला कैमरा मुंह से डालकर भोजन नली, पेट और ड्यूओडेनम को देखा जाता है।",
            "एक पातळ लवचिक कॅमेरा तोंडातून घालून अन्ननलिका, जठर आणि ड्युओडेनम पाहिले जाते.",
        ),
        fasting=8,
        steps=["water_ok", "sedation", "escort", "regular_meds", "bring_prescription"],
        where="procedure",
        minutes=20,
        report="immediate",
    ),
    LabTest(
        "colonoscopy",
        T("Colonoscopy", "कोलोनोस्कोपी", "कोलोनोस्कोपी"),
        T(
            "A thin flexible camera is used to look at the inside of the large intestine.",
            "एक पतले लचीले कैमरे से बड़ी आंत के अंदर देखा जाता है।",
            "एका पातळ लवचिक कॅमेऱ्याने मोठ्या आतड्याचा आतील भाग पाहिला जातो.",
        ),
        steps=["bowel_prep", "sedation", "escort", "bring_prescription"],
        where="procedure",
        minutes=45,
        report="immediate",
    ),
    LabTest(
        "eeg",
        T("EEG (electroencephalogram)", "ईईजी (इलेक्ट्रोएन्सेफ़ेलोग्राम)", "ईईजी (इलेक्ट्रोएन्सेफॅलोग्राम)"),
        T(
            "An EEG records the brain's electrical activity using small sensors on the scalp.",
            "ईईजी सिर की त्वचा पर छोटे सेंसर लगाकर दिमाग की विद्युत गतिविधि रिकॉर्ड करता है।",
            "ईईजी डोक्याच्या त्वचेवर छोटे सेन्सर लावून मेंदूची विद्युत क्रिया नोंदवतो.",
        ),
        steps=["clean_hair", "regular_meds", "bring_prescription"],
        where="clinic",
        minutes=60,
        report="next_day",
    ),
    LabTest(
        "nerve-conduction-study",
        T("Nerve conduction study (NCS)", "नर्व कंडक्शन स्टडी (NCS)", "नर्व्ह कंडक्शन स्टडी (NCS)"),
        T(
            "This test measures how fast signals travel along the nerves of the arms and legs.",
            "यह जांच मापती है कि हाथ-पैरों की नसों में संकेत कितनी तेज़ी से चलते हैं।",
            "ही तपासणी हातापायांच्या मज्जातंतूंमधून संदेश किती वेगाने जातात हे मोजते.",
        ),
        steps=["no_lotion", "loose_clothes", "bring_prescription"],
        where="clinic",
        minutes=45,
        report="next_day",
    ),
]


def build() -> list[KbDoc]:
    docs = []
    for test in TESTS:
        if test.fasting:
            fasting = FAST_HOURS.format(hours=test.fasting)
        else:
            fasting = FAST_NONE
        before = bullets([fasting] + [P[s] for s in test.steps])
        overview = T(
            *(f"{test.about[lang]} {DURATION.format(minutes=test.minutes)[lang]}" for lang in ("en", "hi", "mr"))
        )
        day = WHERE[test.where]
        reports = T(*(f"{REPORT[test.report][lang]} {COLLECT[lang]}" for lang in ("en", "hi", "mr")))
        title = T(
            f"{test.name.en}: preparation",
            f"{test.name.hi}: तैयारी",
            f"{test.name.mr}: तयारी",
        )
        docs.append(
            KbDoc(
                "test_preparation",
                test.slug,
                title,
                [(H_OVERVIEW, overview), (H_BEFORE, before), (H_DAY, day), (H_REPORTS, reports)],
            )
        )
    return docs
