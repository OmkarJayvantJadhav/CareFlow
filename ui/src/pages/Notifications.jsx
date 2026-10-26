import {
  AlarmClock,
  ArrowRightLeft,
  Bell,
  CalendarX2,
  CheckCheck,
  Info,
  ListOrdered,
  RotateCcw,
  Timer,
  UserX,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { useNotifications } from "../notifications";
import { useSession } from "../session";

const KIND = {
  info: { icon: Info, tone: "info" },
  reminder_day: { icon: AlarmClock, tone: "" },
  reminder_soon: { icon: AlarmClock, tone: "" },
  rebook: { icon: RotateCcw, tone: "warn" },
  unavailable: { icon: UserX, tone: "danger" },
  turn_near: { icon: ListOrdered, tone: "" },
  transfer: { icon: ArrowRightLeft, tone: "info" },
  delay: { icon: Timer, tone: "warn" },
};

/** S13: reminders, rebooking offers and other messages (stored, as the demo sends no SMS). */
export default function Notifications() {
  const { t } = useSession();
  const { refresh: refreshBadge } = useNotifications();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setData(await api("/me/notifications"));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function markAll() {
    try {
      await api("/me/notifications/read", { method: "POST" });
      await load();
      refreshBadge();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <main className="narrow">
      <div className="page-header">
        <div>
          <h1>{t("notificationsTitle")}</h1>
          <p className="lead">{t("notificationsNote")}</p>
        </div>
        {data?.unread > 0 && (
          <button type="button" className="secondary" onClick={() => void markAll()}>
            <CheckCheck size={16} aria-hidden="true" />
            {t("markAllRead")}
          </button>
        )}
      </div>
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {data === null && error === null && <Loading />}
      {data?.notifications.length === 0 && (
        <div className="card empty">
          <span className="icon-tile" aria-hidden="true">
            <Bell size={22} />
          </span>
          <span>{t("notificationsNone")}</span>
        </div>
      )}
      {data && data.notifications.length > 0 && (
        <ul className="card note-list">
          {data.notifications.map((n) => {
            const { icon: Icon, tone } = KIND[n.kind] ?? KIND.info;
            return (
              <li key={n.notification_id} className={n.read ? "" : "unread"}>
                <span className={`icon-tile ${tone}`} aria-hidden="true">
                  <Icon size={18} />
                </span>
                <div className="grow">
                  <div className="row">
                    <span className={`badge ${tone}`}>{t(`kind_${n.kind}`)}</span>
                    <span className="muted small">{new Date(n.sent_at).toLocaleString()}</span>
                    {!n.read && <span className="sr-only">(unread)</span>}
                  </div>
                  <p>{n.message}</p>
                  {(n.kind === "rebook" || n.kind === "unavailable") && (
                    <Link to="/appointments" className="small">
                      <CalendarX2 size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />
                      {t("navAppointments")}
                    </Link>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
