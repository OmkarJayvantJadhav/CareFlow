import { Eye, EyeOff, LogIn, UserPlus } from "lucide-react";
import { useState } from "react";
import { LANGS } from "../i18n";
import { useSession } from "../session";
import ErrorMessage from "./ErrorMessage";
import { CustomFields, useRegistrationFields } from "./Registration";

export function PasswordField({ id, value, onChange, autoComplete, hint, label }) {
  const { t } = useSession();
  const [shown, setShown] = useState(false);
  return (
    <div className="field">
      <label htmlFor={id}>{label ?? t("password")}</label>
      <div className="password-wrap">
        <input
          id={id}
          type={shown ? "text" : "password"}
          required
          minLength={autoComplete === "new-password" ? 8 : 1}
          maxLength={128}
          autoComplete={autoComplete}
          value={value}
          aria-describedby={hint ? `${id}-hint` : undefined}
          onChange={(e) => onChange(e.target.value)}
        />
        <button
          type="button"
          className="ghost"
          aria-label={shown ? t("hidePassword") : t("showPassword")}
          aria-pressed={shown}
          onClick={() => setShown(!shown)}
        >
          {shown ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
        </button>
      </div>
      {hint && (
        <p id={`${id}-hint`} className="hint">
          {hint}
        </p>
      )}
    </div>
  );
}

/** Username and password sign-in. */
export function LoginForm({ onDone }) {
  const { logIn, t } = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(await logIn(username.trim(), password));
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} aria-label={t("logIn")}>
      <div className="field">
        <label htmlFor="login-username">{t("username")}</label>
        <input
          id="login-username"
          required
          maxLength={60}
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </div>
      <PasswordField id="login-password" value={password} onChange={setPassword} autoComplete="current-password" />
      {error !== null && <ErrorMessage error={error} />}
      <button type="submit" className="wide" disabled={busy}>
        <LogIn size={18} aria-hidden="true" />
        {busy ? t("signingIn") : t("logIn")}
      </button>
    </form>
  );
}

/** A new patient account (the server keeps the phone number encrypted and shows it masked), or a caregiver's account, which has no
 * patient record of its own and asks patients for access afterwards. */
export function RegisterForm({ onDone }) {
  const { register, demo, lang, t } = useSession();
  const [kind, setKind] = useState("patient");
  const [form, setForm] = useState({ name: "", username: "", password: "", birth_year: "", phone: "", language: lang });
  const [answers, setAnswers] = useState({});
  const fields = useRegistrationFields();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const common = {
        account_type: kind,
        name: form.name.trim(),
        username: form.username.trim().toLowerCase(),
        password: form.password,
        language: form.language,
      };
      onDone(
        await register(
          kind === "patient" ? { ...common, birth_year: Number(form.birth_year), phone: form.phone, answers } : common,
        ),
      );
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} aria-label={t("createAccount")}>
      {demo && <p className="notice warn small">{t("registerNote")}</p>}
      <fieldset className="account-kind">
        <legend>{t("accountFor")}</legend>
        <div className="segmented" role="group">
          <button type="button" aria-pressed={kind === "patient"} onClick={() => setKind("patient")}>
            {t("accountForPatient")}
          </button>
          <button type="button" aria-pressed={kind === "caregiver"} onClick={() => setKind("caregiver")}>
            {t("accountForCaregiver")}
          </button>
        </div>
        <p className="hint">{t(kind === "patient" ? "accountForPatientHint" : "accountForCaregiverHint")}</p>
      </fieldset>
      <div className="field">
        <label htmlFor="reg-name">{t("fullName")}</label>
        <input
          id="reg-name"
          required
          minLength={2}
          maxLength={80}
          autoComplete="name"
          value={form.name}
          onChange={set("name")}
        />
      </div>
      <div className="field">
        <label htmlFor="reg-username">{t("username")}</label>
        <input
          id="reg-username"
          required
          minLength={3}
          maxLength={30}
          pattern="[A-Za-z0-9][A-Za-z0-9._\-]{2,29}"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          aria-describedby="reg-username-hint"
          value={form.username}
          onChange={set("username")}
        />
        <p id="reg-username-hint" className="hint">
          {t("usernameHint")}
        </p>
      </div>
      <PasswordField
        id="reg-password"
        value={form.password}
        onChange={(password) => setForm({ ...form, password })}
        autoComplete="new-password"
        hint={t("passwordHint")}
      />
      {kind === "patient" && (
        <>
          <div className="row" style={{ alignItems: "flex-start" }}>
            <div className="field" style={{ flex: "1 1 7rem" }}>
              <label htmlFor="reg-year">{t("walkInYear")}</label>
              <input
                id="reg-year"
                required
                inputMode="numeric"
                pattern="(19|20)[0-9]{2}"
                maxLength={4}
                autoComplete="bday-year"
                value={form.birth_year}
                onChange={set("birth_year")}
              />
            </div>
            <div className="field" style={{ flex: "1 1 10rem" }}>
              <label htmlFor="reg-lang">{t("preferredLanguage")}</label>
              <select id="reg-lang" value={form.language} onChange={set("language")}>
                {LANGS.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="field">
            <label htmlFor="reg-phone">{t("mobile")}</label>
            <input
              id="reg-phone"
              required
              type="tel"
              inputMode="tel"
              pattern="(\+?91[ \-]?)?[6-9][0-9 \-]{9,12}"
              autoComplete="tel-national"
              aria-describedby="reg-phone-hint"
              value={form.phone}
              onChange={set("phone")}
            />
            <p id="reg-phone-hint" className="hint">
              {t("mobileHint")}
            </p>
          </div>
          <CustomFields fields={fields} answers={answers} onChange={setAnswers} idPrefix="reg" />
        </>
      )}
      {error !== null && <ErrorMessage error={error} />}
      <button type="submit" className="wide" disabled={busy}>
        <UserPlus size={18} aria-hidden="true" />
        {busy ? t("creatingAccount") : t("createAccount")}
      </button>
    </form>
  );
}
