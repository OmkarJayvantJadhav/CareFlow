import { CircleCheck, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import OwnData from "../components/OwnData";
import { CaregiverAccess, PatientPrivacy } from "../components/Privacy";
import Loading from "../components/Loading";
import { initials, longDate } from "../format";
import { LANGS } from "../i18n";
import { useSession } from "../session";
import { PasswordCard } from "./Account";

/** S12: the patient's own details (feature 29); the phone number and e-mail address are kept encrypted. */
export default function Profile() {
  const { user } = useSession();
  return user.role === "caregiver" ? <CaregiverProfile /> : <PatientProfile />;
}

function CaregiverProfile() {
  const { t } = useSession();
  return (
    <main className="narrow">
      <div className="page-header">
        <div>
          <h1>{t("profileTitle")}</h1>
          <p className="lead">{t("caregiverProfileIntro")}</p>
        </div>
      </div>
      <CaregiverAccess />
      <PasswordCard />
      <OwnData />
    </main>
  );
}

function PatientProfile() {
  const { t, lang, refreshUser, config } = useSession();
  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState(null);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/me/profile")
      .then((p) => {
        setProfile(p);
        setForm({
          name: p.name,
          birth_year: String(p.birth_year),
          phone: "",
          language: p.language,
          email: "",
          removeEmail: false,
          contact_by: p.contact_by,
        });
      })
      .catch(setError);
  }, []);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const body = { name: form.name, birth_year: Number(form.birth_year), language: form.language };
      if (form.phone.trim()) body.phone = form.phone;
      if (form.removeEmail) body.email = "";
      else if (form.email.trim()) body.email = form.email;
      if (showContact) body.contact_by = form.removeEmail && form.contact_by === "email" ? "sms" : form.contact_by;
      const p = await api("/me/profile", { method: "PATCH", body });
      setProfile(p);
      setForm({ ...form, name: p.name, phone: "", email: "", removeEmail: false, contact_by: p.contact_by });
      setSaved(true);
      await refreshUser();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  const channels = config?.messaging ?? {};
  // Messages outside the app: only when the hospital sends them, or the patient has already chosen.
  const showContact = Boolean(
    profile && (channels.sms || channels.email || profile.email_masked || profile.contact_by !== "sms"),
  );
  const hasEmail = Boolean((profile?.email_masked && !form?.removeEmail) || form?.email.trim());
  return (
    <main className="narrow">
      <div className="page-header">
        <div>
          <h1>{t("profileTitle")}</h1>
          <p className="lead">{t("profileIntro")}</p>
        </div>
      </div>
      {profile === null && error === null && <Loading />}
      {profile === null && error !== null && <ErrorMessage error={error} />}
      {profile && form && (
        <>
          <section className="card" aria-labelledby="profile-h">
            <div className="card-head">
              <div className="row">
                <span className="avatar lg" aria-hidden="true">
                  {initials(profile.name)}
                </span>
                <div>
                  <h2 id="profile-h">
                    <UserRound
                      size={18}
                      aria-hidden="true"
                      style={{ verticalAlign: "-3px", marginRight: "0.375rem" }}
                    />
                    {profile.name}
                  </h2>
                  <div className="muted small">
                    @{profile.username}
                    {profile.member_since &&
                      ` · ${t("memberSince", { date: longDate(profile.member_since.slice(0, 10), lang) })}`}
                  </div>
                </div>
              </div>
            </div>
            <form onSubmit={save}>
              <div className="field">
                <label htmlFor="pf-name">{t("fullName")}</label>
                <input id="pf-name" required minLength={2} maxLength={80} value={form.name} onChange={set("name")} />
              </div>
              <div className="row" style={{ alignItems: "flex-start" }}>
                <div className="field" style={{ flex: "1 1 7rem" }}>
                  <label htmlFor="pf-year">{t("walkInYear")}</label>
                  <input
                    id="pf-year"
                    required
                    inputMode="numeric"
                    pattern="(19|20)[0-9]{2}"
                    maxLength={4}
                    value={form.birth_year}
                    onChange={set("birth_year")}
                  />
                </div>
                <div className="field" style={{ flex: "1 1 10rem" }}>
                  <label htmlFor="pf-lang">{t("preferredLanguage")}</label>
                  <select id="pf-lang" value={form.language} onChange={set("language")}>
                    {LANGS.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="field">
                <label htmlFor="pf-phone">{t("mobile")}</label>
                <input
                  id="pf-phone"
                  type="tel"
                  inputMode="tel"
                  pattern="(\+?91[ \-]?)?[6-9][0-9 \-]{9,12}"
                  aria-describedby="pf-phone-hint"
                  value={form.phone}
                  onChange={set("phone")}
                />
                <p id="pf-phone-hint" className="hint">
                  {t("phoneOnFile", { phone: profile.phone_masked })} {t("mobileHint")}
                </p>
              </div>
              {showContact && (
                <>
                  <div className="field">
                    <label htmlFor="pf-email">{t("emailOptional")}</label>
                    <input
                      id="pf-email"
                      type="email"
                      inputMode="email"
                      autoComplete="email"
                      maxLength={254}
                      aria-describedby="pf-email-hint"
                      value={form.email}
                      disabled={form.removeEmail}
                      onChange={set("email")}
                    />
                    <p id="pf-email-hint" className="hint">
                      {profile.email_masked ? `${t("emailOnFile", { email: profile.email_masked })} ` : ""}
                      {t("emailHint")}
                    </p>
                    {profile.email_masked && (
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={form.removeEmail}
                          onChange={(e) => setForm({ ...form, removeEmail: e.target.checked, email: "" })}
                        />
                        {t("removeEmail")}
                      </label>
                    )}
                  </div>
                  <fieldset className="plain">
                    <legend>{t("contactBy")}</legend>
                    {["sms", "email", "app"].map((choice) => (
                      <label className="check" key={choice}>
                        <input
                          type="radio"
                          name="contact_by"
                          value={choice}
                          checked={form.contact_by === choice}
                          disabled={choice === "email" && !hasEmail}
                          onChange={set("contact_by")}
                        />
                        {t(`contact_${choice}`)}
                      </label>
                    ))}
                    <p className="hint">{t("contactHint")}</p>
                  </fieldset>
                </>
              )}
              {error !== null && <ErrorMessage error={error} />}
              {saved && (
                <p className="notice" role="status">
                  <CircleCheck size={18} aria-hidden="true" />
                  {t("saved")}
                </p>
              )}
              <button type="submit" disabled={busy}>
                {t("save")}
              </button>
            </form>
          </section>

          <PasswordCard />
          <PatientPrivacy />
          <OwnData />
        </>
      )}
    </main>
  );
}
