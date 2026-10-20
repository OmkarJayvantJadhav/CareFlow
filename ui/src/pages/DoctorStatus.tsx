import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import type { Key } from "../i18n";
import { useSession } from "../session";
import type { DutyDoctor } from "../staff";

/** S7: breaks, delays and unavailability; shows how many patients were informed. */
export default function DoctorStatus() {
  const { t } = useSession();
  const [doctors, setDoctors] = useState<DutyDoctor[] | null>(null);
  const [minutes, setMinutes] = useState<Record<number, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setDoctors((await api<{ doctors: DutyDoctor[] }>("/staff/today")).doctors);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function event(d: DutyDoctor, type: "break" | "delay" | "resume" | "unavailable") {
    if (type === "unavailable" && !window.confirm(t("confirmUnavailable", { doctor: d.doctor_name }))) return;
    setBusy(d.doctor_id);
    setError(null);
    setNotice(null);
    try {
      const sessionId =
        d.session_id ?? (await api<{ session_id: number }>(`/staff/doctors/${d.doctor_id}/session`, { method: "POST" })).session_id;
      const body: { type: string; minutes?: number } = { type };
      if (type === "break" || type === "delay") body.minutes = Number(minutes[d.doctor_id] || (type === "break" ? 15 : 20));
      const result = await api<{ affected?: unknown[] }>(`/queue/sessions/${sessionId}/events`, { method: "POST", body });
      if (type === "unavailable") setNotice(t("affected", { count: result.affected?.length ?? 0 }));
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <main>
      <h1>{t("doctorsTitle")}</h1>
      <p className="lead">{t("doctorsIntro")}</p>
      {notice && (
        <div className="notice" role="status">
          {notice}
        </div>
      )}
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {doctors === null && error === null && <p className="muted">{t("loading")}</p>}
      <div className="grid">
        {doctors?.map((d) => {
          const unavailable = d.doctor_status === "unavailable";
          return (
            <section key={d.doctor_id} className="card" aria-labelledby={`doc-${d.doctor_id}`}>
              <h2 id={`doc-${d.doctor_id}`} style={{ marginTop: 0 }}>
                {d.doctor_name}
              </h2>
              <div className="muted">{d.department}</div>
              <p>
                <span className={`pill ${d.doctor_status === "available" ? "ok" : "warn"}`}>
                  {d.doctor_status === "available" ? "●" : "⏱"} {t(`doctor_${d.doctor_status}` as Key, { minutes: d.delay_minutes })}
                </span>
              </p>
              {!unavailable && (
                <>
                  <div className="field" style={{ maxWidth: 160 }}>
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
                  <div className="row">
                    <button type="button" className="secondary" disabled={busy !== null} onClick={() => event(d, "break")}>
                      {t("markBreak")}
                    </button>
                    <button type="button" className="secondary" disabled={busy !== null} onClick={() => event(d, "delay")}>
                      {t("markDelay")}
                    </button>
                    {d.doctor_status !== "available" && (
                      <button type="button" disabled={busy !== null} onClick={() => event(d, "resume")}>
                        {t("markResume")}
                      </button>
                    )}
                    <button type="button" className="quiet" disabled={busy !== null} onClick={() => event(d, "unavailable")}>
                      {t("markUnavailable")}
                    </button>
                  </div>
                </>
              )}
            </section>
          );
        })}
      </div>
    </main>
  );
}
