import { CalendarDays, CalendarPlus, ChevronRight, ListOrdered } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { longDate } from "../format";
import { useSession } from "../session";

/** Above the assistant: the patient's next appointment and today's queue token, from the same endpoints as
 * My appointments and Queue status. It shows nothing until both have answered, and nothing if either fails:
 * the chat must never wait for it. */
export default function PatientOverview() {
  const { user, lang, t } = useSession();
  const [data, setData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [histories, queue] = await Promise.all([
          Promise.all(user.patients.map((p) => api(`/patients/${p.patient_id}/appointments`))),
          api("/queue/mine"),
        ]);
        const upcoming = histories
          .flatMap((h) => (h.upcoming ?? []).map((a) => ({ ...a, patient_name: h.patient_name })))
          .filter((a) => a.status !== "cancelled")
          .sort((a, b) => `${a.date} ${a.time}`.localeCompare(`${b.date} ${b.time}`));
        if (!cancelled) setData({ next: upcoming[0] ?? null, entry: queue.entries?.[0] ?? null });
      } catch {
        if (!cancelled) setData(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user]);

  if (!data) return null;
  const { next, entry } = data;
  return (
    <section className="overview" aria-label={t("overviewLabel")}>
      {entry ? (
        <Link to="/queue" className="overview-card accent">
          <span className="icon-tile" aria-hidden="true">
            <ListOrdered size={18} />
          </span>
          <span className="overview-text">
            <span className="overview-label">{t("overviewQueue")}</span>
            <strong>
              {t("token")} {entry.token}
              {entry.ahead != null && ` · ${t("overviewAhead", { count: entry.ahead })}`}
            </strong>
            <span className="muted small">
              {entry.doctor_name}
              {entry.estimate?.display ? ` · ${entry.estimate.display}` : ""}
            </span>
          </span>
          <ChevronRight size={18} aria-hidden="true" className="overview-go" />
        </Link>
      ) : null}
      {next ? (
        <Link to="/appointments" className="overview-card">
          <span className="icon-tile" aria-hidden="true">
            <CalendarDays size={18} />
          </span>
          <span className="overview-text">
            <span className="overview-label">{t("overviewNext")}</span>
            <strong>
              {longDate(next.date, lang)} · {next.time}
            </strong>
            <span className="muted small">
              {next.doctor_name}
              {next.department ? ` · ${next.department}` : ""}
            </span>
          </span>
          <ChevronRight size={18} aria-hidden="true" className="overview-go" />
        </Link>
      ) : (
        <Link to="/book" className="overview-card">
          <span className="icon-tile" aria-hidden="true">
            <CalendarPlus size={18} />
          </span>
          <span className="overview-text">
            <span className="overview-label">{t("overviewNext")}</span>
            <strong>{t("overviewNone")}</strong>
            <span className="muted small">{t("bookNew")}</span>
          </span>
          <ChevronRight size={18} aria-hidden="true" className="overview-go" />
        </Link>
      )}
    </section>
  );
}
