// Shared registration pieces (phase 6B): category badges and the hospital's extra registration questions.
import { useEffect, useState } from "react";
import { api } from "../api";
import { useSession } from "../session";

const CATEGORY_TONE = { senior: "info", child: "info", pregnant: "warn", disability: "warn" };

export function CategoryBadges({ categories }) {
  const { t } = useSession();
  if (!categories || categories.length === 0) return null;
  return (
    <span className="category-badges">
      {categories.map((c) => (
        <span key={c} className={`badge ${CATEGORY_TONE[c] ?? ""}`}>
          {t(`category_${c}`)}
        </span>
      ))}
    </span>
  );
}

/** The active extra questions, loaded once (the list is public: the sign-up form needs it). */
export function useRegistrationFields() {
  const [fields, setFields] = useState([]);
  useEffect(() => {
    api("/registration-fields")
      .then((d) => setFields(d.fields))
      .catch(() => setFields([]));
  }, []);
  return fields;
}

/** Inputs for the extra questions; `answers` is {key: value}. The server checks the answers again. */
export function CustomFields({ fields, answers, onChange, idPrefix }) {
  const { lang, t } = useSession();
  if (fields.length === 0) return null;
  const set = (key, value) => onChange({ ...answers, [key]: value });
  return fields.map((f) => {
    const id = `${idPrefix}-${f.key}`;
    const label = f.labels[lang] || f.labels.en;
    const value = answers[f.key] ?? "";
    return (
      <div key={f.key} className="field">
        <label htmlFor={id}>
          {label}
          {!f.required && <span className="muted small"> ({t("optional")})</span>}
        </label>
        {f.kind === "choice" || f.kind === "yes_no" ? (
          <select id={id} required={f.required} value={value} onChange={(e) => set(f.key, e.target.value)}>
            <option value="">{t("chooseOne")}</option>
            {(f.kind === "yes_no" ? ["yes", "no"] : f.options).map((o) => (
              <option key={o} value={o}>
                {f.kind === "yes_no" ? t(o === "yes" ? "yes" : "no") : o}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={id}
            required={f.required}
            maxLength={200}
            inputMode={f.kind === "number" ? "decimal" : undefined}
            pattern={f.kind === "number" ? "-?[0-9]+(\\.[0-9]+)?" : undefined}
            value={value}
            onChange={(e) => set(f.key, e.target.value)}
          />
        )}
      </div>
    );
  });
}
