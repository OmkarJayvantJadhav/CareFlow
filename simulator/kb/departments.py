"""Department and doctor documents, generated from the simulator's hospital definition
so that OPD days, hours, floors and languages always match the database."""

from simulator import hospital
from simulator.kb.common import LANGUAGE_NAMES, WEEKDAYS, KbDoc, T, bullets, clock, list_of

DEPARTMENT_NAMES = {
    "General Medicine": T("General Medicine", "सामान्य चिकित्सा (जनरल मेडिसिन)", "जनरल मेडिसिन (सामान्य औषधोपचार)"),
    "Cardiology": T("Cardiology", "हृदय रोग (कार्डियोलॉजी)", "हृदयरोग (कार्डिओलॉजी)"),
    "ENT": T("ENT (ear, nose and throat)", "ईएनटी (नाक-कान-गला)", "ईएनटी (कान-नाक-घसा)"),
    "Orthopaedics": T("Orthopaedics", "हड्डी रोग (ऑर्थोपेडिक्स)", "अस्थिरोग (ऑर्थोपेडिक्स)"),
    "Paediatrics": T("Paediatrics", "बाल रोग (पीडियाट्रिक्स)", "बालरोग (पेडियाट्रिक्स)"),
    "Dermatology": T("Dermatology", "त्वचा रोग (डर्मेटोलॉजी)", "त्वचारोग (डर्मटोलॉजी)"),
    "Gynaecology": T("Gynaecology", "स्त्री रोग (गायनेकोलॉजी)", "स्त्रीरोग (गायनॅकॉलॉजी)"),
    "Ophthalmology": T("Ophthalmology (eye care)", "नेत्र रोग (ऑफ़्थैल्मोलॉजी)", "नेत्ररोग (ऑप्थल्मॉलॉजी)"),
}

