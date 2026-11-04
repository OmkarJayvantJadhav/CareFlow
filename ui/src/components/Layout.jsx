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
  Siren,
  ListOrdered,
  LogOut,
  Menu,
  UserCog,
  X,
  MessageCircle,
  Stethoscope,
  UserRound,
} from "lucide-react";
import { useEffect, useRef } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { initials } from "../format";
import { LANGS } from "../i18n";
import { useNotifications } from "../notifications";
import { PasswordGate } from "../pages/Account";
import { useSession } from "../session";

// The first few items of each list are the phone's bottom tabs (four, or two in large text so the names
// still fit); the rest are under "More". On a wider screen the sidebar lists them all, in this order.
const TABS = 4;
const TABS_LARGE_TEXT = 2;
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
    { to: "/patients", label: "navPatients", icon: Contact },
    { to: "/coordination", label: "navCoordination", icon: Network },
  ],
  doctor: [{ to: "/my-queue", label: "navMyQueue", icon: ListChecks }],
  admin: [
    { to: "/admin", label: "navDashboard", icon: LayoutDashboard },
    { to: "/hospital-setup", label: "navSetup", icon: Building2 },
    { to: "/accounts", label: "navAccounts", icon: UserCog },
    { to: "/documents", label: "navDocuments", icon: FileText },
    { to: "/patients", label: "navPatients", icon: Contact },
    { to: "/analytics", label: "navAnalytics", icon: BarChart3 },
    { to: "/messaging", label: "navMessaging", icon: Send },
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
function Preferences({ languages = true, largeTextSwitch = true }) {
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
      {largeTextSwitch && <LargeTextSwitch largeText={largeText} setLargeText={setLargeText} t={t} />}
    </>
  );
}

function LargeTextSwitch({ largeText, setLargeText, t }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={largeText} onChange={(e) => setLargeText(e.target.checked)} />
      {t("largeText")}
    </label>
  );
}

/** One drop-down for the language on a phone, where three buttons crowd the header. */
function LanguageMenu() {
  const { lang, setLang, t } = useSession();
  return (
    <select
      className="language-menu"
      aria-label={t("chooseLanguage")}
      value={lang}
      onChange={(e) => setLang(e.target.value)}
    >
      {LANGS.map((l) => (
        <option key={l.code} value={l.code} lang={l.code}>
          {l.label}
        </option>
      ))}
    </select>
  );
}

/** The information library (their navigation does not list it) and the account page, for staff, doctors and admins. */
function StaffTools() {
  const { user, t } = useSession();
  if (user.role === "patient" || user.role === "caregiver") return null;
  return (
    <>
      <NavLink to="/library" className="tool-link desktop-only">
        <BookOpen size={18} aria-hidden="true" />
        {t("navLibrary")}
      </NavLink>
      <NavLink to="/account" className="tool-link desktop-only">
        <UserRound size={18} aria-hidden="true" />
        {t("navAccount")}
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
      <NavLink to="/profile" className="tool-link desktop-only">
        <UserRound size={18} aria-hidden="true" />
        {t("navProfile")}
      </NavLink>
    </>
  );
}

/** The phone's "More" sheet: every page that is not a bottom tab, with its full name, then the account,
 * the large-text switch and signing out. */
