import {
  BarChart3,
  ChevronRight,
  ClipboardList,
  FileCheck2,
  Info,
  Languages,
  ListOrdered,
  UserRound,
  UsersRound,
} from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { HOME } from "../App";
import { LoginForm, RegisterForm } from "../components/AuthForms";
import ErrorMessage from "../components/ErrorMessage";
import { LANGS } from "../i18n";
import { useSession } from "../session";

const ROLES = [
  { role: "patient", label: "rolePatient", hint: "rolePatientHint", icon: UserRound, tone: "" },
  { role: "caregiver", label: "roleCaregiver", hint: "roleCaregiverHint", icon: UsersRound, tone: "" },
  { role: "staff", label: "roleStaff", hint: "roleStaffHint", icon: ClipboardList, tone: "info" },
  { role: "admin", label: "roleAdmin", hint: "roleAdminHint", icon: BarChart3, tone: "info" },
];

const FEATURES = [
  { icon: Languages, title: "feature1Title", text: "feature1Text" },
  { icon: ListOrdered, title: "feature2Title", text: "feature2Text" },
  { icon: FileCheck2, title: "feature3Title", text: "feature3Text" },
];

/** S1: what CareFlow does, the language and the demo role. */
export default function Start() {
  const { user, lang, setLang, signIn, t } = useSession();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [mode, setMode] = useState("login");
  if (user) return <Navigate to={HOME[user.role]} replace />;

  async function choose(role) {
    setBusy(role);
    setError(null);
    try {
      const signedIn = await signIn(role);
      navigate(HOME[signedIn.role]);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="start">
      <section className="hero">
        <span className="eyebrow">{t("hospital")}</span>
        <h1>{t("heroTitle")}</h1>
        <p className="lead">{t("tagline")}</p>
        <ul className="features">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <li key={title}>
              <span className="icon-tile" aria-hidden="true">
                <Icon size={20} />
              </span>
              <div>
                <strong>{t(title)}</strong>
                <span className="muted">{t(text)}</span>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="card roles-card" aria-labelledby="auth-h">
        <h2 id="auth-h">{t("signInTitle")}</h2>
        <div className="segmented auth-tabs" role="group" aria-label={t("signInTitle")}>
          <button type="button" aria-pressed={mode === "login"} onClick={() => setMode("login")}>
            {t("logIn")}
          </button>
          <button type="button" aria-pressed={mode === "register"} onClick={() => setMode("register")}>
            {t("createAccount")}
          </button>
        </div>
        {mode === "login" ? (
          <LoginForm onDone={(u) => navigate(HOME[u.role])} />
        ) : (
          <RegisterForm onDone={(u) => navigate(HOME[u.role])} />
        )}
        <div className="divider">
          <span>{t("orTryDemo")}</span>
        </div>
        <h3 className="sr-only">{t("chooseRole")}</h3>
        <div className="roles">
          {ROLES.map(({ role, label, hint, icon: Icon, tone }) => (
            <button key={role} type="button" className="role" disabled={busy !== null} onClick={() => choose(role)}>
              <span className={`icon-tile ${tone}`} aria-hidden="true">
                <Icon size={20} />
              </span>
              <span className="role-text">
                <strong>{busy === role ? t("signingIn") : t(label)}</strong>
                <span>{t(hint)}</span>
              </span>
              <ChevronRight className="chev" size={18} aria-hidden="true" />
            </button>
          ))}
        </div>
        {error !== null && <ErrorMessage error={error} />}
        <div className="lang-pick">
          <h2>{t("chooseLanguage")}</h2>
          <div className="segmented" role="group" aria-label={t("chooseLanguage")}>
            {LANGS.map((l) => (
              <button
                key={l.code}
                type="button"
                aria-pressed={lang === l.code}
                onClick={() => setLang(l.code)}
                lang={l.code}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>
        <p className="demo-note">
          <Info size={16} aria-hidden="true" />
          {t("demoNote")}
        </p>
      </section>
    </main>
  );
}
