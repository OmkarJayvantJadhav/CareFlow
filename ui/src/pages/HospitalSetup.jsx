import { Building2, CalendarOff, CircleCheck, Pencil, Plus, Stethoscope, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import PolicyRules from "../components/PolicyRules";
import { longDate, weekdayName } from "../format";
import { LANGS } from "../i18n";
import { useSession } from "../session";

const DAYS = [1, 2, 3, 4, 5, 6, 7];
const SHOWN_OUTSIDE = 10;
const NO_DEPT = { name: "", floor: "0", opd_start: "09:00", opd_end: "13:00", aliases: "" };
const NO_DOCTOR = { name: "", department_id: "", languages: ["en"], opd_days: [1, 2, 3, 4, 5], slot_minutes: "15" };

function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** The hospital's name, address, reception and emergency directions. */
function ProfileForm({ profile, onSaved }) {
  const { reloadConfig, t } = useSession();
  const [form, setForm] = useState(profile);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const setIn = (key, lang) => (e) => setForm({ ...form, [key]: { ...form[key], [lang]: e.target.value } });
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const result = await api("/admin/hospital/profile", { method: "PUT", body: form });
      setForm(result);
      setSaved(true);
      onSaved(result);
      await reloadConfig();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={save} aria-labelledby="profile-h">
      <div className="card-head">
        <h2 id="profile-h">
          <Building2 size={20} aria-hidden="true" />
          {t("hospitalDetails")}
        </h2>
      </div>
      <fieldset className="plain">
        <legend>{t("hospitalNameLabel")}</legend>
        <div className="grid-3">
          {LANGS.map((l) => (
            <div className="field" key={l.code}>
              <label htmlFor={`hn-${l.code}`}>{l.label}</label>
              <input
                id={`hn-${l.code}`}
                lang={l.code}
                aria-label={`${t("hospitalNameLabel")} (${l.label})`}
                required={l.code === "en"}
                maxLength={120}
                value={form.name[l.code]}
                onChange={setIn("name", l.code)}
              />
            </div>
          ))}
        </div>
        <p className="hint">{t("hospitalNameHint")}</p>
      </fieldset>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="h-address">{t("hospitalAddress")}</label>
          <input id="h-address" maxLength={200} value={form.address} onChange={set("address")} />
        </div>
        <div className="field">
          <label htmlFor="h-phone">{t("receptionPhone")}</label>
          <input id="h-phone" type="tel" maxLength={30} value={form.phone} onChange={set("phone")} />
        </div>
        <div className="field">
          <label htmlFor="h-opens">{t("receptionOpens")}</label>
          <input id="h-opens" type="time" required value={form.reception_opens} onChange={set("reception_opens")} />
        </div>
        <div className="field">
          <label htmlFor="h-closes">{t("receptionCloses")}</label>
          <input id="h-closes" type="time" required value={form.reception_closes} onChange={set("reception_closes")} />
        </div>
      </div>
      <fieldset className="plain">
        <legend>{t("emergencyDirections")}</legend>
        <p className="hint">{t("emergencyDirectionsHint")}</p>
        {LANGS.map((l) => (
          <div className="field" key={l.code}>
            <label htmlFor={`en-${l.code}`}>{l.label}</label>
            <textarea
              id={`en-${l.code}`}
              lang={l.code}
              aria-label={`${t("emergencyDirections")} (${l.label})`}
              rows={2}
              maxLength={300}
              value={form.emergency_note[l.code]}
              onChange={setIn("emergency_note", l.code)}
            />
          </div>
        ))}
      </fieldset>
      {error !== null && <ErrorMessage error={error} />}
      {saved && (
        <p className="notice" role="status">
          <CircleCheck size={18} aria-hidden="true" />
          {t("saved")}
        </p>
      )}
      <button type="submit" disabled={busy}>
        {busy ? t("saving") : t("save")}
      </button>
    </form>
  );
}

function DepartmentFields({ form, setForm }) {
  const { t } = useSession();
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  return (
    <>
      <div className="field">
        <label htmlFor="dept-name">{t("department")}</label>
        <input id="dept-name" required maxLength={80} value={form.name} onChange={set("name")} />
      </div>
      <div className="grid-3">
        <div className="field">
          <label htmlFor="dept-floor">{t("floorLabel")}</label>
          <input id="dept-floor" type="number" min={-3} max={60} value={form.floor} onChange={set("floor")} />
        </div>
        <div className="field">
          <label htmlFor="dept-start">{t("opdOpens")}</label>
          <input id="dept-start" type="time" required value={form.opd_start} onChange={set("opd_start")} />
        </div>
        <div className="field">
          <label htmlFor="dept-end">{t("opdCloses")}</label>
          <input id="dept-end" type="time" required value={form.opd_end} onChange={set("opd_end")} />
        </div>
      </div>
      <div className="field">
        <label htmlFor="dept-words">{t("searchWords")}</label>
        <input
          id="dept-words"
          maxLength={600}
          aria-describedby="dept-words-hint"
          value={form.aliases}
          onChange={set("aliases")}
        />
        <p id="dept-words-hint" className="hint">
          {t("searchWordsHint")}
        </p>
      </div>
    </>
  );
}

