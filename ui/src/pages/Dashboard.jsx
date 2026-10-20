import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import { useSession } from "../session";

const pct = (x) => (x === null || x === undefined ? "—" : `${(100 * x).toFixed(1)}%`);
const SAFETY_LABELS = {
  emergency_holdout2: "Emergency redirect (held-out)",
  medical_advice: "Medical-advice bait",
  permission: "Permission attacks",
  injection: "Prompt injection",
  analytics: "Unsafe analytics",
};

/** S8: queues by department, delays, no-shows, latest evaluation results, latency and cost; demo reset. */
export default function Dashboard() {
  const { t } = useSession();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api("/admin/dashboard"));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
    const timer = window.setInterval(load, 15000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function reset() {
    if (!window.confirm(t("resetConfirm"))) return;
    setBusy(true);
    setNotice(null);
    try {
      await api("/admin/reset", { method: "POST" });
      setNotice(t("resetDone"));
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const ev = data?.evaluation;
  const agent = ev?.agent;
  return (
    <main>
      <h1>{t("dashboardTitle")}</h1>
      {data && <p className="lead">{data.date}</p>}
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {notice && (
        <div className="notice" role="status">
          {notice}
        </div>
      )}
      {data === null && error === null && <p className="muted">{t("loading")}</p>}
      {data && (
        <>
          <div className="table-wrap card">
            <table>
              <caption className="sr-only">{t("dashboardTitle")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("department")}</th>
                  <th scope="col">{t("waitingNow")}</th>
                  <th scope="col">{t("avgDelay")}</th>
                  <th scope="col">{t("onBreak")}</th>
                  <th scope="col">{t("unavailableDoctors")}</th>
                  <th scope="col">{t("bookedToday")}</th>
                  <th scope="col">{t("noShows")}</th>
                </tr>
              </thead>
              <tbody>
                {data.departments.map((d) => (
                  <tr key={d.department}>
                    <th scope="row">{d.department}</th>
                    <td>{d.waiting}</td>
                    <td>{d.average_delay_min || "—"}</td>
                    <td>{d.doctors_on_break || "—"}</td>
                    <td>{d.doctors_unavailable ? `⚠ ${d.doctors_unavailable}` : "—"}</td>
                    <td>{d.booked_today}</td>
                    <td>{d.no_shows_today}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2>{t("evaluationTitle")}</h2>
          <p className="muted">{t("evaluationNote")}</p>
          <div className="grid">
            <section className="card">
              <h3 style={{ marginTop: 0 }}>Agent</h3>
              {agent ? (
                <>
                  <div className="stat">{pct(agent.pass_1)}</div>
                  <div className="muted">
                    pass^1 · {agent.runs} runs of {agent.scenarios_run}/{agent.scenarios_total} scenarios
                  </div>
                  <p>
                    Wrong actions {pct(agent.wrong_action_rate)} · median {agent.median_turn_latency_s ?? "—"} s · $
                    {agent.mean_cost_per_conversation_usd?.toFixed(5) ?? "—"} per conversation
                  </p>
                </>
              ) : (
                <p className="muted">not run</p>
              )}
            </section>
            <section className="card">
              <h3 style={{ marginTop: 0 }}>Safety</h3>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {Object.entries(SAFETY_LABELS).map(([key, label]) => {
                  const s = ev?.safety?.[key];
                  return (
                    <li key={key}>
                      {label}: {s ? `${s.passed}/${s.run} (${pct(s.pass_rate)})` : "not run"}
                    </li>
                  );
                })}
              </ul>
            </section>
            <section className="card">
              <h3 style={{ marginTop: 0 }}>Retrieval and wait time</h3>
              <p style={{ margin: 0 }}>Recall@5 {pct(ev?.rag?.recall_at_5)} (cross-validated)</p>
              <p style={{ margin: 0 }}>
                Faithfulness{" "}
                {ev?.rag?.answers?.faithfulness != null
                  ? `${pct(ev.rag.answers.faithfulness)} (${ev.rag.answers.graded} answers)`
                  : "not run"}
              </p>
              <p style={{ margin: 0 }}>
                Wait-time MAE {ev?.wait_time?.model_mae ?? "—"} min vs {ev?.wait_time?.baseline_mae ?? "—"} min baseline
                · coverage {pct(ev?.wait_time?.range_coverage)}
              </p>
            </section>
          </div>

          <h2>{t("operationsTitle")}</h2>
          <div className="card">
            {data.operations.turns} turns · median {data.operations.median_latency_s ?? "—"} s ·{" "}
            {data.operations.llm_calls} LLM calls, {data.operations.llm_errors} errors · $
            {data.operations.cost_usd.toFixed(5)}
          </div>

          <h2>{t("resetTitle")}</h2>
          <button type="button" className="quiet" disabled={busy} onClick={reset}>
            {t("resetButton")}
          </button>
        </>
      )}
    </main>
  );
}
