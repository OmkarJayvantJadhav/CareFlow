import { CircleCheck, Coffee, Play, Siren, Timer, UserX } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { initials } from "../format";
import { useSession } from "../session";

const TONE = { available: "ok", on_break: "warn", delayed: "warn", unavailable: "danger" };

/** S7: breaks, delays, emergencies and unavailability (features 49, 50); shows how many patients were
informed and, when a doctor is unavailable, can hand the waiting patients to colleagues (feature 42). */
export default function DoctorStatus() {
  const { t } = useSession();
  const [doctors, setDoctors] = useState(null);
  const [minutes, setMinutes] = useState({});
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [unavailable, setUnavailable] = useState(null);
  const [reassign, setReassign] = useState(true);

  const load = useCallback(async () => {
    try {
      setDoctors((await api("/staff/today")).doctors);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function event(d, type) {
    setBusy(d.doctor_id);
    setError(null);
    setNotice(null);
    try {
      const sessionId =
        d.session_id ?? (await api(`/staff/doctors/${d.doctor_id}/session`, { method: "POST" })).session_id;
      const body = { type };
      if (type === "break" || type === "delay" || type === "emergency")
        body.minutes = Number(minutes[d.doctor_id] || (type === "break" ? 15 : 20));
      if (type === "unavailable") body.reassign = reassign;
      const result = await api(`/queue/sessions/${sessionId}/events`, { method: "POST", body });
      if (type === "unavailable") {
        const moved = result.moved?.length ?? 0;
        setNotice(
          `${t("affected", { count: result.affected?.length ?? 0 })}${moved ? ` ${t("movedCount", { count: moved })}` : ""}`,
        );
        setUnavailable(null);
      }
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("doctorsTitle")}</h1>
          <p className="lead">{t("doctorsIntro")}</p>
        </div>
      </div>
      {notice && (
        <div className="notice" role="status">
          <CircleCheck size={18} aria-hidden="true" />
          {notice}
        </div>
      )}
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {doctors === null && error === null && <Loading />}
      <div className="grid">
        {doctors?.map((d) => {
          const unavailable = d.doctor_status === "unavailable";
          return (
            <section key={d.doctor_id} className="card doctor-card" aria-labelledby={`doc-${d.doctor_id}`}>
              <div className="who">
                <span className="avatar lg" aria-hidden="true">
                  {initials(d.doctor_name)}
                </span>
                <div>
                  <h2 id={`doc-${d.doctor_id}`}>{d.doctor_name}</h2>
                  <div className="muted small">{d.department}</div>
                </div>
              </div>
              <div>
                <span className={`badge ${TONE[d.doctor_status] ?? ""}`}>
                  <span className="dot" aria-hidden="true" />
                  {t(`doctor_${d.doctor_status}`, { minutes: d.delay_minutes })}
                </span>
              </div>
              {!unavailable && (
                <>
                  <div className="controls">
                    <div className="field">
                      <label htmlFor={`min-${d.doctor_id}`}>{t("minutes")}</label>
                      <input
                        id={`min-${d.doctor_id}`}
                        type="number"
                        min={1}
                        max={240}
                        value={minutes[d.doctor_id] ?? ""}
                        placeholder="15"
                        onChange={(e) => setMinutes({ ...minutes, [d.doctor_id]: e.target.value })}
                      />
                    </div>
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy !== null}
                      onClick={() => event(d, "break")}
                    >
                      <Coffee size={16} aria-hidden="true" />
                      {t("markBreak")}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy !== null}
                      onClick={() => event(d, "delay")}
                    >
                      <Timer size={16} aria-hidden="true" />
                      {t("markDelay")}
                    </button>
                    <button
                      type="button"
                      className="danger-outline"
                      disabled={busy !== null}
                      onClick={() => event(d, "emergency")}
                    >
                      <Siren size={16} aria-hidden="true" />
                      {t("markEmergency")}
                    </button>
                  </div>
                  <div className="row">
                    {d.doctor_status !== "available" && (
                      <button type="button" disabled={busy !== null} onClick={() => event(d, "resume")}>
                        <Play size={16} aria-hidden="true" />
                        {t("markResume")}
                      </button>
                    )}
                    <button
                      type="button"
                      className="danger-outline"
                      disabled={busy !== null}
                      onClick={() => {
                        setReassign(true);
                        setUnavailable(d);
                      }}
                    >
                      <UserX size={16} aria-hidden="true" />
                      {t("markUnavailable")}
                    </button>
                  </div>
                </>
              )}
            </section>
          );
        })}
      </div>
      <ConfirmDialog
        open={unavailable !== null}
        title={unavailable ? t("markUnavailable") + ` — ${unavailable.doctor_name}` : ""}
        confirmLabel={t("markUnavailable")}
        cancelLabel={t("back")}
        busy={busy !== null}
        danger
        onConfirm={() => void event(unavailable, "unavailable")}
        onClose={() => setUnavailable(null)}
      >
        {unavailable && (
          <>
            <p>{t("confirmUnavailable", { doctor: unavailable.doctor_name })}</p>
            <label className="check">
              <input type="checkbox" checked={reassign} onChange={(e) => setReassign(e.target.checked)} />
              {t("reassignWaiting")}
            </label>
          </>
        )}
      </ConfirmDialog>
    </main>
  );
}