function MoreMenu({ dialog, items, onSignOut }) {
  const { user, largeText, setLargeText, t } = useSession();
  const staff = user.role !== "patient" && user.role !== "caregiver";
  const extras = staff
    ? [
        { to: "/library", label: "navLibrary", icon: BookOpen },
        { to: "/account", label: "navAccount", icon: UserRound },
      ]
    : [{ to: "/profile", label: "navProfile", icon: UserRound }];
  const close = () => dialog.current?.close();
  return (
    <dialog
      ref={dialog}
      className="more-sheet"
      aria-labelledby="more-title"
      onClick={(e) => e.target === dialog.current && close()}
    >
      <div className="more-head">
        <span className="avatar" aria-hidden="true">
          {initials(user.display_name)}
        </span>
        <div className="who">
          <strong id="more-title">{user.display_name}</strong>
          <span className="muted small">{t(ROLE_LABEL[user.role])}</span>
        </div>
        <button type="button" className="ghost" onClick={close}>
          <X size={18} aria-hidden="true" />
          {t("close")}
        </button>
      </div>
      <nav className="more-list" aria-label={t("moreMenu")}>
        {[...items, ...extras].map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} onClick={close} className={({ isActive }) => (isActive ? "active" : "")}>
            <Icon size={20} aria-hidden="true" />
            <span>{t(label)}</span>
          </NavLink>
        ))}
      </nav>
      <div className="more-foot">
        <LargeTextSwitch largeText={largeText} setLargeText={setLargeText} t={t} />
        <button type="button" className="quiet" onClick={onSignOut}>
          <LogOut size={18} aria-hidden="true" />
          {t("signOut")}
        </button>
      </div>
    </dialog>
  );
}

export default function Layout() {
  const { user, demo, notice, signOut, largeText, t } = useSession();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const more = useRef(null);
  useEffect(() => more.current?.close(), [pathname]);
  // The demo deployment says so on every page (unless DEMO_NOTICE is off); a hospital's own deployment does not.
  const banner = notice && (
    <div className="banner" role="note">
      <Info size={15} aria-hidden="true" />
      {t("banner")}
    </div>
  );

  if (!user) {
    const showLanguages = !(pathname === "/login" || (pathname === "/" && demo));
    return (
      <>
        {banner}
        <header className="topbar start-top">
          <Brand />
          <span className="row" style={{ gap: "0.75rem" }}>
            {/* A hospital's own site keeps its header short: the homepage links to the information itself. */}
            {demo && (
              <NavLink to="/library" className="start-link">
                <BookOpen size={18} aria-hidden="true" />
                {t("navLibrary")}
              </NavLink>
            )}
            {/* The start page has its own language picker; the other pages need one here (a drop-down on phones). */}
            {showLanguages && (
              <span className="desktop-only">
                <Preferences largeTextSwitch={false} />
              </span>
            )}
            {showLanguages && (
              <span className="mobile-only">
                <LanguageMenu />
              </span>
            )}
            {demo && <Preferences languages={false} />}
            {!demo && (
              <span className="top-actions">
                <a href="tel:112" className="button danger">
                  <Siren size={16} aria-hidden="true" />
                  {t("homeCall112")}
                </a>
                {pathname !== "/login" && (
                  <NavLink to="/login" className="button">
                    {t("logIn")}
                  </NavLink>
                )}
              </span>
            )}
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
  const tabs = largeText ? TABS_LARGE_TEXT : TABS;
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
          <p className="nav-label" aria-hidden="true">
            {t("menu")}
          </p>
          <nav className="main-nav" aria-label={t("mainMenu")}>
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
        <nav className="tab-bar" aria-label={t("mainMenu")}>
          {NAV[user.role].slice(0, tabs).map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
              <Icon size={22} aria-hidden="true" />
              <span>{t(label)}</span>
            </NavLink>
          ))}
          <button type="button" aria-haspopup="dialog" onClick={() => more.current?.showModal()}>
            <Menu size={22} aria-hidden="true" />
            <span>{t("more")}</span>
          </button>
        </nav>
        <MoreMenu dialog={more} items={NAV[user.role].slice(tabs)} onSignOut={leave} />
        <div className="main-col">
          <header className="topbar">
            <span className="mobile-only">
              <Brand />
            </span>
            <span className="desktop-only prefs">
              <Preferences />
            </span>
            <span className="tools">
              <StaffTools />
              <PatientTools />
            </span>
            <span className="mobile-only">
              <LanguageMenu />
            </span>
          </header>
          <Outlet />
        </div>
      </div>
    </>
  );
}
