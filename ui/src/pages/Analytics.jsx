import { Code2, Download, Lightbulb, MessageSquareText, Search, Sparkles } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import { useSession } from "../session";

function csvCell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(columns, rows) {
  return [columns, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
}

/** S9: natural-language analytics with the generated SQL shown and CSV export (FR-30, FR-31). */
export default function Analytics() {
  const { t } = useSession();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run(text) {
    const q = text.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await api("/admin/analytics", { method: "POST", body: { question: q } }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function ask(e) {
    e.preventDefault();
    void run(question);
  }

  function suggest(key) {
    setQuestion(t(key));
    void run(t(key));
  }

  function download() {
    if (!answer) return;
    const blob = new Blob([toCsv(answer.columns, answer.rows)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "careflow-analytics.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("analyticsTitle")}</h1>
          <p className="lead">{t("analyticsIntro")}</p>
        </div>
      </div>
      <section className="card">
        <form className="ask-form" onSubmit={ask}>
          <div className="input-wrap">
            <Search size={18} aria-hidden="true" />
            <label htmlFor="question" className="sr-only">
              {t("analyticsTitle")}
            </label>
            <input
              id="question"
              value={question}
              maxLength={1000}
              placeholder={t("analyticsPlaceholder")}
              onChange={(e) => setQuestion(e.target.value)}
            />
          </div>
          <button type="submit" disabled={busy || !question.trim()}>
            <Sparkles size={18} aria-hidden="true" />
            {busy ? t("working") : t("ask")}
          </button>
        </form>
        <div className="row" style={{ marginTop: "0.875rem" }}>
          <span className="muted small" style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
            <Lightbulb size={15} aria-hidden="true" />
            {t("tryAsking")}
          </span>
          {["analyticsSuggest1", "analyticsSuggest2", "analyticsSuggest3"].map((key) => (
            <button key={key} type="button" className="chip" disabled={busy} onClick={() => suggest(key)}>
              {t(key)}
            </button>
          ))}
        </div>
      </section>
      {error !== null && <ErrorMessage error={error} />}
      {answer && (
        <section className="card" style={{ marginTop: "1rem" }} aria-labelledby="answer-h">
          <div className="card-head">
            <h2 id="answer-h">
              <MessageSquareText size={20} aria-hidden="true" />
              {t("answer")}
            </h2>
            {answer.columns.length > 0 && (
              <button type="button" className="secondary" onClick={download}>
                <Download size={16} aria-hidden="true" />
                {t("exportCsv")}
              </button>
            )}
          </div>
          <p style={{ marginBottom: "1rem" }}>{answer.answer}</p>
          {answer.columns.length > 0 && (
            <>
              <p className="muted small" style={{ marginBottom: "0.5rem" }}>
                {t("rows", { count: answer.row_count })}{" "}
                {answer.truncated ? t("truncated", { count: answer.row_count }) : ""}
              </p>
              <div
                className="table-wrap card"
                tabIndex={0}
                role="region"
                aria-labelledby="answer-h"
                style={{ padding: 0, boxShadow: "none" }}
              >
                <table>
                  <thead>
                    <tr>
                      {answer.columns.map((c) => (
                        <th key={c} scope="col">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {answer.rows.slice(0, 100).map((row, i) => (
                      <tr key={i}>
                        {row.map((cell, j) => (
                          <td key={j}>{cell === null ? "—" : String(cell)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {answer.sql && (
            <details open style={{ marginTop: "1rem" }}>
              <summary>
                <Code2 size={16} aria-hidden="true" />
                {t("generatedSql")}
              </summary>
              <pre className="sql">
                <code>{answer.sql}</code>
              </pre>
            </details>
          )}
        </section>
      )}
    </main>
  );
}
