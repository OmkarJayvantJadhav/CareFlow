import { Hourglass, ListOrdered, RefreshCw, Stethoscope, Timer, UsersRound } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, socketUrl } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { useSession } from "../session";

const MAX_DOTS = 12;

const POLL_MS = 5000;

function EntryCard({ initial }) {
  const { t } = useSession();
  const [status, setStatus] = useState(initial);
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
      </div>
    </section>
  );
}

/** S4: token, people ahead, wait estimate with range, doctor status, updated live. */
export default function QueueStatus() {
  const { t } = useSession();
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
      <div style={{ display: "grid", gap: "1rem" }}>
        {entries?.map((e) => (
          <EntryCard key={e.entry_id} initial={e} />
        ))}
      </div>
    </main>
  );
}
