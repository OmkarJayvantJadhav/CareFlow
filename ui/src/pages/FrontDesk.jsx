import {
  ArrowRightLeft,
  CalendarClock,
  Check,
  Clock,
  CircleCheck,
  DoorOpen,
  Footprints,
  ListOrdered,
  Megaphone,
  Play,
  Star,
  Undo2,
  UserPlus,
  UserRoundCheck,
  UserX,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import CodeCheckIn from "../components/CodeCheckIn";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { EntryBadges } from "../components/QueueBadges";
import { CategoryBadges, CustomFields, useRegistrationFields } from "../components/Registration";
import { byDepartment } from "../format";
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
  const [answers, setAnswers] = useState({});
  const [matches, setMatches] = useState(null);
  const [editing, setEditing] = useState(null);
  // Dialogs: ask the doctor for a priority change (feature 52), move a patient (42, 53), left unseen (47).
  const [asking, setAsking] = useState(null);
  const [moving, setMoving] = useState(null);
  const [leaving, setLeaving] = useState(null);
  const fields = useRegistrationFields();

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
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function askDoctor() {
    const done = await act(`/queue/entries/${asking.entry.entry_id}/priority-requests`, "POST", {
      priority: Number(asking.priority),
      reason: asking.reason.trim(),
    });
    if (done) setAsking(null);
  }

  async function moveEntry() {
    const done = await act(`/queue/entries/${moving.entry.entry_id}/transfer`, "POST", {
      doctor_id: Number(moving.doctor_id),
      reason: moving.reason.trim() || null,
    });
    if (done) setMoving(null);
  }

  async function markLeft() {
    if (await act(`/queue/entries/${leaving.entry_id}/left`)) setLeaving(null);
  }

  // Duplicate check first (feature 48): staff see likely matches before a new record is created.
  async function registerWalkIn(e) {
    e.preventDefault();
    if (!doctor || !walkIn.name.trim()) return;
    setError(null);
    try {
      const found = await api("/staff/patients/match", {
        method: "POST",
        body: { name: walkIn.name.trim(), birth_year: Number(walkIn.birth_year), phone: walkIn.phone || null },
      });
      if (found.matches.length > 0) setMatches(found.matches);
      else await registerNew();
    } catch (err) {
      setError(err);
    }
  }

  async function registerNew() {
    await act("/queue/walk-ins", "POST", {
      doctor_id: doctor.doctor_id,
      name: walkIn.name.trim(),
      birth_year: Number(walkIn.birth_year),
      phone: walkIn.phone,
      language: walkIn.language,
      answers,
    });
    setMatches(null);
    setWalkIn({ name: "", birth_year: "", phone: "", language: walkIn.language });
    setAnswers({});
  }

  async function reuseRecord(patientId) {
    await act("/queue/walk-ins", "POST", { doctor_id: doctor.doctor_id, patient_id: patientId });
    setMatches(null);
    setWalkIn({ name: "", birth_year: "", phone: "", language: walkIn.language });
    setAnswers({});
  }

  async function saveCategories() {
    await act(`/staff/patients/${editing.patient_id}/categories`, "PATCH", {
      pregnant: editing.pregnant,
      disability: editing.disability,
    });
    setEditing(null);
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
      <CodeCheckIn onDone={() => void load()} />
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
                        </td>
                        <td>
                          <div>{e.patient_name}</div>
                          <div className="row" style={{ gap: "0.25rem" }}>
                            <span className={`badge ${ENTRY_TONE[e.status] ?? ""}`}>{t(`entry_${e.status}`)}</span>
                            <EntryBadges entry={e} />
                            {e.pending_request && (
                              <span className="badge info">
                                {t("requestPending", { priority: e.pending_request.priority })}
                              </span>
                            )}
                            {e.late_minutes ? (
                              <span className="badge warn">{t("lateBy", { minutes: e.late_minutes })}</span>
                            ) : null}
                          </div>
                        </td>
                        <td>{e.estimate?.display ?? "—"}</td>
                        <td>
                          <div className="row queue-actions">
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
                            {e.joined_remotely && !e.arrived_at && (
                              <button
                                type="button"
                                className="secondary"
                                disabled={busy}
                                aria-label={`${t("arrived")}: ${e.token}`}
                                onClick={() => act(`/queue/entries/${e.entry_id}/arrived`)}
                              >
                                <Footprints size={16} aria-hidden="true" />
                                {t("arrived")}
                              </button>
                            )}
                            {e.status === "waiting" && !e.pending_request && (
                              <button
                                type="button"
                                className="quiet"
                                disabled={busy}
                                aria-label={`${t("askPriority")}: ${e.token}`}
                                title={t("askPriority")}
                                onClick={() =>
                                  setAsking({ entry: e, priority: Math.min(e.priority + 1, MAX_PRIORITY), reason: "" })
                                }
                              >
                                <Star size={16} aria-hidden="true" />
                              </button>
                            )}
                            {(e.status === "waiting" || e.status === "missed") && (
                              <button
                                type="button"
                                className="quiet"
                                disabled={busy}
                                aria-label={`${t("move")}: ${e.token}`}
                                title={t("move")}
                                onClick={() => setMoving({ entry: e, doctor_id: "", reason: "" })}
                              >
                                <ArrowRightLeft size={16} aria-hidden="true" />
                              </button>
                            )}
                            {e.status !== "in_consultation" && (
                              <button
                                type="button"
                                className="quiet"
                                disabled={busy}
                                aria-label={`${t("markLeft")}: ${e.token}`}
                                title={t("markLeft")}
                                onClick={() => setLeaving(e)}
                              >
                                <DoorOpen size={16} aria-hidden="true" />
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
                    <span className="booking-who">
                      <span>
                        <span className="time">{b.time}</span>
                        {b.patient_name}
                        {b.status !== "booked" && <span className="muted"> · {t(`status_${b.status}`)}</span>}
                      </span>
                      <span className="row" style={{ gap: "0.25rem" }}>
                        <CategoryBadges categories={b.categories} />
                        {b.late_minutes ? (
                          <span className="badge warn">{t("lateBy", { minutes: b.late_minutes })}</span>
                        ) : null}
                        {b.checked_in_at && (
                          <span className="muted small">
                            <Clock size={12} aria-hidden="true" /> {t("inAt", { time: b.checked_in_at })}
                            {b.checked_out_at ? ` · ${t("outAt", { time: b.checked_out_at })}` : ""}
                          </span>
                        )}
                      </span>
                    </span>
                    <span className="row" style={{ gap: "0.25rem" }}>
                      <button
                        type="button"
                        className="ghost"
                        aria-label={`${t("categoriesFor")} ${b.patient_name}`}
                        title={t("categoriesFor")}
                        onClick={() =>
                          setEditing({
                            patient_id: b.patient_id,
                            name: b.patient_name,
                            pregnant: b.categories.includes("pregnant"),
                            disability: b.categories.includes("disability"),
                          })
                        }
                      >
                        <Users size={16} aria-hidden="true" />
                      </button>
                      {b.entry_id ? (
                        <span className="badge ok">
                          <Check size={13} aria-hidden="true" />
                          {t("checkedIn")} {b.token}
                          {b.seen_by ? ` · ${t("withDoctor", { doctor: b.seen_by })}` : ""}
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
                    </span>
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
                <CustomFields fields={fields} answers={answers} onChange={setAnswers} idPrefix="wi" />
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
              {matches && (
                <section className="matches" aria-labelledby="matches-h" aria-live="polite">
                  <h3 id="matches-h">{t("possibleMatches")}</h3>
                  <p className="muted small">{t("possibleMatchesHint")}</p>
                  <ul className="booking-list">
                    {matches.map((m) => (
                      <li key={m.patient_id}>
                        <span className="booking-who">
                          <strong>{m.name}</strong>
                          <span className="muted small">
                            {m.birth_year} · {m.phone_masked}
                            {m.last_visit ? ` · ${t("lastVisit", { date: m.last_visit })}` : ""}
                          </span>
                          <span className="row" style={{ gap: "0.25rem" }}>
                            {m.reasons.map((r) => (
                              <span key={r} className="badge">
                                {t(`match_${r}`)}
                              </span>
                            ))}
                            {!m.reuse_allowed && <span className="badge danger">{t("reuseWithdrawn")}</span>}
                          </span>
                        </span>
                        <button
                          type="button"
                          className="secondary"
                          disabled={busy || !m.reuse_allowed}
                          onClick={() => void reuseRecord(m.patient_id)}
                        >
                          <UserRoundCheck size={16} aria-hidden="true" />
                          {t("useThisRecord")}
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="row" style={{ marginTop: "0.5rem" }}>
                    <button type="button" disabled={busy} onClick={() => void registerNew()}>
                      {t("registerAsNew")}
                    </button>
                    <button type="button" className="quiet" onClick={() => setMatches(null)}>
                      {t("back")}
                    </button>
                  </div>
                </section>
              )}
            </section>
          </div>
        </div>
      )}
      <ConfirmDialog
        open={asking !== null}
        title={asking ? t("askPriorityTitle", { token: asking.entry.token }) : ""}
        confirmLabel={t("sendToDoctor")}
        cancelLabel={t("back")}
        busy={busy}
        confirmDisabled={!asking || asking.reason.trim().length < 3}
        onConfirm={() => void askDoctor()}
        onClose={() => setAsking(null)}
      >
        {asking && (
          <>
            <p className="muted small">{t("askPriorityHint")}</p>
            <div className="field">
              <label htmlFor="ask-level">{t("priority")}</label>
              <select
                id="ask-level"
                value={asking.priority}
                onChange={(e) => setAsking({ ...asking, priority: Number(e.target.value) })}
              >
                {Array.from({ length: MAX_PRIORITY + 1 }, (_, p) => (
                  <option key={p} value={p} disabled={p === asking.entry.priority}>
                    {t(`priorityLevel_${p}`)}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="ask-reason">{t("reasonForDoctor")}</label>
              <input
                id="ask-reason"
                required
                minLength={3}
                maxLength={200}
                value={asking.reason}
                onChange={(e) => setAsking({ ...asking, reason: e.target.value })}
              />
            </div>
          </>
        )}
      </ConfirmDialog>
      <ConfirmDialog
        open={moving !== null}
        title={moving ? t("moveTitle", { token: moving.entry.token }) : ""}
        confirmLabel={t("move")}
        cancelLabel={t("back")}
        busy={busy}
        confirmDisabled={!moving?.doctor_id}
        onConfirm={() => void moveEntry()}
        onClose={() => setMoving(null)}
      >
        {moving && doctors && (
          <>
            <p className="muted small">{t("moveHint")}</p>
            <div className="field">
              <label htmlFor="mv-doctor">{t("moveTo")}</label>
              <select
                id="mv-doctor"
                value={moving.doctor_id}
                onChange={(e) => setMoving({ ...moving, doctor_id: e.target.value })}
              >
                <option value="">{t("chooseDoctor")}</option>
                {byDepartment(doctors.filter((d) => d.doctor_id !== selected && d.doctor_status !== "unavailable")).map(
                  ([dept, list]) => (
                    <optgroup key={dept} label={dept}>
                      {list.map((d) => (
                        <option key={d.doctor_id} value={d.doctor_id}>
                          {d.doctor_name}
                        </option>
                      ))}
                    </optgroup>
                  ),
                )}
              </select>
            </div>
            <div className="field">
              <label htmlFor="mv-reason">{t("reasonOptional")}</label>
              <input
                id="mv-reason"
                maxLength={200}
                value={moving.reason}
                onChange={(e) => setMoving({ ...moving, reason: e.target.value })}
              />
            </div>
          </>
        )}
      </ConfirmDialog>
      <ConfirmDialog
        open={leaving !== null}
        title={leaving ? t("markLeftTitle", { token: leaving.token }) : ""}
        confirmLabel={t("markLeft")}
        cancelLabel={t("back")}
        busy={busy}
        danger
        onConfirm={() => void markLeft()}
        onClose={() => setLeaving(null)}
      >
        <p>{t("markLeftText")}</p>
      </ConfirmDialog>
      <ConfirmDialog
        open={editing !== null}
        title={editing ? `${t("categoriesFor")} ${editing.name}` : ""}
        confirmLabel={t("save")}
        cancelLabel={t("back")}
        busy={busy}
        onConfirm={() => void saveCategories()}
        onClose={() => setEditing(null)}
      >
        {editing && (
          <>
            <p className="muted small">{t("categoriesHint")}</p>
            <label className="check">
              <input
                type="checkbox"
                checked={editing.pregnant}
                onChange={(e) => setEditing({ ...editing, pregnant: e.target.checked })}
              />
              {t("category_pregnant")}
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={editing.disability}
                onChange={(e) => setEditing({ ...editing, disability: e.target.checked })}
              />
              {t("category_disability")}
            </label>
          </>
        )}
      </ConfirmDialog>
    </main>
  );
}
