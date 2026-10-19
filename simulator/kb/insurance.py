"""Insurance, billing and assistance-scheme documents. All insurers, TPAs, companies
and schemes named here are fictional."""

from simulator.kb.common import KbDoc, T, bullets


def doc(slug: str, title: T, *sections: tuple[T, T]) -> KbDoc:
    return KbDoc("insurance", slug, title, list(sections))


FICTIONAL = T(
    "All insurer, TPA and company names in this document are fictional.",
    "इस दस्तावेज़ में सभी बीमा कंपनियों, टीपीए और कंपनियों के नाम काल्पनिक हैं।",
    "या दस्तऐवजातील सर्व विमा कंपन्या, टीपीए आणि कंपन्यांची नावे काल्पनिक आहेत.",
)


def build() -> list[KbDoc]:
    return [
        doc(
            "empanelled-insurers",
            T("Empanelled insurers and TPAs", "पैनल में शामिल बीमा कंपनियां और टीपीए", "पॅनेलवरील विमा कंपन्या आणि टीपीए"),
            (
                T("Insurers", "बीमा कंपनियां", "विमा कंपन्या"),
                T(
                    "The hospital offers cashless treatment for policies from Kavach Health Insurance, Sanjeevani General Insurance and Nirbhay Assurance.",
                    "अस्पताल कवच हेल्थ इंश्योरेंस, संजीवनी जनरल इंश्योरेंस और निर्भय एश्योरेंस की पॉलिसियों पर कैशलेस इलाज देता है।",
                    "रुग्णालय कवच हेल्थ इन्शुरन्स, संजीवनी जनरल इन्शुरन्स आणि निर्भय ॲश्युरन्स यांच्या पॉलिसींवर कॅशलेस उपचार देते.",
                ),
            ),
            (
                T(
                    "Third-party administrators (TPAs)",
                    "थर्ड पार्टी एडमिनिस्ट्रेटर (टीपीए)",
                    "थर्ड पार्टी ॲडमिनिस्ट्रेटर (टीपीए)",
                ),
                T(
                    "Claims are also accepted through MediLink TPA and CareBridge TPA. If your insurer is not listed, you can pay and claim reimbursement later. "
                    + FICTIONAL.en,
                    "मेडीलिंक टीपीए और केयरब्रिज टीपीए के ज़रिए भी क्लेम लिए जाते हैं। अगर आपकी बीमा कंपनी सूची में नहीं है, तो आप भुगतान करके बाद में रीइम्बर्समेंट क्लेम कर सकते हैं। "
                    + FICTIONAL.hi,
                    "मेडीलिंक टीपीए आणि केअरब्रिज टीपीए मार्फतही क्लेम स्वीकारले जातात. तुमची विमा कंपनी यादीत नसल्यास तुम्ही पैसे भरून नंतर परतफेड (रिइम्बर्समेंट) क्लेम करू शकता. "
                    + FICTIONAL.mr,
                ),
            ),
        ),
        doc(
            "cashless-treatment",
            T("Cashless treatment", "कैशलेस इलाज", "कॅशलेस उपचार"),
            (
                T("How it works", "यह कैसे काम करता है", "हे कसे चालते"),
                T(
                    "For planned admissions, visit the Insurance desk on the ground floor at least 3 working days before the admission date with your policy card and photo ID. The desk sends a pre-authorisation request to your insurer; you pay only the amounts your policy does not cover.",
                    "पहले से तय भर्ती के लिए, भर्ती की तारीख से कम से कम 3 कार्य-दिवस पहले अपना पॉलिसी कार्ड और फ़ोटो पहचान पत्र लेकर भूतल के बीमा डेस्क पर आएं। डेस्क आपकी बीमा कंपनी को पूर्व-अनुमति (प्री-ऑथराइज़ेशन) का अनुरोध भेजता है; आप सिर्फ़ वही राशि देते हैं जो पॉलिसी में शामिल नहीं है।",
                    "नियोजित दाखल होण्यासाठी, दाखल होण्याच्या तारखेच्या किमान 3 कामाचे दिवस आधी पॉलिसी कार्ड आणि फोटो ओळखपत्र घेऊन तळमजल्यावरील विमा डेस्कवर या. डेस्क तुमच्या विमा कंपनीला पूर्वमंजुरीची (प्री-ऑथरायझेशन) विनंती पाठवतो; पॉलिसीत न येणारी रक्कमच तुम्ही भरता.",
                ),
            ),
            (
                T("Emergency admissions", "इमरजेंसी में भर्ती", "आपत्कालीन दाखल"),
                T(
                    "In an emergency, treatment starts immediately; a family member should inform the Insurance desk within 24 hours of admission.",
                    "इमरजेंसी में इलाज तुरंत शुरू होता है; परिवार के किसी सदस्य को भर्ती के 24 घंटे के अंदर बीमा डेस्क को सूचित करना चाहिए।",
                    "आपत्कालीन स्थितीत उपचार लगेच सुरू होतात; कुटुंबातील सदस्याने दाखल झाल्यापासून 24 तासांच्या आत विमा डेस्कला कळवावे.",
                ),
            ),
            (
                T("Insurance desk timings", "बीमा डेस्क का समय", "विमा डेस्कची वेळ"),
                T(
                    "Monday to Saturday, 09:00–18:00.",
                    "सोमवार से शनिवार, 09:00–18:00।",
                    "सोमवार ते शनिवार, 09:00–18:00.",
                ),
            ),
        ),
        doc(
            "opd-insurance-cover",
            T(
                "Does insurance cover OPD visits?",
                "क्या बीमा ओपीडी विज़िट को कवर करता है?",
                "विमा ओपीडी भेटींना लागू होतो का?",
            ),
            (
                T("OPD cover", "ओपीडी कवर", "ओपीडी कव्हर"),
                T(
                    "Most health insurance policies cover hospital admissions but not OPD consultations or tests. OPD visits are covered only if your plan includes an OPD benefit. Pay at the billing counter and keep the bills, prescription and reports to claim from your insurer.",
                    "ज़्यादातर स्वास्थ्य बीमा पॉलिसियां अस्पताल में भर्ती को कवर करती हैं, लेकिन ओपीडी परामर्श या जांच को नहीं। ओपीडी विज़िट तभी कवर होती है जब आपकी योजना में ओपीडी लाभ शामिल हो। बिलिंग काउंटर पर भुगतान करें और बीमा कंपनी से क्लेम के लिए बिल, पर्चा और रिपोर्ट संभालकर रखें।",
                    "बहुतेक आरोग्य विमा पॉलिसी रुग्णालयात दाखल होणे कव्हर करतात, पण ओपीडी सल्ला किंवा तपासण्या नाही. तुमच्या योजनेत ओपीडी लाभ असेल तरच ओपीडी भेटी कव्हर होतात. बिलिंग काउंटरवर पैसे भरा आणि विमा कंपनीकडे क्लेम करण्यासाठी बिले, चिठ्ठी आणि रिपोर्ट जपून ठेवा.",
                ),
            ),
        ),
        doc(
            "reimbursement-claims",
            T("Reimbursement claims", "रीइम्बर्समेंट क्लेम", "परतफेड (रिइम्बर्समेंट) क्लेम"),
            (
                T("Documents you will need", "ज़रूरी कागज़ात", "आवश्यक कागदपत्रे"),
                bullets(
                    [
                        T(
                            "Original itemised bills and payment receipts.",
                            "मूल विस्तृत बिल और भुगतान की रसीदें।",
                            "मूळ तपशीलवार बिले आणि भरणा पावत्या.",
                        ),
                        T(
                            "The doctor's prescription and consultation notes.",
                            "डॉक्टर का पर्चा और परामर्श नोट्स।",
                            "डॉक्टरांची चिठ्ठी आणि सल्ल्याच्या नोंदी.",
                        ),
                        T(
                            "Test reports and, for admissions, the discharge summary.",
                            "जांच रिपोर्ट और भर्ती होने पर डिस्चार्ज सारांश।",
                            "तपासणी रिपोर्ट आणि दाखल झाल्यास डिस्चार्ज सारांश.",
                        ),
                        T(
                            "Your policy card and photo ID.",
                            "आपका पॉलिसी कार्ड और फ़ोटो पहचान पत्र।",
                            "तुमचे पॉलिसी कार्ड आणि फोटो ओळखपत्र.",
                        ),
                    ]
                ),
            ),
            (
                T("Getting copies", "प्रतियां कैसे लें", "प्रती कशा मिळवाव्या"),
                T(
                    "Ask the billing counter for an itemised bill. Duplicate copies of records are available from the Medical Records counter in 2 working days.",
                    "विस्तृत बिल के लिए बिलिंग काउंटर से कहें। रिकॉर्ड की दूसरी प्रतियां मेडिकल रिकॉर्ड काउंटर से 2 कार्य-दिवसों में मिलती हैं।",
                    "तपशीलवार बिलासाठी बिलिंग काउंटरला सांगा. नोंदींच्या दुसऱ्या प्रती मेडिकल रेकॉर्ड काउंटरवरून 2 कामाच्या दिवसांत मिळतात.",
                ),
            ),
        ),
        doc(
            "documents-for-insurance",
            T("Documents for insurance at admission", "भर्ती के समय बीमा के लिए कागज़ात", "दाखल होताना विम्यासाठी कागदपत्रे"),
            (
                T("Checklist", "सूची", "यादी"),
                bullets(
                    [
                        T(
                            "Health insurance card or policy document.",
                            "स्वास्थ्य बीमा कार्ड या पॉलिसी दस्तावेज़।",
                            "आरोग्य विमा कार्ड किंवा पॉलिसी दस्तऐवज.",
                        ),
                        T(
                            "Photo ID of the patient and of the policy holder.",
                            "मरीज़ और पॉलिसीधारक का फ़ोटो पहचान पत्र।",
                            "रुग्णाचे आणि पॉलिसीधारकाचे फोटो ओळखपत्र.",
                        ),
                        T(
                            "The doctor's advice for admission.",
                            "भर्ती के लिए डॉक्टर की सलाह।",
                            "दाखल होण्यासाठी डॉक्टरांचा सल्ला.",
                        ),
                        T(
                            "Employee ID card, for corporate policies.",
                            "कॉर्पोरेट पॉलिसी के लिए कर्मचारी पहचान पत्र।",
                            "कॉर्पोरेट पॉलिसीसाठी कर्मचारी ओळखपत्र.",
                        ),
                    ]
                ),
            ),
        ),
        doc(
            "sahayata-scheme",
            T("Indravani Sahayata assistance scheme", "इंद्रवाणी सहायता योजना", "इंद्रवाणी सहायता योजना"),
            (
                T("What it is", "यह क्या है", "ही काय आहे"),
                T(
                    "The Sahayata scheme is the hospital's own assistance programme. Families with an annual income below ₹2,50,000 get 50% off consultation fees and 30% off laboratory tests. The scheme is fictional, like the hospital.",
                    "सहायता योजना अस्पताल का अपना मदद कार्यक्रम है। ₹2,50,000 से कम वार्षिक आय वाले परिवारों को परामर्श फ़ीस पर 50% और लैब जांच पर 30% छूट मिलती है। यह योजना, अस्पताल की तरह, काल्पनिक है।",
                    "सहायता योजना ही रुग्णालयाची स्वतःची मदत योजना आहे. ₹2,50,000 पेक्षा कमी वार्षिक उत्पन्न असलेल्या कुटुंबांना सल्ला शुल्कात 50% आणि प्रयोगशाळा तपासण्यांवर 30% सूट मिळते. ही योजना रुग्णालयाप्रमाणेच काल्पनिक आहे.",
                ),
            ),
            (
                T("How to apply", "आवेदन कैसे करें", "अर्ज कसा करावा"),
                T(
                    "Apply at the Social Work desk on the ground floor with an income certificate, a ration card or other address proof, and a photo ID. The card is issued the same day and is valid for one year.",
                    "भूतल के सामाजिक कार्य (सोशल वर्क) डेस्क पर आय प्रमाणपत्र, राशन कार्ड या कोई और पते का प्रमाण, और फ़ोटो पहचान पत्र लेकर आवेदन करें। कार्ड उसी दिन मिलता है और एक साल के लिए मान्य होता है।",
                    "तळमजल्यावरील सामाजिक कार्य (सोशल वर्क) डेस्कवर उत्पन्नाचा दाखला, रेशन कार्ड किंवा इतर पत्त्याचा पुरावा आणि फोटो ओळखपत्र घेऊन अर्ज करा. कार्ड त्याच दिवशी मिळते आणि एक वर्षासाठी वैध असते.",
                ),
            ),
        ),
        doc(
            "senior-citizen-benefits",
            T("Benefits for senior citizens", "वरिष्ठ नागरिकों के लिए सुविधाएं", "ज्येष्ठ नागरिकांसाठी सुविधा"),
            (
                T("Benefits", "सुविधाएं", "सुविधा"),
                bullets(
                    [
                        T(
                            "20% off consultation fees for patients aged 60 and above.",
                            "60 वर्ष और उससे ऊपर के मरीज़ों को परामर्श फ़ीस पर 20% छूट।",
                            "60 वर्षे व त्याहून अधिक वयाच्या रुग्णांना सल्ला शुल्कात 20% सूट.",
                        ),
                        T(
                            "A separate queue at the billing and pharmacy counters.",
                            "बिलिंग और फ़ार्मेसी काउंटर पर अलग कतार।",
                            "बिलिंग आणि फार्मसी काउंटरवर वेगळी रांग.",
                        ),
                        T(
                            "Free wheelchair assistance from the main entrance.",
                            "मुख्य द्वार से मुफ़्त व्हीलचेयर सहायता।",
                            "मुख्य प्रवेशद्वारापासून मोफत व्हीलचेअर सहाय्य.",
                        ),
                    ]
                ),
            ),
            (
                T("How to claim", "लाभ कैसे लें", "लाभ कसा घ्यावा"),
                T(
                    "Show a photo ID with your age at the billing counter.",
                    "बिलिंग काउंटर पर उम्र वाला फ़ोटो पहचान पत्र दिखाएं।",
                    "बिलिंग काउंटरवर वय असलेले फोटो ओळखपत्र दाखवा.",
                ),
            ),
        ),
        doc(
            "corporate-tie-ups",
            T("Corporate tie-ups", "कॉर्पोरेट टाई-अप", "कॉर्पोरेट टाय-अप"),
            (
                T("Partner companies", "साझेदार कंपनियां", "भागीदार कंपन्या"),
                T(
                    "Employees of Sahyog Textiles, Vistara Logistics and Orbit Software Services and their families get direct billing for OPD visits. Show your employee ID card at the billing counter. "
                    + FICTIONAL.en,
                    "सहयोग टेक्सटाइल्स, विस्तारा लॉजिस्टिक्स और ऑर्बिट सॉफ़्टवेयर सर्विसेज़ के कर्मचारियों और उनके परिवारों को ओपीडी विज़िट के लिए डायरेक्ट बिलिंग मिलती है। बिलिंग काउंटर पर अपना कर्मचारी पहचान पत्र दिखाएं। "
                    + FICTIONAL.hi,
                    "सहयोग टेक्सटाइल्स, विस्तारा लॉजिस्टिक्स आणि ऑर्बिट सॉफ्टवेअर सर्व्हिसेस यांच्या कर्मचाऱ्यांना आणि त्यांच्या कुटुंबांना ओपीडी भेटींसाठी थेट बिलिंग मिळते. बिलिंग काउंटरवर तुमचे कर्मचारी ओळखपत्र दाखवा. "
                    + FICTIONAL.mr,
                ),
            ),
        ),
        doc(
            "estimates-and-deposits",
            T("Cost estimates and deposits", "खर्च का अनुमान और जमा राशि", "खर्चाचा अंदाज आणि अनामत रक्कम"),
            (
                T("Estimates", "अनुमान", "अंदाज"),
                T(
                    "For a planned procedure or admission, ask the billing counter for a written cost estimate. The final bill may differ if the treatment changes.",
                    "पहले से तय प्रक्रिया या भर्ती के लिए बिलिंग काउंटर से लिखित खर्च अनुमान मांगें। इलाज बदलने पर अंतिम बिल अलग हो सकता है।",
                    "नियोजित प्रक्रिया किंवा दाखल होण्यासाठी बिलिंग काउंटरकडे लेखी खर्च अंदाज मागा. उपचार बदलल्यास अंतिम बिल वेगळे असू शकते.",
                ),
            ),
            (
                T("Deposits and refunds", "जमा राशि और वापसी", "अनामत रक्कम आणि परतावा"),
                T(
                    "An advance deposit is taken at admission for patients without cashless insurance. Any unused deposit is refunded within 7 working days of discharge.",
                    "कैशलेस बीमा न होने पर भर्ती के समय अग्रिम राशि जमा की जाती है। बची हुई जमा राशि डिस्चार्ज के 7 कार्य-दिवसों में लौटा दी जाती है।",
                    "कॅशलेस विमा नसल्यास दाखल होताना आगाऊ अनामत रक्कम घेतली जाते. न वापरलेली रक्कम डिस्चार्जनंतर 7 कामाच्या दिवसांत परत केली जाते.",
                ),
            ),
        ),
        doc(
            "billing-questions",
            T("Billing questions", "बिल से जुड़े सवाल", "बिलाबद्दल प्रश्न"),
            (
                T("Where to ask", "कहां पूछें", "कुठे विचारावे"),
                T(
                    "The billing counter on the ground floor is open 08:00–20:00 every day. It can explain charges, print duplicate receipts and correct the name or details on a bill.",
                    "भूतल का बिलिंग काउंटर रोज़ 08:00–20:00 खुला रहता है। वहां शुल्क समझाए जाते हैं, रसीदों की दूसरी प्रति छापी जाती है और बिल पर नाम या विवरण ठीक किया जाता है।",
                    "तळमजल्यावरील बिलिंग काउंटर दररोज 08:00–20:00 सुरू असते. तेथे शुल्क समजावून सांगितले जाते, पावत्यांच्या दुसऱ्या प्रती छापल्या जातात आणि बिलावरील नाव किंवा तपशील दुरुस्त केला जातो.",
                ),
            ),
        ),
    ]
