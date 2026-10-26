import {
  ArrowRightLeft,
  Check,
  CircleCheck,
  Coffee,
  ListOrdered,
  Megaphone,
  Play,
  Siren,
  Star,
  Stethoscope,
  Timer,
  UserX,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { EntryBadges } from "../components/QueueBadges";
import { byDepartment } from "../format";
import { useSession } from "../session";
import { followSession } from "../staff";

const MAX_PRIORITY = 3;
const DOCTOR_TONE = { available: "ok", on_break: "warn", delayed: "warn", unavailable: "danger" };

/** The doctor's own queue (features 43, 49, 50, 52): call, see, forward, set priority, answer requests. */
export default function DoctorQueue() {
  const { t } = useSession();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [minutes, setMinutes] = useState("15");
  const [forward, setForward] = useState(null);

  const load = useCallback(async () => {
    try {
      setData(await api("/queue/doctor/today"));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const session = data?.session ?? null;
  const sessionId = session?.session_id ?? null;
  useEffect(() => {
    if (sessionId === null) return;
    return followSession(sessionId, () => void load());
  }, [sessionId, load]);

  async function act(path, method = "POST", body) {
    setBusy(true);
    setError(null);
    try {
      await api(path, { method, body });
      await load();
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function sendForward() {
    const done = await act(`/queue/entries/${forward.entry.entry_id}/transfer`, "POST", {
      doctor_id: Number(forward.doctor_id),
      reason: forward.reason.trim() || null,
    });
    if (done) setForward(null);
  }

  const status = (type) => {
    const body = { type };
    if (type !== "resume") body.minutes = Number(minutes) || 15;
    return act(`/queue/sessions/${sessionId}/events`, "POST", body);
  };

  const entries = session?.entries ?? [];
  const inRoom = entries.find((e) => e.status === "called" || e.status === "in_consultation") ?? null;
  const waiting = entries.filter((e) => e.status === "waiting");
  const missed = entries.filter((e) => e.status === "missed");
  const names = Object.fromEntries(entries.map((e) => [e.entry_id, e.patient_name]));
  const open = session?.status === "open";

  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("myQueueTitle")}</h1>
          <p className="lead">{data ? `${data.doctor_name} · ${data.department}` : t("myQueueIntro")}</p>
        </div>
        {session && (
          <span className={`badge ${DOCTOR_TONE[session.doctor_status] ?? ""}`}>
            <span className="dot" aria-hidden="true" />
            {t(`doctor_${session.doctor_status}`, { minutes: session.delay_minutes })}
          </span>
        )}
      </div>
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {data === null && error === null && <Loading />}
      {data && !session && (
        <div className="card empty">
          <span className="icon-tile" aria-hidden="true">
            <Stethoscope size={22} />
          </span>
          <span>{t("noOpdToday")}</span>
        </div>
      )}
      {session && !open && (
        <div className="notice warn" role="status">
          {t("queueClosedToday")}
        </div>
      )}
      {session && (
        <div className="desk-grid">
          <div className="desk-main">
            <section className="card" aria-labelledby="room-h">
              <div className="card-head">
                <h2 id="room-h">
                  <Stethoscope size={20} aria-hidden="true" />
                  {t("inRoom")}
                </h2>
                {open && !inRoom && (
                  <button type="button" disabled={busy} onClick={() => act(`/queue/sessions/${sessionId}/call-next`)}>
                    <Megaphone size={18} aria-hidden="true" />
                    {t("callNext")}
                  </button>
                )}
              </div>
              {!inRoom && <p className="muted">{waiting.length ? t("roomFree") : t("noQueue")}</p>}
              {inRoom && (
                <div className="current-patient">
                  <div>
                    <span className="token-pill">{inRoom.token}</span> <strong>{inRoom.patient_name}</strong>
                    <div className="row" style={{ gap: "0.25rem", marginTop: "0.35rem" }}>
                      <span className="badge brand">{t(`entry_${inRoom.status}`)}</span>
                      <EntryBadges entry={inRoom} />
                    </div>
                  </div>
                  <div className="row">
                    {inRoom.status === "called" && (
                      <>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => act(`/queue/entries/${inRoom.entry_id}/start`)}
                        >
                          <Play size={16} aria-hidden="true" />
                          {t("start")}
                        </button>
                        <button
                          type="button"
                          className="quiet"
                          disabled={busy}
                          onClick={() => act(`/queue/entries/${inRoom.entry_id}/missed`)}
                        >
                          <UserX size={16} aria-hidden="true" />
                          {t("missed")}
                        </button>
                      </>
                    )}
                    {inRoom.status === "in_consultation" && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => act(`/queue/entries/${inRoom.entry_id}/end`)}
                      >
                        <CircleCheck size={16} aria-hidden="true" />
                        {t("end")}
                      </button>
                    )}
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy}
                      onClick={() => setForward({ entry: inRoom, doctor_id: "", reason: "" })}
                    >
                      <ArrowRightLeft size={16} aria-hidden="true" />
                      {t("forward")}
                    </button>
                  </div>
                </div>
              )}
            </section>
            <section className="card" aria-labelledby="waiting-h">
              <div className="card-head">
                <h2 id="waiting-h">
                  <ListOrdered size={20} aria-hidden="true" />
                  {t("waitingList")} ({waiting.length})
                </h2>
              </div>
              {waiting.length === 0 && <p className="muted">{t("noQueue")}</p>}
              {waiting.length > 0 && (
                <ol className="booking-list" aria-labelledby="waiting-h">
                  {waiting.map((e) => (
                    <li key={e.entry_id}>
                      <span className="booking-who">
                        <span>
                          <span className="token-pill">{e.token}</span> {e.patient_name}
                        </span>
                        <span className="row" style={{ gap: "0.25rem" }}>
                          <EntryBadges entry={e} />
                        </span>
                        <span className="muted small">
                          {t("estimatedWait")}: {e.estimate?.display ?? "—"}
                        </span>
                      </span>
                      <span className="field priority-pick">
                        <label htmlFor={`prio-${e.entry_id}`}>{t("priorityFor", { token: e.token })}</label>
                        <select
                          id={`prio-${e.entry_id}`}
                          value={e.priority}
                          disabled={busy || !open}
                          onChange={(ev) =>
                            void act(`/queue/entries/${e.entry_id}/priority`, "PATCH", {
                              priority: Number(ev.target.value),
                            })
                          }
                        >
                          {Array.from({ length: MAX_PRIORITY + 1 }, (_, p) => (
                            <option key={p} value={p}>
                              {t(`priorityLevel_${p}`)}
                            </option>
                          ))}
                        </select>
                      </span>
                    </li>
                  ))}
                </ol>
              )}
              {missed.length > 0 && (
                <p className="muted small" style={{ marginTop: "0.75rem" }}>
                  {t("missedTurns")}: {missed.map((e) => e.token).join(", ")}
                </p>
              )}
            </section>
          </div>
          <div className="desk-side">
            <section className="card" aria-labelledby="requests-h">
              <div className="card-head">
                <h2 id="requests-h">
                  <Star size={20} aria-hidden="true" />
                  {t("priorityRequests")}
                </h2>
              </div>
              {session.priority_requests.length === 0 && <p className="muted">{t("noPriorityRequests")}</p>}
              <ul className="booking-list">
                {session.priority_requests.map((r) => (
                  <li key={r.request_id}>
                    <span className="booking-who">
                      <span>
                        <span className="token-pill">{r.token}</span> {names[r.entry_id]}
                      </span>
                      <span className="muted small">
                        {t("asksPriority", { from: r.current_priority, to: r.priority })} · “{r.reason}”
                      </span>
                    </span>
                    <span className="row" style={{ gap: "0.25rem" }}>
                      <button
                        type="button"
                        disabled={busy || !open}
                        aria-label={`${t("approve")}: ${r.token}`}
                        onClick={() => act(`/queue/priority-requests/${r.request_id}`, "POST", { approve: true })}
                      >
                        <Check size={16} aria-hidden="true" />
                        {t("approve")}
                      </button>
                      <button
                        type="button"
                        className="danger-outline"
                        disabled={busy}
                        aria-label={`${t("decline")}: ${r.token}`}
                        onClick={() => act(`/queue/priority-requests/${r.request_id}`, "POST", { approve: false })}
                      >
                        <X size={16} aria-hidden="true" />
                        {t("decline")}
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            </section>
            {open && (
              <section className="card" aria-labelledby="status-h">
                <div className="card-head">
                  <h2 id="status-h">
                    <Timer size={20} aria-hidden="true" />
                    {t("myStatus")}
                  </h2>
                </div>
                <p className="muted small" style={{ marginBottom: "0.75rem" }}>
                  {t("myStatusHint")}
                </p>
                <div className="field">
                  <label htmlFor="my-minutes">{t("minutes")}</label>
                  <input
                    id="my-minutes"
                    type="number"
                    min={1}
                    max={240}
                    value={minutes}
                    onChange={(e) => setMinutes(e.target.value)}
                  />
                </div>
                <div className="row">
                  <button type="button" className="secondary" disabled={busy} onClick={() => void status("break")}>
                    <Coffee size={16} aria-hidden="true" />
                    {t("markBreak")}
                  </button>
                  <button type="button" className="secondary" disabled={busy} onClick={() => void status("delay")}>
                    <Timer size={16} aria-hidden="true" />
                    {t("markDelay")}
                  </button>
                  <button
                    type="button"
                    className="danger-outline"
                    disabled={busy}
                    onClick={() => void status("emergency")}
                  >
                    <Siren size={16} aria-hidden="true" />
                    {t("markEmergency")}
                  </button>
                  {session.doctor_status !== "available" && (
                    <button type="button" disabled={busy} onClick={() => void status("resume")}>
                      <Play size={16} aria-hidden="true" />
                      {t("markResume")}
                    </button>
                  )}
                </div>
              </section>
            )}
          </div>
        </div>
      )}
      <ConfirmDialog
        open={forward !== null}
        title={forward ? t("forwardTitle", { token: forward.entry.token }) : ""}
        confirmLabel={t("forward")}
        cancelLabel={t("back")}
        busy={busy}
        confirmDisabled={!forward?.doctor_id}
        onConfirm={() => void sendForward()}
        onClose={() => setForward(null)}
      >
        {forward && data && (
          <>
            <p className="muted small">{t("forwardHint")}</p>
            <div className="field">
              <label htmlFor="fw-doctor">{t("forwardTo")}</label>
              <select
                id="fw-doctor"
                required
                value={forward.doctor_id}
                onChange={(e) => setForward({ ...forward, doctor_id: e.target.value })}
              >
                <option value="">{t("chooseDoctor")}</option>
                {byDepartment(data.forward_to.map((d) => ({ ...d, doctor_name: d.name }))).map(([dept, list]) => (
                  <optgroup key={dept} label={dept}>
                    {list.map((d) => (
                      <option key={d.doctor_id} value={d.doctor_id}>
                        {d.doctor_name}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="fw-reason">{t("reasonOptional")}</label>
              <input
                id="fw-reason"
                maxLength={200}
                value={forward.reason}
                onChange={(e) => setForward({ ...forward, reason: e.target.value })}
              />
            </div>
          </>
        )}
      </ConfirmDialog>
    </main>
  );
}
