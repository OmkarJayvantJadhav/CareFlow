import { useSession } from "../session";

export default function Loading() {
  const { t } = useSession();
  return (
    <div className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      {t("loading")}
    </div>
  );
}
