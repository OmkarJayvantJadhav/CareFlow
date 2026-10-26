import { CircleCheck, Scale } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { useSession } from "../session";
import ErrorMessage from "./ErrorMessage";
import Loading from "./Loading";

const ORDER = [
  "booking_lead_minutes",
  "booking_horizon_days",
  "reschedule_hours",
  "cancel_hours",
  "waitlist_hold_hours",
  "late_grace_minutes",
  "check_in_opens_minutes",
  "virtual_join_opens_minutes",
  "virtual_join_closes_minutes",
  "virtual_queue_cap",
];

/** The hospital's booking and queue rules; saving updates every document that states them. */
export default function PolicyRules() {
  const { reloadConfig, t } = useSession();
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);

  useEffect(() => {
    api("/admin/policy")
      .then((d) => {
        setData(d);
        setForm(Object.fromEntries(ORDER.map((k) => [k, String(d.values[k])])));
      })
      .catch(setError);
  }, []);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const values = Object.fromEntries(ORDER.map((k) => [k, Number(form[k])]));
      const result = await api("/admin/policy", { method: "PUT", body: { values } });
      setData(result);
      setDone(result.documents_updated);
      await reloadConfig();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={save} aria-labelledby="rules-h">
      <div className="card-head">
        <h2 id="rules-h">
          <Scale size={20} aria-hidden="true" />
          {t("rulesTitle")}
        </h2>
      </div>
      <p className="muted small card-intro">{t("rulesIntro")}</p>
      {form === null && error === null && <Loading />}
      {form && (
        <div className="grid-2">
          {ORDER.map((key) => {
            const limit = data.limits[key];
            return (
              <div className="field" key={key}>
                <label htmlFor={`rule-${key}`}>{t(`rule_${key}`)}</label>
                <input
                  id={`rule-${key}`}
                  type="number"
                  inputMode="numeric"
                  required
                  min={limit.min}
                  max={limit.max}
                  aria-describedby={`rule-${key}-hint`}
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                />
                <p id={`rule-${key}-hint`} className="hint">
                  {t("ruleLimits", {
                    min: limit.min,
                    max: limit.max,
                    unit: t(`unit_${limit.unit}`),
                    standard: data.defaults[key],
                  })}
                </p>
              </div>
            );
          })}
        </div>
      )}
      {error !== null && <ErrorMessage error={error} />}
      {done !== null && (
        <p className="notice" role="status">
          <CircleCheck size={18} aria-hidden="true" />
          {t("policySaved", { count: done })}
        </p>
      )}
      {form && (
        <button type="submit" disabled={busy}>
          {busy ? t("savingIndex") : t("save")}
        </button>
      )}
    </form>
  );
}
