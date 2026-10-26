import { CircleCheck, Contact, Eye, Phone, Search, ShieldX, UserRound } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { CategoryBadges, CustomFields, useRegistrationFields } from "../components/Registration";
import { longDate } from "../format";
import { LANGS } from "../i18n";
import { useSession } from "../session";

function formFrom(record, fields) {
  const keys = new Set(fields.map((f) => f.key));
  return {
    name: record.name,
    birth_year: String(record.birth_year),
    phone: "",
    language: record.language,
    pregnant: record.pregnant,
    disability: record.disability,
    answers: Object.fromEntries(Object.entries(record.answers).filter(([k]) => keys.has(k))),
  };
}

function Visits({ title, visits }) {
  const { lang, t } = useSession();
  return (
    <div>
      <h3 className="h4">{title}</h3>
      {visits.length === 0 ? (
        <p className="muted small">{t("none")}</p>
      ) : (
        <ul className="plain-list small">
          {visits.map((v) => (
            <li key={v.appointment_id}>
              {longDate(v.date, lang)}, {v.time} — {v.doctor_name} ({v.department})
              {v.status !== "booked" && v.status !== "rescheduled" && (
                <span className="muted"> · {t(`status_${v.status}`)}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** One patient's record: details staff can correct, the full number on request, visits; erasure for admins. */
function Record({ record, onChanged, onErased }) {
  const { user, t } = useSession();
  const fields = useRegistrationFields();
  const [form, setForm] = useState(() => formFrom(record, fields));
  const [formFor, setFormFor] = useState(fields);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const [phone, setPhone] = useState(null);
  const [phoneError, setPhoneError] = useState(null);
  const [erasing, setErasing] = useState(false);
  const [reason, setReason] = useState("");
  const [eraseError, setEraseError] = useState(null);
  if (formFor !== fields) {
    // The registration questions arrived after the record: keep only answers to active questions.
    setFormFor(fields);
    setForm(formFrom(record, fields));
  }
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const body = {
        name: form.name.trim(),
        birth_year: Number(form.birth_year),
        language: form.language,
        pregnant: form.pregnant,
        disability: form.disability,
        answers: form.answers,
      };
      if (form.phone.trim()) body.phone = form.phone;
      const updated = await api(`/staff/patients/${record.patient_id}`, { method: "PATCH", body });
      setForm(formFrom(updated, fields));
      setPhone(null);
      setSaved(true);
      onChanged(updated);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function showPhone() {
    setPhoneError(null);
    try {
      setPhone((await api(`/staff/patients/${record.patient_id}/phone`, { method: "POST" })).phone);
    } catch (err) {
      setPhoneError(err);
    }
  }

  async function erase() {
    setBusy(true);
    setEraseError(null);
    try {
      await api(`/admin/patients/${record.patient_id}/erase`, { method: "POST", body: { reason } });
      setErasing(false);
      onErased(record);
    } catch (err) {
      setEraseError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card stack" aria-labelledby="record-h">
      <div className="card-head">
        <div>
          <h2 id="record-h">
            <UserRound size={20} aria-hidden="true" />
            {record.name}
          </h2>
          <p className="muted small">
            {t("recordNumber", { id: record.patient_id })}
            {record.username && ` · @${record.username}`}
          </p>
        </div>
        <CategoryBadges categories={record.categories} />
      </div>

      <div className="phone-row">
        <Phone size={18} aria-hidden="true" />
        {phone ? <a href={`tel:${phone.replace(/\s/g, "")}`}>{phone}</a> : <span>{record.phone_masked}</span>}
        {!phone && record.has_full_phone && (
          <button type="button" className="secondary" onClick={showPhone}>
            <Eye size={16} aria-hidden="true" />
            {t("showNumber")}
          </button>
        )}
        {!record.has_full_phone && <span className="muted small">{t("onlyMaskedNumber")}</span>}
      </div>
      {phone && <p className="muted small">{t("numberShownNote")}</p>}
      {phoneError !== null && <ErrorMessage error={phoneError} />}

      <form onSubmit={save} aria-label={t("editPatient")}>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="pt-name">{t("fullName")}</label>
            <input id="pt-name" required minLength={2} maxLength={120} value={form.name} onChange={set("name")} />
          </div>
          <div className="field">
            <label htmlFor="pt-year">{t("walkInYear")}</label>
            <input
              id="pt-year"
              required
              inputMode="numeric"
              pattern="(19|20)[0-9]{2}"
              maxLength={4}
              value={form.birth_year}
              onChange={set("birth_year")}
            />
          </div>
          <div className="field">
            <label htmlFor="pt-phone">{t("newMobile")}</label>
            <input
              id="pt-phone"
              type="tel"
              inputMode="tel"
              maxLength={20}
              aria-describedby="pt-phone-hint"
              value={form.phone}
              onChange={set("phone")}
            />
            <p id="pt-phone-hint" className="hint">
              {t("newMobileHint")}
            </p>
          </div>
          <div className="field">
            <label htmlFor="pt-lang">{t("preferredLanguage")}</label>
            <select id="pt-lang" value={form.language} onChange={set("language")}>
              {LANGS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="check-group">
          <label className="check">
            <input
              type="checkbox"
              checked={form.pregnant}
              onChange={(e) => setForm({ ...form, pregnant: e.target.checked })}
            />
            {t("category_pregnant")}
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={form.disability}
              onChange={(e) => setForm({ ...form, disability: e.target.checked })}
            />
            {t("category_disability")}
          </label>
        </div>
        <CustomFields
          fields={fields}
          answers={form.answers}
          onChange={(answers) => setForm({ ...form, answers })}
          idPrefix="pt"
        />
        {error !== null && <ErrorMessage error={error} />}
        {saved && (
          <p className="notice" role="status">
            <CircleCheck size={18} aria-hidden="true" />
            {t("saved")}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {busy ? t("saving") : t("save")}
        </button>
      </form>

      <div className="grid-2">
        <Visits title={t("upcomingVisits")} visits={record.upcoming} />
        <Visits title={t("recentVisits")} visits={record.past} />
      </div>
      <p className="muted small">
        {t("consentSummary", {
          reuse: record.consent.reuse_registration ? t("allowed") : t("withdrawn"),
          reminders: record.consent.reminders ? t("on") : t("off"),
        })}
        {record.caregivers.length > 0 &&
          ` · ${t("caregiversList", { names: record.caregivers.map((c) => c.name).join(", ") })}`}
      </p>

      {user.role === "admin" && (
        <div className="danger-zone">
          <h3 className="h4">{t("eraseTitle")}</h3>
          <p className="muted small">{t("eraseHelp")}</p>
          <button type="button" className="danger-outline" onClick={() => setErasing(true)}>
            <ShieldX size={16} aria-hidden="true" />
            {t("eraseButton")}
          </button>
        </div>
      )}
      <ConfirmDialog
        open={erasing}
        title={t("eraseTitle")}
        confirmLabel={t("eraseConfirm")}
        cancelLabel={t("cancel")}
        busy={busy}
        danger
        onConfirm={erase}
        onClose={() => setErasing(false)}
      >
        <p>{t("eraseText", { name: record.name })}</p>
        <div className="field">
          <label htmlFor="erase-reason">{t("eraseReason")}</label>
          <input id="erase-reason" maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        {eraseError !== null && <ErrorMessage error={eraseError} />}
      </ConfirmDialog>
    </article>
  );
}

/** Staff and admins find a patient's record, correct it and see their visits (phase 7C). */
export default function Patients() {
  const { t } = useSession();
  const [q, setQ] = useState("");
  const [found, setFound] = useState(null);
  const [error, setError] = useState(null);
  const [record, setRecord] = useState(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState(null);

  async function search(e) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setRecord(null);
    try {
      setFound(await api(`/staff/patients?q=${encodeURIComponent(q.trim())}`));
    } catch (err) {
      setError(err);
    }
  }

  async function open(patientId) {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      setRecord(await api(`/staff/patients/${patientId}`));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("patientsTitle")}</h1>
          <p className="lead">{t("patientsIntro")}</p>
        </div>
      </div>
      <div className="stack">
        <form className="card row account-filters" role="search" onSubmit={search}>
          <div className="field grow">
            <label htmlFor="pt-search">{t("patientSearch")}</label>
            <input
              id="pt-search"
              type="search"
              required
              minLength={2}
              maxLength={60}
              aria-describedby="pt-search-hint"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <p id="pt-search-hint" className="hint">
              {t("patientSearchHint")}
            </p>
          </div>
          <button type="submit">
            <Search size={16} aria-hidden="true" />
            {t("search")}
          </button>
        </form>
        {error !== null && <ErrorMessage error={error} />}
        {notice && (
          <p className="notice" role="status">
            <CircleCheck size={18} aria-hidden="true" />
            {notice}
          </p>
        )}
        {found && (
          <section className="card" aria-labelledby="found-h">
            <h2 id="found-h" className="h4">
              {t("patientsFound", { count: found.patients.length })}
            </h2>
            {found.patients.length === 0 ? (
              <p className="muted">{t("noPatientsFound")}</p>
            ) : (
              <ul className="patient-results">
                {found.patients.map((p) => (
                  <li key={p.patient_id}>
                    <button
                      type="button"
                      className="patient-result"
                      aria-pressed={record?.patient_id === p.patient_id}
                      onClick={() => open(p.patient_id)}
                    >
                      <Contact size={18} aria-hidden="true" />
                      <span>
                        <strong>{p.name}</strong>
                        <span className="muted small">
                          {" "}
                          · {p.birth_year} · {p.phone_masked}
                          {p.username && ` · @${p.username}`}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {found.more && <p className="muted small">{t("patientsMore")}</p>}
          </section>
        )}
        {loading && <Loading />}
        {record && !loading && (
          <Record
            key={record.patient_id}
            record={record}
            onChanged={setRecord}
            onErased={(r) => {
              setRecord(null);
              setFound((f) => f && { ...f, patients: f.patients.filter((p) => p.patient_id !== r.patient_id) });
              setNotice(t("erasedNotice", { name: r.name }));
            }}
          />
        )}
      </div>
    </main>
  );
}
