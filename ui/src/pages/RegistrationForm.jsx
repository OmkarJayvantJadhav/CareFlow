import { CircleCheck, ClipboardPen, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { useSession } from "../session";

const KINDS = ["text", "number", "choice", "yes_no"];
const EMPTY = { en: "", hi: "", mr: "", kind: "text", options: "", required: false };

/** S16: the hospital's extra registration questions, asked at sign-up and at the desk (features 26, 28). */
export default function RegistrationForm() {
  const { lang, t } = useSession();
  const [fields, setFields] = useState(null);
  const [draft, setDraft] = useState(EMPTY);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setFields((await api("/admin/registration-fields")).fields);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const body = (f) => ({
    labels: { en: f.en, hi: f.hi, mr: f.mr },
    kind: f.kind,
    options:
      f.kind === "choice"
        ? f.options
            .split(",")
            .map((o) => o.trim())
            .filter(Boolean)
        : [],
    required: f.required,
    active: f.active ?? true,
  });

  async function save(fn, message) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(message);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const update = (f, changes) =>
    save(
      () =>
        api(`/admin/registration-fields/${f.field_id}`, {
          method: "PATCH",
          body: body({
            ...f.labels,
            kind: f.kind,
            options: f.options.join(","),
            required: f.required,
            active: f.active,
            ...changes,
          }),
        }),
      t("saved"),
    );

  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("registrationFormTitle")}</h1>
          <p className="lead">{t("registrationFormIntro")}</p>
        </div>
      </div>
      {notice && (
        <div className="notice" role="status">
          <CircleCheck size={18} aria-hidden="true" />
          {notice}
        </div>
      )}
      {error !== null && <ErrorMessage error={error} />}
      {fields === null && error === null && <Loading />}
      {fields && (
        <section className="card" aria-labelledby="fields-h">
          <div className="card-head">
            <h2 id="fields-h">
              <ClipboardPen size={20} aria-hidden="true" />
              {t("currentFields")}
            </h2>
          </div>
          {fields.length === 0 && <p className="muted">{t("noFields")}</p>}
          <ul className="booking-list">
            {fields.map((f) => (
              <li key={f.field_id}>
                <span className="booking-who">
                  <strong>{f.labels[lang] || f.labels.en}</strong>
                  <span className="muted small">
                    {t(`kind_field_${f.kind}`)}
                    {f.options.length > 0 && ` · ${f.options.join(", ")}`}
                  </span>
                </span>
                <span className="row">
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={f.required}
                      disabled={busy}
                      onChange={(e) => void update(f, { required: e.target.checked })}
                    />
                    {t("requiredField")}
                  </label>
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={f.active}
                      disabled={busy}
                      onChange={(e) => void update(f, { active: e.target.checked })}
                    />
                    {t("shownField")}
                  </label>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="card" aria-labelledby="new-field-h" style={{ marginTop: "1rem" }}>
        <div className="card-head">
          <h2 id="new-field-h">
            <Plus size={20} aria-hidden="true" />
            {t("addField")}
          </h2>
        </div>
        <form
          className="book-form"
          onSubmit={(e) => {
            e.preventDefault();
            void save(async () => {
              await api("/admin/registration-fields", { method: "POST", body: body(draft) });
              setDraft(EMPTY);
            }, t("fieldAdded"));
          }}
        >
          {["en", "hi", "mr"].map((code) => (
            <div key={code} className="field">
              <label htmlFor={`nf-${code}`}>{t(`fieldLabel_${code}`)}</label>
              <input
                id={`nf-${code}`}
                lang={code}
                required
                maxLength={80}
                value={draft[code]}
                onChange={(e) => setDraft({ ...draft, [code]: e.target.value })}
              />
            </div>
          ))}
          <div className="field">
            <label htmlFor="nf-kind">{t("fieldKind")}</label>
            <select id="nf-kind" value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value })}>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(`kind_field_${k}`)}
                </option>
              ))}
            </select>
          </div>
          {draft.kind === "choice" && (
            <div className="field span-all">
              <label htmlFor="nf-options">{t("fieldOptions")}</label>
              <input
                id="nf-options"
                required
                maxLength={600}
                aria-describedby="nf-options-hint"
                value={draft.options}
                onChange={(e) => setDraft({ ...draft, options: e.target.value })}
              />
              <p id="nf-options-hint" className="hint">
                {t("fieldOptionsHint")}
              </p>
            </div>
          )}
          <div className="field span-all">
            <label className="check">
              <input
                type="checkbox"
                checked={draft.required}
                onChange={(e) => setDraft({ ...draft, required: e.target.checked })}
              />
              {t("requiredField")}
            </label>
          </div>
          <div className="span-all">
            <button type="submit" disabled={busy}>
              <Plus size={18} aria-hidden="true" />
              {t("addField")}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
