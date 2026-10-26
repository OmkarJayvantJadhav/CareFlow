import {
  DoorOpen,
  Hourglass,
  ListOrdered,
  MapPin,
  RefreshCw,
  Smartphone,
  Stethoscope,
  Timer,
  UsersRound,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, socketUrl } from "../api";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { useSession } from "../session";

const MAX_DOTS = 12;

const POLL_MS = 5000;

function EntryCard({ initial, onLeft }) {
  const { t } = useSession();
  const [status, setStatus] = useState(initial);
  const [leaving, setLeaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [updated, setUpdated] = useState(() => new Date());
  const [live, setLive] = useState(false);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      // The status endpoint has no patient name; keep the one the list gave.
      setStatus({ ...(await api(`/queue/entries/${initial.entry_id}/status`)), patient_name: initial.patient_name });
      setUpdated(new Date());
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [initial.entry_id, initial.patient_name]);

  // Live updates over the WebSocket; if it cannot connect or drops, poll every 5 s (FR-26, NFR-02).
  const socket = useRef(null);
  useEffect(() => {
    let closed = false;
    let poll;
    const startPolling = () => {
      setLive(false);
      if (poll === undefined) poll = window.setInterval(refresh, POLL_MS);
    };
    try {
      const ws = new WebSocket(socketUrl(initial.session_id));
      socket.current = ws;
      ws.onopen = () => {
        setLive(true);
        if (poll !== undefined) {
          window.clearInterval(poll);
          poll = undefined;
        }
      };
      ws.onmessage = () => void refresh();
      ws.onerror = () => startPolling();
      ws.onclose = () => {
        if (!closed) startPolling();
      };
    } catch {
      startPolling();
    }
    return () => {
      closed = true;
      socket.current?.close();
      if (poll !== undefined) window.clearInterval(poll);
    };
  }, [initial.session_id, refresh]);

  async function leave() {
    setBusy(true);
    try {
      await api(`/queue/entries/${status.entry_id}/left`, { method: "POST" });
      setLeaving(false);
      onLeft();
    } catch (err) {
      setError(err);
      setLeaving(false);
    } finally {
      setBusy(false);
    }
  }

  const doctorKey = `doctor_${status.doctor_status}`;
  const ahead = status.ahead ?? null;
  const yourTurn = status.status === "called";
  return (
    <section className="card token-card" aria-labelledby={`entry-${status.entry_id}`}>
      <div className="token-hero">
        <div>
          <h2 id={`entry-${status.entry_id}`}>{status.doctor_name}</h2>
          <div className="sub">
            {status.department ? `${status.department}` : ""}
            {status.patient_name ? `${status.department ? " · " : ""}${status.patient_name}` : ""}
          </div>
          <span className="live-badge" title={live ? t("live") : t("polling")}>
            {live ? (
              <>
                <span className="dot pulse" aria-hidden="true" /> {t("live")}
              </>
            ) : (
              <>
                <RefreshCw size={13} aria-hidden="true" /> {t("polling")}
              </>
            )}
          </span>
        </div>
        <div className="token">
          <small>{t("yourToken")}</small>
          <strong>{status.token}</strong>
        </div>
      </div>
      <div className="token-body">
        {yourTurn && (
          <div className="notice your-turn" role="status">
            {t("entry_called")}
          </div>
        )}
        {status.joined_remotely && !status.arrived_at && !yourTurn && (
          <div className="notice info" role="status">
            <MapPin size={18} aria-hidden="true" />
            {t("comeToDesk", { floor: status.floor, token: status.token })}
          </div>
        )}
        {status.doctor_status !== "available" && (
          <div className="notice warn" role="status">
            <Timer size={18} aria-hidden="true" />
            {t(doctorKey, { minutes: status.delay_minutes })}
          </div>
        )}
        <div className="stat-row">
          <div className="stat-box">
            <div className="label">
              <UsersRound size={15} aria-hidden="true" />
              {t("peopleAhead")}
            </div>
            <div className="value">{ahead ?? "—"}</div>
            {ahead !== null && ahead > 0 && (
              <div className="ahead-dots" aria-hidden="true">
                {Array.from({ length: Math.min(ahead, MAX_DOTS) }, (_, i) => (
                  <i key={i} />
                ))}
                <i className="you" />
              </div>
            )}
          </div>
          <div className="stat-box">
            <div className="label">
              <Hourglass size={15} aria-hidden="true" />
              {t("estimatedWait")}
            </div>
            <div className="value">{status.estimate?.display ?? "—"}</div>
          </div>
          <div className="stat-box">
            <div className="label">
              <Stethoscope size={15} aria-hidden="true" />
              {t("doctorStatus")}
            </div>
            <div className="value" style={{ fontSize: "1.05rem" }}>
              {t(doctorKey, { minutes: status.delay_minutes })}
            </div>
            <div className="muted small">{yourTurn ? "" : t(`entry_${status.status}`)}</div>
          </div>
        </div>
        <p className="updated" aria-live="polite">
          <RefreshCw size={13} aria-hidden="true" />
          {t("lastUpdated", { time: updated.toLocaleTimeString() })}
        </p>
        {error !== null && <ErrorMessage error={error} onRetry={refresh} />}
        {(status.status === "waiting" || status.status === "missed") && (
          <button type="button" className="quiet" onClick={() => setLeaving(true)}>
            <DoorOpen size={16} aria-hidden="true" />
            {t("leaveQueue")}
          </button>
        )}
      </div>
      <ConfirmDialog
        open={leaving}
        title={t("leaveQueueTitle", { token: status.token })}
        confirmLabel={t("leaveQueue")}
        cancelLabel={t("back")}
        busy={busy}
        danger
        onConfirm={() => void leave()}
        onClose={() => setLeaving(false)}
      >
        <p>{t("leaveQueueText")}</p>
      </ConfirmDialog>
    </section>
  );
}