ABOUT = {
    "General Medicine": T(
        "The General Medicine department is the first point of care for adults with common illnesses and long-term conditions. If you are not sure which specialist you need, start here.",
        "सामान्य चिकित्सा विभाग आम बीमारियों और लंबी चलने वाली बीमारियों वाले वयस्कों के लिए पहला पड़ाव है। अगर आपको पता नहीं कि किस विशेषज्ञ के पास जाना है, तो यहीं से शुरू करें।",
        "सामान्य आजार आणि दीर्घकालीन आजार असलेल्या प्रौढांसाठी जनरल मेडिसिन विभाग हा पहिला टप्पा आहे. कोणत्या तज्ज्ञाकडे जायचे हे माहीत नसल्यास येथून सुरुवात करा.",
    ),
    "Cardiology": T(
        "The Cardiology department cares for conditions of the heart and blood vessels and runs the ECG, echo, stress-test and Holter services.",
        "हृदय रोग विभाग दिल और रक्त नलियों की बीमारियों का इलाज करता है और ईसीजी, इको, स्ट्रेस टेस्ट और होल्टर सेवाएं चलाता है।",
        "हृदयरोग विभाग हृदय आणि रक्तवाहिन्यांच्या आजारांवर उपचार करतो आणि ईसीजी, इको, स्ट्रेस टेस्ट आणि होल्टर सेवा चालवतो.",
    ),
    "ENT": T(
        "The ENT department treats problems of the ear, nose, throat, sinuses and voice, and runs the hearing-test (audiometry) room.",
        "ईएनटी विभाग कान, नाक, गले, साइनस और आवाज़ की समस्याओं का इलाज करता है और सुनने की जांच (ऑडियोमेट्री) कक्ष चलाता है।",
        "ईएनटी विभाग कान, नाक, घसा, सायनस आणि आवाजाच्या समस्यांवर उपचार करतो आणि ऐकण्याच्या तपासणीची (ऑडिओमेट्री) खोली चालवतो.",
    ),
    "Orthopaedics": T(
        "The Orthopaedics department treats bones, joints, muscles, the spine and sports injuries.",
        "हड्डी रोग विभाग हड्डियों, जोड़ों, मांसपेशियों, रीढ़ और खेल में लगी चोटों का इलाज करता है।",
        "अस्थिरोग विभाग हाडे, सांधे, स्नायू, मणका आणि खेळातील दुखापतींवर उपचार करतो.",
    ),
    "Paediatrics": T(
        "The Paediatrics department cares for babies, children and teenagers up to 18 years, including vaccinations and growth check-ups.",
        "बाल रोग विभाग 18 साल तक के शिशुओं, बच्चों और किशोरों की देखभाल करता है, जिसमें टीकाकरण और विकास की जांच शामिल है।",
        "बालरोग विभाग 18 वर्षांपर्यंतच्या बाळांची, मुलांची आणि किशोरांची काळजी घेतो, ज्यात लसीकरण आणि वाढीची तपासणी समाविष्ट आहे.",
    ),
    "Dermatology": T(
        "The Dermatology department treats conditions of the skin, hair and nails.",
        "त्वचा रोग विभाग त्वचा, बाल और नाखूनों की समस्याओं का इलाज करता है।",
        "त्वचारोग विभाग त्वचा, केस आणि नखांच्या समस्यांवर उपचार करतो.",
    ),
    "Gynaecology": T(
        "The Gynaecology department provides care for women's health, including pregnancy check-ups, menstrual problems and menopause.",
        "स्त्री रोग विभाग महिलाओं के स्वास्थ्य की देखभाल करता है, जिसमें गर्भावस्था जांच, मासिक धर्म की समस्याएं और रजोनिवृत्ति शामिल हैं।",
        "स्त्रीरोग विभाग महिलांच्या आरोग्याची काळजी घेतो, ज्यात गर्भावस्था तपासणी, मासिक पाळीच्या समस्या आणि रजोनिवृत्ती समाविष्ट आहेत.",
    ),
    "Ophthalmology": T(
        "The Ophthalmology department checks vision and treats eye conditions; it also prescribes glasses.",
        "नेत्र रोग विभाग नज़र की जांच करता है, आंखों की बीमारियों का इलाज करता है और चश्मे का नंबर भी देता है।",
        "नेत्ररोग विभाग दृष्टी तपासतो, डोळ्यांच्या आजारांवर उपचार करतो आणि चष्म्याचा नंबरही देतो.",
    ),
}

