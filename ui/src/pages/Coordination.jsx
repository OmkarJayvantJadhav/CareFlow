import { ArrowRight, ArrowRightLeft, Clock, Network, RefreshCw, Scale } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { clockTime } from "../format";
import { useSession } from "../session";

const STATE_TONE = {
  available: "ok",
  not_started: "",
  on_break: "warn",
  delayed: "warn",
  unavailable: "danger",
  on_leave: "danger",
  closed: "",
};
const REFRESH_MS = 30000;

/** Multi-doctor coordination and workload balancing (features 44, 54). Staff confirm every move. */
export default function Coordination() {
  const { user, t } = useSession();
  const [board, setBoard] = useState(null);
  const [department, setDepartment] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const canMove = user.role === "staff";

  const load = useCallback(async () => {
    try {
      setBoard(await api("/queue/coordination"));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  async function move(s) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const moved = await api(`/queue/entries/${s.entry_id}/transfer`, {
        method: "POST",
        body: { doctor_id: s.to_doctor_id, reason: "workload balancing" },
      });
      setNotice(t("movedNotice", { token: s.token, doctor: s.to_doctor, newToken: moved.token }));
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const departments = board?.departments.filter((d) => d.doctors.length > 0) ?? [];
  const shown = department ? departments.filter((d) => String(d.department_id) === department) : departments;
  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("coordinationTitle")}</h1>
          <p className="lead">{t("coordinationIntro")}</p>
        </div>
        <button type="button" className="secondary" onClick={() => void load()}>
          <RefreshCw size={16} aria-hidden="true" />
          {t("refresh")}
        </button>
      </div>
      {notice && (
        <div className="notice" role="status">
          {notice}
        </div>
      )}
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {board === null && error === null && <Loading />}
      {board && (
        <div className="card desk-toolbar">
          <div className="field">
            <label htmlFor="co-dept">{t("department")}</label>
            <select id="co-dept" value={department} onChange={(e) => setDepartment(e.target.value)}>
              <option value="">{t("allDepartments")}</option>
              {departments.map((d) => (
                <option key={d.department_id} value={d.department_id}>
                  {d.department}
                </option>
              ))}
            </select>
          </div>
          <p className="muted small">{t("updatedAt", { time: clockTime(board.at) })}</p>
        </div>
      )}
      {board && departments.length === 0 && <p className="muted">{t("noOpdToday")}</p>}
      <div className="stack">
        {shown.map((dept) => (
          <section key={dept.department_id} className="card" aria-labelledby={`dept-${dept.department_id}`}>
            <div className="card-head">
              <h2 id={`dept-${dept.department_id}`}>
                <Network size={20} aria-hidden="true" />
                {dept.department}
              </h2>
              <span className="muted small">
                <Clock size={13} aria-hidden="true" /> OPD {dept.opd_start}–{dept.opd_end}
              </span>
            </div>
            <div className="table-wrap" tabIndex={0} role="region" aria-labelledby={`dept-${dept.department_id}`}>
              <table>
                <thead>
                  <tr>
                    <th>{t("doctorLabel")}</th>
                    <th>{t("doctorStatus")}</th>
                    <th className="num">{t("waitingNow")}</th>
                    <th>{t("inRoom")}</th>
                    <th className="num">{t("consultMin")}</th>
                    <th>{t("predictedFinish")}</th>
                  </tr>
                </thead>
                <tbody>
                  {dept.doctors.map((d) => (
                    <tr key={d.doctor_id}>
                      <td>
                        <strong>{d.doctor_name}</strong>
                        <div className="muted small">
                          {t("seen")}: {d.seen}
                          {d.left_unseen > 0 ? ` · ${t("leftUnseen")}: ${d.left_unseen}` : ""}
                        </div>
                      </td>
                      <td>
                        <span className={`badge ${STATE_TONE[d.state] ?? ""}`}>
                          {t(`state_${d.state}`, { minutes: d.delay_minutes })}
                        </span>
                      </td>
                      <td className="num">
                        <span className="load-bar" aria-hidden="true">
                          <i style={{ width: `${Math.min(100, d.waiting * 8)}%` }} />
                        </span>
                        {d.waiting}
                        {d.remote_not_arrived > 0 && (
                          <div className="muted small">{t("onlineCount", { count: d.remote_not_arrived })}</div>
                        )}
                      </td>
                      <td>{d.in_room ? <span className="token-pill">{d.in_room}</span> : "—"}</td>
                      <td className="num">{d.consult_minutes}</td>
                      <td>
                        {d.predicted_finish ? clockTime(d.predicted_finish) : "—"}
                        {d.overtime && <span className="badge danger">{t("overtime")}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3 className="sub-head">
              <Scale size={16} aria-hidden="true" />
              {t("balancing")}
            </h3>
            {dept.suggestions.length === 0 && <p className="muted small">{t("balanced")}</p>}
            {dept.suggestions.length > 0 && (
              <ul className="booking-list">
                {dept.suggestions.map((s) => (
                  <li key={s.entry_id}>
                    <span className="booking-who">
                      <span>
                        <span className="token-pill">{s.token}</span> {s.from_doctor}{" "}
                        <ArrowRight size={14} aria-label={t("to")} /> {s.to_doctor}
                      </span>
                      <span className="muted small">
                        {t("savesAbout", { now: s.wait_now_min, after: s.wait_after_min, saves: s.saves_min })}
                      </span>
                    </span>
                    {canMove && (
                      <button
                        type="button"
                        className="secondary"
                        disabled={busy}
                        aria-label={`${t("move")} ${s.token} → ${s.to_doctor}`}
                        onClick={() => void move(s)}
                      >
                        <ArrowRightLeft size={16} aria-hidden="true" />
                        {t("move")}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
    </main>
  );
}
