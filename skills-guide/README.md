# Skills Guide — Omkar Jayvant Jadhav

One file for every skill on the resume. Each file explains **what the skill is**, the **basics you must know**, **exactly how it is used in CareFlow and MedVision AI** (with file paths and real numbers), and **interview questions with answers**.

> **How to use this:** read the "30-second answer" at the top of a file until you can say it without looking. Then read "How I used it" and say it aloud in your own words. Finish with the interview questions.

---

## The two projects in one breath

**CareFlow** — a multilingual (English, Hindi, Marathi) hospital appointment and live-queue platform. Patients book by chatting with an LLM agent (Groq → Gemini fallback) that can only *propose* changes; every write is previewed in a rolled-back database savepoint and runs only after the user taps **Confirm**. Questions are answered with hybrid RAG (pgvector + BM25 + rank fusion + re-ranker) over 363 hospital documents. An emergency classifier checks every message *before* the LLM sees it. A LightGBM model predicts wait times. FastAPI + PostgreSQL + React, deployed with Docker on Render and Neon.

**MedVision AI** — an explainable dermoscopy (skin-lesion) classifier. EfficientNet-B0 fine-tuned on ISIC 2019 (25,331 images, 8 classes) with TensorFlow/Keras; calibrated with temperature scaling (ECE 0.026); a high-risk alert that catches 90.4% of malignant images; input gates (Mahalanobis out-of-distribution detector, noise and quality checks) that reject images instead of guessing; served as ONNX on CPU with FastAPI (~30 ms/image), with Grad-CAM computed in plain NumPy. React + Tailwind frontend, Docker on Render.

---

## Index

