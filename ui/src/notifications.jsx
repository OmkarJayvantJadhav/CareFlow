import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { useSession } from "./session";

const POLL_MS = 60000;
const NotificationsContext = createContext({ unread: 0, refresh: () => {} });

/** The unread count behind the bell, refreshed every minute for patients and caregivers. */
export function NotificationsProvider({ children }) {
  const { user } = useSession();
  const [unread, setUnread] = useState(0);
  const enabled = user?.role === "patient" || user?.role === "caregiver";

  const refresh = useCallback(() => {
    if (!enabled) return;
    api("/me/notifications")
      .then((d) => setUnread(d.unread))
      .catch(() => {
        /* the badge is a convenience; the page itself shows errors */
      });
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      setUnread(0);
      return;
    }
    refresh();
    const timer = window.setInterval(refresh, POLL_MS);
    return () => window.clearInterval(timer);
  }, [enabled, refresh]);

  const value = useMemo(() => ({ unread, refresh }), [unread, refresh]);
  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>;
}

export function useNotifications() {
  return useContext(NotificationsContext);
}
