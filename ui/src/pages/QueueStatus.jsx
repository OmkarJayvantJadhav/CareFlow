import { useCallback, useEffect, useRef, useState } from "react";
import { api, socketUrl } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import { useSession } from "../session";

const POLL_MS = 5000;

function EntryCard({ initial }) {
  const { t } = useSession();
  const [status, setStatus] = useState(initial);
  const [updated, setUpdated] = useState(() => new Date());
  const [live, setLive] = useState(false);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api(`/queue/entries/${initial.entry_id}/status`));
      setUpdated(new Date());
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [initial.entry_id]);

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
  return (
    <section className="card" aria-labelledby={`entry-${status.entry_id}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 id={`entry-${status.entry_id}`} style={{ margin: 0 }}>
          {status.doctor_name}
          {status.patient_name ? ` · ${status.patient_name}` : ""}
        </h2>
        <span className="pill ok" title={live ? t("live") : t("polling")}>
          {live ? (
            <>
              <span className="live-dot" aria-hidden="true" /> {t("live")}
            </>
          ) : (
            t("polling")
          )}
        </span>
      </div>
      {status.doctor_status !== "available" && (
        <div className="notice" role="status">
          ⏱ {t(doctorKey, { minutes: status.delay_minutes })}
        </div>
      )}
      <div className="queue-card" style={{ marginTop: 12 }}>
        <div>
          <div className="muted">{t("token")}</div>
          <div className="stat">{status.token}</div>
        </div>
        <div>
          <div className="muted">{t("peopleAhead")}</div>
          <div className="stat">{status.ahead ?? "—"}</div>
        </div>
        <div>
          <div className="muted">{t("estimatedWait")}</div>
          <div className="stat" style={{ fontSize: "1.4rem" }}>
            {status.estimate?.display ?? "—"}
          </div>
        </div>
        <div>
          <div className="muted">{t("doctorStatus")}</div>
          <div>
            <strong>{t(doctorKey, { minutes: status.delay_minutes })}</strong>
          </div>
          <div className="muted">{t(`entry_${status.status}`)}</div>
        </div>
      </div>
      <p className="muted" aria-live="polite">
        {t("lastUpdated", { time: updated.toLocaleTimeString() })}
      </p>
      {error !== null && <ErrorMessage error={error} onRetry={refresh} />}
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
      <h1>{t("queueTitle")}</h1>
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {entries === null && error === null && <p className="muted">{t("loading")}</p>}
      {entries?.length === 0 && <p className="card">{t("queueNone")}</p>}
      <div style={{ display: "grid", gap: 12 }}>
        {entries?.map((e) => (
          <EntryCard key={e.entry_id} initial={e} />
        ))}
      </div>
    </main>
  );
}
