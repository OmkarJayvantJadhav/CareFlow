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

  async function ask(e) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await api("/admin/analytics", { method: "POST", body: { question: question.trim() } }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
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
      <h1>{t("analyticsTitle")}</h1>
      <p className="lead">{t("analyticsIntro")}</p>
      <form className="row" onSubmit={ask}>
        <label htmlFor="question" className="sr-only">
          {t("analyticsTitle")}
        </label>
        <input
          id="question"
          style={{ flex: "1 1 320px" }}
          value={question}
          maxLength={1000}
          placeholder={t("analyticsPlaceholder")}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button type="submit" disabled={busy || !question.trim()}>
          {busy ? t("working") : t("ask")}
        </button>
      </form>
      {error !== null && <ErrorMessage error={error} />}
      {answer && (
        <section className="card" style={{ marginTop: 16 }}>
          <p style={{ marginTop: 0 }}>{answer.answer}</p>
          {answer.sql && (
            <details open>
              <summary>{t("generatedSql")}</summary>
              <pre style={{ whiteSpace: "pre-wrap", background: "var(--surface)", padding: 10, borderRadius: 8 }}>
                <code>{answer.sql}</code>
              </pre>
            </details>
          )}
          {answer.columns.length > 0 && (
            <>
              <div className="row" style={{ justifyContent: "space-between", margin: "8px 0" }}>
                <span className="muted">
                  {t("rows", { count: answer.row_count })}{" "}
                  {answer.truncated ? t("truncated", { count: answer.row_count }) : ""}
                </span>
                <button type="button" className="secondary" onClick={download}>
                  {t("exportCsv")}
                </button>
              </div>
              <div className="table-wrap">
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
        </section>
      )}
    </main>
  );
}