| Category | Skill | Used in |
|---|---|---|
| **Programming languages** | [Python](01-programming-languages/python.md) | Both (main language) |
| | [JavaScript](01-programming-languages/javascript.md) | Both (React frontends) |
| | [C](01-programming-languages/c.md) | Coursework / DSA (not in these projects) |
| | [C++](01-programming-languages/cpp.md) | Coursework / DSA (not in these projects) |
| | [Java](01-programming-languages/java.md) | Coursework / OOP (not in these projects) |
| **Generative AI** | [LLM agents](02-generative-ai/llm-agents.md) | CareFlow |
| | [Tool calling](02-generative-ai/tool-calling.md) | CareFlow |
| | [RAG](02-generative-ai/rag.md) | CareFlow |
| | [Hybrid search](02-generative-ai/hybrid-search.md) | CareFlow |
| | [Re-ranking](02-generative-ai/re-ranking.md) | CareFlow |
| | [Safety guardrails](02-generative-ai/safety-guardrails.md) | CareFlow (and MedVision input gates) |
| | [Gemini API](02-generative-ai/gemini-api.md) | CareFlow (fallback LLM) |
| | [Groq](02-generative-ai/groq.md) | CareFlow (primary LLM) |
| | [Hugging Face](02-generative-ai/hugging-face.md) | CareFlow (model hub), MedVision (first host) |
| **AI/ML & Deep Learning** | [TensorFlow / Keras](03-ai-ml-deep-learning/tensorflow-keras.md) | MedVision |
| | [CNNs](03-ai-ml-deep-learning/cnns.md) | MedVision |
| | [Transfer learning](03-ai-ml-deep-learning/transfer-learning.md) | MedVision |
| | [Model calibration](03-ai-ml-deep-learning/model-calibration.md) | MedVision (and CareFlow's wait ranges) |
| | [Grad-CAM](03-ai-ml-deep-learning/grad-cam.md) | MedVision |
| | [ONNX Runtime](03-ai-ml-deep-learning/onnx-runtime.md) | MedVision (and CareFlow via fastembed) |
| | [OpenCV](03-ai-ml-deep-learning/opencv.md) | Concepts used in MedVision (implemented in NumPy/Pillow) |
| **Data Science** | [NumPy](04-data-science/numpy.md) | Both |
| | [pandas](04-data-science/pandas.md) | Not imported in these projects — read the file |
| | [scikit-learn](04-data-science/scikit-learn.md) | Both |
| | [LightGBM](04-data-science/lightgbm.md) | CareFlow |
| | [Matplotlib](04-data-science/matplotlib.md) | MedVision |
| | [seaborn](04-data-science/seaborn.md) | Not imported in these projects — read the file |
| **Backend & APIs** | [FastAPI](05-backend-apis/fastapi.md) | Both |
| | [Pydantic](05-backend-apis/pydantic.md) | Both |
| | [REST APIs](05-backend-apis/rest-apis.md) | Both |
| | [WebSockets](05-backend-apis/websockets.md) | CareFlow |
| | [SQLAlchemy](05-backend-apis/sqlalchemy.md) | CareFlow |
| | [Alembic](05-backend-apis/alembic.md) | CareFlow |
| **Frontend** | [React](06-frontend/react.md) | Both |
| | [Vite](06-frontend/vite.md) | Both |
| | [Tailwind CSS](06-frontend/tailwind-css.md) | MedVision (CareFlow uses hand-written CSS) |
| **Databases** | [PostgreSQL](07-databases/postgresql.md) | CareFlow |
| | [pgvector](07-databases/pgvector.md) | CareFlow |
| | [SQL](07-databases/sql.md) | CareFlow |
| | [MySQL](07-databases/mysql.md) | Not in these projects — read the file |
| **Tools & DevOps** | [Git](08-tools-devops/git.md) | Both |
| | [Docker](08-tools-devops/docker.md) | Both |
| | [GitHub Actions](08-tools-devops/github-actions.md) | Both |
| | [pytest](08-tools-devops/pytest.md) | Both |
| | [Vitest](08-tools-devops/vitest.md) | Both |
| | [Playwright](08-tools-devops/playwright.md) | CareFlow |
| | [Render](08-tools-devops/render.md) | Both (live demos) |
| | [Vercel](08-tools-devops/vercel.md) | Not in these projects — read the file |

---

## Be ready for these honesty questions

While checking the two repositories, a few resume items turned out **not to appear in either project's code**:

| Skill | What the code actually uses | What to do |
|---|---|---|
| **pandas** | CSV/JSON handled with the `csv` and `json` modules; arrays with NumPy | Know pandas basics (file explains them) and say where you used it (coursework, Kaggle, notebooks) — or remove it |
| **seaborn** | Plots are made with plain Matplotlib | Same as above |
| **OpenCV** | Image work done with **Pillow + NumPy** (Laplacian blur check, bilinear resize, colour maps) | Explain that you implemented the OpenCV-style operations in NumPy on purpose (parity with training, smaller image) |
| **MySQL** | PostgreSQL only | Explain MySQL vs PostgreSQL differences; say where you used MySQL (DBMS lab, college project) |
| **Vercel** | Both apps are deployed on **Render** (Docker) | Explain why Render fits (one Docker container serves API + UI) and when you'd use Vercel |
| **C, C++, Java** | Not used in these projects | Normal for a CS student — say coursework / DSA practice |

Interviewers often ask "Where did you use X?" for each skill. The files for these skills give you a truthful answer and the basics in case they test you.

### Numbers on the resume vs the repos
- **CareFlow:** 28 database tables ✔ (`app/db/models.py`), 102 decorated REST routes plus the WebSocket in `app/api/` (the resume says 103), 473 pytest / 45 Playwright / 13 Vitest tests (from the README badge; parametrized tests count once per parameter set).
- **MedVision:** the README's "Quality gates" table says **266** tests (131 ml, 100 backend, 35 frontend); the resume says **279**. The frontend now has more `it(...)` blocks than the README lists, so 279 may be current. **Run the suites once and update whichever number is stale** so you can defend it.

---

## Ten-line elevator pitch you can memorise

1. "I build end-to-end AI applications: model, API, UI, tests and deployment."
2. "CareFlow is a hospital OPD platform in three languages with an LLM agent and RAG."
3. "The LLM never writes to the database directly; it proposes, my code previews the change in a rolled-back savepoint, and the user confirms."
4. "Retrieval is hybrid: pgvector dense search plus BM25, fused with reciprocal rank fusion, then re-ranked — 85.9% recall@5 in 5-fold cross-validation."
5. "Every message passes an emergency classifier before the LLM — 60 of 60 held-out emergencies caught."
6. "A LightGBM quantile model gives wait estimates with a range — MAE 17.9 min vs 29.4 for the baseline."
7. "MedVision is an explainable skin-lesion classifier: EfficientNet-B0 on ISIC 2019, calibrated to ECE 0.026."
8. "Its alert is tuned for 90% malignant recall, and gates reject images it can't judge — 99.6% of non-dermoscopy photos rejected."
9. "It is served as ONNX on CPU without TensorFlow at about 30 ms an image, with Grad-CAM in NumPy, and parity tests prove it matches TensorFlow."
10. "Both are tested in CI with GitHub Actions and deployed as Docker containers on Render."
