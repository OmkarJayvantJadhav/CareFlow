# MySQL

## Where it fits in my work (say this honestly)
**MySQL is not used in CareFlow or MedVision** — CareFlow runs on PostgreSQL (MedVision has no database). I know MySQL from coursework (DBMS lab) and the SQL is largely the same. The best interview answer is to show you understand the differences and why you picked PostgreSQL.

> If asked "where did you use MySQL?" → "In my DBMS coursework. For CareFlow I chose PostgreSQL because I needed partial unique indexes to prevent double booking, pgvector for semantic search in the same database, and roles/views for the read-only analytics agent. In MySQL I'd have enforced the booking rule with a generated column plus a unique index, and used a separate vector store."

---

## 30-second answer
MySQL is the most widely used open-source relational database (owned by Oracle; MariaDB is a community fork). Its default storage engine **InnoDB** provides ACID transactions, row-level locking, foreign keys and MVCC. It's popular for web applications (the "LAMP" stack), simple to operate, and very fast for read-heavy workloads.

---

## Basics you must know

### Storage engines
- **InnoDB** (default): transactions, row locks, foreign keys, crash recovery, clustered primary key.
- MyISAM (old): no transactions, table locks.

### Clustered index
InnoDB stores rows ordered by the **primary key**; secondary indexes store the primary key, so a short PK matters.

### Common syntax differences from PostgreSQL
| Feature | MySQL | PostgreSQL |
|---|---|---|
| Auto id | `AUTO_INCREMENT` | `SERIAL` / `GENERATED AS IDENTITY` |
| Identifier quotes | `` `name` `` | `"name"` |
| Upsert | `INSERT … ON DUPLICATE KEY UPDATE` | `INSERT … ON CONFLICT … DO UPDATE` |
| Boolean | `TINYINT(1)` | `BOOLEAN` |
| String concat | `CONCAT(a, b)` | `a || b` (also `CONCAT`) |
| Limit | `LIMIT 10 OFFSET 20` / `LIMIT 20, 10` | `LIMIT 10 OFFSET 20` |
| JSON | `JSON` type | `JSON` and indexed **`JSONB`** |
| Default isolation | **REPEATABLE READ** | READ COMMITTED |

### Features where PostgreSQL is stronger (relevant to CareFlow)
| Need in CareFlow | PostgreSQL | MySQL |
|---|---|---|
| "One **active** booking per slot" | **Partial unique index** `WHERE status IN (...)` | No partial indexes — workaround: a generated column that is NULL for inactive rows + unique index (NULLs don't collide) |
| Vector search for RAG | **pgvector** (HNSW) | MySQL 9 adds a `VECTOR` type; HeatWave offers vector search; otherwise a separate vector DB |
| Read-only analytics role on views | Roles, schemas, `SET LOCAL ROLE`, `SET TRANSACTION READ ONLY` | Users/roles and views exist; `SET TRANSACTION READ ONLY` exists; no `SET LOCAL` equivalent per transaction |
| Savepoints for the agent's preview | Yes | Yes (InnoDB) |
| `SELECT … FOR UPDATE SKIP LOCKED` | Yes | Yes (8.0+) |
| Full-text search in Hindi/Marathi | `tsvector` + GIN (`simple` config) | FULLTEXT indexes (ngram parser for CJK) |
| CHECK constraints | Yes | Enforced since 8.0.16 |

### Things to know for interviews
- Replication: primary → replicas (binlog), read scaling.
- `EXPLAIN` for query plans.
- Index types: B-tree, FULLTEXT, spatial; composite index leftmost-prefix rule.
- Normalisation, joins, GROUP BY, window functions (MySQL 8+), CTEs (MySQL 8+).
- Python drivers: `mysqlclient`, `PyMySQL`, `mysql-connector-python`; SQLAlchemy URL `mysql+pymysql://user:pw@host/db`.

### How CareFlow would change on MySQL
- SQLAlchemy models mostly unchanged; `Vector` column and HNSW index removed (vectors in another store).
- Replace partial unique indexes with generated-column unique indexes.
- Replace the `tsvector` column with a FULLTEXT index or keep BM25 in Python (already the case).
- Alembic migrations would need MySQL-specific DDL (no `CREATE EXTENSION`, different role syntax).

---

## Interview questions

**Q: InnoDB vs MyISAM?**
InnoDB: transactions, row-level locks, foreign keys, crash recovery. MyISAM: none of these, table locks — legacy.

**Q: Why did you choose PostgreSQL over MySQL?**
Partial unique indexes for the booking rule, pgvector for embeddings in the same database, richer roles/views for safe analytics, and JSONB. MySQL would work with workarounds.

**Q: How would you implement "one active booking per slot" in MySQL?**
Add a generated column `active_slot_id = IF(status IN ('booked','rescheduled'), slot_id, NULL)` with a UNIQUE index — NULLs are allowed to repeat, so only active rows collide.

**Q: What's MySQL's default isolation level?**
REPEATABLE READ (PostgreSQL's is READ COMMITTED).
