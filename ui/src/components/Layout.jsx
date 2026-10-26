import {
  BarChart3,
  Bell,
  BookOpen,
  Building2,
  CalendarDays,
  CalendarPlus,
  CalendarRange,
  ClipboardList,
  ClipboardPen,
  FileText,
  Contact,
  HeartPulse,
  Info,
  LayoutDashboard,
  ListChecks,
  Network,
  Scale,
  Send,
  ListOrdered,
  LogOut,
  UserCog,
  MessageCircle,
  Stethoscope,
  UserRound,
} from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { initials } from "../format";
import { LANGS } from "../i18n";
import { useNotifications } from "../notifications";
import { PasswordGate } from "../pages/Account";
import { useSession } from "../session";

const NAV = {
  patient: [
    { to: "/chat", label: "navChat", icon: MessageCircle },
    { to: "/book", label: "navBook", icon: CalendarPlus },
    { to: "/appointments", label: "navAppointments", icon: CalendarDays },
    { to: "/queue", label: "navQueue", icon: ListOrdered },
    { to: "/library", label: "navLibrary", icon: BookOpen },
  ],
  staff: [
    { to: "/desk", label: "navDesk", icon: ClipboardList },
    { to: "/calendar", label: "navCalendar", icon: CalendarRange },
    { to: "/doctors", label: "navDoctors", icon: Stethoscope },
    { to: "/coordination", label: "navCoordination", icon: Network },
    { to: "/patients", label: "navPatients", icon: Contact },
  ],
  doctor: [{ to: "/my-queue", label: "navMyQueue", icon: ListChecks }],
  admin: [
    { to: "/admin", label: "navDashboard", icon: LayoutDashboard },
    { to: "/analytics", label: "navAnalytics", icon: BarChart3 },
    { to: "/hospital-setup", label: "navSetup", icon: Building2 },
    { to: "/patients", label: "navPatients", icon: Contact },
    { to: "/documents", label: "navDocuments", icon: FileText },
    { to: "/messaging", label: "navMessaging", icon: Send },
    { to: "/accounts", label: "navAccounts", icon: UserCog },
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
  const { hospitalName, t } = useSession();
  return (
    <a className="brand" href="/">
      <span className="brand-mark" aria-hidden="true">
        <HeartPulse size={20} />
      </span>
      <span className="brand-text">
        <span className="brand-name">{t("appName")}</span>
        {hospitalName && <span className="brand-sub">{hospitalName}</span>}
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

/** The information library (their navigation does not list it) and the account page, for staff, doctors and admins. */
function StaffTools() {
  const { user, t } = useSession();
  if (user.role === "patient" || user.role === "caregiver") return null;
  return (
    <>
      <NavLink to="/library" className="icon-link" aria-label={t("navLibrary")} title={t("navLibrary")}>
        <BookOpen size={20} aria-hidden="true" />
      </NavLink>
      <NavLink to="/account" className="icon-link" aria-label={t("navAccount")} title={t("navAccount")}>
        <UserRound size={20} aria-hidden="true" />
      </NavLink>
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
  const { user, demo, signOut, t } = useSession();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  // The demo deployment says so on every page; a hospital's own deployment does not.
  const banner = demo && (
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
          <span className="row" style={{ gap: "0.75rem" }}>
            <NavLink to="/library" className="start-link">
              <BookOpen size={18} aria-hidden="true" />
              {t("navLibrary")}
            </NavLink>
            {/* The start page has its own language picker; the library pages need one here. */}
            <Preferences languages={pathname !== "/"} />
          </span>
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
  if (user.must_change_password) {
    return (
      <>
        {banner}
        <header className="topbar start-top">
          <Brand />
          <span className="row" style={{ gap: "0.75rem" }}>
            <Preferences />
            <button type="button" className="quiet" onClick={leave}>
              <LogOut size={18} aria-hidden="true" />
              {t("signOut")}
            </button>
          </span>
        </header>
        <PasswordGate />
      </>
    );
  }
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
              <StaffTools />
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
