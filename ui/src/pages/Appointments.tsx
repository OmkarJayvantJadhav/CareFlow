import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Appointment } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import type { Key } from "../i18n";
import { useSession } from "../session";

interface History {
  patient_id: number;
  patient_name: string;
  upcoming: Appointment[];
  past: Appointment[];
}

/** S3: upcoming and past appointments; changes go through the chat so they get a confirmation card. */
export default function Appointments() {
  const { user, t } = useSession();
  const navigate = useNavigate();
  const [histories, setHistories] = useState<History[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const ids = user!.patients.map((p) => p.patient_id);
      setHistories(await Promise.all(ids.map((id) => api<History>(`/patients/${id}/appointments`))));
    } catch (err) {
      setError(err);
    }
  }, [user]);

  useEffect(() => {
    void load();
  }, [load]);

  function ask(kind: "rescheduleAsk" | "cancelAsk", a: Appointment) {
    navigate("/chat", { state: { prefill: t(kind, { doctor: a.doctor_name, date: a.date, time: a.time }) } });
  }

  function list(items: Appointment[], actions: boolean) {
    if (items.length === 0) return <p className="muted">{t("none")}</p>;
    return (
      <div className="grid">
        {items.map((a) => (
          <article key={a.appointment_id} className="card">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <strong>{a.doctor_name}</strong>
              <span className={`pill ${a.status === "displaced" ? "warn" : a.status === "booked" ? "ok" : ""}`}>
                {t(`status_${a.status}` as Key)}
              </span>
            </div>
            <div className="muted">{a.department}</div>
            <div>
              {a.date} · {a.time}
            </div>
            {actions && (
              <div className="row" style={{ marginTop: 10 }}>
                <button type="button" className="secondary" onClick={() => ask("rescheduleAsk", a)}>
                  {t("reschedule")}
                </button>
                <button type="button" className="quiet" onClick={() => ask("cancelAsk", a)}>
                  {t("cancel")}
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
    );
  }

  return (
    <main>
      <h1>{t("appointmentsTitle")}</h1>
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {histories === null && error === null && <p className="muted">{t("loading")}</p>}
      {histories?.map((h) => (
        <section key={h.patient_id}>
          {histories.length > 1 || user?.role === "caregiver" ? <h2>{h.patient_name}</h2> : null}
          <h2>{t("upcoming")}</h2>
          {list(h.upcoming, true)}
          <h2>{t("past")}</h2>
          {list(h.past, false)}
        </section>
      ))}
    </main>
  );
}
