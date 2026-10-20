"""SQL validator and read-only execution for admin analytics (FR-31, TC-14, TC-15).

A query is run only if it parses as exactly one SELECT over the reporting views,
calls no function outside an allow-list, and has no INTO / FOR UPDATE / recursive
CTE. It then runs wrapped in a row limit, inside a READ ONLY transaction with a
statement timeout, as the SELECT-only ``careflow_analytics`` role when the
database has it (migration 0003). Every check is in code; the LLM's own refusal
is never relied on.
"""

import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlglot import exp
from sqlglot.errors import ParseError

from app.tools.errors import ToolError

SCHEMA = "reporting"
ROLE = "careflow_analytics"
MAX_ROWS = 200
TIMEOUT_MS = 3000
VIEWS = (
    "departments",
    "doctors",
    "slots",
    "appointments",
    "waiting_list",
    "queue_sessions",
    "queue_entries",
    "queue_events",
    "wait_predictions",
)

# Statement and clause types that must never appear anywhere in the tree.
FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Copy,
    exp.Into,
    exp.Lock,
    exp.Set,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Grant,
    exp.TruncateTable,
    exp.Use,
    exp.GenerateSeries,
    exp.ExplodingGenerateSeries,
)
# Functions that sqlglot does not know by type ("Anonymous") are refused unless listed here.
SAFE_ANONYMOUS = {"date_part", "age", "to_char", "to_date", "justify_interval", "make_interval", "width_bucket"}
# Never allowed, even if sqlglot gives them a type: server state, files, sleeping, other databases.
DENIED_NAMES = re.compile(
    r"^(pg_|current_setting|set_config|dblink|lo_|query_to_xml|table_to_xml|txid_|version$|inet_)", re.I
)


@dataclass
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    meta: dict = field(default_factory=dict)


def unsafe(reason: str) -> ToolError:
    return ToolError("UNSAFE_QUERY", f"Only read-only questions about the reporting views are allowed: {reason}.")


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name)
    return node.sql_name()


def validate_sql(sql: str) -> str:
    """Return the normalised single SELECT statement, or raise UNSAFE_QUERY."""
    if not sql or not sql.strip():
        raise unsafe("the query is empty")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError:
        raise unsafe("the query could not be parsed") from None
    if len(statements) != 1:
        raise unsafe("exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise unsafe(f"{type(tree).__name__.upper()} statements are not allowed")
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise unsafe(f"{type(node).__name__.upper()} is not allowed")
        if isinstance(node, exp.Select) and (node.args.get("into") or node.args.get("locks")):
            raise unsafe("SELECT INTO and row locks are not allowed")
        if isinstance(node, exp.With) and node.args.get("recursive"):
            raise unsafe("recursive queries are not allowed")
        if isinstance(node, exp.Func):
            name = _function_name(node)
            if DENIED_NAMES.match(name) or (isinstance(node, exp.Anonymous) and name.lower() not in SAFE_ANONYMOUS):
                raise unsafe(f"the function {name} is not allowed")
    ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise unsafe("only the reporting views can be queried")
        name, schema = table.name.lower(), (table.db or "").lower()
        if not schema and not table.catalog and name in ctes:
            continue
        if table.catalog or schema not in ("", SCHEMA) or name not in VIEWS:
            raise unsafe(f"the table {table.name} is not available; use one of: {', '.join(VIEWS)}")
    return tree.sql(dialect="postgres")


def run_readonly(engine: Engine, sql: str, max_rows: int = MAX_ROWS) -> QueryResult:
    """Validate, then execute in a read-only transaction; nothing is ever committed."""
    statement = validate_sql(sql)
    wrapped = f"SELECT * FROM ({statement}) AS analytics_result LIMIT {max_rows + 1}"
    with engine.connect() as conn:
        with conn.begin() as tx:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f"SET LOCAL statement_timeout = {TIMEOUT_MS}"))
            if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r AND pg_has_role(current_user, oid, 'SET')"),
                            {"r": ROLE}).first():  # fmt: skip
                conn.execute(text(f"SET LOCAL ROLE {ROLE}"))
            conn.execute(text(f"SET LOCAL search_path = {SCHEMA}"))
            try:
                result = conn.execute(text(wrapped))
            except Exception as err:  # noqa: BLE001 - reported back as a query error, never raised raw
                tx.rollback()
                message = str(getattr(err, "orig", err)).splitlines()[0][:200]
                if "statement timeout" in message:
                    raise ToolError("UNSAFE_QUERY", "The query took too long and was stopped.") from None
                raise ToolError("VALIDATION_ERROR", f"The query failed: {message}") from None
            columns = list(result.keys())
            rows = [list(r) for r in result.fetchall()]
            tx.rollback()
    return QueryResult(statement, columns, rows[:max_rows], len(rows) > max_rows)
