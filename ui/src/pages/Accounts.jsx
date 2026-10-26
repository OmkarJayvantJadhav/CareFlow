import { Copy, KeyRound, Pencil, Power, Search, UserPlus, UsersRound } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { byDepartment, clockTime, longDate } from "../format";
import { useSession } from "../session";

const ROLES = ["staff", "doctor", "admin", "caregiver", "patient"];
const CREATABLE = ["staff", "doctor", "admin", "caregiver"];
const ROLE_LABEL = {
  patient: "rolePatient",
  caregiver: "roleCaregiver",
  staff: "roleStaff",
  admin: "roleAdmin",
  doctor: "roleDoctor",
};
const USERNAME = /^[a-z0-9][a-z0-9._-]{2,29}$/;
const EMPTY = { display_name: "", username: "", role: "staff", doctor_id: "" };

/** A new or reset account's temporary password: shown here once, never again. */
function TemporaryPassword({ shown, onClose }) {
  const { t } = useSession();
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(shown.password);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <ConfirmDialog
      open={shown !== null}
      title={t("tempPasswordTitle")}
      confirmLabel={t("done")}
      onConfirm={() => {
        setCopied(false);
        onClose();
      }}
      onClose={() => {
        setCopied(false);
        onClose();
      }}
    >
      {shown && (
        <>
          <p>{t("tempPasswordText", { name: shown.name, username: shown.username })}</p>
          <div className="temp-password">
            <code aria-label={t("temporaryPassword")}>{shown.password}</code>
            <button type="button" className="secondary" onClick={copy}>
              <Copy size={16} aria-hidden="true" />
              {copied ? t("copied") : t("copy")}
            </button>
          </div>
          <p className="muted small">{t("tempPasswordOnce")}</p>
        </>
      )}
    </ConfirmDialog>
  );
}

