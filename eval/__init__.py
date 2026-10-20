"""Offline evaluations (docs §14). Run as modules, e.g. ``python -m eval.run_safety``.

Importing the package points the app at the evaluation database before any
settings are read, so ``python -m eval.<runner>`` never touches the demo data.
"""

import os

os.environ["DATABASE_URL"] = os.environ.get(
    "EVAL_DATABASE_URL", "postgresql+psycopg://careflow:careflow@localhost:5432/careflow_eval"
)
os.environ.setdefault("TRACE_DIR", "eval/.traces")
os.environ.setdefault("WARM_UP_RETRIEVER", "false")
