"""The real app for browser tests, with three test-only changes:

* its own database (careflow_e2e), seeded for Monday 19 October 2026;
* a clock that starts at 08:00 IST that day and then runs normally;
* a rule-based stand-in for the LLM, so the flows are repeatable and need no API key.

    python -m tests.e2e.server <port>

Everything else - tools, rules, cards, safety gate, queue engine, WebSocket, the built UI - is the
production code.
"""

import json
import os
import re
import sys
import time
from datetime import datetime

DATABASE_URL = os.environ.get("E2E_DATABASE_URL", "postgresql+psycopg://careflow:careflow@localhost:5432/careflow_e2e")
_keys = {k: os.environ.get(k, "") for k in ("GROQ_API_KEY", "GEMINI_API_KEY")} if "--real-llm" in sys.argv else {}
os.environ.update(
    DATABASE_URL=DATABASE_URL,
    DEMO_MODE="true",
    WARM_UP_RETRIEVER="false",
    EMBEDDING_BACKEND="local",
    RERANKER_BACKEND="local",
    GROQ_API_KEY="",
    GEMINI_API_KEY="",
    TRACE_DIR=os.environ.get("E2E_TRACE_DIR", "/tmp/careflow-e2e-traces"),
    MAX_MESSAGES_PER_SESSION="200",
    MAX_MESSAGES_PER_IP_PER_HOUR="1000",
)
os.environ.update(_keys)

from app.agent.llm import LLMResponse, ToolCall  # noqa: E402
from app.timeutil import HOSPITAL_TZ  # noqa: E402

START = datetime(2026, 10, 19, 8, 0, tzinfo=HOSPITAL_TZ)
_t0 = time.monotonic()


def clock() -> datetime:
    from datetime import timedelta

    return START + timedelta(seconds=time.monotonic() - _t0)


class RuleLLM:
    """Decides the next step from the user's message and the tool results so far in this turn."""

    name = "e2e:rules"

    def chat(self, messages: list[dict], tools: list[dict], max_tokens: int) -> LLMResponse:
        system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        text = (messages[last_user].get("content") or "").lower()
        turn = messages[last_user + 1 :]
        results = [json.loads(m["content"]) for m in turn if m["role"] == "tool"]
        step = len(results)

        def call(name: str, **args) -> LLMResponse:
            return LLMResponse(None, [ToolCall(f"c{step}", name, args, json.dumps(args))], "e2e", "rules", 50, 10, 5.0)

        def say(reply: str) -> LLMResponse:
            return LLMResponse(reply, [], "e2e", "rules", 50, 10, 5.0)

        if "read-only sql" in system.lower():  # the analytics agent
            if step == 0:
                return call("run_sql", sql="SELECT department, count(*) AS appointments FROM appointments "
                                           "GROUP BY department ORDER BY 2 DESC")  # fmt: skip
            return say("Appointments per department are in the table below.")
        if re.search(r"cardiolog|heart|हृदय", text):
            patient = int(re.search(r"patient_id (\d+)", system).group(1))
            if step == 0:
                return call("search_doctors", specialty="cardiology", language="mr", day="saturday")
            if step == 1:
                return call("check_availability", doctor_id=results[0]["doctors"][0]["doctor_id"], date="saturday")
            if step == 2:
                return call("book_appointment", patient_id=patient, slot_id=results[1]["slots"][0]["slot_id"])
            return say("Please confirm the booking on the card.")
        if re.search(r"lipid|fast|लिपिड", text):
            if step == 0:
                return call("search_knowledge", query="lipid profile fasting")
            return say("Yes. Fast for 10–12 hours before a lipid profile; water is allowed [1].")
        return say("I can help with OPD appointments, hospital information and your queue.")


def prepare() -> None:
    from sqlalchemy import create_engine, text

    from app.db.session import normalize_url, session_scope
    from app.rag.ingest import ingest
    from simulator.seed import reset_demo

    base, _, name = DATABASE_URL.rpartition("/")
    admin = create_engine(normalize_url(f"{base}/postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}).first():
            conn.execute(text(f"CREATE DATABASE {name}"))
    admin.dispose()
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", normalize_url(DATABASE_URL))
    command.upgrade(cfg, "head")
    with session_scope() as db:
        reset_demo(db, START.date(), 42)
        ingest(db, if_needed=True)
    with session_scope() as db:
        from app.rag.retriever import get_retriever

        get_retriever(db)  # load retrieval before serving, as production does at start-up


def main(port: int, real_llm: bool = False) -> None:
    import uvicorn

    import app.agent.tracing
    import app.api.admin_routes
    import app.api.auth
    import app.api.care_routes
    import app.api.queue_routes
    import app.api.routes
    import app.timeutil

    for module in (app.timeutil, app.agent.tracing, app.api.auth, app.api.queue_routes, app.api.routes,
                   app.api.admin_routes, app.api.care_routes):  # fmt: skip
        module.now_ist = clock
    prepare()
    from app.api.deps import get_llm
    from app.api.main import app as api

    if not real_llm:
        llm = RuleLLM()
        api.dependency_overrides[get_llm] = lambda: llm
    uvicorn.run(api, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    # --real-llm keeps the production providers (Groq, then Gemini) - used to record the demo video.
    main(int(sys.argv[1]), real_llm="--real-llm" in sys.argv)
