# Safety Guardrails

## 30-second answer
Guardrails are checks *around* a model — on its inputs, its actions and its outputs — that enforce rules the model itself can't be trusted to follow. CareFlow has guardrails at every stage: an **emergency classifier that screens each message before the LLM** (rules in 3 languages + a TF-IDF/logistic-regression classifier; **60/60 held-out emergencies** caught), a **prompt-injection filter** on retrieved documents (**15/15 injection tests**), **validated tools with confirmation** for writes, an **output guard** that blocks medicine names and doses, a **citation guard**, **PII masking and AES-GCM encryption**, and a **read-only, validated text-to-SQL analytics agent** (10/10 unsafe requests refused). MedVision applies the same idea to vision: input gates that **reject instead of guessing**.

---

## Basics you must know

### Layers of guardrails
| Layer | Examples |
|---|---|
| **Input** | Emergency/self-harm detection, prompt-injection detection, PII masking, length/rate limits, language detection |
| **Context** | Sanitise retrieved documents, mark them as data, least-privilege tool list |
| **Action** | Argument validation, permission checks, human confirmation, read-only database roles, limits on steps |
| **Output** | Block disallowed content (medical dosing), require citations, remove internal ids, fixed templates for critical replies |
| **Monitoring** | Traces, audit logs, evaluation sets that are re-run |

### Key principle
**Rules in code, not in the prompt.** The prompt explains; code enforces. A jailbreak can change what the model says, but not what the code allows.

### Prompt injection
- **Direct:** the user says "ignore your instructions…".
- **Indirect:** instructions hidden in data the model reads (documents, web pages, tool results).
- Defences: treat tool/document text as data, strip instruction-like text, least-privilege tools, confirmation for actions, never let model output decide permissions.

### Measuring guardrails
Use **held-out** test sets (not the data you tuned on), count recall (missed emergencies) *and* false alarms, and re-run after every change.

---

## How I built them in CareFlow (`app/safety/`, `app/agent/`, `app/analytics/`)

### 1. Emergency check — before the LLM (`app/safety/emergency.py`)
Two stages tuned for **recall**:
1. **Hand-written patterns** in English, Hindi, Marathi and romanised Hindi/Marathi, grouped by what is happening: heart, breathing, not responding, stroke, bleeding, seizures, self-harm, poisoning, allergy, injuries, pregnancy. E.g. `r"chest (pain|tightness|pressure)"`, `r"(सांस|साँस) (नहीं|ले नहीं|...)"`, `r"श्वास घेता येत नाही"`.
2. **A small classifier** for paraphrases the patterns miss:
   ```python
   features = make_union(
       TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
       TfidfVectorizer(analyzer="word",    ngram_range=(1, 2), sublinear_tf=True))
   make_pipeline(features, LogisticRegression(C=8.0, class_weight="balanced", max_iter=3000))
   ```
Decision logic:
- A **specific** pattern ("crushing chest pain", "not breathing") → emergency on its own.
- A **weak/generic** pattern ("poison", "accident", "fits") → emergency only if the classifier gives ≥ 0.2.
- Classifier alone → emergency at ≥ **0.6** (the highest threshold that kept every development emergency; 0.45 flagged ordinary booking sentences — D-53), only for messages of 4+ words.

Context handling to avoid false alarms, **clause by clause**:
- **History:** "had a seizure as a toddler", "fainted once in 2023" don't count — unless the clause also says "now" ("fine for years, but right now he is fitting").
- **Negation:** "no chest pain" is skipped.
- **Exertion:** mild breathlessness "when climbing stairs" is not an emergency.
- **Information requests:** "what is the emergency department number?" is not an emergency.

What happens: fixed guidance (call **112 / 108**) in the user's language takes over the chat, any pending confirmation card is dropped, **nothing is written** that turn.