REASONS = {
    "General Medicine": [
        T("fever, cough and cold", "बुखार, खांसी और ज़ुकाम", "ताप, खोकला आणि सर्दी"),
        T(
            "diabetes and blood pressure follow-up",
            "डायबिटीज़ और ब्लड प्रेशर की नियमित जांच",
            "मधुमेह आणि रक्तदाबाची नियमित तपासणी",
        ),
        T("stomach upset, acidity and loose motions", "पेट ख़राब, एसिडिटी और दस्त", "पोट बिघडणे, ॲसिडिटी आणि जुलाब"),
        T("tiredness, weakness or weight change", "थकान, कमज़ोरी या वज़न में बदलाव", "थकवा, अशक्तपणा किंवा वजनात बदल"),
        T("health check-ups", "स्वास्थ्य जांच (हेल्थ चेक-अप)", "आरोग्य तपासणी (हेल्थ चेक-अप)"),
    ],
    "Cardiology": [
        T(
            "high blood pressure that is hard to control",
            "मुश्किल से नियंत्रित होने वाला हाई ब्लड प्रेशर",
            "नियंत्रणात न येणारा उच्च रक्तदाब",
        ),
        T(
            "palpitations (a racing or irregular heartbeat)",
            "धड़कन तेज़ या अनियमित होना",
            "धडधड (वेगवान किंवा अनियमित हृदयाचे ठोके)",
        ),
        T(
            "breathlessness on walking or swelling of the feet",
            "चलने पर सांस फूलना या पैरों में सूजन",
            "चालताना धाप लागणे किंवा पायांना सूज",
        ),
        T(
            "follow-up after a heart attack or heart procedure",
            "दिल के दौरे या दिल की प्रक्रिया के बाद की जांच",
            "हृदयविकाराचा झटका किंवा हृदय प्रक्रियेनंतरची तपासणी",
        ),
        T("high cholesterol", "बढ़ा हुआ कोलेस्ट्रॉल", "वाढलेले कोलेस्टेरॉल"),
    ],
    "ENT": [
        T(
            "ear pain, discharge or reduced hearing",
            "कान में दर्द, पानी आना या कम सुनाई देना",
            "कान दुखणे, कानातून पाणी येणे किंवा कमी ऐकू येणे",
        ),
        T("sinus problems and a blocked nose", "साइनस की समस्या और बंद नाक", "सायनसचा त्रास आणि नाक बंद होणे"),
        T("sore throat, tonsils and voice change", "गले में ख़राश, टॉन्सिल और आवाज़ बदलना", "घसा दुखणे, टॉन्सिल आणि आवाजात बदल"),
        T("dizziness or ringing in the ears", "चक्कर आना या कानों में आवाज़ गूंजना", "चक्कर येणे किंवा कानात आवाज घुमणे"),
        T("snoring", "खर्राटे", "घोरणे"),
    ],
    "Orthopaedics": [
        T("knee, hip or shoulder pain", "घुटने, कूल्हे या कंधे का दर्द", "गुडघा, कंबर किंवा खांद्याचे दुखणे"),
        T("back and neck pain", "कमर और गर्दन का दर्द", "पाठ आणि मानदुखी"),
        T("sprains and sports injuries", "मोच और खेल की चोटें", "मुरगळणे आणि खेळातील दुखापती"),
        T("follow-up of fractures", "फ़्रैक्चर के बाद की जांच", "फ्रॅक्चरनंतरची तपासणी"),
        T("arthritis and osteoporosis", "गठिया और ऑस्टियोपोरोसिस", "संधिवात आणि ऑस्टिओपोरोसिस"),
    ],
    "Paediatrics": [
        T("fever, cough and cold in children", "बच्चों में बुखार, खांसी और ज़ुकाम", "मुलांमध्ये ताप, खोकला आणि सर्दी"),
        T("vaccinations", "टीकाकरण", "लसीकरण"),
        T("growth and nutrition check-ups", "विकास और पोषण की जांच", "वाढ आणि पोषणाची तपासणी"),
        T("feeding problems in babies", "शिशुओं में दूध पिलाने की समस्याएं", "बाळांच्या दूध पिण्याच्या समस्या"),
        T("school fitness certificates", "स्कूल फ़िटनेस प्रमाणपत्र", "शाळेसाठी फिटनेस प्रमाणपत्र"),
    ],
    "Dermatology": [
        T("acne and pimples", "मुंहासे", "मुरुम आणि पुटकुळ्या"),
        T("itching, rashes and allergies of the skin", "त्वचा पर खुजली, चकत्ते और एलर्जी", "त्वचेवर खाज, पुरळ आणि ॲलर्जी"),
        T("hair fall and dandruff", "बाल झड़ना और रूसी", "केस गळणे आणि कोंडा"),
        T("fungal infections", "फंगल संक्रमण", "बुरशीजन्य संसर्ग"),
        T("pigmentation and white patches", "त्वचा का रंग बदलना और सफ़ेद दाग", "त्वचेचा रंग बदलणे आणि पांढरे डाग"),
    ],
    "Gynaecology": [
        T("pregnancy check-ups", "गर्भावस्था की जांच", "गर्भावस्थेची तपासणी"),
        T("irregular or painful periods", "अनियमित या दर्द भरे मासिक धर्म", "अनियमित किंवा वेदनादायक मासिक पाळी"),
        T("menopause problems", "रजोनिवृत्ति की समस्याएं", "रजोनिवृत्तीच्या समस्या"),
        T("family planning advice", "परिवार नियोजन की सलाह", "कुटुंब नियोजनाचा सल्ला"),
        T("routine screening such as Pap smear", "पैप स्मीयर जैसी नियमित जांच", "पॅप स्मिअरसारखी नियमित तपासणी"),
    ],
    "Ophthalmology": [
        T("blurred vision and checks for glasses", "धुंधली नज़र और चश्मे की जांच", "धूसर दृष्टी आणि चष्म्याची तपासणी"),
        T("red, watery or itchy eyes", "लाल, पानी भरी या खुजली वाली आंखें", "लाल, पाणावलेले किंवा खाज सुटणारे डोळे"),
        T("cataract assessment", "मोतियाबिंद की जांच", "मोतीबिंदूची तपासणी"),
        T("eye check-ups for diabetes", "डायबिटीज़ में आंखों की जांच", "मधुमेहात डोळ्यांची तपासणी"),
        T("eye pressure (glaucoma) checks", "आंख के दबाव (ग्लूकोमा) की जांच", "डोळ्यांच्या दाबाची (ग्लॉकोमा) तपासणी"),
    ],
}

