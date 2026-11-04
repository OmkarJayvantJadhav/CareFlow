# SQL

## 30-second answer
SQL (Structured Query Language) is the standard language for relational databases: **DDL** defines tables, **DML** reads and changes rows, **DCL** controls permissions and **TCL** controls transactions. In CareFlow I used SQL in three ways: the **schema** itself (constraints, partial unique indexes, views, roles — through SQLAlchemy and Alembic), **queries** generated with SQLAlchemy, and a **text-to-SQL analytics agent** where an LLM writes `SELECT` queries for admins — every query is parsed with **sqlglot** and must be **one SELECT over whitelisted reporting views with no dangerous functions**, then runs in a **read-only transaction with a 3-second timeout, a row limit and a SELECT-only role**. Requests to change data are refused before the LLM is called; 10/10 unsafe analytics requests were refused.

---

## Basics you must know

### Statement categories
| Category | Statements |
|---|---|
| DDL | `CREATE`, `ALTER`, `DROP`, `TRUNCATE` |
| DML | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE` |
| DCL | `GRANT`, `REVOKE` |
| TCL | `BEGIN`, `COMMIT`, `ROLLBACK`, `SAVEPOINT` |

### Query order of execution
`FROM/JOIN → WHERE → GROUP BY → HAVING → SELECT → DISTINCT → ORDER BY → LIMIT/OFFSET`  
(That's why you can't use a SELECT alias in WHERE, but can in ORDER BY.)

### Joins
- `INNER JOIN` — matching rows only.
- `LEFT JOIN` — all left rows, NULLs where no match.
- `RIGHT`, `FULL OUTER`, `CROSS`, self-join.

### Aggregation
```sql
SELECT d.department, COUNT(*) AS visits, AVG(e.wait_minutes) AS avg_wait
FROM reporting.queue_entries e
JOIN reporting.doctors d ON d.id = e.doctor_id
WHERE e.date >= CURRENT_DATE - 7
GROUP BY d.department
HAVING COUNT(*) > 10
ORDER BY avg_wait DESC;
```
`WHERE` filters rows before grouping; `HAVING` filters groups.

### Subqueries and CTEs
```sql
WITH daily AS (
  SELECT doctor, appt_date, COUNT(*) FILTER (WHERE status = 'no_show') AS no_shows, COUNT(*) AS total
  FROM reporting.appointments GROUP BY doctor, appt_date
)
SELECT doctor, SUM(no_shows)::float / SUM(total) AS no_show_rate FROM daily GROUP BY doctor;
```

### Window functions
```sql
SELECT doctor, date, consult_minutes,
       AVG(consult_minutes) OVER (PARTITION BY doctor ORDER BY date ROWS 6 PRECEDING) AS rolling_avg,
       RANK() OVER (PARTITION BY date ORDER BY consult_minutes DESC) AS rnk
