import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import { LANGS } from "../i18n";
import { useSession } from "../session";
import { followSession } from "../staff";

const MAX_PRIORITY = 3;

/** S6: today's doctors, check-in, walk-ins and the live queue (staff). */
export default function FrontDesk() {
  const { t } = useSession();
  const [doctors, setDoctors] = useState(null);
  const [selected, setSelected] = useState(null);
  const [entries, setEntries] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [walkIn, setWalkIn] = useState({ name: "", birth_year: "", phone: "", language: "en" });

  const doctor = doctors?.find((d) => d.doctor_id === selected) ?? null;

  const load = useCallback(async () => {
    try {
      const today = await api("/staff/today");
      setDoctors(today.doctors);
      setSelected((current) => current ?? today.doctors[0]?.doctor_id ?? null);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);

  const loadQueue = useCallback(async (sessionId) => {
    if (sessionId === null) {
      setEntries([]);
      return;
    }
    try {
      setEntries((await api(`/queue/sessions/${sessionId}`)).entries);
    } catch (err) {
      setError(err);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const sessionId = doctor?.session_id ?? null;
  useEffect(() => {
    void loadQueue(sessionId);
    if (sessionId === null) return;
    return followSession(sessionId, () => {
      void loadQueue(sessionId);
      void load();
    });
  }, [sessionId, loadQueue, load]);

  async function act(path, method = "POST", body) {
    setBusy(true);
    setError(null);
    try {
      await api(path, { method, body });
      await load();
      await loadQueue(sessionId);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function registerWalkIn(e) {
    e.preventDefault();
    if (!doctor || !walkIn.name.trim()) return;
    await act("/queue/walk-ins", "POST", {
      doctor_id: doctor.doctor_id,
      name: walkIn.name.trim(),
      birth_year: walkIn.birth_year ? Number(walkIn.birth_year) : null,
      phone: walkIn.phone || null,
      language: walkIn.language,
    });
    setWalkIn({ name: "", birth_year: "", phone: "", language: walkIn.language });
  }

  const visible = entries.filter((e) => ["waiting", "called", "in_consultation", "missed"].includes(e.status));
  return (
    <main>
      <h1>{t("deskTitle")}</h1>
      <p className="lead">{t("deskIntro")}</p>
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {doctors === null && error === null && <p className="muted">{t("loading")}</p>}
      {doctors && (
        <div className="field" style={{ maxWidth: 480 }}>
          <label htmlFor="doctor">{t("doctorLabel")}</label>
          <select id="doctor" value={selected ?? ""} onChange={(e) => setSelected(Number(e.target.value))}>
            {doctors.map((d) => (
              <option key={d.doctor_id} value={d.doctor_id}>
                {d.doctor_name} — {d.department}
              </option>
            ))}
          </select>
        </div>
      )}
      {doctor && (
        <div className="grid">
          <section className="card" aria-labelledby="queue-h">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <h2 id="queue-h" style={{ margin: 0 }}>
                {t("queue")}
              </h2>
              {sessionId !== null && (
                <button type="button" disabled={busy} onClick={() => act(`/queue/sessions/${sessionId}/call-next`)}>
                  {t("callNext")}
                </button>
              )}
            </div>
            {visible.length === 0 && <p className="muted">{t("noQueue")}</p>}
            {visible.length > 0 && (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>{t("token")}</th>
                      <th>{t("patientLabel")}</th>
                      <th>{t("estimatedWait")}</th>
                      <th>
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((e) => (
                      <tr key={e.entry_id}>
                        <td>
                          <strong>{e.token}</strong>
                          {e.priority > 0 && (
                            <div className="pill warn">
                              ★ {t("priority")} {e.priority}
                            </div>
                          )}
                        </td>
                        <td>
                          {e.patient_name}
                          <div className="muted">{t(`entry_${e.status}`)}</div>
                        </td>
                        <td>{e.estimate?.display ?? "—"}</td>
                        <td>
                          <div className="row">
                            {e.status === "called" && (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => act(`/queue/entries/${e.entry_id}/start`)}
                              >
                                {t("start")}
                              </button>
                            )}
                            {e.status === "in_consultation" && (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => act(`/queue/entries/${e.entry_id}/end`)}
                              >
                                {t("end")}
                              </button>
                            )}
                            {e.status === "called" && (
                              <button
                                type="button"
                                className="quiet"
                                disabled={busy}
                                onClick={() => act(`/queue/entries/${e.entry_id}/missed`)}
                              >
                                {t("missed")}
                              </button>
                            )}
                            {e.status === "missed" && (
                              <button
                                type="button"
                                className="secondary"
                                disabled={busy}
                                onClick={() => act(`/queue/entries/${e.entry_id}/return`)}
                              >
                                {t("returned")}
                              </button>
                            )}
                            {e.status === "waiting" && e.priority < MAX_PRIORITY && (
                              <button
                                type="button"
                                className="quiet"
                                disabled={busy}
                                aria-label={`${t("priorityUp")}: ${e.token}`}
                                onClick={() =>
                                  act(`/queue/entries/${e.entry_id}/priority`, "PATCH", { priority: e.priority + 1 })
                                }
                              >
                                ★+
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          <section className="card" aria-labelledby="bookings-h">
            <h2 id="bookings-h" style={{ marginTop: 0 }}>
              {t("bookings")}
            </h2>
            {doctor.bookings.length === 0 && <p className="muted">{t("none")}</p>}
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {doctor.bookings.map((b) => (
                <li
                  key={b.appointment_id}
                  className="row"
                  style={{ justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)" }}
                >
                  <span>
                    <strong>{b.time}</strong> {b.patient_name}
                    {b.status !== "booked" && <span className="muted"> · {t(`status_${b.status}`)}</span>}
                  </span>
                  {b.entry_id ? (
                    <span className="pill ok">
                      ✓ {t("checkedIn")} {b.token}
                    </span>
                  ) : b.status === "booked" ? (
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy}
                      onClick={() => act(`/queue/entries/${b.appointment_id}/check-in`)}
                    >
                      {t("checkIn")}
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
          <section className="card" aria-labelledby="walkin-h">
            <h2 id="walkin-h" style={{ marginTop: 0 }}>
              {t("walkIn")}
            </h2>
            <form onSubmit={registerWalkIn}>
              <div className="field">
                <label htmlFor="wi-name">{t("walkInName")}</label>
                <input
                  id="wi-name"
                  required
                  maxLength={120}
                  value={walkIn.name}
                  onChange={(e) => setWalkIn({ ...walkIn, name: e.target.value })}
                />
              </div>
              <div className="row">
                <div className="field" style={{ flex: "1 1 120px" }}>
                  <label htmlFor="wi-year">{t("walkInYear")}</label>
                  <input
                    id="wi-year"
                    required
                    inputMode="numeric"
                    pattern="(19|20)[0-9]{2}"
                    value={walkIn.birth_year}
                    onChange={(e) => setWalkIn({ ...walkIn, birth_year: e.target.value })}
                  />
                </div>
                <div className="field" style={{ flex: "1 1 160px" }}>
                  <label htmlFor="wi-phone">{t("walkInPhone")}</label>
                  <input
                    id="wi-phone"
                    required
                    inputMode="tel"
                    pattern="[6-9][0-9]{9}"
                    value={walkIn.phone}
                    onChange={(e) => setWalkIn({ ...walkIn, phone: e.target.value })}
                  />
                </div>
                <div className="field" style={{ flex: "1 1 120px" }}>
                  <label htmlFor="wi-lang">{t("walkInLanguage")}</label>
                  <select
                    id="wi-lang"
                    value={walkIn.language}
                    onChange={(e) => setWalkIn({ ...walkIn, language: e.target.value })}
                  >
                    {LANGS.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <button type="submit" disabled={busy}>
                {t("register")}
              </button>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