/** Join a doctor's queue from the phone, without a booking (feature 38). */
function JoinQueue({ onJoined }) {
  const { user, t } = useSession();
  const patients = user.patients ?? [];
  const [options, setOptions] = useState(null);
  const [department, setDepartment] = useState("");
  const [patientId, setPatientId] = useState(patients[0]?.patient_id ?? null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api("/queue/virtual/options");
      setOptions(data.departments);
      setDepartment((current) => current || String(data.departments[0]?.department_id ?? ""));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function join(doctorId) {
    setBusy(true);
    setError(null);
    try {
      await api("/queue/virtual/join", { method: "POST", body: { doctor_id: doctorId, patient_id: patientId } });
      onJoined();
    } catch (err) {
      setError(err);
      await load();
    } finally {
      setBusy(false);
    }
  }

  if (patients.length === 0) return null;
  const dept = options?.find((d) => String(d.department_id) === department) ?? null;
  return (
    <section className="card" aria-labelledby="join-h" style={{ marginTop: "1rem" }}>
      <div className="card-head">
        <h2 id="join-h">
          <Smartphone size={20} aria-hidden="true" />
          {t("joinTitle")}
        </h2>
      </div>
      <p className="muted" style={{ marginBottom: "0.75rem" }}>
        {t("joinIntro")}
      </p>
      {error !== null && <ErrorMessage error={error} />}
      {options === null && error === null && <Loading />}
      {options?.length === 0 && <p className="muted">{t("noOpdToday")}</p>}
      {options && options.length > 0 && (
        <>
          <div className="row" style={{ alignItems: "flex-end" }}>
            {patients.length > 1 && (
              <div className="field" style={{ flex: "1 1 12rem" }}>
                <label htmlFor="join-patient">{t("forPatient")}</label>
                <select
                  id="join-patient"
                  value={patientId ?? ""}
                  onChange={(e) => setPatientId(Number(e.target.value))}
                >
                  {patients.map((p) => (
                    <option key={p.patient_id} value={p.patient_id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="field" style={{ flex: "1 1 12rem" }}>
              <label htmlFor="join-dept">{t("department")}</label>
              <select id="join-dept" value={department} onChange={(e) => setDepartment(e.target.value)}>
                {options.map((d) => (
                  <option key={d.department_id} value={d.department_id}>
                    {d.department}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {dept && (
            <>
              <p className="muted small">
                {dept.window_open
                  ? t("joinOpenUntil", { closes: dept.closes, floor: dept.floor })
                  : t("joinWindow", { opens: dept.opens, closes: dept.closes })}
              </p>
              <ul className="booking-list" aria-label={dept.department}>
                {dept.doctors.map((d) => (
                  <li key={d.doctor_id}>
                    <span className="booking-who">
                      <strong>{d.doctor_name}</strong>
                      <span className="muted small">
                        {d.state === "on_leave" || d.state === "unavailable" || d.state === "closed"
                          ? t(`state_${d.state}`, { minutes: 0 })
                          : `${t("waitingNow")}: ${d.waiting} · ${t("aboutMinutes", { minutes: d.estimated_wait_min ?? 0 })}`}
                        {d.full ? ` · ${t("onlineFull")}` : ""}
                      </span>
                    </span>
                    <button
                      type="button"
                      disabled={busy || !d.can_join || patientId === null}
                      aria-label={`${t("joinQueue")}: ${d.doctor_name}`}
                      onClick={() => void join(d.doctor_id)}
                    >
                      {t("joinQueue")}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}

/** S4: token, people ahead, wait estimate with range, doctor status, updated live. */
export default function QueueStatus() {
  const { user, t } = useSession();
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      setEntries((await api("/queue/mine")).entries);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <main className="narrow">
      <div className="page-header">
        <div>
          <h1>{t("queueTitle")}</h1>
          <p className="lead">{t("queueIntro")}</p>
        </div>
      </div>
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {entries === null && error === null && <Loading />}
      {entries?.length === 0 && (
        <div className="card empty">
          <span className="icon-tile" aria-hidden="true">
            <ListOrdered size={22} />
          </span>
          <span>{t("queueNone")}</span>
        </div>
      )}
      <div className="stack">
        {entries?.map((e) => (
          <EntryCard key={e.entry_id} initial={e} onLeft={() => void load()} />
        ))}
      </div>
      {entries !== null && (user.role === "caregiver" || entries.length === 0) && (
        <JoinQueue onJoined={() => void load()} />
      )}
    </main>
  );
}