DOCTOR_NAMES = {
    "Dr. Suresh Pawar": "डॉ. सुरेश पवार",
    "Dr. Kavita Joshi": "डॉ. कविता जोशी",
    "Dr. Imran Shaikh": "डॉ. इमरान शेख",
    "Dr. Anand Kulkarni": "डॉ. आनंद कुलकर्णी",
    "Dr. Farah Siddiqui": "डॉ. फ़राह सिद्दीक़ी",
    "Dr. Meera Iyer": "डॉ. मीरा अय्यर",
    "Dr. Snehal Gokhale": "डॉ. स्नेहल गोखले",
    "Dr. Rohit Malhotra": "डॉ. रोहित मल्होत्रा",
    "Dr. Vikram Bhosale": "डॉ. विक्रम भोसले",
    "Dr. Neha Kapoor": "डॉ. नेहा कपूर",
    "Dr. Aparna Deshpande": "डॉ. अपर्णा देशपांडे",
    "Dr. Joseph Mathew": "डॉ. जोसेफ़ मैथ्यू",
    "Dr. Ritu Agarwal": "डॉ. ऋतु अग्रवाल",
    "Dr. Prakash Shinde": "डॉ. प्रकाश शिंदे",
    "Dr. Sunita Patwardhan": "डॉ. सुनीता पटवर्धन",
    "Dr. Ayesha Khan": "डॉ. आयशा ख़ान",
    "Dr. Nitin Chavan": "डॉ. नितिन चव्हाण",
    "Dr. Lakshmi Rao": "डॉ. लक्ष्मी राव",
}

