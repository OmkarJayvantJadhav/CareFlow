import { CalendarPlus, CalendarX2, Clock, RefreshCw, Stethoscope, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { dateTile, longDate } from "../format";
import { useSession } from "../session";

const STATUS_TONE = { booked: "ok", rescheduled: "brand", displaced: "warn", cancelled: "", no_show: "danger" };

/** S3: upcoming and past appointments; changes go through the chat so they get a confirmation card. */
export default function Appointments() {
  const { user, lang, t } = useSession();
  const navigate = useNavigate();
  const [histories, setHistories] = useState(null);
  const [error, setError] = useState(null);

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

  function ask(kind, a) {
    navigate("/chat", { state: { prefill: t(kind, { doctor: a.doctor_name, date: a.date, time: a.time }) } });
  }

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
          <button type="button" onClick={() => navigate("/chat")}>
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
                <button type="button" className="secondary" onClick={() => ask("rescheduleAsk", a)}>
                  <RefreshCw size={16} aria-hidden="true" />
                  {t("reschedule")}
                </button>
                <button type="button" className="danger-outline" onClick={() => ask("cancelAsk", a)}>
                  <X size={16} aria-hidden="true" />
                  {t("cancel")}
                </button>
              </div>
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
        <button type="button" onClick={() => navigate("/chat")}>
          <CalendarPlus size={18} aria-hidden="true" />
          {t("bookNew")}
        </button>
      </div>
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
    </main>
  );
}