FROM ...;
```
`ROW_NUMBER`, `RANK`, `DENSE_RANK`, `LAG`, `LEAD`, `SUM() OVER`.

### Constraints
`PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL`, `CHECK`, `DEFAULT`.

### Normalisation
1NF (atomic values), 2NF (no partial dependency on a composite key), 3NF (no transitive dependency). Denormalise deliberately for performance or constraints — CareFlow copies `doctor_id` and `appt_date` onto appointments so the "one booking per patient, doctor and day" rule can be a unique index.

### Indexes and performance
B-tree for equality/range, composite index column order matters, `EXPLAIN ANALYZE`, avoid `SELECT *` in hot paths, avoid functions on indexed columns in WHERE.

### Transactions and concurrency
ACID, isolation levels, `SELECT … FOR UPDATE`, deadlocks.

### SQL injection
Never build SQL by string-concatenating user input — use bound parameters (`:name`). LLM-generated SQL is user input too.

---

## How I used it in CareFlow

### Schema SQL (through SQLAlchemy/Alembic)
Partial unique indexes on active appointments, CHECK constraints on statuses, foreign keys, a computed `tsvector` column, an HNSW vector index. See [PostgreSQL](postgresql.md).

### Reporting views (migration `0003`)
Nine views in schema `reporting` — `departments`, `doctors`, `slots`, `appointments`, `waiting_list`, `queue_sessions`, `queue_entries`, `queue_events`, `wait_predictions` — that **exclude names and phone numbers** (patients appear as `patient_ref`, birth year, language) and pre-compute useful columns:
```sql
EXTRACT(EPOCH FROM (e.consult_start - e.checked_in_at)) / 60 AS wait_minutes,
EXTRACT(EPOCH FROM (e.consult_end - e.consult_start)) / 60 AS consult_minutes
```
Plus a role `careflow_analytics` with SELECT on those views only.

### Text-to-SQL analytics agent (`app/analytics/agent.py`)
1. **Refuse write intent before any LLM call** — regex for delete/drop/update/insert/"mark all as…"/"add a patient" in English, Hindi and Marathi.
2. The LLM gets the **view columns** (read from `information_schema.columns`), the current date, and one tool `run_sql(sql)`; at most 4 steps.
3. Every query goes through the **validator** and **read-only executor**.
4. The admin sees the answer, a table, **the SQL itself**, and can export CSV.

### The SQL validator (`app/analytics/sql_guard.py`)
```python
statements = sqlglot.parse(sql, read="postgres")
if len(statements) != 1:                      raise unsafe("exactly one statement is allowed")
if not isinstance(tree, exp.Query):           raise unsafe("... statements are not allowed")
for node in tree.walk():
    FORBIDDEN_NODES: Insert, Update, Delete, Merge, Drop, Create, Alter, Command, Copy, Into,
                     Lock, Set, Transaction, Commit, Rollback, Grant, TruncateTable, Use, GenerateSeries
    SELECT ... INTO / FOR UPDATE              → refused
    WITH RECURSIVE                            → refused (runaway queries)
    functions: DENIED_NAMES (pg_*, current_setting, set_config, dblink, lo_*, version, inet_*, ...)
               unknown ("Anonymous") functions only if in SAFE_ANONYMOUS (date_part, age, to_char, ...)
tables: only the 9 reporting views (or CTE names), no other schema or catalog
return tree.sql(dialect="postgres")           # normalised SQL
```
**Why parse instead of regex?** A regex for "DELETE" is easy to fool (comments, casing, nested statements); a real SQL parser sees the actual syntax tree.

### The read-only executor (`run_readonly`)
```sql
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = 3000;                 -- 3 s
SET LOCAL ROLE careflow_analytics;                  -- if available
SET LOCAL search_path = reporting;
SELECT * FROM (<validated>) AS analytics_result LIMIT 201;   -- 200 rows + 1 to detect truncation
```
Errors are returned as a query error, never raised raw. Nothing is ever committed.

**Defence in depth:** even if the validator had a hole, the transaction is read-only, the role can only read views without personal data, and the query times out.

### Results
10/10 unsafe analytics requests refused (`eval/datasets/safety/analytics.jsonl`).

---

## Interview questions

**Q: WHERE vs HAVING?**
WHERE filters rows before grouping; HAVING filters groups after aggregation.

**Q: INNER vs LEFT JOIN?**
INNER keeps only matches; LEFT keeps every left row with NULLs when there's no match.

**Q: What is a window function?**
An aggregate computed over a "window" of related rows without collapsing them — e.g. a running average per doctor.

**Q: How do you prevent SQL injection?**
Parameterised queries. For LLM-written SQL (which can't be parameterised), parse and whitelist it, then run it with least privilege, read-only and with a timeout.

**Q: How would you find the second-highest wait time?**
`SELECT DISTINCT wait_minutes FROM … ORDER BY wait_minutes DESC OFFSET 1 LIMIT 1;` or `DENSE_RANK() OVER (ORDER BY wait_minutes DESC) = 2`.

**Q: Why views for analytics?**
They hide personal data, give the LLM a small, stable, documented schema, and let me grant access to views only.
