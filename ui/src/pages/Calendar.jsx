import {
  CalendarOff,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  Lock,
  LockOpen,
  Plane,
  Timer,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { dateTile, longDate } from "../format";
import { useSession } from "../session";

const DAYS = 7;

function shift(iso, days) {
  const [y, m, d] = iso.split("-").map(Number);
  const next = new Date(Date.UTC(y, m - 1, d + days));
  return next.toISOString().slice(0, 10);
}

/** S14: a doctor's week of slots, blocking and reopening slots, and leave days (features 2 and 13). */
export default function Calendar() {
  const { lang, t } = useSession();
  const [doctors, setDoctors] = useState(null);
  const [doctorId, setDoctorId] = useState(null);
  const [start, setStart] = useState(null);
  const [cal, setCal] = useState(null);
  const [open, setOpen] = useState(null);
  const [leave, setLeave] = useState({ start_date: "", end_date: "", reason: "" });
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/doctors")
      .then((d) => {
        setDoctors(d.doctors);
        setDoctorId((current) => current ?? d.doctors[0]?.doctor_id ?? null);
      })
      .catch(setError);
  }, []);

  const load = useCallback(async () => {
    if (doctorId === null) return;
    try {
      const params = new URLSearchParams({ days: String(DAYS) });
      if (start) params.set("start", start);
      const body = await api(`/staff/doctors/${doctorId}/calendar?${params}`);
      setCal(body);
      if (!start) setStart(body.days[0].date);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [doctorId, start]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(fn) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const message = await fn();
      if (message) setNotice(message);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const addLeave = () =>
    act(async () => {
      const r = await api(`/staff/doctors/${doctorId}/leave`, { method: "POST", body: leave });
      setLeave({ start_date: "", end_date: "", reason: "" });
      setConfirmLeave(false);
      return t("leaveAdded", { count: r.affected.length });
    }).finally(() => setConfirmLeave(false));

  const minutes = cal?.consultation_minutes;
  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("calendarTitle")}</h1>
          <p className="lead">{t("calendarIntro")}</p>
        </div>
      </div>
      {doctors === null && error === null && <Loading />}
      {doctors && (
        <div className="card desk-toolbar">
          <div className="field">
            <label htmlFor="cal-doctor">{t("doctorLabel")}</label>
            <select
              id="cal-doctor"
              value={doctorId ?? ""}
              onChange={(e) => {
                setDoctorId(Number(e.target.value));
                setOpen(null);
              }}
            >
              {doctors.map((d) => (
                <option key={d.doctor_id} value={d.doctor_id}>
                  {d.name} — {d.department}
                </option>
              ))}
            </select>
          </div>
          {minutes && (
            <div className="muted small" style={{ display: "flex", gap: "0.375rem", alignItems: "center" }}>
              <Timer size={16} aria-hidden="true" />
              <span>
                {t("consultLength", { typical: minutes.typical, long: minutes.long })}{" "}
                {minutes.source === "history"
                  ? t("consultFromHistory", { visits: minutes.visits })
                  : t("consultFromSlots", { minutes: cal.slot_minutes })}
              </span>
            </div>
          )}
        </div>
      )}
      {notice && (
        <div className="notice" role="status">
          <CircleCheck size={18} aria-hidden="true" />
          {notice}
        </div>
      )}
      {error !== null && <ErrorMessage error={error} onRetry={load} />}

      {cal && (
        <>
          <div className="section-title">
            <h2>
              {longDate(cal.days[0].date, lang)} – {longDate(cal.days[cal.days.length - 1].date, lang)}
            </h2>
            <div className="row">
              <button type="button" className="quiet" onClick={() => setStart(shift(start, -DAYS))}>
                <ChevronLeft size={16} aria-hidden="true" />
                {t("previousWeek")}
              </button>
              <button type="button" className="quiet" onClick={() => setStart(shift(start, DAYS))}>
                {t("nextWeek")}
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
          <div className="week">
            {cal.days.map((day) => {
              const tile = dateTile(day.date, lang);
              const expanded = open === day.date;
              return (
                <section
                  key={day.date}
                  className={`card day ${day.leave ? "on-leave" : ""}`}
                  aria-label={longDate(day.date, lang)}
                >
                  <div className="day-head">
                    <div className="date-tile" aria-hidden="true">
                      <span className="m">{tile.month}</span>
                      <span className="d">{tile.day}</span>
                      <span className="w">{tile.weekday}</span>
                    </div>
                    <div className="day-counts">
                      {day.leave ? (
                        <span className="badge danger">
                          <Plane size={13} aria-hidden="true" /> {t("onLeave")}
                          {day.leave.reason ? ` · ${day.leave.reason}` : ""}
                        </span>
                      ) : !day.works ? (
                        <span className="badge">
                          <CalendarOff size={13} aria-hidden="true" /> {t("noOpd")}
                        </span>
                      ) : null}
                      {day.slots.length > 0 && (
                        <>
                          <span className="badge ok">{t("freeCount", { count: day.free })}</span>
                          <span className="badge brand">{t("bookedCount", { count: day.booked })}</span>
                          {day.blocked > 0 && (
                            <span className="badge warn">{t("blockedCount", { count: day.blocked })}</span>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                  {day.slots.length > 0 && (
                    <button
                      type="button"
                      className="ghost slots-toggle"
                      aria-expanded={expanded}
                      onClick={() => setOpen(expanded ? null : day.date)}
                    >
                      {t("showSlots")} ({day.slots.length})
                    </button>
                  )}
                  {expanded && (
                    <ul className="slot-grid">
                      {day.slots.map((s) => (
                        <li key={s.slot_id} className={`slot ${s.status}`}>
                          <span className="time">{s.time}</span>
                          <span className="muted small">{t(`slotStatus_${s.status}`)}</span>
                          {!s.past && s.status === "free" && (
                            <button
                              type="button"
                              className="quiet"
                              disabled={busy}
                              aria-label={`${t("block")} ${s.time}`}
                              onClick={() => act(() => api(`/staff/slots/${s.slot_id}/block`, { method: "POST" }))}
                            >
                              <Lock size={14} aria-hidden="true" />
                              {t("block")}
                            </button>
                          )}
                          {!s.past && s.status === "blocked" && !day.leave && (
                            <button
                              type="button"
                              className="secondary"
                              disabled={busy}
                              aria-label={`${t("unblock")} ${s.time}`}
                              onClick={() => act(() => api(`/staff/slots/${s.slot_id}/unblock`, { method: "POST" }))}
                            >
                              <LockOpen size={14} aria-hidden="true" />
                              {t("unblock")}
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              );
            })}
          </div>

          <section className="card" aria-labelledby="leave-h" style={{ marginTop: "1rem" }}>
            <div className="card-head">
              <h2 id="leave-h">
                <Plane size={20} aria-hidden="true" />
                {t("leaveTitle")}
              </h2>
            </div>
            {cal.leaves.length === 0 && (
              <p className="muted" style={{ marginBottom: "1rem" }}>
                {t("noLeave")}
              </p>
            )}
            {cal.leaves.length > 0 && (
              <ul className="booking-list" style={{ marginBottom: "1rem" }}>
                {cal.leaves.map((lv) => (
                  <li key={lv.leave_id}>
                    <span>
                      <strong>
                        {longDate(lv.start_date, lang)}
                        {lv.end_date !== lv.start_date ? ` – ${longDate(lv.end_date, lang)}` : ""}
                      </strong>
                      {lv.reason ? <span className="muted"> · {lv.reason}</span> : null}
                    </span>
                    <button
                      type="button"
                      className="danger-outline"
                      disabled={busy}
                      onClick={() =>
                        act(async () => {
                          const r = await api(`/staff/leave/${lv.leave_id}`, { method: "DELETE" });
                          return t("leaveRemoved", { count: r.slots_reopened });
                        })
                      }
                    >
                      <Trash2 size={14} aria-hidden="true" />
                      {t("cancelLeave")}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <form
              className="row"
              style={{ alignItems: "flex-end" }}
              onSubmit={(e) => {
                e.preventDefault();
                setConfirmLeave(true);
              }}
            >
              <div className="field" style={{ flex: "1 1 10rem", margin: 0 }}>
                <label htmlFor="lv-from">{t("fromDate")}</label>
                <input
                  id="lv-from"
                  type="date"
                  required
                  value={leave.start_date}
                  onChange={(e) =>
                    setLeave({ ...leave, start_date: e.target.value, end_date: leave.end_date || e.target.value })
                  }
                />
              </div>
              <div className="field" style={{ flex: "1 1 10rem", margin: 0 }}>
                <label htmlFor="lv-to">{t("toDate")}</label>
                <input
                  id="lv-to"
                  type="date"
                  required
                  min={leave.start_date || undefined}
                  value={leave.end_date}
                  onChange={(e) => setLeave({ ...leave, end_date: e.target.value })}
                />
              </div>
              <div className="field" style={{ flex: "2 1 14rem", margin: 0 }}>
                <label htmlFor="lv-reason">{t("leaveReason")}</label>
                <input
                  id="lv-reason"
                  maxLength={120}
                  value={leave.reason}
                  onChange={(e) => setLeave({ ...leave, reason: e.target.value })}
                />
              </div>
              <button type="submit" disabled={busy}>
                <Plane size={16} aria-hidden="true" />
                {t("addLeave")}
              </button>
            </form>
          </section>
        </>
      )}
      <ConfirmDialog
        open={confirmLeave}
        title={t("addLeave")}
        confirmLabel={t("addLeave")}
        cancelLabel={t("back")}
        busy={busy}
        danger
        onConfirm={() => void addLeave()}
        onClose={() => setConfirmLeave(false)}
      >
        <p>
          {cal?.doctor_name}: {leave.start_date && longDate(leave.start_date, lang)}
          {leave.end_date && leave.end_date !== leave.start_date ? ` – ${longDate(leave.end_date, lang)}` : ""}
        </p>
        <p className="muted">{t("calendarIntro")}</p>
      </ConfirmDialog>
    </main>
  );
}
