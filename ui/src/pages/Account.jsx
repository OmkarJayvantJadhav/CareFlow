import { KeyRound, ShieldCheck, UserRound } from "lucide-react";
import PasswordForm from "../components/PasswordForm";
import { initials } from "../format";
import { useSession } from "../session";

const ROLE_LABEL = {
  patient: "rolePatient",
  caregiver: "roleCaregiver",
  staff: "roleStaff",
  admin: "roleAdmin",
  doctor: "roleDoctor",
};

/** Change one's own password; demo accounts have none. */
export function PasswordCard() {
  const { user, demo, t } = useSession();
  return (
    <section className="card" aria-labelledby="pw-h" style={{ marginTop: "1rem" }}>
      <div className="card-head">
        <h2 id="pw-h">
          <KeyRound size={18} aria-hidden="true" />
          {t("changePassword")}
        </h2>
      </div>
      {user.has_password ? <PasswordForm /> : <p className="muted">{t(demo ? "demoNoPassword" : "noPasswordYet")}</p>}
    </section>
  );
}

/** The account page for staff, doctors and admins: who is signed in, and their password. */
export default function Account() {
  const { user, t } = useSession();
  return (
    <main className="narrow">
      <div className="page-header">
        <div>
          <h1>{t("accountTitle")}</h1>
          <p className="lead">{t("accountIntro")}</p>
        </div>
      </div>
      <section className="card" aria-labelledby="account-h">
        <div className="row">
          <span className="avatar lg" aria-hidden="true">
            {initials(user.display_name)}
          </span>
          <div>
            <h2 id="account-h">
              <UserRound size={18} aria-hidden="true" style={{ verticalAlign: "-3px", marginRight: "0.375rem" }} />
              {user.display_name}
            </h2>
            <div className="muted small">
              @{user.username} · {t(ROLE_LABEL[user.role])}
            </div>
          </div>
        </div>
        <p className="muted small">{t("accountNameNote")}</p>
      </section>
      <PasswordCard />
    </main>
  );
}

/** Shown instead of every page while the account still has a temporary password (set by an admin). */
export function PasswordGate() {
  const { user, t } = useSession();
  return (
    <main className="narrow">
      <section className="card" aria-labelledby="gate-h">
        <div className="card-head">
          <h1 id="gate-h" className="h2">
            <ShieldCheck size={20} aria-hidden="true" />
            {t("gateTitle")}
          </h1>
        </div>
        <p className="gate-text">{t("gateText", { name: user.display_name })}</p>
        <PasswordForm idPrefix="gate" currentLabel={t("temporaryPassword")} />
      </section>
    </main>
  );
}
