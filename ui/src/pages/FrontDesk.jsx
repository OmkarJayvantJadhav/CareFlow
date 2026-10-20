import {
  CalendarClock,
  Check,
  CircleCheck,
  ListOrdered,
  Megaphone,
  Play,
  Star,
  Undo2,
  UserPlus,
  UserX,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { LANGS } from "../i18n";
import { useSession } from "../session";
import { followSession } from "../staff";

const MAX_PRIORITY = 3;
const ENTRY_TONE = { waiting: "", called: "ok", in_consultation: "brand", missed: "danger" };
const DOCTOR_TONE = { available: "ok", on_break: "warn", delayed: "warn", unavailable: "danger" };

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
  const checkedIn = doctor?.bookings.filter((b) => b.entry_id).length ?? 0;
  const waiting = entries.filter((e) => e.status === "waiting").length;
  const seen = entries.filter((e) => e.status === "done").length;
  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("deskTitle")}</h1>
          <p className="lead">{t("deskIntro")}</p>
        </div>
      </div>
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {doctors === null && error === null && <Loading />}
      {doctors && (
        <div className="card desk-toolbar">
          <div className="field">
            <label htmlFor="doctor">{t("doctorLabel")}</label>
            <select id="doctor" value={selected ?? ""} onChange={(e) => setSelected(Number(e.target.value))}>
              {doctors.map((d) => (
                <option key={d.doctor_id} value={d.doctor_id}>
                  {d.doctor_name} — {d.department}
                </option>
              ))}
            </select>
          </div>
          {doctor && (
            <div className="desk-stats">
              <span className={`badge ${DOCTOR_TONE[doctor.doctor_status] ?? ""}`}>
                <span className="dot" aria-hidden="true" />
                {t(`doctor_${doctor.doctor_status}`, { minutes: doctor.delay_minutes })}
              </span>
              <span className="badge">
                {t("bookedToday")}: {doctor.bookings.length}
              </span>
              <span className="badge">
                {t("checkedIn")}: {checkedIn}
              </span>
              <span className="badge">
                {t("waitingNow")}: {waiting}
              </span>
              <span className="badge">
                {t("seen")}: {seen}
              </span>
            </div>
          )}
        </div>
      )}
      {doctor && (
        <div className="desk-grid">
          <section className="card" aria-labelledby="queue-h">
            <div className="card-head">
              <h2 id="queue-h">
                <ListOrdered size={20} aria-hidden="true" />
                {t("queue")}
              </h2>
              {sessionId !== null && (
                <button type="button" disabled={busy} onClick={() => act(`/queue/sessions/${sessionId}/call-next`)}>
                  <Megaphone size={18} aria-hidden="true" />
                  {t("callNext")}
                </button>
              )}
            </div>
            {visible.length === 0 && (
              <div className="empty">
                <span className="icon-tile" aria-hidden="true">
                  <ListOrdered size={22} />
                </span>
                <span>{t("noQueue")}</span>
              </div>
            )}
            {visible.length > 0 && (
              <div className="table-wrap" tabIndex={0} role="region" aria-labelledby="queue-h">
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
                          <span className="token-pill">{e.token}</span>
                          {e.priority > 0 && (
                            <div className="badge warn" style={{ marginTop: "0.25rem" }}>
                              <Star size={12} aria-hidden="true" /> {t("priority")} {e.priority}
                            </div>
                          )}
                        </td>
                        <td>
                          <div>{e.patient_name}</div>
                          <span className={`badge ${ENTRY_TONE[e.status] ?? ""}`}>{t(`entry_${e.status}`)}</span>
                        </td>
                        <td>{e.estimate?.display ?? "—"}</td>
                        <td>
                          <div className="row" style={{ justifyContent: "flex-end" }}>
                            {e.status === "called" && (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => act(`/queue/entries/${e.entry_id}/start`)}
                              >
                                <Play size={16} aria-hidden="true" />
                                {t("start")}
                              </button>
                            )}
                            {e.status === "in_consultation" && (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => act(`/queue/entries/${e.entry_id}/end`)}
                              >
                                <CircleCheck size={16} aria-hidden="true" />
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
                                <UserX size={16} aria-hidden="true" />
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
                                <Undo2 size={16} aria-hidden="true" />
                                {t("returned")}
                              </button>
                            )}
                            {e.status === "waiting" && e.priority < MAX_PRIORITY && (
                              <button
                                type="button"
                                className="quiet"
                                disabled={busy}
                                aria-label={`${t("priorityUp")}: ${e.token}`}
                                title={t("priorityUp")}
                                onClick={() =>
                                  act(`/queue/entries/${e.entry_id}/priority`, "PATCH", { priority: e.priority + 1 })
                                }
                              >
                                <Star size={16} aria-hidden="true" />+
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
          <div className="desk-side">
            <section className="card" aria-labelledby="bookings-h">
              <div className="card-head">
                <h2 id="bookings-h">
                  <CalendarClock size={20} aria-hidden="true" />
                  {t("bookings")}
                </h2>
              </div>
              {doctor.bookings.length === 0 && <p className="muted">{t("none")}</p>}
              <ul className="booking-list">
                {doctor.bookings.map((b) => (
                  <li key={b.appointment_id}>
                    <span>
                      <span className="time">{b.time}</span>
                      {b.patient_name}
                      {b.status !== "booked" && <span className="muted"> · {t(`status_${b.status}`)}</span>}
                    </span>
                    {b.entry_id ? (
                      <span className="badge ok">
                        <Check size={13} aria-hidden="true" />
                        {t("checkedIn")} {b.token}
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
              <div className="card-head">
                <h2 id="walkin-h">
                  <UserPlus size={20} aria-hidden="true" />
                  {t("walkIn")}
                </h2>
              </div>
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
                <div className="row" style={{ alignItems: "flex-end" }}>
                  <div className="field" style={{ flex: "1 1 7rem" }}>
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
                  <div className="field" style={{ flex: "1 1 10rem" }}>
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
                </div>
                <div className="field">
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
                <button type="submit" disabled={busy} style={{ width: "100%" }}>
                  <UserPlus size={18} aria-hidden="true" />
                  {t("register")}
                </button>
              </form>
            </section>
          </div>
        </div>
      )}
    </main>
  );
}
