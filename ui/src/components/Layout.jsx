import {
  BarChart3,
  Bell,
  CalendarDays,
  CalendarPlus,
  CalendarRange,
  ClipboardList,
  ClipboardPen,
  HeartPulse,
  Info,
  LayoutDashboard,
  ListChecks,
  Network,
  Scale,
  ListOrdered,
  LogOut,
  MessageCircle,
  Stethoscope,
  UserRound,
} from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { initials } from "../format";
import { LANGS } from "../i18n";
import { useNotifications } from "../notifications";
import { useSession } from "../session";

const NAV = {
  patient: [
    { to: "/chat", label: "navChat", icon: MessageCircle },
    { to: "/book", label: "navBook", icon: CalendarPlus },
    { to: "/appointments", label: "navAppointments", icon: CalendarDays },
    { to: "/queue", label: "navQueue", icon: ListOrdered },
  ],
  staff: [
    { to: "/desk", label: "navDesk", icon: ClipboardList },
    { to: "/calendar", label: "navCalendar", icon: CalendarRange },
    { to: "/doctors", label: "navDoctors", icon: Stethoscope },
    { to: "/coordination", label: "navCoordination", icon: Network },
  ],
  doctor: [{ to: "/my-queue", label: "navMyQueue", icon: ListChecks }],
  admin: [
    { to: "/admin", label: "navDashboard", icon: LayoutDashboard },
    { to: "/analytics", label: "navAnalytics", icon: BarChart3 },
    { to: "/registration-form", label: "navRegistrationForm", icon: ClipboardPen },
    { to: "/priority-rules", label: "navPriorityRules", icon: Scale },
    { to: "/coordination", label: "navCoordination", icon: Network },
  ],
};
NAV.caregiver = NAV.patient;

const ROLE_LABEL = {
  patient: "rolePatient",
  caregiver: "roleCaregiver",
  staff: "roleStaff",
  admin: "roleAdmin",
  doctor: "roleDoctor",
};

function Brand() {
  const { t } = useSession();
  return (
    <a className="brand" href="/">
      <span className="brand-mark" aria-hidden="true">
        <HeartPulse size={20} />
      </span>
      <span className="brand-text">
        <span className="brand-name">{t("appName")}</span>
        <span className="brand-sub">{t("hospital")}</span>
      </span>
    </a>
  );
}

/** Language and large-text switches. The start page has its own language picker, so it shows only the switch. */
function Preferences({ languages = true }) {
  const { lang, setLang, largeText, setLargeText, t } = useSession();
  return (
    <>
      {languages && (
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
      )}
      <label className="toggle">
        <input type="checkbox" checked={largeText} onChange={(e) => setLargeText(e.target.checked)} />
        {t("largeText")}
      </label>
    </>
  );
}

/** Bell with the unread count, and the profile link, for patients and caregivers. */
function PatientTools() {
  const { user, t } = useSession();
  const { unread } = useNotifications();
  if (user.role !== "patient" && user.role !== "caregiver") return null;
  return (
    <>
      <NavLink
        to="/notifications"
        className="icon-link"
        aria-label={unread ? t("notificationsUnread", { count: unread }) : t("notificationsTitle")}
        title={t("notificationsTitle")}
      >
        <Bell size={20} aria-hidden="true" />
        {unread > 0 && (
          <span className="count" aria-hidden="true">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </NavLink>
      {(user.role === "patient" || user.role === "caregiver") && (
        <NavLink to="/profile" className="icon-link" aria-label={t("navProfile")} title={t("navProfile")}>
          <UserRound size={20} aria-hidden="true" />
        </NavLink>
      )}
    </>
  );
}

export default function Layout() {
  const { user, signOut, t } = useSession();
  const navigate = useNavigate();
  const banner = (
    <div className="banner" role="note">
      <Info size={15} aria-hidden="true" />
      {t("banner")}
    </div>
  );

  if (!user) {
    return (
      <>
        {banner}
        <header className="topbar start-top">
          <Brand />
          <Preferences languages={false} />
        </header>
        <Outlet />
      </>
    );
  }

  const leave = () => {
    signOut();
    navigate("/");
  };
  const signOutLabel = `${t("signOut")} (${user.display_name})`;
  return (
    <>
      {banner}
      <div className="app with-nav">
        <aside className="sidebar">
          <Brand />
          <nav className="main-nav" aria-label="Main">
            {NAV[user.role].map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
                <Icon size={20} aria-hidden="true" />
                <span>{t(label)}</span>
              </NavLink>
            ))}
          </nav>
          <div className="user-card">
            <span className="avatar" aria-hidden="true">
              {initials(user.display_name)}
            </span>
            <div className="who">
              <strong>{user.display_name}</strong>
              <span className="muted small">{t(ROLE_LABEL[user.role])}</span>
            </div>
            <button type="button" className="ghost" aria-label={signOutLabel} title={t("signOut")} onClick={leave}>
              <LogOut size={18} aria-hidden="true" />
            </button>
          </div>
        </aside>
        <div className="main-col">
          <header className="topbar">
            <span className="mobile-only">
              <Brand />
            </span>
            <Preferences />
            <span className="tools">
              <PatientTools />
            </span>
            <button
              type="button"
              className="quiet mobile-only"
              aria-label={signOutLabel}
              title={t("signOut")}
              onClick={leave}
            >
              <LogOut size={18} aria-hidden="true" />
            </button>
          </header>
          <Outlet />
        </div>
      </div>
    </>
  );
}