INTERESTS = {
    "Dr. Suresh Pawar": T(
        "diabetes, thyroid disorders and fevers", "डायबिटीज़, थायरॉइड की बीमारियां और बुखार", "मधुमेह, थायरॉईडचे आजार आणि ताप"
    ),
    "Dr. Kavita Joshi": T(
        "high blood pressure, preventive health check-ups and women's health",
        "हाई ब्लड प्रेशर, बचाव वाली स्वास्थ्य जांच और महिलाओं का स्वास्थ्य",
        "उच्च रक्तदाब, प्रतिबंधात्मक आरोग्य तपासणी आणि महिलांचे आरोग्य",
    ),
    "Dr. Imran Shaikh": T(
        "infections, asthma and elderly care", "संक्रमण, अस्थमा और बुज़ुर्गों की देखभाल", "संसर्ग, दमा आणि ज्येष्ठांची काळजी"
    ),
    "Dr. Anand Kulkarni": T(
        "heart failure, high blood pressure and preventive cardiology",
        "हार्ट फ़ेल्योर, हाई ब्लड प्रेशर और बचाव वाली हृदय देखभाल",
        "हृदय निकामी होणे, उच्च रक्तदाब आणि प्रतिबंधात्मक हृदयरोग उपचार",
    ),
    "Dr. Farah Siddiqui": T(
        "heart rhythm problems and echocardiography",
        "दिल की धड़कन की समस्याएं और इकोकार्डियोग्राफ़ी",
        "हृदयाच्या ठोक्यांच्या समस्या आणि इकोकार्डिओग्राफी",
    ),
    "Dr. Meera Iyer": T(
        "coronary artery disease and cardiac rehabilitation",
        "कोरोनरी आर्टरी डिज़ीज़ और हृदय पुनर्वास",
        "कोरोनरी आर्टरी डिसीज आणि हृदय पुनर्वसन",
    ),
    "Dr. Snehal Gokhale": T(
        "sinus disease, allergies and children's ENT problems",
        "साइनस, एलर्जी और बच्चों की ईएनटी समस्याएं",
        "सायनस, ॲलर्जी आणि मुलांच्या ईएनटी समस्या",
    ),
    "Dr. Rohit Malhotra": T(
        "hearing loss, vertigo and voice disorders",
        "कम सुनाई देना, चक्कर और आवाज़ की समस्याएं",
        "कमी ऐकू येणे, चक्कर आणि आवाजाच्या समस्या",
    ),
    "Dr. Vikram Bhosale": T(
        "knee and hip problems and sports injuries",
        "घुटने और कूल्हे की समस्याएं और खेल की चोटें",
        "गुडघा आणि कंबरेच्या समस्या आणि खेळातील दुखापती",
    ),
    "Dr. Neha Kapoor": T(
        "spine problems, back pain and osteoporosis",
        "रीढ़ की समस्याएं, कमर दर्द और ऑस्टियोपोरोसिस",
        "मणक्याच्या समस्या, पाठदुखी आणि ऑस्टिओपोरोसिस",
    ),
    "Dr. Aparna Deshpande": T(
        "newborn care, vaccinations and child nutrition",
        "नवजात देखभाल, टीकाकरण और बच्चों का पोषण",
        "नवजात बाळांची काळजी, लसीकरण आणि मुलांचे पोषण",
    ),
    "Dr. Joseph Mathew": T("childhood asthma and allergies", "बच्चों में अस्थमा और एलर्जी", "मुलांमधील दमा आणि ॲलर्जी"),
    "Dr. Ritu Agarwal": T(
        "acne, hair fall and skin allergies", "मुंहासे, बाल झड़ना और त्वचा की एलर्जी", "मुरुम, केस गळणे आणि त्वचेची ॲलर्जी"
    ),
    "Dr. Prakash Shinde": T(
        "fungal infections, psoriasis and pigmentation",
        "फंगल संक्रमण, सोरायसिस और त्वचा का रंग बदलना",
        "बुरशीजन्य संसर्ग, सोरायसिस आणि त्वचेचा रंग बदलणे",
    ),
    "Dr. Sunita Patwardhan": T(
        "pregnancy care and high-risk pregnancies",
        "गर्भावस्था की देखभाल और जोखिम वाली गर्भावस्था",
        "गर्भावस्थेची काळजी आणि जोखमीची गर्भावस्था",
    ),
    "Dr. Ayesha Khan": T(
        "menstrual problems, PCOS and menopause",
        "मासिक धर्म की समस्याएं, पीसीओएस और रजोनिवृत्ति",
        "मासिक पाळीच्या समस्या, पीसीओएस आणि रजोनिवृत्ती",
    ),
    "Dr. Nitin Chavan": T(
        "cataract and diabetic eye disease",
        "मोतियाबिंद और डायबिटीज़ से जुड़ी आंखों की बीमारी",
        "मोतीबिंदू आणि मधुमेहामुळे होणारे डोळ्यांचे आजार",
    ),
    "Dr. Lakshmi Rao": T(
        "glaucoma and children's eye care", "ग्लूकोमा और बच्चों की आंखों की देखभाल", "ग्लॉकोमा आणि मुलांच्या डोळ्यांची काळजी"
    ),
}

FLOOR = {
    0: T("ground floor", "भूतल", "तळमजला"),
    1: T("first floor", "पहली मंज़िल", "पहिला मजला"),
    2: T("second floor", "दूसरी मंज़िल", "दुसरा मजला"),
    3: T("third floor", "तीसरी मंज़िल", "तिसरा मजला"),
    4: T("fourth floor", "चौथी मंज़िल", "चौथा मजला"),
}

