import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { LANGS, type Key } from "../i18n";
import { useSession } from "../session";

const NAV: Record<string, { to: string; label: Key }[]> = {
  patient: [
    { to: "/chat", label: "navChat" },
    { to: "/appointments", label: "navAppointments" },
    { to: "/queue", label: "navQueue" },
  ],
  staff: [
    { to: "/desk", label: "navDesk" },
    { to: "/doctors", label: "navDoctors" },
  ],
  admin: [
    { to: "/admin", label: "navDashboard" },
    { to: "/analytics", label: "navAnalytics" },
  ],
};
NAV.caregiver = NAV.patient;

export default function Layout() {
  const { user, lang, setLang, largeText, setLargeText, signOut, t } = useSession();
  const navigate = useNavigate();
  return (
    <>
      <div className="banner" role="note">
        {t("banner")}
      </div>
      <header className="topbar">
        <a className="brand" href="/">
          <span className="brand-mark" aria-hidden="true">
            +
          </span>
          {t("appName")}
          <span className="sr-only"> — {t("hospital")}</span>
        </a>
        <div className="topbar-tools">
          <div className="segmented" role="group" aria-label={t("chooseLanguage")}>
            {LANGS.map((l) => (
              <button key={l.code} type="button" aria-pressed={lang === l.code} onClick={() => setLang(l.code)} lang={l.code}>
                {l.label}
              </button>
            ))}
          </div>
          <label className="toggle">
            <input type="checkbox" checked={largeText} onChange={(e) => setLargeText(e.target.checked)} />
            {t("largeText")}
          </label>
          {user && (
            <button
              type="button"
              className="quiet"
              onClick={() => {
                signOut();
                navigate("/");
              }}
            >
              {t("signOut")} ({user.display_name})
            </button>
          )}
        </div>
      </header>
      {user && (
        <nav className="tabs" aria-label="Main">
          {NAV[user.role].map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? "active" : "")}>
              {t(item.label)}
            </NavLink>
          ))}
        </nav>
      )}
      <Outlet />
    </>
  );
}
