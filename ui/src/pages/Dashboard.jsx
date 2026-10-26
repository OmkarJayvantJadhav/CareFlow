import {
  Activity,
  BarChart3,
  Bot,
  CalendarCheck,
  CircleCheck,
  Coffee,
  Database,
  DoorOpen,
  Gauge,
  RotateCcw,
  Search,
  ShieldCheck,
  UserCheck,
  UsersRound,
  UserX,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { longDate } from "../format";
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
  const { t, lang } = useSession();
  const [data, setData] = useState(null);
  const [usage, setUsage] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [dashboard, utilization] = await Promise.all([api("/admin/dashboard"), api("/admin/utilization?days=7")]);
      setData(dashboard);
      setUsage(utilization);
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
  const depts = data?.departments ?? [];
  const sum = (key) => depts.reduce((n, d) => n + (d[key] || 0), 0);
  const maxBooked = Math.max(1, ...depts.map((d) => d.booked_today));
  const kpis = [
    { label: "bookedToday", value: sum("booked_today"), icon: CalendarCheck, tone: "" },
    { label: "waitingNow", value: sum("waiting"), icon: UsersRound, tone: "info" },
    { label: "noShows", value: sum("no_shows_today"), icon: UserX, tone: "danger" },
    {
      label: "doctorsAway",
      value: sum("doctors_on_break") + sum("doctors_unavailable"),
      icon: Coffee,
      tone: "warn",
    },
  ];
  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("dashboardTitle")}</h1>
          {data && <p className="lead">{longDate(data.date, lang)}</p>}
        </div>
      </div>
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {notice && (
        <div className="notice" role="status">
          <CircleCheck size={18} aria-hidden="true" />
          {notice}
        </div>
      )}
      {data === null && error === null && <Loading />}
      {data && (
        <>
          <div className="kpis">
            {kpis.map(({ label, value, icon: Icon, tone }) => (
              <div key={label} className="card kpi">
                <span className={`icon-tile ${tone}`} aria-hidden="true">
                  <Icon size={20} />
                </span>
                <div>
                  <div className="value">{value}</div>
                  <div className="label">{t(label)}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="dash-grid">
            <section className="card" aria-labelledby="chart-h">
              <div className="card-head">
                <h2 id="chart-h">
                  <BarChart3 size={20} aria-hidden="true" />
                  {t("chartTitle")}
                </h2>
              </div>
              {/* The same numbers are in the table next to it, so the bars are hidden from screen readers. */}
              <div className="bars" aria-hidden="true">
                {[...depts]
                  .sort((a, b) => b.booked_today - a.booked_today)
                  .map((d) => (
                    <div key={d.department} className="bar-row">
                      <span>{d.department}</span>
                      <span className="bar-track">
                        <span
                          className="bar-fill"
                          style={{ display: "block", width: `${(100 * d.booked_today) / maxBooked}%` }}
                        />
                      </span>
                      <strong className="num">{d.booked_today}</strong>
                    </div>
                  ))}
              </div>
            </section>
            <section className="card" aria-labelledby="dept-h">
              <div className="card-head">
                <h2 id="dept-h">
                  <Activity size={20} aria-hidden="true" />
                  {t("departmentsTitle")}
                </h2>
              </div>
              <div className="table-wrap" tabIndex={0} role="region" aria-labelledby="dept-h">
                <table>
                  <caption className="sr-only">{t("departmentsTitle")}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t("department")}</th>
                      <th scope="col" className="num">
                        {t("waitingNow")}
                      </th>
                      <th scope="col" className="num">
                        {t("avgDelay")}
                      </th>
                      <th scope="col" className="num">
                        {t("onBreak")}
                      </th>
                      <th scope="col" className="num">
                        {t("unavailableDoctors")}
                      </th>
                      <th scope="col" className="num">
                        {t("bookedToday")}
                      </th>
                      <th scope="col" className="num">
                        {t("noShows")}
                      </th>
                      <th scope="col" className="num">
                        {t("leftUnseen")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {depts.map((d) => (
                      <tr key={d.department}>
                        <th scope="row">{d.department}</th>
                        <td className="num">{d.waiting}</td>
                        <td className="num">{d.average_delay_min || "—"}</td>
                        <td className="num">{d.doctors_on_break || "—"}</td>
                        <td className="num">
                          {d.doctors_unavailable ? <span className="badge danger">{d.doctors_unavailable}</span> : "—"}
                        </td>
                        <td className="num">{d.booked_today}</td>
                        <td className="num">{d.no_shows_today}</td>
                        <td className="num">{d.left_unseen_today || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          {usage && (
            <section aria-labelledby="usage-h">
              <div className="section-title">
                <div>
                  <h2 id="usage-h">{t("utilizationTitle")}</h2>
                  <p className="muted small">{t("utilizationNote")}</p>
                </div>
              </div>
              <div className="kpis">
                {[
                  ["utilizationNext7", usage.overall.utilization, Gauge, ""],
                  ["attendance30", usage.overall.attendance_rate, UserCheck, "info"],
                  ["noShowRate30", usage.overall.no_show_rate, UserX, "danger"],
                  ["abandonment30", usage.overall.abandonment_rate, DoorOpen, "warn"],
                ].map(([label, value, Icon, tone]) => (
                  <div key={label} className="card kpi">
                    <span className={`icon-tile ${tone}`} aria-hidden="true">
                      <Icon size={20} />
                    </span>
                    <div>
                      <div className="value">{pct(value)}</div>
                      <div className="label">{t(label)}</div>
                    </div>
                  </div>
                ))}
              </div>
              <section className="card">
                <div className="table-wrap" tabIndex={0} role="region" aria-labelledby="usage-table-h">
                  <table>
                    <caption id="usage-table-h" className="sr-only">
                      {t("utilizationTable")}
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">{t("department")}</th>
                        <th scope="col">{t("utilization")}</th>
                        <th scope="col" className="num">
                          {t("bookedLabel")}
                        </th>
                        <th scope="col" className="num">
                          {t("freeSlots")}
                        </th>
                        <th scope="col" className="num">
                          {t("attended")}
                        </th>
                        <th scope="col" className="num">
                          {t("noShows")}
                        </th>
                        <th scope="col" className="num">
                          {t("leftUnseen")}
                        </th>
                        <th scope="col" className="num">
                          {t("attendance")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {usage.departments.map((d) => (
                        <tr key={d.department}>
                          <th scope="row">{d.department}</th>
                          <td>
                            <div className="meter-cell">
                              <span className="meter" aria-hidden="true">
                                <span style={{ width: `${100 * (d.utilization ?? 0)}%` }} />
                              </span>
                              {pct(d.utilization)}
                            </div>
                          </td>
                          <td className="num">{d.booked}</td>
                          <td className="num">{d.free}</td>
                          <td className="num">{d.attended}</td>
                          <td className="num">{d.no_shows}</td>
                          <td className="num">{d.left_unseen}</td>
                          <td className="num">{pct(d.attendance_rate)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <details style={{ marginTop: "0.75rem" }}>
                  <summary>{t("byDoctor")}</summary>
                  <ul className="booking-list">
                    {usage.doctors.map((d) => (
                      <li key={d.doctor_id}>
                        <span>
                          <strong>{d.doctor_name}</strong> <span className="muted small">{d.department}</span>
                        </span>
                        <span className="muted small">
                          {t("utilization")} {pct(d.utilization)} · {t("attendance")} {pct(d.attendance_rate)} ·{" "}
                          {d.typical_consult_min} min
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              </section>
            </section>
          )}

          <div className="section-title">
            <div>
              <h2>{t("evaluationTitle")}</h2>
              <p className="muted small">{t("evaluationNote")}</p>
            </div>
          </div>
          <div className="grid">
            <section className="card" aria-labelledby="ev-agent">
              <div className="card-head">
                <h3 id="ev-agent">
                  <Bot size={18} aria-hidden="true" />
                  Agent
                </h3>
              </div>
              {agent ? (
                <>
                  <div className="big-number">{pct(agent.pass_1)}</div>
                  <div className="muted small">
                    pass^1 · {agent.runs} runs of {agent.scenarios_run}/{agent.scenarios_total} scenarios
                  </div>
                  <div className="mini-stats" style={{ marginTop: "1rem" }}>
                    <div>
                      <strong>{pct(agent.wrong_action_rate)}</strong>
                      <span className="muted small">Wrong actions</span>
                    </div>
                    <div>
                      <strong>{agent.median_turn_latency_s ?? "—"} s</strong>
                      <span className="muted small">Median turn</span>
                    </div>
                    <div>
                      <strong>${agent.mean_cost_per_conversation_usd?.toFixed(5) ?? "—"}</strong>
                      <span className="muted small">Per conversation</span>
                    </div>
                  </div>
                </>
              ) : (
                <p className="muted">not run</p>
              )}
            </section>
            <section className="card" aria-labelledby="ev-safety">
              <div className="card-head">
                <h3 id="ev-safety">
                  <ShieldCheck size={18} aria-hidden="true" />
                  Safety
                </h3>
              </div>
              {Object.entries(SAFETY_LABELS).map(([key, label]) => {
                const r = ev?.safety?.[key];
                return (
                  <div key={key} className="metric">
                    <div className="top">
                      <span>{r ? `${label}: ${r.passed}/${r.run}` : `${label}: not run`}</span>
                      <strong>{r ? pct(r.pass_rate) : "—"}</strong>
                    </div>
                    {r && (
                      <div className="meter" aria-hidden="true">
                        <span style={{ width: `${100 * r.pass_rate}%` }} />
                      </div>
                    )}
                  </div>
                );
              })}
            </section>
            <section className="card" aria-labelledby="ev-rag">
              <div className="card-head">
                <h3 id="ev-rag">
                  <Search size={18} aria-hidden="true" />
                  Retrieval and wait time
                </h3>
              </div>
              <div className="metric">
                <div className="top">
                  <span>Recall@5 (cross-validated)</span>
                  <strong>{pct(ev?.rag?.recall_at_5)}</strong>
                </div>
                {ev?.rag?.recall_at_5 != null && (
                  <div className="meter" aria-hidden="true">
                    <span style={{ width: `${100 * ev.rag.recall_at_5}%` }} />
                  </div>
                )}
              </div>
              <div className="metric">
                <div className="top">
                  <span>Faithfulness</span>
                  <strong>
                    {ev?.rag?.answers?.faithfulness != null
                      ? `${pct(ev.rag.answers.faithfulness)} (${ev.rag.answers.graded} answers)`
                      : "not run"}
                  </strong>
                </div>
              </div>
              <div className="metric">
                <div className="top">
                  <span>Wait-time MAE (model vs baseline)</span>
                  <strong>
                    {ev?.wait_time?.model_mae ?? "—"} vs {ev?.wait_time?.baseline_mae ?? "—"} min
                  </strong>
                </div>
              </div>
              <div className="metric">
                <div className="top">
                  <span>Range coverage</span>
                  <strong>{pct(ev?.wait_time?.range_coverage)}</strong>
                </div>
              </div>
            </section>
          </div>

          <div className="ops-grid">
            <section className="card" aria-labelledby="ops-h">
              <div className="card-head">
                <h2 id="ops-h">
                  <Activity size={20} aria-hidden="true" />
                  {t("operationsTitle")}
                </h2>
              </div>
              <div className="mini-stats">
                <div>
                  <strong>{data.operations.turns}</strong>
                  <span className="muted small">turns</span>
                </div>
                <div>
                  <strong>{data.operations.median_latency_s ?? "—"} s</strong>
                  <span className="muted small">median latency</span>
                </div>
                <div>
                  <strong>{data.operations.llm_calls}</strong>
                  <span className="muted small">LLM calls</span>
                </div>
                <div>
                  <strong>{data.operations.llm_errors}</strong>
                  <span className="muted small">errors</span>
                </div>
                <div>
                  <strong>${data.operations.cost_usd.toFixed(5)}</strong>
                  <span className="muted small">cost</span>
                </div>
              </div>
            </section>
            <section className="card" aria-labelledby="reset-h">
              <div className="card-head">
                <h2 id="reset-h">
                  <Database size={20} aria-hidden="true" />
                  {t("resetTitle")}
                </h2>
              </div>
              <p className="muted" style={{ marginBottom: "1rem" }}>
                {t("resetConfirm")}
              </p>
              <button type="button" className="danger-outline" disabled={busy} onClick={reset}>
                <RotateCcw size={16} aria-hidden="true" />
                {t("resetButton")}
              </button>
            </section>
          </div>
        </>
      )}
    </main>
  );
}