function Checks({ legend, options, value, onChange }) {
  const toggle = (v) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  return (
    <fieldset className="plain">
      <legend>{legend}</legend>
      <div className="check-group">
        {options.map((o) => (
          <label key={o.value} className="check" lang={o.lang}>
            <input type="checkbox" checked={value.includes(o.value)} onChange={() => toggle(o.value)} />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function DoctorFields({ form, setForm, departments }) {
  const { lang, t } = useSession();
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  return (
    <>
      <div className="field">
        <label htmlFor="doc-name">{t("doctorName")}</label>
        <input id="doc-name" required maxLength={120} value={form.name} onChange={set("name")} />
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="doc-dept">{t("department")}</label>
          <select id="doc-dept" required value={form.department_id} onChange={set("department_id")}>
            <option value="">{t("chooseDepartment")}</option>
            {departments.map((d) => (
              <option key={d.department_id} value={d.department_id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="doc-minutes">{t("appointmentMinutes")}</label>
          <input
            id="doc-minutes"
            type="number"
            min={5}
            max={60}
            step={5}
            required
            value={form.slot_minutes}
            onChange={set("slot_minutes")}
          />
        </div>
      </div>
      <Checks
        legend={t("languagesSpoken")}
        options={LANGS.map((l) => ({ value: l.code, label: l.label, lang: l.code }))}
        value={form.languages}
        onChange={(languages) => setForm({ ...form, languages })}
      />
      <Checks
        legend={t("opdDays")}
        options={DAYS.map((d) => ({ value: d, label: weekdayName(d, lang, "long") }))}
        value={form.opd_days}
        onChange={(opd_days) => setForm({ ...form, opd_days })}
      />
    </>
  );
}

/** What a timetable change did: from when, and the bookings kept outside the new timetable. */
function Outcome({ outcome }) {
  const { lang, t } = useSession();
  if (!outcome) return null;
  return (
    <div className="notice setup-outcome" role="status">
      <CircleCheck size={18} aria-hidden="true" />
      <div>
        <p>{outcome.text}</p>
        {outcome.outside?.length > 0 && (
          <>
            <p>{t("outsideTimetable", { count: outcome.outside.length })}</p>
            <ul>
              {outcome.outside.slice(0, SHOWN_OUTSIDE).map((b) => (
                <li key={b.appointment_id}>
                  {longDate(b.date, lang)}, {b.time} — {b.patient_name} ({b.doctor_name})
                </li>
              ))}
            </ul>
            {outcome.outside.length > SHOWN_OUTSIDE && (
              <p>{t("andMoreInCalendar", { count: outcome.outside.length - SHOWN_OUTSIDE })}</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/** Admins set up the hospital: its details, departments, doctors and OPD timetables. */
export default function HospitalSetup() {
  const { lang, t } = useSession();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [dialog, setDialog] = useState(null); // {kind, dept?, doctor?}
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState(null);
  const [outcome, setOutcome] = useState(null);

  const load = useCallback(async () => {
    try {
      setData(await api("/admin/hospital"));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  function open(kind, { dept = null, doctor = null } = {}) {
    setDialogError(null);
    setOutcome(null);
    if (kind === "dept") {
      setForm(dept ? { ...dept, floor: String(dept.floor), aliases: dept.aliases.join(", ") } : NO_DEPT);
    } else if (kind === "doctor") {
      setForm(
        doctor
          ? { ...doctor, department_id: String(doctor.department_id), slot_minutes: String(doctor.slot_minutes) }
          : { ...NO_DOCTOR, department_id: dept ? String(dept.department_id) : "" },
      );
    } else if (kind === "lastDay") {
      setForm({ last_day: doctor.last_day ?? "" });
    } else {
      setForm({});
    }
    setDialog({ kind, dept, doctor });
  }

  async function run(action) {
    setBusy(true);
    setDialogError(null);
    try {
      setOutcome(await action());
      setDialog(null);
      await load();
    } catch (err) {
      setDialogError(err);
    } finally {
      setBusy(false);
    }
  }

  function timetableText(timetable, saved) {
    if (!timetable?.from) return { text: saved };
    return {
      text: `${saved} ${t("timetableFrom", { date: longDate(timetable.from, lang) })}`,
      outside: timetable.outside,
    };
  }

  function confirm() {
    const { kind, dept, doctor } = dialog;
    if (kind === "dept") {
      const body = {
        name: form.name.trim(),
        floor: Number(form.floor),
        opd_start: form.opd_start,
        opd_end: form.opd_end,
        aliases: form.aliases
          .split(",")
          .map((w) => w.trim())
          .filter(Boolean),
      };
      return run(async () => {
        const result = dept
          ? await api(`/admin/departments/${dept.department_id}`, { method: "PATCH", body })
          : await api("/admin/departments", { method: "POST", body });
        return timetableText(result.timetable, t("departmentSaved", { name: result.name }));
      });
    }
    if (kind === "doctor") {
      const body = {
        name: form.name.trim(),
        department_id: Number(form.department_id),
        languages: form.languages,
        opd_days: form.opd_days,
        slot_minutes: Number(form.slot_minutes),
      };
      return run(async () => {
        if (doctor) {
          const result = await api(`/admin/doctors/${doctor.doctor_id}`, { method: "PATCH", body });
          return timetableText(result.timetable, t("doctorSaved", { name: result.name }));
        }
        const result = await api("/admin/doctors", { method: "POST", body });
        return {
          text: `${t("doctorAdded", { name: result.name })} ${t("timetableFrom", { date: longDate(result.from, lang) })}`,
        };
      });
    }
    if (kind === "lastDay") {
      return run(async () => {
        const result = await api(`/admin/doctors/${doctor.doctor_id}/last-day`, {
          method: "PUT",
          body: { last_day: form.last_day || null },
        });
        if (!result.last_day) return { text: t("doctorStays", { name: result.name }) };
        const text = t("lastDaySaved", { name: result.name, date: longDate(result.last_day, lang) });
        return { text: result.moved.length ? `${text} ${t("visitsMoved", { count: result.moved.length })}` : text };
      });
    }
    if (kind === "removeDept") {
      return run(async () => {
        await api(`/admin/departments/${dept.department_id}`, { method: "DELETE" });
        return { text: t("removed", { name: dept.name }) };
      });
    }
    return run(async () => {
      await api(`/admin/doctors/${doctor.doctor_id}`, { method: "DELETE" });
      return { text: t("removed", { name: doctor.name }) };
    });
  }

  const ready =
    dialog?.kind === "dept"
      ? form.name.trim().length >= 2 && form.opd_start < form.opd_end
      : dialog?.kind === "doctor"
        ? form.name.trim().length >= 3 &&
          form.department_id !== "" &&
          form.languages.length > 0 &&
          form.opd_days.length > 0 &&
          Number(form.slot_minutes) >= 5 &&
          Number(form.slot_minutes) <= 60
        : true;
  const titles = {
    dept: dialog?.dept ? t("editDepartment") : t("addDepartment"),
    doctor: dialog?.doctor ? t("editDoctor") : t("addDoctor"),
    lastDay: t("lastDayTitle"),
    removeDept: t("removeDepartment"),
    removeDoctor: t("removeDoctor"),
  };
  const danger = dialog?.kind === "removeDept" || dialog?.kind === "removeDoctor";

  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("setupTitle")}</h1>
          <p className="lead">{t("setupIntro")}</p>
        </div>
      </div>
      {error !== null && <ErrorMessage error={error} onRetry={load} />}
      {data === null && error === null && <Loading />}
      {data && (
        <div className="stack">
          <ProfileForm profile={data.profile} onSaved={() => setOutcome(null)} />
          <PolicyRules />

          <section aria-labelledby="depts-h" className="stack">
            <div className="section-head">
              <h2 id="depts-h">{t("departmentsAndDoctors")}</h2>
              <div className="row">
                <button type="button" className="secondary" onClick={() => open("dept")}>
                  <Plus size={18} aria-hidden="true" />
                  {t("addDepartment")}
                </button>
                <button
                  type="button"
                  disabled={data.departments.length === 0}
                  onClick={() => open("doctor", { dept: data.departments[0] })}
                >
                  <Plus size={18} aria-hidden="true" />
                  {t("addDoctor")}
                </button>
              </div>
            </div>
            <p className="muted small">{t("timetableNote")}</p>
            <Outcome outcome={outcome} />
            {data.departments.length === 0 && <p className="muted">{t("noDepartments")}</p>}
            {data.departments.map((dept) => (
              <article className="card" key={dept.department_id} aria-labelledby={`dept-${dept.department_id}`}>
                <div className="card-head">
                  <div>
                    <h3 id={`dept-${dept.department_id}`}>{dept.name}</h3>
                    <p className="muted small">
                      {t("floorShort", { floor: dept.floor })} ·{" "}
                      {t("opdHours", { from: dept.opd_start, to: dept.opd_end })}
                      {dept.aliases.length > 0 && ` · ${dept.aliases.join(", ")}`}
                    </p>
                  </div>
                  <div className="row">
                    <button
                      type="button"
                      className="quiet"
                      aria-label={`${t("editDepartment")}: ${dept.name}`}
                      onClick={() => open("dept", { dept })}
                    >
                      <Pencil size={16} aria-hidden="true" />
                      {t("edit")}
                    </button>
                    {dept.doctors.length === 0 && (
                      <button
                        type="button"
                        className="quiet"
                        aria-label={`${t("removeDepartment")}: ${dept.name}`}
                        onClick={() => open("removeDept", { dept })}
                      >
                        <Trash2 size={16} aria-hidden="true" />
                        {t("remove")}
                      </button>
                    )}
                    <button
                      type="button"
                      className="secondary"
                      aria-label={`${t("addDoctor")}: ${dept.name}`}
                      onClick={() => open("doctor", { dept })}
                    >
                      <Plus size={16} aria-hidden="true" />
                      {t("addDoctor")}
                    </button>
                  </div>
                </div>
                {dept.doctors.length === 0 ? (
                  <p className="muted">{t("noDoctorsYet")}</p>
                ) : (
                  <ul className="setup-doctors">
                    {dept.doctors.map((d) => (
                      <li key={d.doctor_id} className={d.current ? "" : "past"}>
                        <span className="icon-tile info" aria-hidden="true">
                          <Stethoscope size={18} />
                        </span>
                        <div className="setup-doctor-text">
                          <strong>{d.name}</strong>
                          <span className="muted small">
                            {d.opd_days.map((day) => weekdayName(day, lang)).join(", ")} ·{" "}
                            {t("minutesEach", { minutes: d.slot_minutes })} ·{" "}
                            {LANGS.filter((l) => d.languages.includes(l.code))
                              .map((l) => l.label)
                              .join(", ")}
                            {d.account && ` · @${d.account}`}
                          </span>
                          {d.last_day && (
                            <span className={`badge ${d.current ? "warn" : ""}`}>
                              {d.current
                                ? t("leavesAfter", { date: longDate(d.last_day, lang) })
                                : t("leftOn", { date: longDate(d.last_day, lang) })}
                            </span>
                          )}
                        </div>
                        <span className="row setup-actions">
                          <button
                            type="button"
                            className="quiet"
                            aria-label={`${t("editDoctor")}: ${d.name}`}
                            title={t("editDoctor")}
                            onClick={() => open("doctor", { doctor: d })}
                          >
                            <Pencil size={16} aria-hidden="true" />
                          </button>
                          <button
                            type="button"
                            className="quiet"
                            aria-label={`${t("lastDayTitle")}: ${d.name}`}
                            title={t("lastDayTitle")}
                            onClick={() => open("lastDay", { doctor: d })}
                          >
                            <CalendarOff size={16} aria-hidden="true" />
                          </button>
                          <button
                            type="button"
                            className="quiet"
                            aria-label={`${t("removeDoctor")}: ${d.name}`}
                            title={t("removeDoctor")}
                            onClick={() => open("removeDoctor", { doctor: d })}
                          >
                            <Trash2 size={16} aria-hidden="true" />
                          </button>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
          </section>
        </div>
      )}

      <ConfirmDialog
        open={dialog !== null}
        title={dialog ? titles[dialog.kind] : ""}
        confirmLabel={danger ? t("remove") : t("save")}
        cancelLabel={t("cancel")}
        busy={busy}
        danger={danger}
        confirmDisabled={!ready}
        onConfirm={confirm}
        onClose={() => setDialog(null)}
      >
        {dialog?.kind === "dept" && <DepartmentFields form={form} setForm={setForm} />}
        {dialog?.kind === "doctor" && (
          <>
            {dialog.doctor && <p className="muted small">{t("timetableNote")}</p>}
            <DoctorFields form={form} setForm={setForm} departments={data.departments} />
          </>
        )}
        {dialog?.kind === "lastDay" && (
          <>
            <p>{t("lastDayText", { name: dialog.doctor.name })}</p>
            <div className="field">
              <label htmlFor="last-day">{t("lastDayLabel")}</label>
              <input
                id="last-day"
                type="date"
                min={todayIso()}
                aria-describedby="last-day-hint"
                value={form.last_day}
                onChange={(e) => setForm({ last_day: e.target.value })}
              />
              <p id="last-day-hint" className="hint">
                {t("lastDayHint")}
              </p>
            </div>
          </>
        )}
        {dialog?.kind === "removeDept" && <p>{t("removeDepartmentText", { name: dialog.dept.name })}</p>}
        {dialog?.kind === "removeDoctor" && <p>{t("removeDoctorText", { name: dialog.doctor.name })}</p>}
        {dialogError !== null && <ErrorMessage error={dialogError} />}
      </ConfirmDialog>
    </main>
  );
}