/** Name, username (new accounts only), role and, for a doctor, which doctor. */
function AccountFields({ form, setForm, isNew, self, doctors }) {
  const { t } = useSession();
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  return (
    <>
      <div className="field">
        <label htmlFor="acc-name">{t("fullName")}</label>
        <input id="acc-name" required maxLength={120} value={form.display_name} onChange={set("display_name")} />
      </div>
      {isNew && (
        <div className="field">
          <label htmlFor="acc-username">{t("username")}</label>
          <input
            id="acc-username"
            required
            maxLength={30}
            autoCapitalize="none"
            spellCheck={false}
            aria-describedby="acc-username-hint"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase() })}
          />
          <p id="acc-username-hint" className="hint">
            {t("usernameHint")}
          </p>
        </div>
      )}
      {form.role !== "patient" && (
        <div className="field">
          <label htmlFor="acc-role">{t("accountRole")}</label>
          <select id="acc-role" value={form.role} disabled={self} onChange={set("role")}>
            {CREATABLE.map((r) => (
              <option key={r} value={r}>
                {t(ROLE_LABEL[r])}
              </option>
            ))}
          </select>
          {self && <p className="hint">{t("ownRoleNote")}</p>}
        </div>
      )}
      {form.role === "doctor" && (
        <div className="field">
          <label htmlFor="acc-doctor">{t("accountDoctor")}</label>
          {doctors === null ? (
            <Loading />
          ) : (
            <select id="acc-doctor" required value={form.doctor_id} onChange={set("doctor_id")}>
              <option value="">{t("chooseDoctor")}</option>
              {byDepartment(doctors).map(([department, list]) => (
                <optgroup key={department} label={department}>
                  {list.map((d) => (
                    <option key={d.doctor_id} value={d.doctor_id}>
                      {d.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          )}
        </div>
      )}
    </>
  );
}

function lastSeen(iso, lang, t) {
  if (!iso) return t("neverSignedIn");
  return `${longDate(iso.slice(0, 10), lang)}, ${clockTime(iso)}`;
}

/** Admins add, change, switch off and reset the hospital's accounts (staff, doctors, admins, caregivers). */
export default function Accounts() {
  const { user, lang, t } = useSession();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [role, setRole] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [doctors, setDoctors] = useState(null);
  const [dialog, setDialog] = useState(null); // {kind: "create" | "edit" | "reset" | "toggle", account?}
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState(null);
  const [shown, setShown] = useState(null);
  const [notice, setNotice] = useState(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (role) params.set("role", role);
    if (query) params.set("q", query);
    try {
      setData(await api(`/admin/accounts?${params}`));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [role, query]);
  useEffect(() => {
    void load();
  }, [load]);

  const needsDoctors = dialog !== null && form.role === "doctor" && doctors === null;
  useEffect(() => {
    if (!needsDoctors) return;
    api("/doctors")
      .then((d) => setDoctors(d.doctors))
      .catch(setDialogError);
  }, [needsDoctors]);

  function open(kind, account = null) {
    setDialogError(null);
    setNotice(null);
    setForm(
      account
        ? {
            display_name: account.display_name,
            username: account.username,
            role: account.role,
            doctor_id: account.doctor_id ? String(account.doctor_id) : "",
          }
        : EMPTY,
    );
    setDialog({ kind, account });
  }

  async function run(action) {
    setBusy(true);
    setDialogError(null);
    try {
      await action();
      setDialog(null);
      await load();
    } catch (err) {
      setDialogError(err);
    } finally {
      setBusy(false);
    }
  }

  const doctorId = form.role === "doctor" && form.doctor_id ? Number(form.doctor_id) : null;
  const formReady =
    form.display_name.trim().length >= 2 &&
    (dialog?.kind !== "create" || USERNAME.test(form.username.trim())) &&
    (form.role !== "doctor" || doctorId !== null);

  function confirm() {
    const { kind, account } = dialog;
    if (kind === "create") {
      return run(async () => {
        const body = { display_name: form.display_name.trim(), username: form.username.trim(), role: form.role };
        if (doctorId !== null) body.doctor_id = doctorId;
        const made = await api("/admin/accounts", { method: "POST", body });
        setShown({
          name: made.account.display_name,
          username: made.account.username,
          password: made.temporary_password,
        });
      });
    }
    if (kind === "edit") {
      return run(async () => {
        const body = { display_name: form.display_name.trim() };
        if (form.role !== account.role) body.role = form.role;
        if (doctorId !== null && doctorId !== account.doctor_id) body.doctor_id = doctorId;
        await api(`/admin/accounts/${account.user_id}`, { method: "PATCH", body });
        setNotice(t("accountSaved", { name: body.display_name }));
      });
    }
    if (kind === "reset") {
      return run(async () => {
        const reset = await api(`/admin/accounts/${account.user_id}/reset-password`, { method: "POST" });
        setShown({ name: account.display_name, username: account.username, password: reset.temporary_password });
      });
    }
    return run(async () => {
      await api(`/admin/accounts/${account.user_id}`, { method: "PATCH", body: { active: !account.active } });
      setNotice(t(account.active ? "accountTurnedOff" : "accountTurnedOn", { name: account.display_name }));
    });
  }

  const target = dialog?.account;
  const titles = {
    create: t("newAccount"),
    edit: t("editAccount"),
    reset: t("resetPassword"),
    toggle: target?.active ? t("turnOffAccount") : t("turnOnAccount"),
  };
  const confirmLabels = {
    create: t("createAccount"),
    edit: t("save"),
    reset: t("resetPassword"),
    toggle: target?.active ? t("turnOff") : t("turnOn"),
  };

  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("accountsTitle")}</h1>
          <p className="lead">{t("accountsIntro")}</p>
        </div>
        <button type="button" onClick={() => open("create")}>
          <UserPlus size={18} aria-hidden="true" />
          {t("newAccount")}
        </button>
      </div>

      <div className="stack">
        <section className="card" aria-labelledby="accounts-h">
          <div className="card-head">
            <h2 id="accounts-h">
              <UsersRound size={20} aria-hidden="true" />
              {t("accountsList")}
            </h2>
          </div>
          <form
            className="row account-filters"
            role="search"
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(search.trim());
            }}
          >
            <div className="field">
              <label htmlFor="acc-filter-role">{t("accountRole")}</label>
              <select id="acc-filter-role" value={role} onChange={(e) => setRole(e.target.value)}>
                <option value="">{t("allRoles")}</option>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {t(ROLE_LABEL[r])}
                    {data ? ` (${data.counts[r]})` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="field grow">
              <label htmlFor="acc-search">{t("searchAccounts")}</label>
              <input
                id="acc-search"
                type="search"
                maxLength={60}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button type="submit" className="secondary">
              <Search size={16} aria-hidden="true" />
              {t("search")}
            </button>
          </form>
          {notice && (
            <p className="notice" role="status">
              {notice}
            </p>
          )}
          {error !== null && <ErrorMessage error={error} onRetry={load} />}
          {data === null && error === null && <Loading />}
          {data && data.accounts.length === 0 && <p className="muted">{t("noAccounts")}</p>}
          {data && data.accounts.length > 0 && (
            <div className="table-wrap" tabIndex={0} role="region" aria-labelledby="accounts-h">
              <table className="accounts-table">
                <caption className="sr-only">{t("accountsList")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("fullName")}</th>
                    <th scope="col">{t("accountRole")}</th>
                    <th scope="col">{t("accountStatus")}</th>
                    <th scope="col">{t("lastSignIn")}</th>
                    <th scope="col">
                      <span className="sr-only">{t("actions")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.accounts.map((a) => {
                    const self = a.user_id === user.user_id;
                    return (
                      <tr key={a.user_id}>
                        <th scope="row">
                          <span className="account-name">{a.display_name}</span>
                          <span className="muted small"> @{a.username}</span>
                          {self && <span className="badge brand">{t("you")}</span>}
                        </th>
                        <td>{t(ROLE_LABEL[a.role])}</td>
                        <td>
                          <span className="badges">
                            {a.active ? (
                              <span className="badge ok">{t("accountActive")}</span>
                            ) : (
                              <span className="badge danger">{t("accountOff")}</span>
                            )}
                            {a.must_change_password && <span className="badge warn">{t("temporaryPassword")}</span>}
                            {!a.has_password && <span className="badge">{t("noPassword")}</span>}
                          </span>
                        </td>
                        <td className="small">{lastSeen(a.last_login_at, lang, t)}</td>
                        <td>
                          <span className="row account-actions">
                            {a.role !== "patient" && (
                              <button
                                type="button"
                                className="quiet"
                                aria-label={`${t("editAccount")}: ${a.display_name}`}
                                title={t("editAccount")}
                                onClick={() => open("edit", a)}
                              >
                                <Pencil size={16} aria-hidden="true" />
                              </button>
                            )}
                            {!self && (
                              <>
                                <button
                                  type="button"
                                  className="quiet"
                                  aria-label={`${t("resetPassword")}: ${a.display_name}`}
                                  title={t("resetPassword")}
                                  onClick={() => open("reset", a)}
                                >
                                  <KeyRound size={16} aria-hidden="true" />
                                </button>
                                <button
                                  type="button"
                                  className="quiet"
                                  aria-label={`${a.active ? t("turnOff") : t("turnOn")}: ${a.display_name}`}
                                  title={a.active ? t("turnOff") : t("turnOn")}
                                  onClick={() => open("toggle", a)}
                                >
                                  <Power size={16} aria-hidden="true" />
                                </button>
                              </>
                            )}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {data?.more && <p className="muted small">{t("accountsMore")}</p>}
        </section>
      </div>

      <ConfirmDialog
        open={dialog !== null}
        title={dialog ? titles[dialog.kind] : ""}
        confirmLabel={dialog ? confirmLabels[dialog.kind] : ""}
        cancelLabel={t("cancel")}
        busy={busy}
        danger={dialog?.kind === "toggle" && target?.active}
        confirmDisabled={(dialog?.kind === "create" || dialog?.kind === "edit") && !formReady}
        onConfirm={confirm}
        onClose={() => setDialog(null)}
      >
        {dialog?.kind === "create" && (
          <>
            <p className="muted small">{t("newAccountNote")}</p>
            <AccountFields form={form} setForm={setForm} isNew doctors={doctors} />
          </>
        )}
        {dialog?.kind === "edit" && (
          <AccountFields form={form} setForm={setForm} self={target.user_id === user.user_id} doctors={doctors} />
        )}
        {dialog?.kind === "reset" && <p>{t("resetPasswordText", { name: target.display_name })}</p>}
        {dialog?.kind === "toggle" && (
          <p>{t(target.active ? "turnOffText" : "turnOnText", { name: target.display_name })}</p>
        )}
        {dialogError !== null && <ErrorMessage error={dialogError} />}
      </ConfirmDialog>
      <TemporaryPassword shown={shown} onClose={() => setShown(null)} />
    </main>
  );
}
