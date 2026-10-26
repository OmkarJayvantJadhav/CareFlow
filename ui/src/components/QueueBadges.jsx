import { Star } from "lucide-react";
import { useSession } from "../session";
import { CategoryBadges } from "./Registration";

/** Where a queue entry came from (online, moved here), its priority and the patient's categories. */
export function EntryBadges({ entry }) {
  const { t } = useSession();
  return (
    <>
      {entry.effective_priority > 0 && (
        <span className="badge warn">
          <Star size={12} aria-hidden="true" /> {t("priority")} {entry.effective_priority}
          {entry.priority < entry.effective_priority ? ` · ${t("priorityAuto")}` : ""}
        </span>
      )}
      {entry.joined_remotely && !entry.arrived_at && <span className="badge info">{t("onlineNotHere")}</span>}
      {entry.joined_remotely && entry.arrived_at && <span className="badge">{t("onlineArrived")}</span>}
      {entry.transferred_from_id && <span className="badge">{t("movedHere")}</span>}
      <CategoryBadges categories={entry.categories} />
    </>
  );
}