# Marathi needs the locative form ("on the first floor").
FLOOR_AT_MR = {0: "तळमजल्यावर", 1: "पहिल्या मजल्यावर", 2: "दुसऱ्या मजल्यावर", 3: "तिसऱ्या मजल्यावर", 4: "चौथ्या मजल्यावर"}

H_ABOUT = T("About the department", "विभाग के बारे में", "विभागाविषयी")
H_REASONS = T("Common reasons to visit", "यहां आने के आम कारण", "येथे येण्याची सामान्य कारणे")
H_TIMINGS = T("OPD timings and location", "ओपीडी समय और स्थान", "ओपीडीची वेळ आणि ठिकाण")
H_DOCTORS = T("Doctors", "डॉक्टर", "डॉक्टर")
H_BEFORE = T("Before your visit", "आने से पहले", "येण्यापूर्वी")
H_PROFILE = T("Profile", "परिचय", "परिचय")
H_INTERESTS = T("Areas of interest", "विशेष रुचि के क्षेत्र", "विशेष आवडीची क्षेत्रे")
H_BOOKING = T("How to book", "अपॉइंटमेंट कैसे लें", "अपॉइंटमेंट कशी घ्यावी")

BEFORE_VISIT = bullets(
    [
        T(
            "Bring your previous prescriptions, reports and a photo ID.",
            "अपने पुराने पर्चे, रिपोर्ट और फ़ोटो पहचान पत्र साथ लाएं।",
            "तुमच्या जुन्या चिठ्ठ्या, रिपोर्ट आणि फोटो ओळखपत्र सोबत आणा.",
        ),
        T(
            "Arrive 15 minutes before your appointment and check in at the reception or with CareFlow.",
            "अपॉइंटमेंट से 15 मिनट पहले पहुंचें और रिसेप्शन पर या CareFlow से चेक-इन करें।",
            "अपॉइंटमेंटच्या 15 मिनिटे आधी या आणि रिसेप्शनवर किंवा CareFlow वरून चेक-इन करा.",
        ),
        T(
            "Note down your symptoms and questions so you do not forget them during the consultation.",
            "अपने लक्षण और सवाल लिख लें ताकि परामर्श के समय भूलें नहीं।",
            "तुमची लक्षणे आणि प्रश्न लिहून ठेवा म्हणजे सल्लामसलतीच्या वेळी विसरणार नाही.",
        ),
    ]
)

BOOKING = T(
    "Book, reschedule or cancel an appointment by chatting with CareFlow in English, Hindi or Marathi, or at the reception desk on the ground floor. Walk-in patients get a token at the reception and are seen between booked appointments.",
    "CareFlow से अंग्रेज़ी, हिंदी या मराठी में चैट करके, या भूतल के रिसेप्शन पर अपॉइंटमेंट बुक करें, बदलें या रद्द करें। बिना अपॉइंटमेंट आने वाले मरीज़ों को रिसेप्शन पर टोकन मिलता है और उन्हें बुक किए गए मरीज़ों के बीच देखा जाता है।",
    "CareFlow शी इंग्रजी, हिंदी किंवा मराठीत चॅट करून, किंवा तळमजल्यावरील रिसेप्शनवर अपॉइंटमेंट बुक करा, बदला किंवा रद्द करा. अपॉइंटमेंटशिवाय येणाऱ्या रुग्णांना रिसेप्शनवर टोकन मिळते आणि त्यांना बुक केलेल्या रुग्णांच्या दरम्यान पाहिले जाते.",
)


def _doctor_name(name: str) -> T:
    return T(name, DOCTOR_NAMES[name], DOCTOR_NAMES[name])


def _days(days: list[int]) -> T:
    return list_of([WEEKDAYS[d] for d in days])


def _langs(codes: list[str]) -> T:
    return list_of([LANGUAGE_NAMES[c] for c in codes])