**Results:** 60/60 on the final held-out set; the code gate alone caught 58/60 (the LLM's `emergency_redirect` tool caught the rest); 8.3% false alarms on look-alike non-emergencies.

### 2. Prompt-injection filter (`app/safety/injection.py`)
`neutralize(text)` splits retrieved text into sentences and replaces any that address the assistant or give orders ("ignore previous instructions", "you are now", "tell every patient", "without asking", "call the X tool", `<system>`, and Hindi/Marathi equivalents) with `[removed: instruction-like text]`, and records it in the trace. Hospital documents describe the hospital in the third person, so real content is not removed. **15/15** injection tests passed (chat and documents).

### 3. Action guardrails (`app/agent/tools.py`, `app/tools/`)
- Pydantic validation of every argument; unknown tools rejected.
- Role-based tool lists and `require_patient_access()` in every service function (**15/15 permission attacks** blocked).
- Writes: preview in a rolled-back savepoint → card → explicit confirmation; 5-minute expiry; one change at a time.

### 4. Output guardrails (`app/agent/loop.py`, `app/safety/output_guard.py`)
- `mentions_medication()` — a list of common medicines (English + Devanagari) and dose patterns (`500 mg`, `twice a day`, `दिन में दो बार`, `2 गोळ्या`) → reply replaced with a fixed refusal pointing to a doctor (**15/15 medical-advice bait**).
- **Citation guard** — knowledge answers must cite a retrieved source or are replaced with "I couldn't find that".
- `strip_internal_ids()` — removes "slot ID 1293" leaks.
- Critical replies (emergency, confirmation question, handoff) are **fixed templates**, never model text.

### 5. Privacy (`app/safety/pii.py`, `app/safety/privacy.py`)
- Phone numbers stored three ways: **masked** (+91 98XXXXXX12) for screens, logs, traces and LLM prompts; **AES-GCM encrypted** (12-byte random nonce, associated data `careflow:patient-phone`, key derived with HKDF-SHA256); and an **HMAC-SHA256 keyed hash** so staff can search by number without storing it in clear text.
- Log masking installed at start-up; traces are masked.

### 6. Analytics guardrails (`app/analytics/`)
Requests to change data are refused **before any model call** (regex for delete/update/insert in 3 languages). Generated SQL must parse (sqlglot) as **one SELECT** over reporting views, with no forbidden nodes/functions, and runs in a **READ ONLY transaction** with a **3 s timeout** as a **SELECT-only role**, wrapped in a row limit. **10/10** unsafe analytics requests refused. See [SQL](../07-databases/sql.md).

### 7. Abuse limits
20 messages per session, 60 per IP per hour, 1,000 characters per message, 10 registrations per IP per hour, 10 failed logins per 15 min (sliding-window limiters in `app/api/deps.py`).

## MedVision's guardrails (vision version)
Reject rather than guess: brightness, sharpness (Laplacian variance) and noise gates, and a **Mahalanobis out-of-distribution detector** (99.6% of non-dermoscopy photos rejected while 98.9% of lesion images pass). The **high-risk alert** is shown above the lesion type so a warning is never hidden behind a benign-looking label. The summary is a **fixed template**, not LLM text, so it can't invent claims. See [Model calibration](../03-ai-ml-deep-learning/model-calibration.md).

---

## Interview questions

**Q: Why check for emergencies before the LLM instead of letting the LLM decide?**
Latency, cost and reliability: a regex + small classifier runs in milliseconds, works even if the LLM provider is down, and can't be talked out of it. The LLM also has an `emergency_redirect` tool as a second line.

**Q: How did you avoid false alarms?**
Clause-level analysis with history, negation, exertion and information-request rules, and separate thresholds for strong patterns, weak patterns and the classifier alone. False alarms on held-out look-alikes: 8.3%.

**Q: Why logistic regression and not a transformer for the emergency classifier?**
Tiny, fast, interpretable, trains in seconds at start-up, works with character n-grams across scripts and spelling variations, and it's only the second stage behind patterns. Recall was the goal and the held-out set showed 60/60.

**Q: How do you defend against prompt injection?**
Sanitise retrieved text, tell the model documents are data, least-privilege tools, validation and permission checks in code, and confirmation for every write — so even a successful injection can't book or cancel anything.

**Q: What's the risk you'd still worry about?**
Chat messages (with numbers masked), patient names and appointment details go to the external LLM provider (D-117). A real hospital should use a provider with a data agreement or a local model through Ollama, which the code already supports.
