import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import type { Role } from "../api";
import { HOME } from "../App";
import ErrorMessage from "../components/ErrorMessage";
import { LANGS, type Key } from "../i18n";
import { useSession } from "../session";

const ROLES: { role: Role; label: Key; hint: Key }[] = [
  { role: "patient", label: "rolePatient", hint: "rolePatientHint" },
  { role: "caregiver", label: "roleCaregiver", hint: "roleCaregiverHint" },
  { role: "staff", label: "roleStaff", hint: "roleStaffHint" },
  { role: "admin", label: "roleAdmin", hint: "roleAdminHint" },
];

/** S1: language and demo role picker. */
export default function Start() {
  const { user, lang, setLang, signIn, t } = useSession();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<Role | null>(null);
  const [error, setError] = useState<unknown>(null);
  if (user) return <Navigate to={HOME[user.role]} replace />;

  async function choose(role: Role) {
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
    <main className="narrow">
      <h1>{t("hospital")}</h1>
      <p className="lead">{t("tagline")}</p>
      <h2>{t("chooseLanguage")}</h2>
      <div className="segmented" role="group" aria-label={t("chooseLanguage")}>
        {LANGS.map((l) => (
          <button key={l.code} type="button" aria-pressed={lang === l.code} onClick={() => setLang(l.code)} lang={l.code}>
            {l.label}
          </button>
        ))}
      </div>
      <h2>{t("chooseRole")}</h2>
      <div className="roles">
        {ROLES.map((r) => (
          <button key={r.role} type="button" className="role" disabled={busy !== null} onClick={() => choose(r.role)}>
            <strong>{busy === r.role ? t("signingIn") : t(r.label)}</strong>
            <span>{t(r.hint)}</span>
          </button>
        ))}
      </div>
      {error !== null && <ErrorMessage error={error} />}
    </main>
  );
}