def build() -> list[KbDoc]:
    departments = {name: (floor, start, end) for name, floor, start, end in hospital.DEPARTMENTS}
    docs = []
    for dept, (floor, start, end) in departments.items():
        name = DEPARTMENT_NAMES[dept]
        doctors = [d for d in hospital.DOCTORS if d[1] == dept]
        timings = T(
            f"The {name.en} OPD is on the {FLOOR[floor].en}. OPD hours are {clock(start)}–{clock(end)} on each doctor's OPD days (see below). Sunday is closed except for emergencies.",
            f"{name.hi} ओपीडी {FLOOR[floor].hi} पर है। ओपीडी का समय हर डॉक्टर के ओपीडी दिनों में {clock(start)}–{clock(end)} है (नीचे देखें)। रविवार को सिर्फ़ इमरजेंसी सेवा खुली रहती है।",
            f"{name.mr} ओपीडी {FLOOR_AT_MR[floor]} आहे. प्रत्येक डॉक्टरांच्या ओपीडी दिवशी ओपीडीची वेळ {clock(start)}–{clock(end)} आहे (खाली पाहा). रविवारी फक्त आपत्कालीन सेवा सुरू असते.",
        )
        lines = []
        for doc_name, _, languages, days, _minutes in doctors:
            dn = _doctor_name(doc_name)
            lines.append(
                T(
                    f"{dn.en}: OPD on {_days(days).en}; speaks {_langs(languages).en}.",
                    f"{dn.hi}: ओपीडी {_days(days).hi} को; भाषाएं: {_langs(languages).hi}।",
                    f"{dn.mr}: ओपीडी {_days(days).mr}; भाषा: {_langs(languages).mr}.",
                )
            )
        reasons = bullets(REASONS[dept])
        docs.append(
            KbDoc(
                "departments",
                dept.lower().replace(" ", "-"),
                T(f"{name.en} department", f"{name.hi} विभाग", f"{name.mr} विभाग"),
                [
                    (H_ABOUT, ABOUT[dept]),
                    (H_REASONS, reasons),
                    (H_TIMINGS, timings),
                    (H_DOCTORS, bullets(lines)),
                    (H_BEFORE, BEFORE_VISIT),
                ],
            )
        )

    for doc_name, dept, languages, days, minutes in hospital.DOCTORS:
        floor, start, end = departments[dept]
        dn, dname = _doctor_name(doc_name), DEPARTMENT_NAMES[dept]
        profile = T(
            f"{dn.en} is a consultant in the {dname.en} department ({FLOOR[floor].en}). OPD days: {_days(days).en}, {clock(start)}–{clock(end)}. Languages: {_langs(languages).en}. Each appointment slot is {minutes} minutes.",
            f"{dn.hi} {dname.hi} विभाग ({FLOOR[floor].hi}) में कंसल्टेंट हैं। ओपीडी के दिन: {_days(days).hi}, {clock(start)}–{clock(end)}। भाषाएं: {_langs(languages).hi}। हर अपॉइंटमेंट स्लॉट {minutes} मिनट का है।",
            f"{dn.mr} हे {dname.mr} विभागात ({FLOOR[floor].mr}) कन्सल्टंट आहेत. ओपीडीचे दिवस: {_days(days).mr}, {clock(start)}–{clock(end)}. भाषा: {_langs(languages).mr}. प्रत्येक अपॉइंटमेंट स्लॉट {minutes} मिनिटांचा आहे.",
        )
        interests = INTERESTS[doc_name]
        docs.append(
            KbDoc(
                "doctors",
                doc_name.lower().replace("dr. ", "").replace(" ", "-"),
                T(f"{dn.en}, {dname.en}", f"{dn.hi}, {dname.hi}", f"{dn.mr}, {dname.mr}"),
                [
                    (H_PROFILE, profile),
                    (H_INTERESTS, T(f"{interests.en}.", f"{interests.hi}।", f"{interests.mr}.")),
                    (H_BOOKING, BOOKING),
                ],
            )
        )
    return docs
