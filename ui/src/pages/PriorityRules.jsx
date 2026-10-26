import { CircleCheck, Scale } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { useSession } from "../session";

const LEVELS = [0, 1, 2, 3];

/** Configurable queue-priority rules (feature 51): how much priority each patient category gets. */
export default function PriorityRules() {
  const { t } = useSession();
  const [weights, setWeights] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    try {
      const { rules } = await api("/admin/priority-rules");
      setWeights(Object.fromEntries(rules.map((r) => [r.category, r.weight])));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const result = await api("/admin/priority-rules", { method: "PUT", body: { weights } });
      setWeights(Object.fromEntries(result.rules.map((r) => [r.category, r.weight])));
      setSaved(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="narrow">
      <div className="page-header">
        <div>
          <h1>{t("priorityRulesTitle")}</h1>
          <p className="lead">{t("priorityRulesIntro")}</p>
        </div>
      </div>
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {weights === null && error === null && <Loading />}
      {weights && (
        <form className="card" onSubmit={save} aria-labelledby="rules-h">
          <div className="card-head">
            <h2 id="rules-h">
              <Scale size={20} aria-hidden="true" />
              {t("priorityByCategory")}
            </h2>
          </div>
          {Object.keys(weights).map((category) => (
            <div key={category} className="consent-row">
              <div>
                <strong>{t(`category_${category}`)}</strong>
                <p className="muted small">{t(`categoryRule_${category}`)}</p>
              </div>
              <div className="field" style={{ margin: 0, flex: "0 1 11rem", minWidth: 0 }}>
                <label className="sr-only" htmlFor={`rule-${category}`}>
                  {t("priorityFor", { token: t(`category_${category}`) })}
                </label>
                <select
                  id={`rule-${category}`}
                  value={weights[category]}
                  onChange={(e) => {
                    setSaved(false);
                    setWeights({ ...weights, [category]: Number(e.target.value) });
                  }}
                >
                  {LEVELS.map((p) => (
                    <option key={p} value={p}>
                      {t(`priorityLevel_${p}`)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          ))}
          <p className="muted small">{t("priorityRulesNote")}</p>
          <div className="row" style={{ marginTop: "1rem" }}>
            <button type="submit" disabled={busy}>
              {t("save")}
            </button>
            {saved && (
              <span className="notice" role="status" style={{ margin: 0 }}>
                <CircleCheck size={16} aria-hidden="true" />
                {t("rulesSaved")}
              </span>
            )}
          </div>
        </form>
      )}
    </main>
  );
}
