import {
  CalendarPlus,
  CalendarX2,
  CircleCheck,
  Clock,
  FileText,
  LogIn,
  RefreshCw,
  RotateCcw,
  Stethoscope,
  Ticket,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { dateTile, longDate } from "../format";
import { useSession } from "../session";

// The rule itself is enforced by the server (FR-13); a refusal shows the server's explanation.
const CANCEL_POLICY_NOTE = {
  en: "Appointments can be cancelled free of charge up to 4 hours before the appointment time.",
  hi: "अपॉइंटमेंट के समय से 4 घंटे पहले तक अपॉइंटमेंट मुफ़्त में रद्द किया जा सकता है।",
  mr: "अपॉइंटमेंटच्या वेळेच्या 4 तास आधीपर्यंत अपॉइंटमेंट मोफत रद्द करता येते.",
};

const STATUS_TONE = { booked: "ok", rescheduled: "brand", displaced: "warn", cancelled: "", no_show: "danger" };

/** S3: upcoming and past appointments, with receipts, rescheduling, cancelling and rebooking;
every change is confirmed in a dialog first (the same rule as the chat's confirmation cards). */
export default function Appointments() {
  const { user, lang, t } = useSession();
  const navigate = useNavigate();
  const [histories, setHistories] = useState(null);
  const [error, setError] = useState(null);
  const [cancelling, setCancelling] = useState(null);
  const [checkingIn, setCheckingIn] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const ids = user.patients.map((p) => p.patient_id);
      setHistories(await Promise.all(ids.map((id) => api(`/patients/${id}/appointments`))));
    } catch (err) {
      setError(err);
    }
  }, [user]);

  useEffect(() => {
    void load();
  }, [load]);

  async function cancel() {
    setBusy(true);
    setError(null);
    try {
      await api(`/appointments/${cancelling.appointment_id}?confirmed=true`, { method: "DELETE" });
      setNotice(t("cancelledDone"));
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
      setCancelling(null);
    }
  }

  // Online check-in (features 24, 25): offered by the server inside its window; confirmed here first.
  async function checkIn() {
    setBusy(true);
    setError(null);
    try {
      const entry = await api(`/queue/entries/${checkingIn.appointment_id}/check-in`, { method: "POST" });
      setNotice(t("checkedInToken", { token: entry.token }));
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
      setCheckingIn(null);
    }
  }

  const checkInControl = (a) =>
    a.token ? (
      <Link className="button secondary" to="/queue">
        <Ticket size={16} aria-hidden="true" />
        {t("checkedInToken", { token: a.token })}
      </Link>
    ) : a.can_check_in ? (
      <button type="button" onClick={() => setCheckingIn(a)}>
        <LogIn size={16} aria-hidden="true" />
        {t("checkInNow")}
      </button>
    ) : null;

  const badge = (a) => <span className={`badge ${STATUS_TONE[a.status] ?? ""}`}>{t(`status_${a.status}`)}</span>;

  function upcoming(items) {
    if (items.length === 0) {
      return (
        <div className="card empty">
          <span className="icon-tile" aria-hidden="true">
            <CalendarX2 size={22} />
          </span>
          <strong>{t("noUpcoming")}</strong>
          <span>{t("noUpcomingHint")}</span>
          <button type="button" onClick={() => navigate("/book")}>
            <CalendarPlus size={18} aria-hidden="true" />
            {t("bookNew")}
          </button>
        </div>
      );
    }
    return (
      <div className="appt-list">
        {items.map((a) => {
          const tile = dateTile(a.date, lang);
          return (
            <article key={a.appointment_id} className="card appt">
              <div className="date-tile" aria-hidden="true">
                <span className="m">{tile.month}</span>
                <span className="d">{tile.day}</span>
                <span className="w">{tile.weekday}</span>
              </div>
              <div className="info">
                <div className="row">
                  <strong>{a.doctor_name}</strong>
                  {badge(a)}
                </div>
                <div className="meta">
                  <span>
                    <Stethoscope size={15} aria-hidden="true" />
                    {a.department}
                  </span>
                  <span>
                    <Clock size={15} aria-hidden="true" />
                    {longDate(a.date, lang)} · {a.time}
                  </span>
                </div>
              </div>
              <div className="actions">
                {checkInControl(a)}
                <Link className="button quiet" to={`/receipt/${a.appointment_id}`}>
                  <FileText size={16} aria-hidden="true" />
                  {t("receipt")}
                </Link>
                <button
                  type="button"
                  className="secondary"
                  disabled={!a.can_reschedule}
                  onClick={() => navigate("/book", { state: { reschedule: a } })}
                >
                  {a.status === "displaced" ? (
                    <RotateCcw size={16} aria-hidden="true" />
                  ) : (
                    <RefreshCw size={16} aria-hidden="true" />
                  )}
                  {a.status === "displaced" ? t("rebook") : t("reschedule")}
                </button>
                <button
                  type="button"
                  className="danger-outline"
                  disabled={!a.can_cancel}
                  onClick={() => setCancelling(a)}
                >
                  <X size={16} aria-hidden="true" />
                  {t("cancel")}
                </button>
              </div>
              {(!a.can_reschedule || !a.can_cancel) && <p className="hint span-row">{t("changesClosed")}</p>}
            </article>
          );
        })}
      </div>
    );
  }

  function past(items) {
    if (items.length === 0) return <p className="muted">{t("none")}</p>;
    return (
      <ul className="card past-list">
        {items.map((a) => (
          <li key={a.appointment_id}>
            <div className="grow">
              <strong>{a.doctor_name}</strong>
              <div className="muted small">
                {a.department} · {longDate(a.date, lang)} · {a.time}
              </div>
            </div>
            {badge(a)}
            {checkInControl(a)}
            {a.status === "no_show" && (
              <button type="button" className="secondary" onClick={() => navigate("/book", { state: { rebook: a } })}>
                <RotateCcw size={16} aria-hidden="true" />
                {t("rebook")}
              </button>
            )}
          </li>
        ))}
      </ul>
    );
  }

  const showNames = (histories?.length ?? 0) > 1 || user?.role === "caregiver";
  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("appointmentsTitle")}</h1>
          <p className="lead">{t("appointmentsIntro")}</p>
        </div>
        <button type="button" onClick={() => navigate("/book")}>
          <CalendarPlus size={18} aria-hidden="true" />
          {t("bookNew")}
        </button>
      </div>
      {notice && (
        <div className="notice" role="status">
          <CircleCheck size={18} aria-hidden="true" />
          {notice}
        </div>
      )}
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {histories === null && error === null && <Loading />}
      {histories?.map((h) => (
        <section key={h.patient_id} aria-label={h.patient_name}>
          {showNames && (
            <div className="section-title">
              <h2>{h.patient_name}</h2>
            </div>
          )}
          <div className="section-title">
            <h2>{t("upcoming")}</h2>
          </div>
          {upcoming(h.upcoming)}
          <div className="section-title">
            <h2>{t("past")}</h2>
          </div>
          {past(h.past)}
        </section>
      ))}
      <ConfirmDialog
        open={checkingIn !== null}
        title={t("checkInNow")}
        confirmLabel={t("checkIn")}
        cancelLabel={t("back")}
        busy={busy}
        onConfirm={() => void checkIn()}
        onClose={() => setCheckingIn(null)}
      >
        {checkingIn && (
          <>
            <p>
              <strong>{checkingIn.doctor_name}</strong> ({checkingIn.department}) · {checkingIn.time}
            </p>
            <p className="muted">{t("checkInNote")}</p>
          </>
        )}
      </ConfirmDialog>
      <ConfirmDialog
        open={cancelling !== null}
        title={t("confirmCancel")}
        confirmLabel={t("yesCancel")}
        cancelLabel={t("keepIt")}
        busy={busy}
        danger
        onConfirm={() => void cancel()}
        onClose={() => setCancelling(null)}
      >
        {cancelling && (
          <>
            <p>
              <strong>{cancelling.doctor_name}</strong> ({cancelling.department}) · {longDate(cancelling.date, lang)} ·{" "}
              {cancelling.time}
            </p>
            <p className="muted">{CANCEL_POLICY_NOTE[lang] ?? CANCEL_POLICY_NOTE.en}</p>
          </>
        )}
      </ConfirmDialog>
    </main>
  );
}
