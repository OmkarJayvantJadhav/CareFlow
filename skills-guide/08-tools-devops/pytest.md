# pytest

## 30-second answer
pytest is Python's standard testing framework: tests are plain functions starting with `test_` that use plain `assert`; **fixtures** provide setup (database, app client, model files) through dependency injection; **parametrize** runs one test with many inputs; **markers** group tests. CareFlow has **473 pytest tests** that run against a **real PostgreSQL + pgvector** database with a fixed clock and a **scripted fake LLM** — including **concurrency tests** where 10 threads race to book the same slot. MedVision has backend and ML suites (with **98% backend coverage**) including **parity tests** proving the TensorFlow-free serving code matches TensorFlow.

---

## Basics you must know

### Writing tests
```python
def test_temperature_does_not_change_ranking():
    logits = np.array([[2.0, 1.0, 0.1]])
    assert calibrated_probabilities(logits, 2.0).argmax() == logits.argmax()

def test_rejects_negative_temperature():
    with pytest.raises(ValueError):
        calibrated_probabilities(np.zeros((1, 3)), 0)
```
`pytest.approx(0.1)` for floats.

### Fixtures
```python
@pytest.fixture(scope="session")
def engine(): ...                 # created once per test run

@pytest.fixture
def db(engine):
    session = Session(engine)
    yield session                 # teardown after yield
    session.close()

def test_booking(db): ...         # injected by name
```
Scopes: `function` (default), `class`, `module`, `session`. `conftest.py` shares fixtures across files. Built-ins: `tmp_path`, `monkeypatch`, `capsys`, `caplog`.

### Parametrize
```python
@pytest.mark.parametrize("text, expected", [("my father collapsed", True), ("book ENT on Monday", False)])
def test_emergency(text, expected):
    assert check_emergency(text).is_emergency is expected
```
Each parameter set counts as a separate test.

### Markers and selection
```bash
pytest -k "booking and not reschedule"
pytest -m e2e
pytest -x --lf                # stop at first failure / rerun last failures
pytest --cov=app --cov-report=term-missing
```

### Mocking
`monkeypatch.setattr(...)`, `unittest.mock.patch`, or better — design code with injectable dependencies (protocols) so tests pass a fake.

### Test pyramid
Many fast unit tests → fewer integration tests (real DB, real HTTP app) → few end-to-end browser tests.

---

## How I used it in CareFlow (`tests/`)

### Real database, not mocks (`tests/conftest.py`)
```python
os.environ["DATABASE_URL"] = TEST_DATABASE_URL       # point the app at the test DB before imports
os.environ["EMBEDDING_BACKEND"] = "local"            # deterministic retrieval models
os.environ["GROQ_API_KEY"] = ""                      # never call a real LLM

NOW = datetime(2026, 10, 19, 8, 0, tzinfo=HOSPITAL_TZ)   # fixed clock: Monday 08:00 IST

@pytest.fixture(scope="session")
def engine():
    # DROP SCHEMA public CASCADE; CREATE SCHEMA public; alembic upgrade head   (once per run)

def wipe(engine):
    # TRUNCATE <operational tables> RESTART IDENTITY CASCADE   (before every test)
```
Partial unique indexes, row locks, pgvector and savepoints behave exactly as in production. The knowledge base is ingested once per run.

### Deterministic LLM — `ScriptedLLM` (`app/agent/llm.py`)
Each step is a function of the messages so far; it can return text or a dict of tool calls. Agent tests check: tool validation, confirmation cards, emergencies, citations, budgets, fallback logic — without network or cost.

### Concurrency tests (`tests/test_concurrency.py`)
```python
def race(factory, attempts):
    barrier = threading.Barrier(len(attempts))       # all threads start at the same moment
    def run(i, actor, patient_id, slot_id):
        db = factory()
        barrier.wait()
        book_appointment(db, actor, patient_id, slot_id, confirmed=True, now=NOW); db.commit()
        ...
def test_ten_way_race_still_one_winner(world, factory):
    outcomes = race(factory, [(world.staff, p, slot.id) for p in patients])
    assert outcomes.count("ok") == 1 and outcomes.count("SLOT_TAKEN") == 9
```

### Test files cover every area
`test_booking`, `test_waiting_list`, `test_queue*`, `test_balance`, `test_merge`, `test_wait_time`, `test_agent`, `test_agent_queue`, `test_llm`, `test_knowledge`, `test_safety`, `test_analytics`, `test_permissions`, `test_patient_data`, `test_audit_privacy`, `test_messaging`, `test_api`, …
Requirements are traced to tests in the README (e.g. FR-10/11 double booking → TC-02–TC-04).

### Markers
`pyproject.toml`: `addopts = "-q -m 'not e2e'"` — plain `pytest` skips browser tests; `pytest -m e2e tests/e2e` runs the 45 Playwright tests.

## How I used it in MedVision AI
- **Backend** (`backend/tests/`): `TestClient` API tests — health/ready/meta, predict (malignant, benign, low confidence, rejected), upload validation, **oversized body refused before reading**, **uploads stay in memory**, explain PNGs, missing model keeps service up, rate limit, forwarded-IP trust, CORS, request IDs, hidden internal errors, serving the frontend; plus math, preprocessing, predictor, CLI, download (checksums), and an **OpenAPI snapshot test**. Coverage **98%** (`pytest --cov`).
- **ML** (`ml/tests/`): splitting/grouping/leakage/dedupe/hashing, class weights, calibration, OOD, noise, metrics, robustness, subgroups, models, config, CLI, notebook, and the Matplotlib backend.
- **Parity tests** (`test_export_parity.py`): build a tiny model with random weights (`weights=None`) at 64 px so tests are fast, export to ONNX, and compare ONNX vs Keras, NumPy heatmap vs TensorFlow Grad-CAM, served resize vs training pipeline, OOD and noise scores.
- `tmp_path_factory` fixtures for exported model directories; `parametrize` for many image cases.

---

## Interview questions

**Q: What are fixtures and why use them?**
Reusable setup/teardown injected by name, with scopes. They remove duplication and make dependencies explicit (DB, app client, exported model).

**Q: Why test against a real database instead of mocking?**
The important rules (partial unique indexes, row locks, savepoints, pgvector queries) live in PostgreSQL; a mock would test nothing. Wiping with TRUNCATE keeps it fast.

**Q: How do you test code that depends on time?**
Inject `now` into functions (CareFlow passes `now=` everywhere) and use a fixed clock in tests.

**Q: How do you test an LLM agent?**
Unit/integration tests with a scripted fake LLM for determinism; separate evaluation runs with real models for quality.

**Q: How did you test race conditions?**
Threads with separate sessions synchronised by `threading.Barrier` all book the same slot; assert exactly one success.

**Q: What's a parity test?**
A test that two implementations (TensorFlow training vs NumPy/ONNX serving) give the same results on the same input.
